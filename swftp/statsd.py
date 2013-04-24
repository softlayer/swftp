"""
See COPYING for license information.
"""
from twisted.internet import reactor
from txstatsd.client import TwistedStatsDClient, StatsDClientProtocol
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

    # Attach log observer to collect metrics for us
    metric_collector = MetricCollector()
    metric_collector.start()

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
        results = self.collector.current
        for name, value in results.items():
            self.metric.increment(name, value)
        self.collector.sample()
