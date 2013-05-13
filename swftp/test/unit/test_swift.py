"""
See COPYING for license information.
"""
from mock import MagicMock

from twisted.python.failure import Failure
from twisted.trial import unittest
from twisted.internet import defer, protocol
from twisted.web.http_headers import Headers
from twisted.web._newclient import ResponseDone
from twisted.web import error

from swftp.swift import (
    SwiftConnection, ThrottledSwiftConnection, ResponseReceiver,
    ResponseIgnorer, cb_recv_resp, cb_process_resp, NotFound, UnAuthenticated,
    UnAuthorized, Conflict, RequestError)


class StubWebAgent(protocol.Protocol):
    def __init__(self):
        self.requests = []

    def request(self, *args, **kwargs):
        result = defer.Deferred()
        self.requests.append((result, args, kwargs))
        return result


class StubResponse(object):
    def __init__(self, code, headers=None, body=None):
        self.version = ('HTTP', 1, 1)
        self.code = code
        self.headers = headers or Headers()
        self.body = body or ''
        self.length = len(self.body)
        self.producing = True

    def deliverBody(self, receiver):
        receiver.makeConnection(self)
        if self.producing and self.body:
            receiver.dataReceived(self.body)
        receiver.connectionLost(Failure(ResponseDone()))

    def stopProducing(self):
        self.producing = False


class SwiftConnectionTest(unittest.TestCase):
    def setUp(self):
        self.conn = SwiftConnection(
            'http://127.0.0.1:8080/auth/v1.0', 'username', 'api_key',
            extra_headers={'extra': 'header'},
            verbose=True)
        self.agent = StubWebAgent()
        self.conn.agent = self.agent
        self.conn.storage_url = 'http://127.0.0.1:8080/v1/AUTH_user'
        self.conn.auth_token = 'TOKEN_123'

    def test_init(self):
        conn = SwiftConnection(
            'http://127.0.0.1:8080/auth/v1.0', 'username', 'api_key')
        self.assertEqual(conn.auth_url, 'http://127.0.0.1:8080/auth/v1.0')
        self.assertEqual(conn.username, 'username')
        self.assertEqual(conn.api_key, 'api_key')
        self.assertEqual(conn.auth_token, None)
        self.assertEqual(conn.verbose, False)
        self.assertIsNotNone(conn.agent)

        pool = MagicMock()
        conn = SwiftConnection(
            'http://127.0.0.1:8080/auth/v1.0', 'username', 'api_key',
            pool=pool,
            verbose=True)
        self.assertEqual(conn.auth_url, 'http://127.0.0.1:8080/auth/v1.0')
        self.assertEqual(conn.username, 'username')
        self.assertEqual(conn.api_key, 'api_key')
        self.assertEqual(conn.auth_token, None)
        self.assertEqual(conn.verbose, True)
        self.assertIsNotNone(conn.agent)
        self.assertEqual(conn.pool, pool)

    def test_make_request(self):
        make_request = self.conn.make_request('method', 'path/to/resource',
                                              params={'param': 'value'},
                                              headers={'header': 'value'},
                                              body='body')
        self.assertEqual(len(self.agent.requests), 1)
        d, args, kwargs = self.agent.requests[0]
        self.assertEqual(args, (
            'method',
            'http://127.0.0.1:8080/v1/AUTH_user/path/to/resource?param=value',
            Headers({
                'header': ['value'],
                'user-agent': ['Twisted Swift'],
                'x-auth-token': ['TOKEN_123'],
                'extra': ['header']}),
            'body'))

        response = StubResponse(200, body='some body')
        d.callback(response)

        def cbCheckResponse(resp):
            self.assertEqual(resp, response)
            return resp
        make_request.addCallback(cbCheckResponse)
        make_request.addCallback(cb_recv_resp, load_body=True)

        def cbCheckResponseWithBody(resp):
            self.assertEqual(resp, (response, 'some body'))
            return resp
        make_request.addCallback(cbCheckResponseWithBody)
        return make_request

    def test_make_request_failed_auth(self):
        # Make initial request
        make_request = self.conn.make_request('method', 'path/to/resource',
                                              params={'param': 'value'},
                                              headers={'header': 'value'},
                                              body='body')

        self.assertEqual(len(self.agent.requests), 1)
        d, args, kwargs = self.agent.requests[0]
        self.assertEqual(args, (
            'method',
            'http://127.0.0.1:8080/v1/AUTH_user/path/to/resource?param=value',
            Headers({
                'header': ['value'],
                'user-agent': ['Twisted Swift'],
                'x-auth-token': ['TOKEN_123'],
                'extra': ['header']}),
            'body'))

        # Return a 401
        response = StubResponse(401)
        d.callback(response)

        # Check to make sure an auth request is being sent now
        self.assertEqual(len(self.agent.requests), 2)
        d, args, kwargs = self.agent.requests[1]
        self.assertEqual(args, (
            'GET',
            'http://127.0.0.1:8080/auth/v1.0',
            Headers({
                'user-agent': ['Twisted Swift'],
                'x-auth-user': ['username'],
                'x-auth-key': ['api_key'],
                'extra': ['header']})))

        # Return a 200 for the auth request
        response = StubResponse(200, headers=Headers({
            'x-storage-url': ['AUTHED_STORAGE_URL'],
            'x-auth-token': ['AUTHED_TOKEN'],
        }))
        d.callback(response)

        # Make sure authentication has been performed successfully
        self.assertEqual(self.conn.storage_url, 'AUTHED_STORAGE_URL')
        self.assertEqual(self.conn.auth_token, 'AUTHED_TOKEN')

        # Check to make sure there's a second attempt at the original request
        self.assertEqual(len(self.agent.requests), 3)
        d, args, kwargs = self.agent.requests[2]
        self.assertEqual(args, (
            'method',
            'AUTHED_STORAGE_URL/path/to/resource?param=value',
            Headers({
                'header': ['value'],
                'user-agent': ['Twisted Swift'],
                'x-auth-token': ['AUTHED_TOKEN'],
                'extra': ['header']}),
            'body'))

        # Return a 200 for the second attempt
        response = StubResponse(200)
        d.callback(response)

        def cbCheckResponse(resp):
            self.assertEqual(resp, response)
        make_request.addCallback(cbCheckResponse)
        return make_request

    def test_authenticate(self):
        auth_d = self.conn.authenticate()
        self.assertEqual(len(self.agent.requests), 1)
        d, args, kwargs = self.agent.requests[0]
        self.assertEqual(args, (
            'GET',
            'http://127.0.0.1:8080/auth/v1.0',
            Headers({
                'user-agent': ['Twisted Swift'],
                'x-auth-user': ['username'],
                'x-auth-key': ['api_key'],
                'extra': ['header']})))

        response = StubResponse(200, headers=Headers({
            'x-storage-url': ['AUTHED_STORAGE_URL'],
            'x-auth-token': ['AUTHED_TOKEN'],
        }))
        d.callback(response)

        def cbCheckResponse(resp):
            self.assertEqual(self.conn.storage_url, 'AUTHED_STORAGE_URL')
            self.assertEqual(self.conn.auth_token, 'AUTHED_TOKEN')
            self.assertEqual(resp, (response, ''))
        auth_d.addCallback(cbCheckResponse)
        return auth_d

    def test_head_account(self):
        make_request = self.conn.head_account()
        self.assertEqual(len(self.agent.requests), 1)
        d, args, kwargs = self.agent.requests[0]
        self.assertEqual(args, (
            'HEAD', 'http://127.0.0.1:8080/v1/AUTH_user/',
            Headers({
                'user-agent': ['Twisted Swift'],
                'x-auth-token': ['TOKEN_123'],
                'extra': ['header']}),
            None))

        response = StubResponse(204, headers=Headers({
            'X-Account-Container-Count': ['3'],
            'X-Account-Bytes-Used': ['323479'],
        }))
        d.callback(response)

        def cbCheckResponse(resp):
            self.assertEqual(resp, {
                'x-account-bytes-used': '323479',
                'x-account-container-count': '3'
            })
            return resp
        make_request.addCallback(cbCheckResponse)
        return make_request

    def test_get_account(self):
        make_request = self.conn.get_account(limit=10,
                                             marker='test_container_0',
                                             end_marker='test_container_3')
        self.assertEqual(len(self.agent.requests), 1)
        d, args, kwargs = self.agent.requests[0]
        self.assertEqual(args, (
            'GET',
            'http://127.0.0.1:8080/v1/AUTH_user/?marker=test_container_0'
            '&limit=10&end_marker=test_container_3&format=json',
            Headers({
                'user-agent': ['Twisted Swift'],
                'x-auth-token': ['TOKEN_123'],
                'extra': ['header']}),
            None))

        response = StubResponse(200, body='''[
    {"name":"test_container_1", "count":2, "bytes":78},
    {"name":"test_container_2", "count":1, "bytes":17}
]''')
        d.callback(response)

        def cbCheckResponse(resp):
            self.assertEqual(resp, (response, [
                {u'bytes': 78, u'count': 2, u'name': u'test_container_1'},
                {u'bytes': 17, u'count': 1, u'name': u'test_container_2'}
            ]))
            return resp
        make_request.addCallback(cbCheckResponse)
        return make_request

    def test_head_container(self):
        make_request = self.conn.head_container('container')
        self.assertEqual(len(self.agent.requests), 1)
        d, args, kwargs = self.agent.requests[0]
        self.assertEqual(args, (
            'HEAD', 'http://127.0.0.1:8080/v1/AUTH_user/container',
            Headers({
                'user-agent': ['Twisted Swift'],
                'x-auth-token': ['TOKEN_123'],
                'extra': ['header']}),
            None))

        response = StubResponse(200, headers=Headers({
            'X-Container-Object-Count': ['7'],
            'X-Container-Bytes-Used': ['413'],
            'X-Container-Meta-InspectedBy': ['JackWolf'],
        }))
        d.callback(response)

        def cbCheckResponse(resp):
            self.assertEqual(resp, {
                'x-container-bytes-used': '413',
                'x-container-meta-inspectedby': 'JackWolf',
                'x-container-object-count': '7'
            })
            return resp
        make_request.addCallback(cbCheckResponse)
        return make_request

    def test_get_container(self):
        make_request = self.conn.get_container('container',
                                               limit=10,
                                               marker='test_obj_0',
                                               end_marker='test_obj_3',
                                               prefix='test_obj', path='path',
                                               delimiter='/')
        self.assertEqual(len(self.agent.requests), 1)
        d, args, kwargs = self.agent.requests[0]
        self.assertEqual(args, (
            'GET',
            'http://127.0.0.1:8080/v1/AUTH_user/container'
            '?end_marker=test_obj_3&format=json&delimiter=/&prefix=test_obj'
            '&limit=10&marker=test_obj_0&path=path',
            Headers({
                'user-agent': ['Twisted Swift'],
                'x-auth-token': ['TOKEN_123'],
                'extra': ['header']}),
            None))

        response = StubResponse(200, body='''[
   {"name":"test_obj_1",
    "hash":"4281c348eaf83e70ddce0e07221c3d28",
    "bytes":14,
    "content_type":"application\/octet-stream",
    "last_modified":"2009-02-03T05:26:32.612278"},
   {"name":"test_obj_2",
    "hash":"b039efe731ad111bc1b0ef221c3849d0",
    "bytes":64,
    "content_type":"application\/octet-stream",
    "last_modified":"2009-02-03T05:26:32.612278"}
]''')
        d.callback(response)

        def cbCheckResponse(resp):
            self.assertEqual(resp, (response, [{
                u'bytes': 14,
                u'content_type': u'application/octet-stream',
                u'hash': u'4281c348eaf83e70ddce0e07221c3d28',
                u'last_modified': u'2009-02-03T05:26:32.612278',
                u'name': u'test_obj_1'
            }, {
                u'bytes': 64,
                u'content_type': u'application/octet-stream',
                u'hash': u'b039efe731ad111bc1b0ef221c3849d0',
                u'last_modified': u'2009-02-03T05:26:32.612278',
                u'name': u'test_obj_2'
            }]))
            return resp
        make_request.addCallback(cbCheckResponse)
        return make_request

    def test_put_container(self):
        make_request = self.conn.put_container('container')
        self.assertEqual(len(self.agent.requests), 1)
        d, args, kwargs = self.agent.requests[0]
        self.assertEqual(args, (
            'PUT',
            'http://127.0.0.1:8080/v1/AUTH_user/container',
            Headers({
                'user-agent': ['Twisted Swift'],
                'x-auth-token': ['TOKEN_123'],
                'extra': ['header']}),
            None))

        response = StubResponse(201)
        d.callback(response)

        def cbCheckResponse(resp):
            self.assertEqual(resp, (response, None))
            return resp
        make_request.addCallback(cbCheckResponse)
        return make_request

    def test_delete_container(self):
        make_request = self.conn.delete_container('container')
        self.assertEqual(len(self.agent.requests), 1)
        d, args, kwargs = self.agent.requests[0]
        self.assertEqual(args, (
            'DELETE',
            'http://127.0.0.1:8080/v1/AUTH_user/container',
            Headers({
                'user-agent': ['Twisted Swift'],
                'x-auth-token': ['TOKEN_123'],
                'extra': ['header']}),
            None))

        response = StubResponse(204)
        d.callback(response)

        def cbCheckResponse(resp):
            self.assertEqual(resp, (response, None))
            return resp
        make_request.addCallback(cbCheckResponse)
        return make_request

    def test_head_object(self):
        make_request = self.conn.head_object('container', 'object')
        self.assertEqual(len(self.agent.requests), 1)
        d, args, kwargs = self.agent.requests[0]
        self.assertEqual(args, (
            'HEAD', 'http://127.0.0.1:8080/v1/AUTH_user/container/object',
            Headers({
                'user-agent': ['Twisted Swift'],
                'x-auth-token': ['TOKEN_123'],
                'extra': ['header']}),
            None))

        response = StubResponse(200, headers=Headers({
            'Last-Modified': ['Fri, 12 Jun 2010 13:40:18 GMT'],
            'ETag': ['8a964ee2a5e88be344f36c22562a6486'],
            'Content-Length': ['512000'],
            'Content-Type': ['text/plain; charset=UTF-8'],
            'X-Object-Meta-Meat': ['Bacon'],
            'X-Object-Meta-Fruit': ['Bacon'],
            'X-Object-Meta-Veggie': ['Bacon'],
            'X-Object-Meta-Dairy': ['Bacon'],
        }))
        d.callback(response)

        def cbCheckResponse(resp):
            self.assertEqual(resp, {
                'content-length': '512000',
                'content-type': 'text/plain; charset=UTF-8',
                'etag': '8a964ee2a5e88be344f36c22562a6486',
                'last-modified': 'Fri, 12 Jun 2010 13:40:18 GMT',
                'x-object-meta-dairy': 'Bacon',
                'x-object-meta-fruit': 'Bacon',
                'x-object-meta-meat': 'Bacon',
                'x-object-meta-veggie': 'Bacon'
            })
            return resp
        make_request.addCallback(cbCheckResponse)
        return make_request

    def test_get_object(self):
        received = defer.Deferred()
        receiver = ResponseReceiver(received)
        make_request = self.conn.get_object('container', 'object',
                                            receiver=receiver)
        self.assertEqual(len(self.agent.requests), 1)
        d, args, kwargs = self.agent.requests[0]
        self.assertEqual(args, (
            'GET', 'http://127.0.0.1:8080/v1/AUTH_user/container/object',
            Headers({
                'user-agent': ['Twisted Swift'],
                'x-auth-token': ['TOKEN_123'],
                'extra': ['header']}),
            None))

        response = StubResponse(200, headers=Headers({
            'Last-Modified': ['Fri, 12 Jun 2010 13:40:18 GMT'],
            'ETag': ['8a964ee2a5e88be344f36c22562a6486'],
            'Content-Length': ['512000'],
            'Content-Type': ['text/plain; charset=UTF-8'],
            'X-Object-Meta-Meat': ['Bacon'],
            'X-Object-Meta-Fruit': ['Bacon'],
            'X-Object-Meta-Veggie': ['Bacon'],
            'X-Object-Meta-Dairy': ['Bacon'],
        }), body=' ' * 512000)
        d.callback(response)

        def cbCheckResponse(resp):
            self.assertEqual(resp, response)
            return resp
        make_request.addCallback(cbCheckResponse)

        def cbCheckResponseBody(resp):
            self.assertEqual(resp, ' ' * 512000)
            return resp
        received.addCallback(cbCheckResponseBody)
        return defer.gatherResults([make_request, received])

    def test_put_object(self):
        make_request = self.conn.put_object('container', 'object')
        self.assertEqual(len(self.agent.requests), 1)
        d, args, kwargs = self.agent.requests[0]
        self.assertEqual(args, (
            'PUT',
            'http://127.0.0.1:8080/v1/AUTH_user/container/object',
            Headers({
                'content-length': ['0'],
                'user-agent': ['Twisted Swift'],
                'x-auth-token': ['TOKEN_123'],
                'extra': ['header']}),
            None))

        response = StubResponse(201)
        d.callback(response)

        def cbCheckResponse(resp):
            self.assertEqual(resp, (response, ''))
            return resp
        make_request.addCallback(cbCheckResponse)
        return make_request

    def test_delete_object(self):
        make_request = self.conn.delete_object('container', 'object')
        self.assertEqual(len(self.agent.requests), 1)
        d, args, kwargs = self.agent.requests[0]
        self.assertEqual(args, (
            'DELETE',
            'http://127.0.0.1:8080/v1/AUTH_user/container/object',
            Headers({
                'user-agent': ['Twisted Swift'],
                'x-auth-token': ['TOKEN_123'],
                'extra': ['header']}),
            None))

        response = StubResponse(204)
        d.callback(response)

        def cbCheckResponse(resp):
            self.assertEqual(resp, (response, None))
            return resp
        make_request.addCallback(cbCheckResponse)
        return make_request


class ThrottledSwiftConnectionTest(unittest.TestCase):
    def setUp(self):
        self.agent = StubWebAgent()

    def test_single_lock(self):
        lock = defer.DeferredLock()
        conn = ThrottledSwiftConnection(
            [lock], 'http://127.0.0.1:8080/auth/v1.0', 'username', 'api_key',
            verbose=True)
        conn.agent = self.agent
        conn.storage_url = 'http://127.0.0.1:8080/v1/AUTH_user'
        conn.auth_token = 'TOKEN_123'

        conn.make_request('method', 'path')

        self.assertEqual(len(self.agent.requests), 1)
        self.assertEqual(lock.locked, 1)

        conn.make_request('method', 'path2')
        self.assertEqual(len(self.agent.requests), 1)
        d, args, kwargs = self.agent.requests[0]
        d.callback(StubResponse(200))

        self.assertEqual(len(self.agent.requests), 2)
        d, args, kwargs = self.agent.requests[1]
        d.callback(StubResponse(200))
        self.assertEqual(lock.locked, 0)

    def test_multi_lock(self):
        lock = defer.DeferredLock()
        sem = defer.DeferredSemaphore(2)
        conn = ThrottledSwiftConnection(
            [lock, sem],
            'http://127.0.0.1:8080/auth/v1.0', 'username', 'api_key',
            verbose=True)
        conn.agent = self.agent
        conn.storage_url = 'http://127.0.0.1:8080/v1/AUTH_user'
        conn.auth_token = 'TOKEN_123'

        conn.make_request('method', 'path')

        self.assertEqual(len(self.agent.requests), 1)
        self.assertEqual(lock.locked, 1)
        self.assertEqual(sem.tokens, 1)

        conn.make_request('method', 'path2')
        self.assertEqual(len(self.agent.requests), 1)
        d, args, kwargs = self.agent.requests[0]
        d.callback(StubResponse(200))

        self.assertEqual(len(self.agent.requests), 2)
        d, args, kwargs = self.agent.requests[1]
        d.callback(StubResponse(200))
        self.assertEqual(lock.locked, 0)
        self.assertEqual(sem.tokens, 2)


class HelpersTest(unittest.TestCase):

    def test_cb_process_resp(self):
        resp = StubResponse(200)
        response, body = cb_process_resp(None, resp)
        self.assertEqual(response, resp)
        self.assertEqual(body, None)

        # > 404 raises NotFound
        self.assertRaises(NotFound, cb_process_resp, None, StubResponse(404))

        # > 401 raises UnAuthenticated
        self.assertRaises(
            UnAuthenticated, cb_process_resp, None, StubResponse(401))

        # > 403 raises UnAuthorized
        self.assertRaises(
            UnAuthorized, cb_process_resp, None, StubResponse(403))

        # > 409 raises Conflict
        self.assertRaises(Conflict, cb_process_resp, None, StubResponse(409))

        # > 300-399 raises a RequestError
        self.assertRaises(
            error.PageRedirect, cb_process_resp, None, StubResponse(300))

        # > 400 raises a RequestError
        self.assertRaises(
            RequestError, cb_process_resp, None, StubResponse(400))

    def test_response_ignorer(self):
        finished = defer.Deferred()
        ignorer = ResponseIgnorer(finished)
        transport = MagicMock()

        ignorer.makeConnection(transport)
        transport.stopProducing.assert_called_with()

        ignorer.dataReceived(None)
        ignorer.connectionLost(None)

        return finished

    def test_response_receiver(self):
        finished = defer.Deferred()
        recv = ResponseReceiver(finished)
        recv.dataReceived('bytes')
        recv.dataReceived(' go')
        recv.dataReceived('here.')

        err = error.Error('Something Happened')
        recv.connectionLost(Failure(err))

        def checkError(result):
            result.trap(error.Error)
            self.assertRaises(error.Error, result.raiseException)
        finished.addBoth(checkError)
        return finished
