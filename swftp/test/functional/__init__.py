"""
See COPYING for license information.
"""
import hashlib
import unittest
import os
import uuid
import ConfigParser
import time

from twisted.internet import defer
from twisted.internet.defer import DeferredList
from twisted.web.client import FileBodyProducer
from swftp.swift import SwiftConnection, Conflict
from swftp.swiftfilesystem import SwiftFileSystem

utf8_chars = u'\uF10F\uD20D\uB30B\u9409\u8508\u5605\u3703\u1801'\
             u'\u0900\uF110\uD20E\uB30C\u940A\u8509\u5606\u3704'\
             u'\u1802\u0901\uF111\uD20F\uB30D\u940B\u850A\u5607'\
             u'\u3705\u1803\u0902\uF112\uD210\uB30E\u940C\u850B'\
             u'\u5608\u3706\u1804\u0903\u03A9\u2603'


def get_config():
    config_file = os.environ.get('SWFTP_TEST_CONFIG_FILE',
                                 '/etc/swftp/test.conf')
    section = 'func_test'
    config = ConfigParser.ConfigParser()
    config.read(config_file)

    config_dict = {}
    for option in config.options(section):
        config_dict[option] = config.get(section, option)

    return config_dict

conf = get_config()


def has_item(name, listing):
    return len(filter(lambda h: h['name'] == name, listing)) > 0


def compute_md5(filepath):
    hsh = hashlib.md5()
    with open(filepath, 'rb') as f:
        for chunk in iter(lambda: f.read(128 * hsh.block_size), b''):
            hsh.update(chunk)
    return hsh.hexdigest()


def create_test_file(tmpdir, size):
    hsh = hashlib.md5()
    filepath = os.path.join(tmpdir, uuid.uuid4().hex)
    with open(filepath, 'w+') as f:
        current_size = 0
        chunk_size = 100000
        while current_size < size:
            s = chunk_size
            if current_size + chunk_size > size:
                s = size - current_size
            data = os.urandom(s)
            hsh.update(data)
            f.write(data)
            current_size += s
    return filepath, hsh.hexdigest()


def get_swift_client(config, pool=None):
    for key in 'account username password'.split():
        if key not in config:
            raise unittest.SkipTest("%s not set in the test config file" % key)
    protocol = 'http'
    if config.get('auth_ssl', 'no').lower() in ('yes', 'true', 'on', '1'):
        protocol = 'https'
    host = config.get('auth_host', '127.0.0.1')
    port = config.get('auth_port', '8080')
    auth_prefix = config.get('auth_prefix', '/auth/')
    auth_url = '%s://%s:%s%sv1.0' % (protocol, host, port, auth_prefix)
    username = "%s:%s" % (config['account'], config['username'])
    api_key = config['password']
    return SwiftConnection(auth_url, username, api_key, pool=pool)


def upload_file(swift, container, path, src_path, md5):
    def cb(result):
        resp, body = result
        assert md5 == resp.headers['etag']

    d = swift.put_object(
        container, path, body=FileBodyProducer(open(src_path)))
    d.addCallback(cb)
    return d


@defer.inlineCallbacks
def clean_swift(swift):
    yield swift.authenticate()
    yield remove_test_data(swift, 'sftp_tests')
    yield remove_test_data(swift, 'ftp_tests')


@defer.inlineCallbacks
def remove_test_data(swift, prefix):
    swift_fs = SwiftFileSystem(swift)
    time.sleep(2)
    containers = yield swift_fs.get_account_listing()
    sem = defer.DeferredSemaphore(200)
    for container in containers:
        if container.startswith(prefix):
            while True:
                objs = yield list_all_objects(swift, container)
                dl = []
                for obj in objs:
                    dl.append(sem.run(
                        swift.delete_object, container, obj['name']))
                # Wait till all objects are done deleting
                yield DeferredList(dl, fireOnOneErrback=True)
                try:
                    # Delete the container
                    yield swift.delete_container(container)
                    break
                except Conflict:
                    # Retry listing if there are still objects
                    # (this can happen a lot since the container server isn't
                    # guarenteed to be consistent)
                    pass


@defer.inlineCallbacks
def list_all_objects(swift, container):
    all_objects = []
    next_marker = None

    while True:
        _, files = yield swift.get_container(container, marker=next_marker)
        for f in files:
            all_objects.append(f)
            next_marker = f['name']
        if len(files) == 0:
            break
    defer.returnValue(all_objects)


class RandFile(object):
    def __init__(self, size):
        self.size = size
        self.offset = 0
        self.hash = hashlib.md5()

    def computed_hash(self):
        return self.hash.hexdigest()

    def read(self, length):
        if self.offset + length > self.size:
            length = self.size - self.offset
        data = os.urandom(length)
        self.hash.update(data)
        self.offset += len(length)
        return data
