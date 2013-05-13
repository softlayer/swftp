"""
See COPYING for license information.
"""
from zope.interface import implements
from twisted.internet import defer, reactor
from twisted.web.client import HTTPConnectionPool
from twisted.python import log
from twisted.cred import checkers, error, credentials

from swftp.swift import ThrottledSwiftConnection, UnAuthenticated, UnAuthorized
from swftp import USER_AGENT


class SwiftBasedAuthDB:
    """
        Swift-based authentication

        Implements twisted.cred.ICredentialsChecker

        :param auth_url: auth endpoint for swift
        :param int global_max_concurrency: The max concurrency for the entire
            server
        :param int max_concurrency: The max concurrency for each
            ThrottledSwiftConnection object
        :param bool verbose: verbose setting
    """
    implements(checkers.ICredentialsChecker)
    credentialInterfaces = (
        credentials.IUsernamePassword,
    )

    def __init__(self,
                 auth_url,
                 global_max_concurrency=100,
                 max_concurrency=10,
                 timeout=260,
                 extra_headers=None,
                 verbose=False):
        self.auth_url = auth_url
        self.global_max_concurrency = global_max_concurrency
        self.max_concurrency = max_concurrency
        self.timeout = timeout
        self.extra_headers = extra_headers
        self.verbose = verbose

    def _after_auth(self, result, connection):
        log.msg(metric='auth.succeed')
        return connection

    def requestAvatarId(self, c):
        creds = credentials.IUsernamePassword(c, None)

        if creds is not None:
            defer.DeferredSemaphore(self.max_concurrency)

            locks = []
            pool = HTTPConnectionPool(reactor, persistent=False)
            pool.cachedConnectionTimeout = self.timeout
            if self.max_concurrency:
                pool.persistent = True
                pool.maxPersistentPerHost = self.max_concurrency
                locks.append(
                    defer.DeferredSemaphore(self.max_concurrency))

            if self.global_max_concurrency:
                locks.append(
                    defer.DeferredSemaphore(self.global_max_concurrency))

            conn = ThrottledSwiftConnection(
                locks, self.auth_url, creds.username, creds.password,
                pool=pool,
                extra_headers=self.extra_headers,
                verbose=self.verbose)
            conn.user_agent = USER_AGENT

            d = conn.authenticate()
            d.addCallback(self._after_auth, conn)
            d.addErrback(eb_failed_auth)
            return d
        return defer.fail(error.UnauthorizedLogin())


def eb_failed_auth(failure):
    failure.trap(UnAuthenticated, UnAuthorized)
    log.msg(metric='auth.fail')
    return defer.fail(error.UnauthorizedLogin())
