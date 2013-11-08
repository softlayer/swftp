"""
See COPYING for license information.
"""
from collections import defaultdict
import time

from twisted.python import log
from twisted.internet import reactor, tcp
try:
    from collections import OrderedDict
except ImportError:
    from ordereddict import OrderedDict  # NOQA

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
    'num_clients',
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
        for date_format in DATE_FORMATS:
            try:
                mtime_tuple = time.strptime(datetime_str, date_format)
                mtime = time.mktime(tuple(mtime_tuple))
            except ValueError:
                pass
            else:
                break
    return mtime


def parse_key_value_config(config_value):
    """ Parses out key-value pairs from a string that has the following format:
        key: value, key2: value, key3: value

        :param string config_value: a string to parse key-value pairs from

        :returns dict:
    """
    if not config_value:
        return {}

    key_values_unparsed = config_value.split(',')
    key_values = {}
    for key_value_pair in key_values_unparsed:
        key, value = key_value_pair.strip().split(':')
        key_values[key.strip()] = value.strip()
    return key_values


class MetricCollector(object):
    """ Collects metrics using Twisted Logging

    :param int sample_size: how many samples to save. This is useful for
                            rolling aggregates.

    Example:
        >>> h = MetricCollector()
        >>> h.start()
        >>> h.totals
        {}
        >>> log.msg(metric='my_metric')
        >>> h.totals
        {'my_metric1': 1}
        >>> h.samples
        >>> h.sample()
        {'my_metric1': [1]}
        >>> h.sample()
        >>> h.samples
        {'my_metric1': [1, 0]}
        >>> h.stop()

    """
    def __init__(self, sample_size=10):
        self.sample_size = sample_size
        self.current = defaultdict(int)
        self.totals = defaultdict(long)
        self.samples = defaultdict(list)

    def emit(self, eventDict):
        " If there is a metric in the eventDict, collect that metric "
        if 'metric' in eventDict:
            self.add_metric(eventDict['metric'], eventDict.get('count', 1))

    def add_metric(self, metric, count=1):
        " Adds a metric with the given count to the totals/current "
        self.current[metric] += count
        self.totals[metric] += count

    def sample(self):
        " Create a sample of the current metrics "
        keys = list(
            set(self.samples.keys()) | set(self.current.keys()))

        for key in keys:
            self.samples[key].append(self.current[key])
            self.samples[key] = \
                self.samples[key][-self.sample_size - 1:]

        self.current = defaultdict(int)

    def start(self):
        " Start observing log events "
        log.addObserver(self.emit)

    def stop(self):
        " Stop observing log events "
        log.removeObserver(self.emit)


def runtime_info():
    delayed = reactor.getDelayedCalls()
    readers = reactor.getReaders()
    writers = reactor.getWriters()
    servers = []
    clients = []
    other = []
    for reader in readers:
        if isinstance(reader, tcp.Server):
            servers.append({
                'transport': reader,
                'host': reader.getHost(),
                'peer': reader.getPeer()
            })
        elif isinstance(reader, tcp.Client):
            clients.append({
                'transport': reader,
                'host': reader.getHost(),
                'peer': reader.getPeer()
            })
        else:
            other.append(reader)
    return {
        'num_clients': len(clients),
        'num_servers': len(servers),
        'num_other': len(other),
        'num_writers': len(writers),
        'num_delayed': len(delayed),
        'clients': clients,
        'servers': servers,
        'other': other,
        'writers': writers,
        'delayed': delayed,
    }


def log_runtime_info(*args):
    info = runtime_info()
    log.msg("[Servers: %(num_servers)s] [Clients: %(num_clients)s] "
            "[Other: %(other)s] [Writers: %(num_writers)s] "
            "[DelayedCalls: %(num_delayed)s]" % info)

    for c in info['clients']:
        log.msg("[client]: %s" % c)

    for d in info['servers']:
        log.msg("[server]: %s" % d)

    for d in info['other']:
        log.msg("[other]: %s" % d)

    for d in info['delayed']:
        log.msg("[delayed]: %s" % d)

    for w in info['writers']:
        log.msg("[writer]: %s" % w)
