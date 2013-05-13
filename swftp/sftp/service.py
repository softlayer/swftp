"""
This file defines what is required for swftp-sftp to work with twistd.

See COPYING for license information.
"""
from swftp import VERSION

from twisted.application import internet, service
from twisted.python import usage, log
from twisted.internet import reactor

import ConfigParser
import signal
import os
import sys
import time


CONFIG_DEFAULTS = {
    'auth_url': 'http://127.0.0.1:8080/auth/v1.0',
    'host': '0.0.0.0',
    'port': '5022',
    'priv_key': '/etc/swftp/id_rsa',
    'pub_key': '/etc/swftp/id_rsa.pub',
    'num_persistent_connections': '100',
    'num_connections_per_session': '10',
    'connection_timeout': '240',
    'extra_headers': '',
    'verbose': 'false',

    'log_statsd_host': '',
    'log_statsd_port': '8125',
    'log_statsd_sample_rate': '10.0',
    'log_statsd_metric_prefix': 'swftp.sftp',

    'stats_host': '',
    'stats_port': '38022',
}


def run():
    options = Options()
    try:
        options.parseOptions(sys.argv[1:])
    except usage.UsageError, errortext:
        print '%s: %s' % (sys.argv[0], errortext)
        print '%s: Try --help for usage details.' % (sys.argv[0])
        sys.exit(1)
    log.startLogging(sys.stdout)
    s = makeService(options)
    s.startService()
    reactor.run()


def get_config(config_path, overrides):
    c = ConfigParser.ConfigParser(CONFIG_DEFAULTS)
    c.add_section('sftp')
    if config_path:
        log.msg('Reading configuration from path: %s' % config_path)
        c.read(config_path)
    else:
        config_paths = [
            '/etc/swftp/swftp.conf',
            os.path.expanduser('~/.swftp.cfg')
        ]
        log.msg('Reading configuration from paths: %s' % config_paths)
        c.read(config_paths)
    for k, v in overrides.iteritems():
        if v:
            c.set('sftp', k, str(v))
    return c


class Options(usage.Options):
    "Defines Command-line options for the swftp-sftp service"
    optFlags = [
        ["verbose", "v", "Make the server more talkative"]
    ]
    optParameters = [
        ["config_file", "c", None, "Location of the swftp config file."],
        ["auth_url", "a", None,
            "Auth Url to use. Defaults to the config file value if it exists."
            "[default: http://127.0.0.1:8080/auth/v1.0]"],
        ["port", "p", None, "Port to bind to."],
        ["host", "h", None, "IP to bind to."],
        ["priv_key", "priv-key", None, "Private Key Location."],
        ["pub_key", "pub-key", None, "Public Key Location."],
    ]


def makeService(options):
    """
    Makes a new swftp-sftp service. The only option is the config file
    location. See CONFIG_DEFAULTS for list of configuration options.
    """
    from twisted.conch.ssh.factory import SSHFactory
    from twisted.conch.ssh.keys import Key
    from twisted.cred.portal import Portal

    from swftp.sftp.server import SwiftSFTPRealm, SwiftSSHServerTransport, \
        SwiftSSHConnection
    from swftp.auth import SwiftBasedAuthDB
    from swftp.utils import (
        log_runtime_info, GLOBAL_METRICS, parse_key_value_config)

    c = get_config(options['config_file'], options)

    sftp_service = service.MultiService()

    # ensure timezone is GMT
    os.environ['TZ'] = 'GMT'
    time.tzset()

    print('Starting SwFTP-sftp %s' % VERSION)

    # Add statsd service
    if c.get('sftp', 'log_statsd_host'):
        try:
            from swftp.statsd import makeService as makeStatsdService
            makeStatsdService(
                c.get('sftp', 'log_statsd_host'),
                c.getint('sftp', 'log_statsd_port'),
                sample_rate=c.getfloat('sftp', 'log_statsd_sample_rate'),
                prefix=c.get('sftp', 'log_statsd_metric_prefix')
            ).setServiceParent(sftp_service)
        except ImportError:
            sys.stderr.write('Missing Statsd Module. Requires "txstatsd" \n')

    if c.get('sftp', 'stats_host'):
        from swftp.report import makeService as makeReportService
        known_fields = [
            'command.login',
            'command.logout',
            'command.gotVersion',
            'command.openFile',
            'command.removeFile',
            'command.renameFile',
            'command.makeDirectory',
            'command.removeDirectory',
            'command.openDirectory',
            'command.getAttrs',
        ] + GLOBAL_METRICS
        makeReportService(
            c.get('sftp', 'stats_host'),
            c.getint('sftp', 'stats_port'),
            known_fields=known_fields
        ).setServiceParent(sftp_service)

    authdb = SwiftBasedAuthDB(
        c.get('sftp', 'auth_url'),
        global_max_concurrency=c.getint('sftp', 'num_persistent_connections'),
        max_concurrency=c.getint('sftp', 'num_connections_per_session'),
        timeout=c.getint('sftp', 'connection_timeout'),
        extra_headers=parse_key_value_config(c.get('sftp', 'extra_headers')),
        verbose=c.getboolean('sftp', 'verbose'))

    sftpportal = Portal(SwiftSFTPRealm())
    sftpportal.registerChecker(authdb)

    sshfactory = SSHFactory()
    sshfactory.protocol = SwiftSSHServerTransport
    sshfactory.noisy = False
    sshfactory.portal = sftpportal
    sshfactory.services['ssh-connection'] = SwiftSSHConnection

    pub_key_string = file(c.get('sftp', 'pub_key')).read()
    priv_key_string = file(c.get('sftp', 'priv_key')).read()
    sshfactory.publicKeys = {
        'ssh-rsa': Key.fromString(data=pub_key_string)}
    sshfactory.privateKeys = {
        'ssh-rsa': Key.fromString(data=priv_key_string)}

    signal.signal(signal.SIGUSR1, log_runtime_info)
    signal.signal(signal.SIGUSR2, log_runtime_info)

    internet.TCPServer(
        c.getint('sftp', 'port'),
        sshfactory,
        interface=c.get('sftp', 'host')).setServiceParent(sftp_service)

    return sftp_service
