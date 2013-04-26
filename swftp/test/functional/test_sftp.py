"""
See COPYING for license information.
"""
from twisted.trial import unittest
from twisted.internet import defer, reactor
from twisted.web.client import HTTPConnectionPool
import paramiko

import tempfile
import shutil

from . import get_config, has_item, create_test_file, clean_swift, \
    compute_md5, upload_file, utf8_chars, get_swift_client

from stat import S_ISDIR
import os
import time

CONFIG = get_config()


class SFTPFuncTest(unittest.TestCase):
    @defer.inlineCallbacks
    def setUp(self):
        self.pool = HTTPConnectionPool(reactor, persistent=True)
        self.swift = get_swift_client(CONFIG, pool=self.pool)
        self.tmpdir = tempfile.mkdtemp()
        self.sftp = get_sftp_client(CONFIG)
        yield clean_swift(self.swift)

    @defer.inlineCallbacks
    def tearDown(self):
        shutil.rmtree(self.tmpdir)
        self.sftp.close()
        yield clean_swift(self.swift)
        yield self.pool.closeCachedConnections()


def get_sftp_client(config):
    for key in 'sftp_host sftp_port account username password'.split():
        if key not in config:
            raise unittest.SkipTest("%s not set in the test config file" % key)
    hostname = config['sftp_host']
    port = int(config['sftp_port'])
    username = "%s:%s" % (config['account'], config['username'])
    password = config['password']

    t = paramiko.Transport((hostname, port))
    t.connect(username=username, password=password)
    return paramiko.SFTPClient.from_transport(t)


class BasicTests(unittest.TestCase):
    def test_get_client(self):
        sftp = get_sftp_client(CONFIG)
        sftp.stat('/')
        sftp.close()


class ClientTests(unittest.TestCase):
    def test_get_many_client(self):
        for i in range(32):
            sftp = get_sftp_client(CONFIG)
            sftp.close()

    def test_get_many_concurrent(self):
        connections = []
        for i in range(32):
            sftp = get_sftp_client(CONFIG)
            connections.append(sftp)
        time.sleep(10)
        for sftp in connections:
            sftp.close()


class RenameTests(SFTPFuncTest):
    def test_rename_account(self):
        self.assertRaises(IOError, self.sftp.rename, '/', '/a')

    @defer.inlineCallbacks
    def test_rename_container(self):
        yield self.swift.put_container('sftp_tests')

        self.sftp.rename('sftp_tests', 'sftp_tests_2')
        r, listing = yield self.swift.get_account()

        self.assertTrue(has_item('sftp_tests_2', listing))
        self.assertFalse(has_item('sftp_tests', listing))

    @defer.inlineCallbacks
    def test_rename_container_populated(self):
        yield self.swift.put_container('sftp_tests')
        yield self.swift.put_object('sftp_tests', 'a')

        self.assertRaises(IOError, self.sftp.rename, 'sftp_tests',
                          'sftp_tests_2')

    @defer.inlineCallbacks
    def test_rename_object(self):
        yield self.swift.put_container('sftp_tests')
        yield self.swift.put_object('sftp_tests', 'a')
        yield self.swift.put_object(
            'sftp_tests', 'b',
            headers={'Content-Type': 'application/directory'})
        yield self.swift.put_object('sftp_tests', 'b/nested')
        yield self.swift.put_object('sftp_tests', 'c/nested')

        self.sftp.rename('sftp_tests/a', 'sftp_tests/a1')

        r, listing = yield self.swift.get_container('sftp_tests')

        self.assertTrue(has_item('a1', listing))
        self.assertFalse(has_item('a', listing))

        self.assertRaises(IOError, self.sftp.rename, 'sftp_tests/b',
                          'sftp_tests/b1')
        self.assertRaises(IOError, self.sftp.rename, 'sftp_tests/c',
                          'sftp_tests/c1')

    def test_rename_object_not_found(self):
        self.assertRaises(IOError, self.sftp.rename, 'sftp_tests/a',
                          'sftp_tests/b')


class DownloadTests(SFTPFuncTest):
    timeout = 240

    @defer.inlineCallbacks
    def _test_download(self, size, name):
        yield self.swift.put_container('sftp_tests')
        src_path, md5 = create_test_file(self.tmpdir, size)
        yield upload_file(self.swift, 'sftp_tests', name, src_path, md5)

        dlpath = '%s/%s_dl' % (self.tmpdir, name)
        self.sftp.get('sftp_tests/%s' % name, dlpath)

        self.assertEqual(os.stat(dlpath).st_size, size)
        self.assertEqual(md5, compute_md5(dlpath))

    def test_zero_byte_file(self):
        return self._test_download(0, '0b.dat')

    def test_32kb_file(self):
        return self._test_download(32 * 1024 + 1, '32kb.dat')

    def test_1mb_file(self):
        return self._test_download(1024 * 1024, '1mb.dat')

    def test_10mb_file(self):
        return self._test_download(1024 * 1024 * 10, '10mb.dat')


class UploadTests(SFTPFuncTest):
    timeout = 240

    @defer.inlineCallbacks
    def _test_upload(self, size, name):
        yield self.swift.put_container('sftp_tests')
        src_path, md5 = create_test_file(self.tmpdir, size)

        self.sftp.put(src_path, 'sftp_tests/%s' % name, confirm=False)

        headers = yield self.swift.head_object('sftp_tests', name)
        self.assertEqual(md5, headers['etag'])
        self.assertEqual(size, int(headers['content-length']))

    def test_zero_byte_file(self):
        return self._test_upload(0, '0b.dat')

    def test_32kb_file(self):
        return self._test_upload(1024 * 32 + 1, '32kb.dat')

    def test_1mb_file(self):
        return self._test_upload(1024 * 1024, '1mb.dat')

    def test_10mb_file(self):
        return self._test_upload(1024 * 1024 * 10, '10mb.dat')


class StatTests(SFTPFuncTest):
    def test_stat_root(self):
        stat = self.sftp.stat('/')
        self.assertTrue(S_ISDIR(stat.st_mode))

    @defer.inlineCallbacks
    def test_container_stat(self):
        yield self.swift.put_container('sftp_tests')
        stat = self.sftp.stat('sftp_tests')
        self.assertTrue(S_ISDIR(stat.st_mode))
        self.assertEqual(stat.st_size, 0)

    @defer.inlineCallbacks
    def test_dir_stat(self):
        yield self.swift.put_container('sftp_tests')
        yield self.swift.put_object('sftp_tests', utf8_chars.encode('utf-8'))
        stat = self.sftp.stat('sftp_tests')
        self.assertTrue(S_ISDIR(stat.st_mode))
        self.assertEqual(stat.st_size, 0)

    @defer.inlineCallbacks
    def test_dir_dir_stat(self):
        yield self.swift.put_container('sftp_tests')
        yield self.swift.put_object(
            'sftp_tests',
            '%s/%s' % (utf8_chars.encode('utf-8'), utf8_chars.encode('utf-8')))
        stat = self.sftp.stat('sftp_tests/%s' % utf8_chars)
        self.assertTrue(S_ISDIR(stat.st_mode))
        self.assertEqual(stat.st_size, 0)

    def test_stat_container_not_found(self):
        self.assertRaises(IOError, self.sftp.stat, 'sftp_tests')

    def test_stat_object_not_found(self):
        self.assertRaises(IOError, self.sftp.stat, 'sftp_tests/not/existing')


class DeleteTests(SFTPFuncTest):
    @defer.inlineCallbacks
    def test_delete_populated_container(self):
        yield self.swift.put_container('sftp_tests')
        yield self.swift.put_object(
            'sftp_tests', 'dir1',
            headers={'Content-Type': 'application/directory'})
        self.assertRaises(IOError, self.sftp.rmdir, 'sftp_tests')

    @defer.inlineCallbacks
    def test_delete_populated_dir(self):
        yield self.swift.put_container('sftp_tests')
        yield self.swift.put_object(
            'sftp_tests', 'dir1',
            headers={'Content-Type': 'application/directory'})
        yield self.swift.put_object('sftp_tests', 'dir1/obj2')
        self.sftp.rmdir('sftp_tests/dir1')

    @defer.inlineCallbacks
    def test_delete_populated_dir_not_existing(self):
        yield self.swift.put_container('sftp_tests')
        yield self.swift.put_object('sftp_tests', 'dir1/obj2')
        self.sftp.rmdir('sftp_tests/dir1')


class ListingTests(SFTPFuncTest):
    timeout = 360

    def test_listing(self):
        listing = self.sftp.listdir()
        self.assertNotIn('sftp_tests', listing)

    @defer.inlineCallbacks
    def test_listing_exists(self):
        yield self.swift.put_container('sftp_tests')
        listing = self.sftp.listdir()
        self.assertIn('sftp_tests', listing)

    @defer.inlineCallbacks
    def test_directory_listing(self):
        yield self.swift.put_container('sftp_tests')
        yield self.swift.put_object(
            'sftp_tests', 'dir1',
            headers={'Content-Type': 'application/directory'})
        yield self.swift.put_object(
            'sftp_tests', 'dir2',
            headers={'Content-Type': 'application/directory'})
        yield self.swift.put_object('sftp_tests', 'dir2/obj1')
        yield self.swift.put_object('sftp_tests', 'dir3/obj2')

        listing = self.sftp.listdir('sftp_tests')
        self.assertIn('dir1', listing)
        self.assertIn('dir2', listing)
        self.assertIn('dir3', listing)
        self.assertEqual(3, len(listing))

        listing = self.sftp.listdir('sftp_tests/dir1')
        self.assertEqual(0, len(listing))

        listing = self.sftp.listdir('sftp_tests/dir2')
        self.assertIn('obj1', listing)
        self.assertEqual(1, len(listing))

        listing = self.sftp.listdir('sftp_tests/dir3')
        self.assertIn('obj2', listing)
        self.assertEqual(1, len(listing))

    @defer.inlineCallbacks
    def test_long_listing(self):
        yield self.swift.put_container('sftp_tests')
        for i in range(10):
            yield self.swift.put_object(
                'sftp_tests', str(i),
                headers={'Content-Type': 'application/directory'})
        time.sleep(2)
        listing = self.sftp.listdir('sftp_tests')
        self.assertEqual(10, len(listing))


class MkdirTests(SFTPFuncTest):

    @defer.inlineCallbacks
    def test_make_container(self):
        self.sftp.mkdir('sftp_tests')
        yield self.swift.head_container('sftp_tests')

    @defer.inlineCallbacks
    def test_make_object_dir(self):
        yield self.swift.put_container('sftp_tests')
        self.sftp.mkdir('sftp_tests/mkdir')
        yield self.swift.head_object('sftp_tests', 'mkdir')

    @defer.inlineCallbacks
    def test_make_nested_object_dir(self):
        yield self.swift.put_container('sftp_tests')
        self.sftp.mkdir('sftp_tests/nested/mkdir')
        yield self.swift.head_object('sftp_tests', 'nested/mkdir')


class RmdirTests(SFTPFuncTest):

    @defer.inlineCallbacks
    def test_rmdir_container(self):
        yield self.swift.put_container('sftp_tests')
        self.sftp.rmdir('sftp_tests/nested/mkdir')
        resp, listing = yield self.swift.get_account('sftp_tests')
        self.assertNotIn('sftp_tests', listing)

    @defer.inlineCallbacks
    def test_rmdir_container_populated(self):
        yield self.swift.put_container('sftp_tests')
        yield self.swift.put_object('sftp_tests', utf8_chars.encode('utf-8'))
        self.assertRaises(IOError, self.sftp.rmdir, 'sftp_tests')

    @defer.inlineCallbacks
    def test_rmdir_object_dir(self):
        yield self.swift.put_container('sftp_tests')
        yield self.swift.put_object('sftp_tests', 'nested/dir')
        self.sftp.rmdir('sftp_tests/nested/dir')
        resp, listing = yield self.swift.get_container('sftp_tests')
        self.assertEqual(len(listing), 0)

    @defer.inlineCallbacks
    def test_rmdir_nested_object_dir(self):
        yield self.swift.put_container('sftp_tests')
        self.sftp.rmdir('sftp_tests/nested/mkdir')
        resp, listing = yield self.swift.get_container('sftp_tests')
        self.assertEqual(len(listing), 0)


class RemoveTests(SFTPFuncTest):

    @defer.inlineCallbacks
    def test_remove_file(self):
        yield self.swift.put_container('sftp_tests')
        yield self.swift.put_object('sftp_tests', utf8_chars.encode('utf-8'))
        self.sftp.remove('sftp_tests/%s' % utf8_chars.encode('utf-8'))
        resp, listing = yield self.swift.get_container('sftp_tests')
        self.assertEqual(len(listing), 0)

    @defer.inlineCallbacks
    def test_remove_container(self):
        yield self.swift.put_container('sftp_tests')
        self.assertRaises(IOError, self.sftp.remove, 'sftp_tests')
