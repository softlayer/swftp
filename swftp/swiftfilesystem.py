"""
This file includes a set of helpers that make treating Swift as a filesystem a
bit easier.

See COPYING for license information.
"""
import datetime
import stat
import os
import urlparse
import time

from twisted.internet import defer, reactor, task
from twisted.web.iweb import IBodyProducer, UNKNOWN_LENGTH
from twisted.internet.interfaces import IConsumer
from twisted.python import log

from zope import interface

from swftp.utils import OrderedDict
from swftp.utils import try_datetime_parse
from swftp.swift import NotFound, Conflict


def obj_to_path(path):
    " Convert an entire path to a (container, item) tuple "
    path = path.strip('/')
    path = urlparse.urljoin('/', path)
    path = path.strip('/')
    path_parts = path.split('/', 1)

    container = None
    if len(path_parts) > 0 and path_parts[0] != '':
        container = path_parts[0]
    item = None
    if len(path_parts) > 1:
        item = path_parts[1]

    return container, item


def cb_parse_account_headers(headers):
    return {
        'count': headers.get('x-account-container-count', 0),
        'size': headers.get('x-account-bytes-used', 0),
        'content_type': 'application/directory',
    }


def cb_parse_container_headers(headers):
    return {
        'count': headers.get('x-container-object-count', 0),
        'size': headers.get('x-container-bytes-used', 0),
        'content_type': 'application/directory',
    }


def cb_parse_object_headers(headers):
    return {
        'size': headers.get('content-length', 0),
        'last_modified': headers.get('last-modified', 0),
        'content_type': headers.get('content-type'),
    }


def swift_stat(last_modified=None, content_type="application/directory",
               count=1, bytes=0, size=0, **kwargs):
    size = int(size) or int(bytes)
    mtime = try_datetime_parse(last_modified)
    if not mtime:
        mtime = time.mktime(datetime.datetime.utcnow().timetuple())

    if content_type == "application/directory":
        mode = 0700 | stat.S_IFDIR
    else:
        mode = 0600 | stat.S_IFREG
    return os.stat_result((mode, 0, 0, count, 65535, 65535, size, mtime,
                           mtime, mtime))


class SwiftWriteFile(object):
    """ Adapts IBodyProducer and IConsumer """
    interface.implements(IBodyProducer, IConsumer)

    def __init__(self, length=None):
        self.length = length or UNKNOWN_LENGTH
        self.started = defer.Deferred()
        self.finished = defer.Deferred()
        self.consumer = None  # is set later
        self.producer = None  # is set later

    # IConsumer
    def registerProducer(self, producer, streaming):
        self.producer = producer
        assert streaming

    def unregisterProducer(self):
        self.finished.callback(None)

    def write(self, data):
        self.consumer.write(data)
        log.msg(metric='transfer.ingress_bytes', count=len(data))

    # IBodyProducer
    def startProducing(self, consumer):
        self.consumer = consumer
        self.started.callback(self)
        return self.finished

    def pauseProducing(self):
        self.producer.pauseProducing()

    def resumeProducing(self):
        self.producer.resumeProducing()

    def stopProducing(self):
        self.producer.stopProducing()


class SwiftFileSystem(object):
    "Defines a common interface used to create Swift similar to a filesystem"
    def __init__(self, swiftconn):
        self.swiftconn = swiftconn

    def startFileUpload(self, fullpath):
        "returns IConsumer to write to object data to"
        container, path = obj_to_path(fullpath)
        consumer = SwiftWriteFile()
        d = self.swiftconn.put_object(container, path, body=consumer)
        return d, consumer

    def startFileDownload(self, fullpath, consumer, offset=0):
        "consumer: Protocol"
        container, path = obj_to_path(fullpath)
        headers = {}
        if offset > 0:
            headers['Range'] = 'bytes=%s-' % offset
        d = self.swiftconn.get_object(container, path, receiver=consumer,
                                      headers=headers)
        return d

    def touchFile(self, fullpath):
        container, path = obj_to_path(fullpath)
        return self.swiftconn.put_object(container, path, body=None)

    def checkFileExistance(self, fullpath):
        container, path = obj_to_path(fullpath)
        if container is None or path is None:
            raise NotImplementedError

        d = self.swiftconn.head_object(container, path)
        d.addCallback(cb_parse_object_headers)
        return d

    def removeFile(self, fullpath):
        container, path = obj_to_path(fullpath)
        if container is None or path is None:
            raise NotImplementedError
        d = self.swiftconn.delete_object(container, path)
        return d

    @defer.inlineCallbacks
    def renameFile(self, oldpath, newpath):
        container, path = obj_to_path(oldpath)
        newcontainer, newpath = obj_to_path(newpath)
        if not container or not newcontainer:
            raise NotImplementedError

        if not path and not newpath:
            # Attempt to 'rename' a container (metadata is lost)
            yield self.swiftconn.delete_container(container)
            yield self.swiftconn.put_container(newcontainer)
            defer.returnValue(None)
        else:
            # If the object doesn't actually exist, ABORT
            path = path or ''
            newpath = newpath or ''
            try:
                yield self.swiftconn.head_object(container, path)
            except NotFound:
                raise NotImplementedError

            # List out children of this path. If there are any, ABORT
            prefix = None
            if path:
                prefix = "%s/" % path
            _, children = yield self.swiftconn.get_container(
                container, prefix=prefix, limit=1)
            if len(children) > 0:
                raise NotImplementedError

            # This is an actual object with no children. Free to rename.
            yield self.swiftconn.put_object(
                newcontainer, newpath,
                headers={'X-Copy-From': '%s/%s' % (container, path)})
            yield self.swiftconn.delete_object(container, path)

    @defer.inlineCallbacks
    def getAttrs(self, fullpath):
        container, path = obj_to_path(fullpath)
        if path:
            try:
                headers = yield self.swiftconn.head_object(container, path)
                defer.returnValue(
                    cb_parse_object_headers(headers))
            except NotFound:
                prefix = None
                if path:
                    prefix = "%s/" % path
                _, children = yield self.swiftconn.get_container(
                    container, prefix=prefix, limit=1)
                if len(children) == 0:
                    raise NotFound(404, 'Not Found')
                defer.returnValue(
                    {'content_type': 'application/directory'})

        elif container:
            headers = yield self.swiftconn.head_container(container)
            defer.returnValue(cb_parse_container_headers(headers))
        else:
            headers = yield self.swiftconn.head_account()
            defer.returnValue(cb_parse_account_headers(headers))

    def makeDirectory(self, fullpath, attrs=None):
        container, path = obj_to_path(fullpath)
        if path:
            headers = {'Content-Type': 'application/directory'}
            d = self.swiftconn.put_object(container, path, headers=headers)
        else:
            d = self.swiftconn.put_container(container)
        return d

    @defer.inlineCallbacks
    def removeDirectory(self, fullpath):
        container, path = obj_to_path(fullpath)
        if path:
            yield self.swiftconn.delete_object(container, path)
        else:
            try:
                yield self.swiftconn.delete_container(container)
            except Conflict:
                # Wait 2 seconds and try to delete the container once more
                yield task.deferLater(
                    reactor, 2, self.swiftconn.delete_container, container)

    def get_full_listing(self, fullpath):
        """
            Return a full listing of objects, collapsed into a directory
            structure. Works for account, container and object prefix listings.


            @returns dict of {name: property} values
        """
        container, path = obj_to_path(fullpath)
        if container:
            return self.get_container_listing(container, path)
        else:
            return self.get_account_listing()

    def get_container_listing(self, container, path, marker=None,
                              all_files=None):
        if all_files is None:
            all_files = OrderedDict()
        prefix = None
        if path:
            prefix = "%s/" % path
        d = self.swiftconn.get_container(
            container, prefix=prefix, delimiter='/', marker=marker)

        def cb(results):
            r, files = results
            next_marker = None
            for f in files:
                if 'subdir' in f:
                    f['name'] = f['subdir']
                    f['content-type'] = 'application/directory'
                f['formatted_name'] = os.path.basename(
                    f['name'].encode("utf-8").rstrip('/'))
                all_files[f['formatted_name']] = f
                next_marker = f['name']
            if len(files) > 0:
                return self.get_container_listing(
                    container, path, marker=next_marker, all_files=all_files)
            return all_files
        d.addCallback(cb)
        return d

    def get_account_listing(self, marker=None, all_files=None):
        if all_files is None:
            all_files = OrderedDict()
        d = self.swiftconn.get_account(marker=marker)

        def cb(results):
            headers, files = results
            next_marker = None
            for f in files:
                f['content-type'] = 'application/directory'
                f['formatted_name'] = f['name'].encode("utf-8")
                all_files[f['formatted_name']] = f
                next_marker = f['name']
            if len(files) > 0:
                return self.get_account_listing(
                    marker=next_marker, all_files=all_files)
            return all_files
        d.addCallback(cb)
        return d
