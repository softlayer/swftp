"""
This file contains the primary server code for the FTP server.

See COPYING for license information.
"""
import stat
from collections import defaultdict

from zope.interface import implements
from twisted.protocols.ftp import (
    FTP, IFTPShell, IReadFile, IWriteFile, FileNotFoundError,
    CmdNotImplementedForArgError, IsNotADirectoryError, IsADirectoryError,
    RESPONSE, TOO_MANY_CONNECTIONS)
from twisted.internet import defer, reactor
from twisted.internet.protocol import Protocol
from twisted.python import log
from twisted.protocols.ftp import (
    CmdArgSyntaxError, BadCmdSequenceError,
    REQ_FILE_ACTN_PENDING_FURTHER_INFO, PortConnectionError
)

from swftp.logging import msg
from swftp.swiftfilesystem import SwiftFileSystem, swift_stat, obj_to_path
from swftp.swift import NotFound, Conflict


def stat_format(keys, props):
    st = swift_stat(**props)
    l = []
    for key in keys:
        if key == 'size':
            val = st.st_size
        elif key == 'directory':
            val = st.st_mode & stat.S_IFDIR == stat.S_IFDIR
        elif key == 'permissions':
            val = st.st_mode
        elif key == 'hardlinks':
            val = 0
        elif key == 'modified':
            val = int(st.st_mtime)
        elif key in 'owner':
            val = 'nobody'
        elif key in 'group':
            val = 'nobody'
        else:  # Unknown Value
            val = ''
        l.append(val)
    return l


class SwftpFTPProtocol(FTP, object):
    _connCountMap = defaultdict(int)
    maxConnectionsPerUser = 10

    def connectionMade(self, *args, **kwargs):
        log.msg(metric='num_clients')
        return super(SwftpFTPProtocol, self).connectionMade(*args, **kwargs)

    def connectionLost(self, *args, **kwargs):
        log.msg(metric='num_clients', count=-1)

        if self.shell:
            username = self.shell.username()
            msg("User Disconnected (%s) [%s/%s]" % (
                username,
                self._connCountMap[username],
                self.maxConnectionsPerUser,
                ))
            self._connCountMap[username] -= 1
            # To avoid a slow memory leak
            if self._connCountMap[username] == 0:
                del self._connCountMap[username]
        return super(SwftpFTPProtocol, self).connectionLost(*args, **kwargs)

    def ftp_PASS(self, *args, **kwargs):
        # Check to see if the user has too many connections
        d = super(SwftpFTPProtocol, self).ftp_PASS(*args, **kwargs)

        def pass_cb(res):
            username = self.shell.username()
            self._connCountMap[username] += 1
            msg("User Connected (%s) [%s/%s]" % (
                username,
                self._connCountMap[username],
                self.maxConnectionsPerUser,
                ))
            if self.maxConnectionsPerUser != 0 and \
                    self._connCountMap[username] > self.maxConnectionsPerUser:
                msg("Too Many Connections For User (%s) [%s/%s]" % (
                    username,
                    self._connCountMap[username],
                    self.maxConnectionsPerUser,
                    ))
                self.sendLine(RESPONSE[TOO_MANY_CONNECTIONS])
                self.transport.loseConnection()
            return res

        d.addCallback(pass_cb)
        return d

    def ftp_LIST(self, path=''):
        # ignore special flags for command LIST
        keys = ['-a', '-l', '-la', '-al']
        segm = path.split()
        path = " ".join(s for s in segm if s.lower() not in keys)

        return super(SwftpFTPProtocol, self).ftp_LIST(path)

    def ftp_NLST(self, path=''):
        """
        Overwrite for fix http://twistedmatrix.com/trac/ticket/4258
        """
        return super(SwftpFTPProtocol, self).ftp_NLST(path)

    def ftp_PASV(self):
        d = super(SwftpFTPProtocol, self).ftp_PASV()

        def dtp_connect_timeout_eb(failure):
            failure.trap(PortConnectionError)

        return d.addErrback(dtp_connect_timeout_eb)

    def ftp_REST(self, value):
        if self.dtpInstance is None:
            raise BadCmdSequenceError('PORT or PASV required before RETR')

        try:
            value = int(value)
            if value < 0:
                raise ValueError
        except ValueError:
            raise CmdArgSyntaxError('Value must be nonnegative integer')
        else:
            self.dtpInstance.rest_offset = value

        return (REQ_FILE_ACTN_PENDING_FURTHER_INFO, )

    def cleanupDTP(self):
        """
        Overwrite cleanupDTP() for fix socket leak
        (see http://twistedmatrix.com/trac/ticket/5367)
        """
        transport = None
        if self.dtpInstance is not None:
            if self.dtpInstance.transport is not None:
                transport = self.dtpInstance.transport

        super(SwftpFTPProtocol, self).cleanupDTP()

        if transport:
            transport.abortConnection()


class SwiftFTPShell(object):
    """ Implements all the methods needed to treat Swift as an FTP Shell """
    implements(IFTPShell)

    def __init__(self, swiftconn):
        self.swiftconn = swiftconn
        self.swiftfilesystem = SwiftFileSystem(self.swiftconn)
        self.log_command('login')

    def log_command(self, command, *args):
        arg_list = ', '.join(str(arg) for arg in args)
        msg("cmd: %s(%s)" % (command, arg_list),
            system="SwFTP-FTP, (%s)" % self.swiftconn.username,
            metric='command.%s' % command)

    def username(self):
        return self.swiftconn.username

    def logout(self):
        self.log_command('logout')
        if self.swiftconn.pool:
            self.swiftconn.pool.closeCachedConnections()
        del self.swiftconn

    def _fullpath(self, path_parts):
        return '/'.join(path_parts)

    def makeDirectory(self, path):
        self.log_command('makeDirectory', path)
        fullpath = self._fullpath(path)
        return self.swiftfilesystem.makeDirectory(fullpath)

    def removeDirectory(self, path):
        self.log_command('removeDirectory', path)
        fullpath = self._fullpath(path)

        def not_found_eb(failure):
            failure.trap(NotFound)

        def conflict_eb(failure):
            failure.trap(Conflict)
            raise CmdNotImplementedForArgError(
                'Cannot delete non-empty directories.')

        d = self.swiftfilesystem.removeDirectory(fullpath)
        d.addErrback(not_found_eb)
        d.addErrback(conflict_eb)
        return d

    def removeFile(self, path):
        self.log_command('removeFile', path)
        fullpath = self._fullpath(path)

        def errback(failure):
            failure.trap(NotFound, NotImplementedError)
            if failure.check(NotImplementedError):
                return defer.fail(IsADirectoryError(fullpath))
        d = defer.maybeDeferred(self.swiftfilesystem.removeFile, fullpath)
        d.addErrback(errback)
        return d

    def rename(self, fromPath, toPath):
        self.log_command('rename', fromPath, toPath)
        oldpath = self._fullpath(fromPath)
        newpath = self._fullpath(toPath)

        d = self.swiftfilesystem.renameFile(oldpath, newpath)

        def errback(failure):
            failure.trap(NotFound, Conflict, NotImplementedError)
            if failure.check(NotFound):
                return defer.fail(FileNotFoundError(oldpath))
            else:
                return defer.fail(CmdNotImplementedForArgError(oldpath))
        d.addErrback(errback)
        return d

    def access(self, path):
        self.log_command('access', path)
        fullpath = self._fullpath(path)

        d = self.swiftfilesystem.getAttrs(fullpath)

        def cb(result):
            if result['content_type'] == 'application/directory':
                return defer.succeed(lambda: None)
            return defer.fail(IsNotADirectoryError(fullpath))
        d.addCallback(cb)

        def err(failure):
            failure.trap(NotFound)
            # Containers need to actually exist before uploading anything
            # inside of them. Therefore require containers to actually exist.
            # All other paths don't have to.
            if len(path) != 1:
                return defer.succeed(lambda: None)
            else:
                return defer.fail(IsNotADirectoryError(fullpath))

        d.addErrback(err)
        return d

    def stat(self, path, keys=()):
        self.log_command('stat', path, keys)
        fullpath = self._fullpath(path)

        def cb(result):
            return stat_format(keys, result)

        def err(failure):
            failure.trap(NotFound)
            return defer.fail(FileNotFoundError(fullpath))

        d = self.swiftfilesystem.getAttrs(fullpath)
        d.addCallback(cb)
        d.addErrback(err)
        return d

    def list(self, path=None, keys=()):
        self.log_command('list', path)
        fullpath = self._fullpath(path)

        def cb(results):
            l = []
            for key, value in results.iteritems():
                l.append([key, stat_format(keys, value)])
            return l

        def err(failure):
            failure.trap(NotFound)
            return defer.fail(FileNotFoundError(fullpath))

        d = self.swiftfilesystem.get_full_listing(fullpath)
        d.addCallback(cb)
        d.addErrback(err)
        return d

    def openForReading(self, path):
        self.log_command('openForReading', path)
        fullpath = self._fullpath(path)

        def cb(results):
            return SwiftReadFile(self.swiftfilesystem, fullpath)

        def err(failure):
            failure.trap(NotFound)
            return defer.fail(FileNotFoundError(fullpath))

        try:
            d = self.swiftfilesystem.checkFileExistance(fullpath)
            d.addCallback(cb)
            d.addErrback(err)
            return d
        except NotImplementedError:
            return defer.fail(IsADirectoryError(fullpath))

    def openForWriting(self, path):
        self.log_command('openForWriting', path)
        fullpath = self._fullpath(path)
        container, obj = obj_to_path(fullpath)
        if not container or not obj:
            raise CmdNotImplementedForArgError(
                'Cannot upload files to root directory.')
        f = SwiftWriteFile(self.swiftfilesystem, fullpath)
        return defer.succeed(f)


class SwiftWriteFile(object):
    implements(IWriteFile)

    def __init__(self, swiftfilesystem, fullpath):
        self.swiftfilesystem = swiftfilesystem
        self.fullpath = fullpath
        self.finished = None

    def receive(self):
        d, writer = self.swiftfilesystem.startFileUpload(self.fullpath)
        self.finished = d
        return writer.started

    def close(self):
        return self.finished


class SwiftReadFile(Protocol):
    implements(IReadFile)

    def __init__(self, swiftfilesystem, fullpath):
        self.swiftfilesystem = swiftfilesystem
        self.fullpath = fullpath
        self.finished = defer.Deferred()
        self.backend_transport = None
        self.timeout = None
        self._timedout = False

    def setTimeout(self, seconds):
        if self.timeout:
            self.cancelTimeout()
        self.timeout = reactor.callLater(seconds, self.timedOut)

    def cancelTimeout(self):
        if self.timeout:
            self.timeout.cancel()

    def timedOut(self):
        self._timedout = True
        self.stopProducing()

    # IReadFile Interface
    def send(self, consumer):
        at = getattr(consumer, "rest_offset", 0)
        if at:
            del consumer.rest_offset  # reset for next command
        self.consumer = consumer
        d = self.swiftfilesystem.startFileDownload(
            self.fullpath, self, offset=at)
        d.addCallback(lambda _: self.finished)
        self.consumer.registerProducer(self, True)
        return d

    # Producer Interface
    def resumeProducing(self):
        self.setTimeout(20)
        if self.backend_transport:
            self.backend_transport.resumeProducing()

    def pauseProducing(self):
        if self.backend_transport:
            self.backend_transport.pauseProducing()

    def stopProducing(self):
        if self.backend_transport:
            self.backend_transport.stopProducing()

    # Protocol
    def dataReceived(self, data):
        log.msg(metric='transfer.egress_bytes', count=len(data))
        self.consumer.write(data)
        self.setTimeout(20)

    def connectionLost(self, reason):
        from twisted.web._newclient import ResponseDone
        from twisted.web.http import PotentialDataLoss

        if reason.check(ResponseDone) or reason.check(PotentialDataLoss):
            self.finished.callback(None)
        else:
            if self._timedout:
                defer.timeout(self.finished)
            else:
                self.finished.errback(reason)
        self.backend_transport = None
        self.consumer.unregisterProducer()

    def makeConnection(self, transport):
        self.backend_transport = transport

    def connectionMade(self):
        pass
