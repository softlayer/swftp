"""
See COPYING for license information.
"""
from twisted.trial import unittest

from mock import patch, MagicMock
from twisted.cred.credentials import UsernamePassword
from twisted.cred.error import UnauthorizedLogin
from twisted.internet import defer

from swftp.auth import SwiftBasedAuthDB
from swftp.swift import UnAuthenticated


def authenticate_good(ignored):
    return defer.succeed(None)


def authenticate_bad(ignored):
    return defer.fail(UnAuthenticated(401, 'Not Authenticated'))


class AuthenticateTest(unittest.TestCase):
    def setUp(self):
        self.auth_db = SwiftBasedAuthDB('http://127.0.0.1:8080/v1/auth')

    def test_init(self):
        auth_db = SwiftBasedAuthDB('http://127.0.0.1:8080/v1/auth')
        self.assertEquals(auth_db.auth_url, 'http://127.0.0.1:8080/v1/auth')
        self.assertEquals(auth_db.global_max_concurrency, 100)
        self.assertEquals(auth_db.max_concurrency, 10)
        self.assertEquals(auth_db.timeout, 260)
        self.assertEquals(auth_db.verbose, False)
        self.assertEquals(auth_db.rewrite_scheme, None)
        self.assertEquals(auth_db.rewrite_netloc, None)

        auth_db = SwiftBasedAuthDB(
            'http://127.0.0.1:8080/v1/auth',
            global_max_concurrency=200,
            max_concurrency=20,
            timeout=460,
            verbose=True,
            rewrite_scheme='https',
            rewrite_netloc='some-hostname:1234',
        )
        self.assertEquals(auth_db.auth_url, 'http://127.0.0.1:8080/v1/auth')
        self.assertEquals(auth_db.global_max_concurrency, 200)
        self.assertEquals(auth_db.max_concurrency, 20)
        self.assertEquals(auth_db.timeout, 460)
        self.assertEquals(auth_db.verbose, True)
        self.assertEquals(auth_db.rewrite_scheme, 'https')
        self.assertEquals(auth_db.rewrite_netloc, 'some-hostname:1234')

    @patch('swftp.auth.ThrottledSwiftConnection.authenticate',
           authenticate_good)
    def test_request_avatar_id(self):
        creds = UsernamePassword('username', 'password')
        return self.auth_db.requestAvatarId(creds)

    @patch('swftp.auth.ThrottledSwiftConnection.authenticate',
           authenticate_good)
    def test_zero_concurrency(self):
        auth_db = SwiftBasedAuthDB(
            'http://127.0.0.1:8080/v1/auth',
            global_max_concurrency=0,
            max_concurrency=0,
        )

        def check_connection(conn):
            self.assertEquals(conn.username, 'username')
            self.assertEquals(conn.api_key, 'password')
            # Default connection pool size per host is 2
            self.assertEquals(conn.pool.maxPersistentPerHost, 2)
            self.assertEquals(conn.pool.persistent, False)
            self.assertEquals(conn.locks, [])

        creds = UsernamePassword('username', 'password')
        d = auth_db.requestAvatarId(creds)
        d.addCallback(check_connection)
        return d

    @patch('swftp.auth.ThrottledSwiftConnection.authenticate',
           authenticate_bad)
    def test_request_avatar_id_fail(self):
        creds = UsernamePassword('username', 'password')
        d = self.auth_db.requestAvatarId(creds)
        return self.assertFailure(d, UnauthorizedLogin)

    def test_request_avatar_id_invalid_method(self):
        return self.assertFailure(
            self.auth_db.requestAvatarId('nope'), UnauthorizedLogin)


class StorageUrlRewriteTest(unittest.TestCase):

    def test_no_storage_url(self):
        swift_conn = MagicMock()
        swift_conn.storage_url = 'http://some-storage-url/v1/AUTH_12345'
        auth_db = SwiftBasedAuthDB('http://127.0.0.1:8080/v1/auth')
        auth_db._rewrite_storage_url(swift_conn)

        self.assertEquals(swift_conn.storage_url,
                          'http://some-storage-url/v1/AUTH_12345')

    def test_hostname(self):
        swift_conn = MagicMock()
        swift_conn.storage_url = 'http://some-storage-url/v1/AUTH_12345'
        auth_db = SwiftBasedAuthDB(
            'http://127.0.0.1:8080/v1/auth',
            rewrite_netloc='hostname')
        auth_db._rewrite_storage_url(swift_conn)

        self.assertEquals(swift_conn.storage_url,
                          'http://hostname/v1/AUTH_12345')

    def test_hostname_port(self):
        swift_conn = MagicMock()
        swift_conn.storage_url = 'http://some-storage-url/v1/AUTH_12345'
        auth_db = SwiftBasedAuthDB(
            'http://127.0.0.1:8080/v1/auth',
            rewrite_netloc='hostname:1234')
        auth_db._rewrite_storage_url(swift_conn)

        self.assertEquals(swift_conn.storage_url,
                          'http://hostname:1234/v1/AUTH_12345')

    def test_scheme(self):
        swift_conn = MagicMock()
        swift_conn.storage_url = 'http://some-storage-url/v1/AUTH_12345'
        auth_db = SwiftBasedAuthDB(
            'http://127.0.0.1:8080/v1/auth',
            rewrite_scheme='https')
        auth_db._rewrite_storage_url(swift_conn)

        self.assertEquals(swift_conn.storage_url,
                          'https://some-storage-url/v1/AUTH_12345')

    def test_all(self):
        swift_conn = MagicMock()
        swift_conn.storage_url = 'http://some-storage-url/v1/AUTH_12345'
        auth_db = SwiftBasedAuthDB(
            'http://127.0.0.1:8080/v1/auth',
            rewrite_scheme='https',
            rewrite_netloc='hostname:1234')
        auth_db._rewrite_storage_url(swift_conn)

        self.assertEquals(swift_conn.storage_url,
                          'https://hostname:1234/v1/AUTH_12345')
