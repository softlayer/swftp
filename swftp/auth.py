"""
See COPYING for license information.
"""
import urlparse

from zope.interface import implements
from twisted.internet import defer, reactor
from twisted.web.client import HTTPConnectionPool
from twisted.python import log
from twisted.cred import checkers, error, credentials

from swftp.swift import ThrottledSwiftConnection, UnAuthenticated, UnAuthorized
from swftp import USER_AGENT


class SwiftBasedAuthDB(object):
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
                 verbose=False,
                 rewrite_scheme=None,
                 rewrite_netloc=None):
        self.auth_url = auth_url
        self.global_max_concurrency = global_max_concurrency
        self.max_concurrency = max_concurrency
        self.timeout = timeout
        self.extra_headers = extra_headers
        self.verbose = verbose
        self.rewrite_scheme = rewrite_scheme
        self.rewrite_netloc = rewrite_netloc

    def _rewrite_storage_url(self, connection):
        if not any((self.rewrite_scheme, self.rewrite_netloc)):
            return

        storage_url_parsed = urlparse.urlparse(connection.storage_url)

        new_parts = {
            'scheme': storage_url_parsed.scheme,
            'netloc': storage_url_parsed.netloc,
            'path': storage_url_parsed.path,
            'query': storage_url_parsed.query,
            'fragment': storage_url_parsed.fragment,
        }

        part_mapping = {
            'scheme': self.rewrite_scheme,
            'netloc': self.rewrite_netloc,
        }

        for k, v in part_mapping.items():
            if v:
                new_parts[k] = v

        # Rebuild the URL and set it to the connection's storage_url
        connection.storage_url = urlparse.urlunsplit((
            new_parts['scheme'], new_parts['netloc'], new_parts['path'],
            new_parts['query'], new_parts['fragment']))

    def _after_auth(self, result, connection):
        log.msg(metric='auth.succeed')
        self._rewrite_storage_url(connection)
        return connection

    def requestAvatarId(self, c):
        creds = credentials.IUsernamePassword(c, None)

        if creds is not None:
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
