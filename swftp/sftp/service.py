"""
This file defines what is required for swftp-sftp to work with twistd.

See COPYING for license information.
"""
from swftp import VERSION
from swftp.logging import StdOutObserver
from swftp.sftp.server import SwiftSSHServerTransport

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

    'rewrite_storage_scheme': '',
    'rewrite_storage_netloc': '',

    'priv_key': '/etc/swftp/id_rsa',
    'pub_key': '/etc/swftp/id_rsa.pub',
    'num_persistent_connections': '100',
    'num_connections_per_session': '10',
    'connection_timeout': '240',
    'sessions_per_user': '10',
    'extra_headers': '',
    'verbose': 'false',

    'log_statsd_host': '',
    'log_statsd_port': '8125',
    'log_statsd_sample_rate': '10.0',
    'log_statsd_metric_prefix': 'swftp.sftp',

    'stats_host': '',
    'stats_port': '38022',

    # ordered by performance
    'chiphers': 'blowfish-cbc,aes128-cbc,aes192-cbc,cast128-cbc,aes128-ctr,'
                'aes256-cbc,aes192-ctr,aes256-ctr,3des-cbc',
    'macs': 'hmac-md5, hmac-sha1',
    'compressions': 'none, zlib',
}


def run():
    options = Options()
    try:
        options.parseOptions(sys.argv[1:])
    except usage.UsageError as errortext:
        print '%s: %s' % (sys.argv[0], errortext)
        print '%s: Try --help for usage details.' % (sys.argv[0])
        sys.exit(1)

    # Start Logging
    obs = StdOutObserver()
    obs.start()

    s = makeService(options)
    s.startService()
    reactor.run()


def parse_config_list(conf_name, conf_value, valid_options_list):
    lst, lst_not = [], []
    for ch in conf_value.split(","):
        ch = ch.strip()
        if ch in valid_options_list:
            lst.append(ch)
        else:
            lst_not.append(ch)

    if lst_not:
        log.msg(
            "Unsupported {}: {}".format(conf_name, ", ".join(lst_not)))
    return lst


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

    # Parse Chipher List
    chiphers = parse_config_list('ciphers',
                                 c.get('sftp', 'chiphers'),
                                 SwiftSSHServerTransport.supportedCiphers)
    c.set('sftp', 'chiphers', chiphers)

    # Parse Mac List
    macs = parse_config_list('macs',
                             c.get('sftp', 'macs'),
                             SwiftSSHServerTransport.supportedMACs)
    c.set('sftp', 'macs', macs)

    # Parse Compression List
    compressions = parse_config_list(
        'compressions', c.get('sftp', 'compressions'),
        SwiftSSHServerTransport.supportedCompressions)
    c.set('sftp', 'compressions', compressions)

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
    from twisted.conch.ssh.connection import SSHConnection
    from twisted.conch.ssh.factory import SSHFactory
    from twisted.conch.ssh.keys import Key
    from twisted.cred.portal import Portal

    from swftp.realm import SwftpRealm
    from swftp.sftp.server import SwiftSSHUserAuthServer
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
        verbose=c.getboolean('sftp', 'verbose'),
        rewrite_scheme=c.get('sftp', 'rewrite_storage_scheme'),
        rewrite_netloc=c.get('sftp', 'rewrite_storage_netloc'),
    )

    realm = SwftpRealm()
    sftpportal = Portal(realm)
    sftpportal.registerChecker(authdb)

    sshfactory = SSHFactory()
    protocol = SwiftSSHServerTransport
    protocol.maxConnectionsPerUser = c.getint('sftp', 'sessions_per_user')
    protocol.supportedCiphers = c.get('sftp', 'chiphers')
    protocol.supportedMACs = c.get('sftp', 'macs')
    protocol.supportedCompressions = c.get('sftp', 'compressions')
    sshfactory.protocol = protocol
    sshfactory.noisy = False
    sshfactory.portal = sftpportal
    sshfactory.services['ssh-userauth'] = SwiftSSHUserAuthServer
    sshfactory.services['ssh-connection'] = SSHConnection

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
