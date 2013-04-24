"""
Deals with file upload and download. This streams to and from the OpenStack
Swift server.

See COPYING for license information.
"""
from zope import interface

from twisted.internet import defer, task, reactor
from twisted.conch.ssh.filetransfer import (
    FXF_CREAT, FXF_TRUNC, SFTPError, FX_NO_SUCH_FILE, FX_FAILURE,
    FX_CONNECTION_LOST)
from twisted.conch.interfaces import ISFTPFile
from twisted.internet.protocol import Protocol
from twisted.internet.interfaces import IPushProducer
from twisted.internet.error import ConnectionLost
from twisted.python import log

from swftp.swift import NotFound


def cb_log_egress_bytes(result):
    if result:
        log.msg(metric='transfer.egress_bytes', count=len(result))
    return result


class SwiftFileReceiver(Protocol):
    "Streams data from Swift user to SFTP session"
    download_buffer_limit = 1024 * 1024
    upload_buffer_limit = 1024 * 1024

    def __init__(self, size, session):
        self.size = size
        self.session = session
        self.finished = defer.Deferred()
        self.done = False
        self.consume_paused = False

        self._offset = 0
        self._recv_buffer = ""
        self._recv_listeners = []
        self.transport = None

    def dataReceived(self, bytes):
        """
            Data has been received from Swift. Pauses Swift if the
            download_buffer_limit has been reached.
        """
        self._recv_buffer += bytes
        self._readloop()
        if len(self._recv_buffer) > self.download_buffer_limit:
            self.consume_paused = True
            self.transport.pauseProducing()

    def _checksessionbuffertimer(self):
        """
            Checks session buffer to see if we need to resume.
            Reschedules itself if the buffer is still not small enough
        """
        if not self.consume_paused:
            return
        if len(self.session.buf) <= self.upload_buffer_limit:
            self.consume_paused = False
            self.transport.resumeProducing()
        else:
            reactor.callLater(0, self._checksessionbuffertimer)

    def _checksessionbuffer(self):
        "Checks buffer size to see if we need to pause"
        if not self.transport:
            return
        if self.consume_paused:
            return
        if len(self.session.buf) > self.upload_buffer_limit:
            self.consume_paused = True
            self.transport.pauseProducing()
            reactor.callLater(0, self._checksessionbuffertimer)

    def _readloop(self):
        """
            The loop that checks to see if there is enough data to give back to
            the SFTP client.
        """
        self._checksessionbuffer()
        for callback in self._recv_listeners:
            d, offset, length = callback
            if len(self._recv_buffer) >= length:
                data = self._recv_buffer[:length]
                d.callback(data)
                self._recv_listeners.remove(callback)
                self._offset += len(data)
                self._recv_buffer = self._recv_buffer[length:]

                if self.consume_paused and \
                        len(self._recv_buffer) <= self.download_buffer_limit:
                    self.consume_paused = False
                    self.transport.resumeProducing()
            else:
                break

    def read(self, offset, length):
        """
            Register the fact that this session wants a slice of data
            described by the given offset/length. Returns a deferred that fires
            with the data once it is available.
        """
        if offset + length > self.size:
            length = self.size - offset

        def cb(result):
            if result is None:
                raise EOFError("EOF")
            return result

        # It looks like the SFTP client is asking for too much.
        if self.done and len(self._recv_buffer) == 0:
            raise EOFError("EOF")

        d = defer.Deferred()
        d.addCallback(cb)
        self._recv_listeners.append((d, offset, length))
        self._readloop()
        return d

    def connectionLost(self, reason):
        """
            For some reason, the HTTP connection has been lost. We can either
            be done reading from Swift or something back could have happened.
        """
        from twisted.web._newclient import ResponseDone
        from twisted.web.http import PotentialDataLoss

        self.done = True

        if reason.check(ResponseDone) or reason.check(PotentialDataLoss):
            self._readloop()
            for callback in self._recv_listeners:
                d, offset, length = callback
                d.errback(reason)
            self._recv_listeners = []
            self.finished.callback(None)
        else:
            for callback in self._recv_listeners:
                d, offset, length = callback
                d.errback(reason)
            self._recv_listeners = []
            self.finished.errback(reason)


class SwiftFileSender(object):
    "Streams data from SFTP user to Swift"
    interface.implements(IPushProducer)
    max_buffer_writes = 20
    buffer_writes_resume = 5

    def __init__(self, swiftfilesystem, fullpath, session):
        self.swiftfilesystem = swiftfilesystem
        self.fullpath = fullpath
        self.session = session

        self.write_finished = None  # Deferred that fires when finished writing
        self._task = None           # Task loop
        self._done_sending = False  # Set to True when the user closes the file
        self._writeBuffer = []

        self.paused = False
        self.started = False

    def pauseProducing(self):
        self._task.pause()

    def resumeProducing(self):
        self._task.resume()

    def stopProducing(self):
        if self._task:
            try:
                self._task.stop()
            except task.TaskStopped:
                pass

        for buf in self._writeBuffer:
            d, data = buf
            d.errback(SFTPError(FX_CONNECTION_LOST, 'Connection Lost'))
            self._writeBuffer.remove(buf)
        self._writeBuffer = []

    def _writeFlusher(self, writer):
        while True:
            if self._done_sending and len(self._writeBuffer) == 0:
                writer.unregisterProducer()
                break

            if len(self._writeBuffer) == 0:
                yield
                continue

            try:
                d, data = self._writeBuffer.pop(0)
                writer.write(data)
                d.callback(len(data))
                self._checkBuffer()
                yield
            except IndexError:
                pass
            finally:
                yield

    def _checkBuffer(self):
        if self.paused and len(self._writeBuffer) < self.buffer_writes_resume:
            self.session.conn.transport.transport.resumeProducing()
            self.paused = False
        elif not self.paused \
                and len(self._writeBuffer) > self.max_buffer_writes:
            self.session.conn.transport.transport.pauseProducing()
            self.paused = True

    def cb_start_task(self, writer):
        self._task = task.cooperate(self._writeFlusher(writer))

    def close(self):
        self._done_sending = True
        return self.write_finished

    def write(self, data):
        if not self.started:
            # If we haven't started uploading to Swift, start up that process
            self.write_finished, writer = \
                self.swiftfilesystem.startFileUpload(self.fullpath)
            writer.registerProducer(self, streaming=True)
            writer.started.addCallback(self.cb_start_task)
            self.started = True
        d = defer.Deferred()
        self._writeBuffer.append((d, data))
        self._checkBuffer()
        return d


class SwiftFile(object):
    "Acts as an open file for the SFTP Server instance"
    interface.implements(ISFTPFile)

    def __init__(self, server, fullpath, flags=None, attrs=None):
        self.server = server
        self.swiftfilesystem = server.swiftfilesystem
        self.fullpath = fullpath
        self.flags = flags
        self.attrs = attrs
        self.r = None
        self.w = None
        self.props = None
        self.session = None  # Set later

    def checkExistance(self):
        """
            Checks whether or not the file exists. If the file flags specify,
            it will create the file and return a deffered with that has been
            completed.
        """
        d = self.swiftfilesystem.checkFileExistance(self.fullpath)

        def cb(props):
            self.props = props

        def errback(failure):
            failure.trap(NotFound)
            if self.flags & FXF_CREAT == FXF_CREAT:
                return self.swiftfilesystem.touchFile(self.fullpath)
            if self.flags & FXF_TRUNC == FXF_TRUNC:
                return self.swiftfilesystem.touchFile(self.fullpath)
            else:
                raise SFTPError(FX_NO_SUCH_FILE, 'File Not Found')

        d.addCallback(cb)
        d.addErrback(errback)
        return d

    # New Writer Methods
    def close(self):
        " Returns a deferred that fires when the connection is closed "
        if self.w:
            d = defer.maybeDeferred(self.w.close)
            d.addErrback(self._errClose)
            return d
        del self.session

    def _errClose(self, failure):
        failure.trap(ConnectionLost, NotFound)
        if failure.check(ConnectionLost):
            raise SFTPError(FX_CONNECTION_LOST, "Connection Lost")
        elif failure.check(NotFound):
            raise SFTPError(FX_FAILURE, "Container Doesn't Exist")

    def writeChunk(self, offset, data):
        if not self.w:
            self.w = SwiftFileSender(
                self.swiftfilesystem, self.fullpath, self.session)

        d = self.w.write(data)

        def errback(failure):
            raise SFTPError(FX_FAILURE, 'Upload Failure')
        d.addErrback(errback)

        def cb(result):
            return result
        d.addCallback(cb)
        return d

    # Reading Methods
    def readChunk(self, offset, length):
        if not self.r:
            self.r = SwiftFileReceiver(int(self.props['size']), self.session)
            self.swiftfilesystem.startFileDownload(
                self.fullpath, self.r, offset=offset)
        d = self.r.read(offset, length)
        d.addCallback(cb_log_egress_bytes)
        return d

    def getAttrs(self):
        return self.server.getAttrs(self.fullpath)

    def setAttrs(self, attrs):
        raise NotImplementedError
