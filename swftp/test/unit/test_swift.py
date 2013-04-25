"""
See COPYING for license information.
"""
from mock import MagicMock

from twisted.python.failure import Failure
from twisted.trial import unittest
from twisted.internet import defer, protocol
from twisted.web.http_headers import Headers
from twisted.web._newclient import ResponseDone

from swftp.swift import SwiftConnection


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
        self.headers = headers or {}
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
            'http://127.0.0.1:8080/auth/v1.0', 'username', 'api_key')
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
        self.assertEqual(conn.agent._pool, pool)

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
                'x-auth-token': ['TOKEN_123']}),
            'body'))
        self.assertEqual(kwargs, {})

        response = StubResponse(200, body='some body')
        d.callback(response)

        def cbCheckResponse(resp):
            self.assertEqual(resp, response)
        make_request.addCallback(cbCheckResponse)
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
                'x-auth-token': ['TOKEN_123']}),
            'body'))
        self.assertEqual(kwargs, {})

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
                'x-auth-key': ['api_key']})))
        self.assertEqual(kwargs, {})

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
            'http://127.0.0.1:8080/v1/AUTH_user/path/to/resource?param=value',
            Headers({
                'header': ['value'],
                'user-agent': ['Twisted Swift'],
                'x-auth-token': ['AUTHED_TOKEN']}),
            'body'))
        self.assertEqual(kwargs, {})

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
                'x-auth-key': ['api_key']})))
        self.assertEqual(kwargs, {})

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
