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
        reporting.schedule(report, sample_rate, metrics.gauge)

    for report in NET_STATS:
        reporting.schedule(report, sample_rate, metrics.gauge)

    for report in COUNTER_STATS:
        reporting.schedule(report, sample_rate, metrics.gauge)

    # Attach statsd log observer
    metric_collector = StatsdMetricCollector(metrics)
    reporting.schedule(metric_collector.report_metrics, sample_rate, None)
    log.addObserver(metric_collector.emit)

    protocol = StatsDClientProtocol(client)
    reactor.listenUDP(0, protocol)
    return reporting


class StatsdMetricCollector(object):
    def __init__(self, metric):
        self.metric = metric
        self.metrics = defaultdict(int)

    def emit(self, eventDict):
        if 'metric' in eventDict:
            self.metrics[eventDict['metric']] += eventDict.get('count', 1)

    def reset_metrics(self):
        self.metrics = defaultdict(int)

    def report_metrics(self):
        # Report collected metrics
        results = self.metrics
        self.reset_metrics()
        for name, value in results.items():
            self.metric.increment(name, value)

        # Generate/send Aux stats
        num_clients = len(
            [r for r in reactor.getReaders() if isinstance(r, tcp.Server)])
        self.metric.gauge('clients', num_clients)
