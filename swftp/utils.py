"""
See COPYING for license information.
"""
import time
import signal

import twisted.internet.tcp
from twisted.python import log
from twisted.internet import reactor
try:
    from collections import OrderedDict
except ImportError:
    from ordereddict import OrderedDict  # NOQA

VERSION = '1.0.4'
USER_AGENT = 'SwFTP v%s' % VERSION

DATE_FORMATS = [
    "%a, %d %b %Y %H:%M:%S %Z",
    "%a, %d %b %Y %H:%M:%S.%f %Z",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M:%S.%f",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M:%S.%f",
    "%Y-%m-%d"
]


def try_datetime_parse(datetime_str):
    """
    Tries to parse the datetime and return the UNIX epoch version of the time.

    returns timestamp(float) or None
    """
    mtime = None
    if datetime_str:
        for format in DATE_FORMATS:
            try:
                mtime_tuple = time.strptime(datetime_str, format)
                mtime = time.mktime(tuple(mtime_tuple))
            except ValueError:
                pass
            else:
                break
    return mtime


def print_runtime_info(sig, frame):
    if sig in [signal.SIGUSR1, signal.SIGUSR2]:
        delayed = reactor.getDelayedCalls()
        readers = reactor.getReaders()
        writers = reactor.getWriters()
        clients = []
        http_conn_num = 0
        for reader in readers:
            if isinstance(reader, twisted.internet.tcp.Server):
                clients.append(reader.getPeer())
            if isinstance(reader, twisted.internet.tcp.Client):
                http_conn_num += 1
        log.msg("[Clients: %(client_num)s] [HTTP Conns: %(http_conn_num)s] "
                "[Readers: %(reader_num)s] [Writers: %(writer_num)s] "
                "[DelayedCalls: %(delayed_num)s]" % {
                    "client_num": len(clients),
                    "http_conn_num": http_conn_num,
                    "reader_num": len(readers),
                    "writer_num": len(writers),
                    "delayed_num": len(delayed),
                })
        log.msg("[Connected Clients]: %s" % clients)
        if sig == signal.SIGUSR2:
            for d in delayed:
                log.msg("SIGUSR2[delayed]: %s" % d)

            for r in readers:
                log.msg("SIGUSR2[reader]: %s" % r)

            for w in writers:
                log.msg("SIGUSR2[writer]: %s" % w)
