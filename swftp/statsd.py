from collections import defaultdict

from twisted.internet import reactor, tcp
from twisted.python import log
from txstatsd.client import TwistedStatsDClient, StatsDClientProtocol  # NOQA
from txstatsd.metrics.metrics import Metrics
from txstatsd.process import PROCESS_STATS, NET_STATS, COUNTER_STATS
from txstatsd.report import ReportingService


def makeService(host='127.0.0.1', port=8125, sample_rate=1.0, prefix=''):
    client = TwistedStatsDClient(host, port)
    metrics = Metrics(connection=client, namespace=prefix)
    reporting = ReportingService()

    for report in PROCESS_STATS:
        reporting.schedule(report, sample_rate, metrics.increment)

    for report in NET_STATS:
        reporting.schedule(report, sample_rate, metrics.increment)

    for report in COUNTER_STATS:
        reporting.schedule(report, sample_rate, metrics.increment)

    # Attach statsd log observer
    metric_collector = StatsdMetricCollector()
    reporting.schedule(
        metric_collector.report_events, sample_rate, metrics.meter)
    reporting.schedule(
        metric_collector.report_stats, sample_rate, metrics.increment)
    log.addObserver(metric_collector.emit)

    protocol = StatsDClientProtocol(client)
    reactor.listenUDP(0, protocol)
    return reporting


class StatsdMetricCollector(object):
    def __init__(self):
        self.metrics = defaultdict(int)

    def emit(self, eventDict):
        if 'metric' in eventDict:
            self.metrics[eventDict['metric']] += eventDict.get('count', 1)

    def reset_metrics(self):
        self.metrics = defaultdict(int)

    def report_events(self):
        result = self.metrics
        self.reset_metrics()
        return result

    def report_stats(self):
        num_clients = len(
            [r for r in reactor.getReaders() if isinstance(r, tcp.Server)])
        return {
            'clients': num_clients,
        }
