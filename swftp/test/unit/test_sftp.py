"""
See COPYING for license information.
"""
import os.path
import socket

from twisted.trial import unittest

from swftp.sftp.service import makeService, Options


TEST_PATH = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))


class SFTPServiceTest(unittest.TestCase):

    def setUp(self):
        opts = Options()
        opts.parseOptions([
            '--config_file=%s' % os.path.join(TEST_PATH, 'test.conf'),
            '--priv_key=%s' % os.path.join(TEST_PATH, 'test_id_rsa'),
            '--pub_key=%s' % os.path.join(TEST_PATH, 'test_id_rsa.pub'),
        ])
        self.service = makeService(opts)
        return self.service.startService()

    def tearDown(self):
        return self.service.stopService()

    def test_service_listen(self):
        sock = socket.socket()
        sock.connect(('127.0.0.1', 6022))
