"""
See COPYING for license information.
"""
from zope.interface import implements
from twisted.internet import defer
from twisted.cred import checkers, error, credentials

from swftp.swift import (
    SwiftConnection, ThrottledSwiftConnection, UnAuthenticated, UnAuthorized)
from swftp.utils import USER_AGENT


class SwiftBasedAuthDB:
    """
        Swift-based authentication.

        Implements twisted.cred.ICredentialsChecker
    """
    implements(checkers.ICredentialsChecker)

    def __init__(self, auth_url=None, pool=None, max_concurrency=20,
                 verbose=False):
        self.auth_url = auth_url
        self.pool = pool
        self.verbose = verbose
        if max_concurrency:
            self.swift_connection_class = ThrottledSwiftConnection
            self.swift_connection_class.max_concurrency = max_concurrency
        else:
            self.swift_connection_class = SwiftConnection

    credentialInterfaces = (
        credentials.IUsernamePassword,
    )

    def _after_auth(self, result, connection):
        return connection

    def requestAvatarId(self, c):
        creds = credentials.IUsernamePassword(c, None)
        if creds is not None:
            conn = self.swift_connection_class(
                self.auth_url, creds.username, creds.password,
                pool=self.pool,
                verbose=self.verbose)
            conn.user_agent = USER_AGENT
            d = conn.authenticate()
            d.addCallback(self._after_auth, conn)
            d.addErrback(failed_auth)
            return d
        return defer.fail(error.UnauthorizedLogin())


def failed_auth(failure):
    failure.trap(UnAuthenticated, UnAuthorized)
    return defer.fail(error.UnauthorizedLogin())
