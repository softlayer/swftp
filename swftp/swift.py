"""
swift includes a basic swift client for twisted.

    client = SwiftConnection(auth_url, username, api_key, pool=pool)
    d = client.put_object('container', 'path/to/obj')

See COPYING for license information.
"""
from twisted.internet import reactor
from twisted.internet.defer import Deferred, succeed
from twisted.web.client import Agent, WebClientContextFactory
from twisted.internet.protocol import Protocol
from twisted.web.http_headers import Headers
from twisted.web import error
from twisted.web._newclient import ResponseDone
from twisted.web.http import PotentialDataLoss
from twisted.python import log

import json
from urllib import quote as _quote


class RequestError(error.Error):
    pass


class NotFound(RequestError):
    pass


class UnAuthenticated(RequestError):
    pass


class UnAuthorized(RequestError):
    pass


class Conflict(RequestError):
    pass


class ResponseReceiver(Protocol):
    """
    Assembles HTTP response from return stream.
    """

    def __init__(self, finished):
        self.recv_chunks = []
        self.finished = finished

    def dataReceived(self, bytes, final=False):
        self.recv_chunks.append(bytes)

    def connectionLost(self, reason):
        if reason.check(ResponseDone) or reason.check(PotentialDataLoss):
            self.finished.callback(''.join(self.recv_chunks))
        else:
            self.finished.errback(reason)


class ResponseIgnorer(Protocol):
    def __init__(self, finished):
        self.finished = finished

    def makeConnection(self, transport):
        transport.stopProducing()
        self.finished.callback(None)

    def dataReceived(self, bytes):
        pass

    def connectionLost(self, reason):
        pass


def cb_recv_resp(response, load_body=False, receiver=None):
    d_resp_recvd = Deferred()
    if response.code == 204:
        response.deliverBody(ResponseIgnorer(d_resp_recvd))
    elif load_body:
        response.deliverBody(ResponseReceiver(d_resp_recvd))
    else:
        if receiver:
            response.deliverBody(receiver)
            return response
        else:
            response.deliverBody(ResponseIgnorer(d_resp_recvd))
    d_resp_recvd.addCallback(cb_process_resp, response)
    return d_resp_recvd


def cb_process_resp(body, response):
    if response.code == 404:
        raise NotFound(response.code, body)
    if response.code == 401:
        raise UnAuthenticated(response.code, body)
    if response.code == 403:
        raise UnAuthorized(response.code, body)
    if response.code == 409:
        raise Conflict(response.code, body)
    elif response.code > 299 and response.code < 400:
        raise error.PageRedirect(response.code, body)
    elif response.code > 399:
        raise RequestError(response.code, body)
    headers = {}
    for k, v in response.headers.getAllRawHeaders():
        headers[k.lower()] = v.pop()
    response.headers = headers
    return response, body


def format_head_response(result):
    resp, body = result
    return resp.headers


def cb_json_decode(result):
    resp, body = result
    return resp, json.loads(body)


class SwiftConnection:
    """ A basic connection class to interface with OpenStack Swift.

        :param auth_url: auth endpoint for swift
        :param username: username for swift
        :param api_key: password/api_key for swift
        :param pool: A twisted.web.client.HTTPConnectionPool object
        :param dict extra_headers: extra HTTP headers to send with each request
        :param bool verbose: verbose setting
    """
    user_agent = 'Twisted Swift'

    def __init__(self, auth_url, username, api_key, pool=None,
                 extra_headers=None, verbose=False):
        self.auth_url = auth_url
        self.username = username
        self.api_key = api_key
        self.storage_url = None
        self.auth_token = None
        contextFactory = WebClientContextFactory()
        contextFactory.noisy = False
        self.pool = pool
        self.agent = Agent(reactor, contextFactory, pool=self.pool)
        self.extra_headers = extra_headers
        self.verbose = verbose

    def _form_url(self, path, params):
        url = "/".join((self.storage_url, path))
        if params:
            param_lst = []
            for k, v in params.iteritems():
                param_lst.append("%s=%s" % (k, v))
            url = "%s?%s" % (url, "&".join(param_lst))
        return url

    def make_request(self, method, path, params=None, headers=None, body=None):
        """ Make an HTTP request against Swift. This method will try once to
        re-authenticate to swift after receiving a 401 or 403 and then
        (if successful) will re-attempt the request.

        :param method: HTTP Method. E.G. GET, POST, PUT
        :param path: Path to be appended to the storage url
        :param dict params: Parameters to be used at the query parameter
        :param dict headers: Additional headers for the request
        :param body: Object which implements twisted.web.iweb.IBodyProducer

        :returns t.w.c.Response:

        """
        h = {
            'User-Agent': [self.user_agent],
        }
        if headers:
            for k, v in headers.iteritems():
                h[k] = [v]

        if self.extra_headers:
            for k, v in self.extra_headers.iteritems():
                h[k] = [v]

        def doRequest(ignored):
            h['X-Auth-Token'] = [self.auth_token]
            url = self._form_url(path, params)
            if self.verbose:
                log.msg('Request: %s %s, headers: %s' % (method, url, h))
            return self.agent.request(method, url, Headers(h), body)

        d = doRequest(None)

        def retryAuth(response):
            if response.code in [401, 403]:
                d_resp_recvd = Deferred()
                response.deliverBody(ResponseIgnorer(d_resp_recvd))
                d_resp_recvd.addCallback(self.cb_retry_auth)
                d_resp_recvd.addCallback(doRequest)
                return d_resp_recvd
            return response
        d.addCallback(retryAuth)

        return d

    def cb_retry_auth(self, ignored):
        return self.authenticate()

    def after_authenticate(self, result):
        response, body = result
        self.storage_url = response.headers['x-storage-url']
        self.auth_token = response.headers['x-auth-token']
        return result

    def authenticate(self):
        """ Authenticate against Swift (using v1 auth)

        :returns t.w.c.Response:

        """
        h = {
            'User-Agent': [self.user_agent],
            'X-Auth-User': [self.username],
            'X-Auth-Key': [self.api_key],
        }

        if self.extra_headers:
            for k, v in self.extra_headers.iteritems():
                h[k] = [v]

        d = self.agent.request('GET', self.auth_url, Headers(h))
        d.addCallback(cb_recv_resp, load_body=True)
        d.addCallback(self.after_authenticate)
        return d

    def head_account(self):
        " Get details of the account "
        d = self.make_request('HEAD', '')
        d.addCallback(cb_recv_resp)
        d.addCallback(format_head_response)
        return d

    def get_account(self, limit=None, marker=None, end_marker=None):
        """ Get listing of containers in the account

        :param int limit: The max number of results to return
        :param marker: container names greater than this value
        :param end_marker: container names less than this value

        :returns t.w.c.Response, list:

        """
        params = {'format': 'json'}
        if limit:
            params['limit'] = str(limit)
        if marker:
            params['marker'] = quote(marker)
        if marker:
            params['end_marker'] = quote(end_marker)

        d = self.make_request('GET', '', params=params)
        d.addCallback(cb_recv_resp, load_body=True)
        d.addCallback(cb_json_decode)
        return d

    def head_container(self, container):
        """ Get details on a container

        :param container: The container name

        :returns dict:

        """
        d = self.make_request('HEAD', quote(container))
        d.addCallback(cb_recv_resp)
        d.addCallback(format_head_response)
        return d

    def get_container(self, container, limit=None, marker=None,
                      end_marker=None, prefix=None, path=None, delimiter=None):
        """ Create a container

        :param container: The container name
        :param int limit: The max number of results to return
        :param marker: object names greater than this value
        :param end_marker: object names less than this value
        :param prefix: return objects with names that start with this value
        :param delimiter: Delimiter to use for hierarchy

        :returns t.w.c.Response, list:

        """
        params = {'format': 'json'}
        if limit:
            params['limit'] = str(limit)
        if marker:
            params['marker'] = quote(marker)
        if marker:
            params['end_marker'] = quote(end_marker)
        if prefix:
            params['prefix'] = quote(prefix)
        if path:
            params['path'] = quote(path)
        if delimiter:
            params['delimiter'] = quote(delimiter)

        d = self.make_request('GET', quote(container), params=params)
        d.addCallback(cb_recv_resp, load_body=True)
        d.addCallback(cb_json_decode)
        return d

    def put_container(self, container, headers=None):
        """ Create a container

        :param container: The container name
        :param header: Optional headers to add to the request

        :returns t.w.c.Response:

        """
        d = self.make_request('PUT', quote(container), headers=headers)
        d.addCallback(cb_recv_resp)
        return d

    def delete_container(self, container):
        """ Delete a container

        :param container: The container name

        :returns t.w.c.Response:

        """
        d = self.make_request('DELETE', quote(container))
        d.addCallback(cb_recv_resp)
        return d

    def head_object(self, container, path):
        """ Get details about an object

        :param container: The container name
        :param path: The object name/path

        :returns dict:

        """
        _path = "/".join((quote(container), quote(path)))
        d = self.make_request('HEAD', _path)
        d.addCallback(cb_recv_resp)
        d.addCallback(format_head_response)
        return d

    def get_object(self, container, path, headers=None, receiver=None):
        """ Download an object

        :param container: The container name
        :param path: The object name/path
        :param dict headers: Extra headers to use with the HTTP request
        :param receiver: A twisted.internet.protocol.Protocol that will receive
                         the contents of the object

        :returns t.w.c.Response:

        """
        _path = "/".join((quote(container), quote(path)))
        d = self.make_request('GET', _path, headers=headers)
        d.addCallback(cb_recv_resp, receiver=receiver)
        return d

    def put_object(self, container, path, headers=None, body=None):
        """ Create a new object

        :param container: The container name
        :param path: The object name/path
        :param dict headers: Extra headers to use with the HTTP request
        :param body: Object which implements twisted.web.iweb.IBodyProducer

        :returns t.w.c.Response:

        """
        if not headers:
            headers = {}
        if not body:
            headers['Content-Length'] = '0'
        _path = "/".join((quote(container), quote(path)))
        d = self.make_request('PUT', _path, headers=headers, body=body)
        d.addCallback(cb_recv_resp, load_body=True)
        return d

    def delete_object(self, container, path):
        """ Delete an object

        :param container: The container name
        :param path: The object name/path

        :returns t.w.c.Response:

        """
        _path = "/".join((quote(container), quote(path)))
        d = self.make_request('DELETE', _path)
        d.addCallback(cb_recv_resp)
        return d


class ThrottledSwiftConnection(SwiftConnection):
    """ A SwiftConnection that has a list of locks that it needs to acquire
        before making requests. Locks can either be a DeferredSemaphore, a
        DeferredLock, or anything else that implements
        twisted.internet.defer._ConcurrencyPrimitive. Locks are acquired in the
        order in the list.

        :param locks: list of locks that implement
            twisted.internet.defer._ConcurrencyPrimitive
        :param \*args: same arguments as `SwiftConnection`
        :param \*\*args: same keyword arguments as `SwiftConnection`
    """
    def __init__(self, locks, *args, **kwargs):
        SwiftConnection.__init__(self, *args, **kwargs)
        self.locks = locks or []

    def _release_all(self, result):
        for i, lock in enumerate(self.locks):
            lock.release()
        return result

    def _aquire_all(self):
        d = succeed(None)
        for i, lock in enumerate(self.locks):
            d.addCallback(lambda r: lock.acquire())
        return d

    def make_request(self, *args, **kwargs):
        def execute(ignored):
            d = SwiftConnection.make_request(self, *args, **kwargs)
            d.addBoth(self._release_all)
            return d

        d = self._aquire_all()
        d.addCallback(execute)
        return d


def quote(value, safe='/'):
    """
    Patched version of urllib.quote that encodes utf8 strings before quoting
    """
    value = encode_utf8(value)
    if isinstance(value, str):
        return _quote(value, safe)
    else:
        return value


def encode_utf8(value):
    if isinstance(value, unicode):
        value = value.encode('utf8')
    return value
