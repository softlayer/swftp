"""
See COPYING for license information.
"""
from twisted.trial import unittest

from mock import patch
from twisted.cred.credentials import UsernamePassword
from twisted.cred.error import UnauthorizedLogin
from twisted.internet import defer

from swftp.auth import SwiftBasedAuthDB
from swftp.swift import UnAuthenticated


def authenticate_good(ignored):
    return defer.succeed(None)


def authenticate_bad(ignored):
    return defer.fail(UnAuthenticated(401, 'Not Authenticated'))


class MetricCollectorTest(unittest.TestCase):
    def setUp(self):
        self.auth_db = SwiftBasedAuthDB('http://127.0.0.1:8080/v1/auth')

    def test_init(self):
        auth_db = SwiftBasedAuthDB('http://127.0.0.1:8080/v1/auth')
        self.assertEquals(auth_db.auth_url, 'http://127.0.0.1:8080/v1/auth')
        self.assertEquals(auth_db.global_max_concurrency, 100)
        self.assertEquals(auth_db.max_concurrency, 10)
        self.assertEquals(auth_db.timeout, 260)
        self.assertEquals(auth_db.verbose, False)

        auth_db = SwiftBasedAuthDB(
            'http://127.0.0.1:8080/v1/auth',
            global_max_concurrency=200,
            max_concurrency=20,
            timeout=460,
            verbose=True,
        )
        self.assertEquals(auth_db.auth_url, 'http://127.0.0.1:8080/v1/auth')
        self.assertEquals(auth_db.global_max_concurrency, 200)
        self.assertEquals(auth_db.max_concurrency, 20)
        self.assertEquals(auth_db.timeout, 460)
        self.assertEquals(auth_db.verbose, True)

    @patch('swftp.auth.ThrottledSwiftConnection.authenticate',
           authenticate_good)
    def test_request_avatar_id(self):
        creds = UsernamePassword('username', 'password')
        return self.auth_db.requestAvatarId(creds)

    @patch('swftp.auth.ThrottledSwiftConnection.authenticate',
           authenticate_bad)
    def test_request_avatar_id_fail(self):
        creds = UsernamePassword('username', 'password')
        d = self.auth_db.requestAvatarId(creds)
        return self.assertFailure(d, UnauthorizedLogin)

    def test_request_avatar_id_invalid_method(self):
        return self.assertFailure(
            self.auth_db.requestAvatarId('nope'), UnauthorizedLogin)
