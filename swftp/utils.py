"""
See COPYING for license information.
"""
import time
from collections import defaultdict

import twisted.internet.tcp
from twisted.python import log
from twisted.internet import reactor
try:
    from collections import OrderedDict
except ImportError:
    from ordereddict import OrderedDict  # NOQA

VERSION = '1.0.5'
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

GLOBAL_METRICS = [
    'auth.succeed',
    'auth.fail',
    'transfer.egress_bytes',
    'transfer.ingress_bytes',
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


class MetricCollector(object):
    def __init__(self, known_fields=None):
        self.known_fields = known_fields or []
        self.metrics = defaultdict(long)
        self.metric_rates = defaultdict(int)
        self.metric_samples = defaultdict(list)

        for field in self.known_fields:
            self.metrics[field] = 0

        for field in self.known_fields:
            self.metric_rates[field] = 0
        self.sample_size = 10
        self.num_clients = 0

    def emit(self, eventDict):
        if 'metric' in eventDict:
            self.add_metric(eventDict['metric'], eventDict.get('count', 1))
        if 'connect' in eventDict:
            if eventDict['connect']:
                self.num_clients += 1
            else:
                self.num_clients -= 1

    def add_metric(self, metric, count=1):
        self.metric_rates[metric] += count
        self.metrics[metric] += count

    def sample(self):
        keys = list(
            set(self.metric_samples.keys()) | set(self.metric_rates.keys()))

        for key in keys:
            self.metric_samples[key].append(self.metric_rates[key])
            self.metric_samples[key] = \
                self.metric_samples[key][-self.sample_size - 1:]

        self.metric_rates = defaultdict(int)


def runtime_info():
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
    info = {
        'num_clients': len(clients),
        'num_http_conn': http_conn_num,
        'num_readers': len(readers),
        'num_writers': len(writers),
        'num_delayed': len(delayed),
        'clients': clients,
        'readers': readers,
        'writers': writers,
        'delayed': delayed,
    }
    return info


def log_runtime_info(sig, frame):
    info = runtime_info()
    log.msg("[Clients: %(num_clients)s] [HTTP Conns: %(num_http_conn)s] "
            "[Readers: %(num_readers)s] [Writers: %(num_writers)s] "
            "[DelayedCalls: %(num_delayed)s]" % info)

    for c in info['clients']:
        log.msg("[client]: %s" % c)

    for d in info['delayed']:
        log.msg("[delayed]: %s" % d)

    for r in info['readers']:
        log.msg("[reader]: %s" % r)

    for w in info['writers']:
        log.msg("[writer]: %s" % w)
