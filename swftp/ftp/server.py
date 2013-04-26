"""
This file contains the primary server code for the FTP server.

See COPYING for license information.
"""
from zope.interface import implements
from twisted.cred import portal
from twisted.protocols.ftp import IFTPShell, IReadFile, IWriteFile, \
    FileNotFoundError, CmdNotImplementedForArgError, IsNotADirectoryError, \
    IsADirectoryError
from twisted.internet import defer
from twisted.internet.protocol import Protocol
from twisted.python import log
import stat

from swftp.swiftfilesystem import SwiftFileSystem, swift_stat, obj_to_path
from swftp.swift import NotFound, Conflict


class SwiftFTPRealm:
    implements(portal.IRealm)

    def getHomeDirectory(self):
        return '/'

    def requestAvatar(self, avatarId, mind, *interfaces):
        shell = SwiftFTPShell(avatarId)
        return interfaces[0], shell, shell.logout


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


class SwiftFTPShell:
    """ Implements all the methods needed to treat Swift as an FTP Shell """
    implements(IFTPShell)

    def __init__(self, swiftconn):
        self.swiftconn = swiftconn
        self.swiftfilesystem = SwiftFileSystem(self.swiftconn)
        self.log_command('login')
        log.msg(metric='num_clients')

    def log_command(self, command, *args):
        arg_list = ', '.join(str(arg) for arg in args)
        log.msg("COMMAND: %s(%s)" % (command, arg_list),
                system="SwFTP-FTP, (%s)" % self.swiftconn.username,
                metric='command.%s' % command)

    def logout(self):
        self.log_command('logout')
        log.msg(metric='num_clients', count=-1)
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
            log.msg('cannot upload to root')
            raise CmdNotImplementedForArgError(
                'Cannot upload files to root directory.')
        f = SwiftWriteFile(self.swiftfilesystem, fullpath)
        return defer.succeed(f)


class SwiftWriteFile:
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

    def cb_send(self, result):
        return self.finished

    def send(self, consumer):
        self.consumer = consumer
        d = self.swiftfilesystem.startFileDownload(self.fullpath, self)
        d.addCallback(self.cb_send)
        return d

    def dataReceived(self, data):
        self.consumer.write(data)
        log.msg(metric='transfer.egress_bytes', count=len(data))

    def connectionLost(self, reason):
        from twisted.web._newclient import ResponseDone
        from twisted.web.http import PotentialDataLoss

        if reason.check(ResponseDone) or reason.check(PotentialDataLoss):
            self.finished.callback(None)
        else:
            self.finished.errback(reason)
        self.consumer.unregisterProducer()

    def makeConnection(self, transport):
        pass

    def connectionMade(self):
        pass
