"""
See COPYING for license information.
"""
from zope.interface import implements
from twisted.internet import defer
from twisted.cred import checkers, error, credentials

from swftp.swift import ThrottledSwiftConnection, UnAuthenticated, UnAuthorized
from swftp.utils import USER_AGENT


class SwiftBasedAuthDB:
    """
        Swift-based authentication

        Implements twisted.cred.ICredentialsChecker

        :param auth_url: auth endpoint for swift
        :param pool: A twisted.web.client.HTTPConnectionPool object
        :param int max_concurrency: The max concurrency for each
            ThrottledSwiftConnection object
        :param bool verbose: verbose setting
    """
    implements(checkers.ICredentialsChecker)
    credentialInterfaces = (
        credentials.IUsernamePassword,
    )

    def __init__(self,
                 auth_url=None,
                 pool=None,
                 max_concurrency=20,
                 verbose=False):
        self.auth_url = auth_url
        self.pool = pool
        self.global_lock = None
        if self.pool:
            self.global_lock = defer.DeferredSemaphore(
                pool.maxPersistentPerHost)
        self.verbose = verbose
        self.max_concurrency = max_concurrency

    def _after_auth(self, result, connection):
        return connection

    def requestAvatarId(self, c):
        creds = credentials.IUsernamePassword(c, None)
        if creds is not None:
            defer.DeferredSemaphore(self.max_concurrency)

            semaphores = []
            if self.max_concurrency:
                semaphores.append(
                    defer.DeferredSemaphore(self.max_concurrency))
            if self.global_lock:
                semaphores.append(self.global_lock)

            conn = ThrottledSwiftConnection(
                semaphores, self.auth_url, creds.username, creds.password,
                pool=self.pool, verbose=self.verbose)
            conn.user_agent = USER_AGENT

            d = conn.authenticate()
            d.addCallback(self._after_auth, conn)
            d.addErrback(eb_failed_auth)
            return d
        return defer.fail(error.UnauthorizedLogin())


def eb_failed_auth(failure):
    failure.trap(UnAuthenticated, UnAuthorized)
    return defer.fail(error.UnauthorizedLogin())
