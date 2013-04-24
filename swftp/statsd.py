from twisted.internet import reactor, tcp
from twisted.python import log
from txstatsd.client import TwistedStatsDClient, StatsDClientProtocol  # NOQA
from txstatsd.metrics.metrics import Metrics
from txstatsd.process import PROCESS_STATS, NET_STATS, COUNTER_STATS
from txstatsd.report import ReportingService

from swftp.utils import MetricCollector


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
    metric_collector = MetricCollector()
    log.addObserver(metric_collector.emit)

    metric_reporter = MetricReporter(metrics, metric_collector)
    reporting.schedule(metric_reporter.report_metrics, sample_rate, None)

    protocol = StatsDClientProtocol(client)
    reactor.listenUDP(0, protocol)
    return reporting


class MetricReporter(object):
    def __init__(self, metric, collector):
        self.metric = metric
        self.collector = collector

    def report_metrics(self):
        # Report collected metrics
        results = self.collector.metric_rates
        self.collector.sample()
        for name, value in results.items():
            self.metric.increment(name, value)

        # Generate/send Aux stats
        num_clients = len(
            [r for r in reactor.getReaders() if isinstance(r, tcp.Server)])
        self.metric.gauge('clients', num_clients)
