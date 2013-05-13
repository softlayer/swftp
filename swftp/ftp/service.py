"""
This file defines what is required for swftp-ftp to work with twistd.

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

CONFIG_DEFAULTS = {
    'auth_url': 'http://127.0.0.1:8080/auth/v1.0',
    'host': '0.0.0.0',
    'port': '5021',
    'num_persistent_connections': '100',
    'num_connections_per_session': '10',
    'connection_timeout': '240',
    'extra_headers': '',
    'verbose': 'false',
    'welcome_message': 'Welcome to SwFTP'
                       ' - an FTP interface for Openstack Swift',
    'log_statsd_host': '',
    'log_statsd_port': '8125',
    'log_statsd_sample_rate': '10.0',
    'log_statsd_metric_prefix': 'swftp.ftp',

    'stats_host': '',
    'stats_port': '38021',
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
    c.add_section('ftp')
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
            c.set('ftp', k, str(v))
    return c


class Options(usage.Options):
    "Defines Command-line options for the swftp-ftp service"
    optFlags = [
        ["verbose", "v", "Make the server more talkative"]
    ]
    optParameters = [
        ["config_file", "c", None, "Location of the swftp config file."],
        ["auth_url", "a", None,
            "Auth Url to use. Defaults to the config file value if it exists. "
            "[default: http://127.0.0.1:8080/auth/v1.0]"],
        ["port", "p", None, "Port to bind to."],
        ["host", "h", None, "IP to bind to."],
    ]


def makeService(options):
    """
    Makes a new swftp-ftp service. The only option is the config file
    location. See CONFIG_DEFAULTS for list of configuration options.
    """
    from twisted.protocols.ftp import FTPFactory
    from twisted.cred.portal import Portal

    from swftp.ftp.server import SwiftFTPRealm
    from swftp.auth import SwiftBasedAuthDB
    from swftp.utils import (
        log_runtime_info, GLOBAL_METRICS, parse_key_value_config)

    print('Starting SwFTP-ftp %s' % VERSION)

    c = get_config(options['config_file'], options)
    ftp_service = service.MultiService()

    # Add statsd service
    if c.get('ftp', 'log_statsd_host'):
        try:
            from swftp.statsd import makeService as makeStatsdService
            makeStatsdService(
                c.get('ftp', 'log_statsd_host'),
                c.getint('ftp', 'log_statsd_port'),
                sample_rate=c.getfloat('ftp', 'log_statsd_sample_rate'),
                prefix=c.get('ftp', 'log_statsd_metric_prefix')
            ).setServiceParent(ftp_service)
        except ImportError:
            sys.stderr.write('Missing Statsd Module. Requires "txstatsd" \n')

    if c.get('ftp', 'stats_host'):
        from swftp.report import makeService as makeReportService
        known_fields = [
            'command.login',
            'command.logout',
            'command.makeDirectory',
            'command.removeDirectory',
            'command.removeFile',
            'command.rename',
            'command.access',
            'command.stat',
            'command.list',
            'command.openForReading',
            'command.openForWriting',
        ] + GLOBAL_METRICS
        makeReportService(
            c.get('sftp', 'stats_host'),
            c.getint('sftp', 'stats_port'),
            known_fields=known_fields
        ).setServiceParent(ftp_service)

    authdb = SwiftBasedAuthDB(
        c.get('ftp', 'auth_url'),
        global_max_concurrency=c.getint('ftp', 'num_persistent_connections'),
        max_concurrency=c.getint('ftp', 'num_connections_per_session'),
        timeout=c.getint('ftp', 'connection_timeout'),
        extra_headers=parse_key_value_config(c.get('ftp', 'extra_headers')),
        verbose=c.getboolean('ftp', 'verbose'))

    ftpportal = Portal(SwiftFTPRealm())
    ftpportal.registerChecker(authdb)
    ftpfactory = FTPFactory(ftpportal)
    ftpfactory.welcomeMessage = c.get('ftp', 'welcome_message')
    ftpfactory.allowAnonymous = False

    signal.signal(signal.SIGUSR1, log_runtime_info)
    signal.signal(signal.SIGUSR2, log_runtime_info)

    internet.TCPServer(
        c.getint('ftp', 'port'),
        ftpfactory,
        interface=c.get('ftp', 'host')).setServiceParent(ftp_service)
    return ftp_service
