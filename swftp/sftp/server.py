"""
This file contains the primary server code for the SFTP server.

See COPYING for license information.
"""
from zope import interface

from twisted.conch.interfaces import ISFTPServer, ISession
from twisted.cred import portal
from twisted.python import components, log
from twisted.internet import defer

from twisted.conch import avatar
from twisted.conch.ssh import session
from twisted.conch.ssh.filetransfer import FileTransferServer, SFTPError, \
    FX_FAILURE, FX_NO_SUCH_FILE
from twisted.conch.ssh.common import getNS
from twisted.conch.ssh.transport import SSHServerTransport

from swftp.swift import NotFound, Conflict
from swftp.sftp.swiftfile import SwiftFile
from swftp.sftp.swiftdirectory import SwiftDirectory
from swftp.swiftfilesystem import SwiftFileSystem, swift_stat, obj_to_path


class SwiftSession:
    " Barebones Session that closes when a client tries to open a shell "
    interface.implements(ISession)

    def __init__(self, avatar):
        self.avatar = avatar

    def openShell(self, proto):
        self.avatar.conn.transport.transport.loseConnection()

    def getPty(self, term, windowSize, modes):
        pass

    def closed(self):
        pass


class SwiftSFTPRealm:
    "Swift SFTP Realm"
    interface.implements(portal.IRealm)

    def requestAvatar(self, avatarId, mind, *interfaces):
        avatar = SwiftSFTPAvatar(avatarId)
        return interfaces[0], avatar, avatar.logout


class SwiftFileTransferServer(FileTransferServer):
    # Overridden to expose the session to the file object to do intellegent
    # throttling. Without this, memory bloat occurs.
    def _cbOpenFile(self, fileObj, requestId):
        fileObj.session = self.transport.session
        FileTransferServer._cbOpenFile(self, fileObj, requestId)

    # This is overridden because Flow was sending data that looks to be invalid
    def packet_REALPATH(self, data):
        requestId = data[:4]
        data = data[4:]
        path, data = getNS(data)
        # assert data == '', 'still have data in REALPATH: %s' % repr(data)
        d = defer.maybeDeferred(self.client.realPath, path)
        d.addCallback(self._cbReadLink, requestId)  # same return format
        d.addErrback(self._ebStatus, requestId, 'realpath failed')


class SwiftSSHServerTransport(SSHServerTransport):
    # Overridden to set the version string.
    version = 'SwFTP'
    ourVersionString = 'SSH-2.0-SwFTP'


class SwiftSFTPAvatar(avatar.ConchUser):
    "Swift SFTP Avatar"
    def __init__(self, swiftconn):
        avatar.ConchUser.__init__(self)
        self.swiftconn = swiftconn

        self.channelLookup.update({"session": session.SSHSession})
        self.subsystemLookup.update({"sftp": SwiftFileTransferServer})

        self.cwd = ''

    def logout(self):
        self.log_command('logout')
        self.swiftconn = None

    def log_command(self, command, *args):
        arg_list = ', '.join(str(arg) for arg in args)
        log.msg("COMMAND: %s(%s)" % (command, arg_list),
                system="SwFTP-SFTP, (%s)" % self.swiftconn.username,
                metric='command.%s' % command)


class SFTPServerForSwiftConchUser:
    "SFTP Server For a Swift User"
    interface.implements(ISFTPServer)

    def __init__(self, avatar):
        self.swiftconn = avatar.swiftconn
        self.swiftfilesystem = SwiftFileSystem(self.swiftconn)
        self.avatar = avatar
        self.conn = avatar.conn
        self.log_command('login')

    def log_command(self, *args, **kwargs):
        return self.avatar.log_command(*args, **kwargs)

    def gotVersion(self, otherVersion, extData):
        return {}

    def openFile(self, fullpath, flags, attrs):
        self.log_command('openFile', fullpath, flags, attrs)
        f = SwiftFile(self, fullpath, flags=flags, attrs=attrs)
        d = f.checkExistance()

        def errback(failure):
            failure.trap(NotFound)
            raise SFTPError(FX_FAILURE, "Container Doesn't Exist")

        d.addCallback(lambda r: f)
        d.addErrback(errback)
        return d

    def removeFile(self, fullpath):
        self.log_command('removeFile', fullpath)
        return self.swiftfilesystem.removeFile(fullpath)

    def renameFile(self, oldpath, newpath):
        self.log_command('renameFile', oldpath, newpath)
        d = self.swiftfilesystem.renameFile(oldpath, newpath)

        def errback(failure):
            failure.trap(NotFound, Conflict)
            if failure.check(NotFound):
                raise SFTPError(FX_NO_SUCH_FILE, 'No Such File')
            if failure.check(Conflict):
                raise NotImplementedError

        d.addErrback(errback)
        return d

    def makeDirectory(self, fullpath, attrs):
        self.log_command('makeDirectory', fullpath, attrs)

        def errback(failure):
            failure.trap(NotFound)
            raise SFTPError(FX_NO_SUCH_FILE, 'Directory Not Found')

        d = self.swiftfilesystem.makeDirectory(fullpath, attrs)
        d.addErrback(errback)
        return d

    def removeDirectory(self, fullpath):
        self.log_command('removeDirectory', fullpath)
        d = self.swiftfilesystem.removeDirectory(fullpath)

        def errback(failure):
            failure.trap(NotFound, Conflict)
            if failure.check(NotFound):
                return
            if failure.check(Conflict):
                raise SFTPError(FX_FAILURE, 'Directory Not Empty')

        d.addErrback(errback)
        return d

    def openDirectory(self, fullpath):
        self.log_command('openDirectory', fullpath)
        directory = SwiftDirectory(self.swiftfilesystem, fullpath)

        def cb(*result):
            return directory

        def errback(failure):
            failure.trap(NotFound)
            raise SFTPError(FX_FAILURE, 'Not Found')

        d = directory.get_full_listing()
        d.addCallback(cb)
        d.addErrback(errback)
        return d

    def getAttrs(self, fullpath, followLinks=False):
        self.log_command('getAttrs', fullpath)
        d = self.swiftfilesystem.getAttrs(fullpath)

        def cb(result):
            return self.format_attrs(result)

        def errback(failure):
            failure.trap(NotFound)
            raise SFTPError(FX_NO_SUCH_FILE, 'Not Found')

        d.addCallback(cb)
        d.addErrback(errback)

        return d

    def format_attrs(self, result):
        s = swift_stat(**result)
        return {
            "size": s.st_size,
            "uid": s.st_uid,
            "gid": s.st_gid,
            "permissions": s.st_mode,
            "atime": int(s.st_atime),
            "mtime": int(s.st_mtime)
        }

    def setAttrs(self, path, attrs):
        return

    def readLink(self, path):
        raise NotImplementedError

    def makeLink(self, linkPath, targetPath):
        raise NotImplementedError

    def realPath(self, path):
        container, obj = obj_to_path(path)
        real_path = '/'
        if container:
            real_path += container
        if obj:
            real_path += '/' + obj
        return real_path

    def extendedRequest(self, extName, extData):
        raise NotImplementedError

components.registerAdapter(
    SFTPServerForSwiftConchUser, SwiftSFTPAvatar, ISFTPServer)
components.registerAdapter(SwiftSession, SwiftSFTPAvatar, ISession)
