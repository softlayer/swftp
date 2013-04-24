import json

from twisted.internet import task
from twisted.python import log
from twisted.web.server import Site
from twisted.web.resource import Resource
from twisted.web.http_headers import Headers
from twisted.application import internet

from swftp.utils import MetricCollector


class Stats(Resource):
    isLeaf = True

    def __init__(self, metric_collector):
        self.current_rates = metric_collector.metrics
        self.metric_collector = metric_collector

    def get_stats(self):
        return {
            'totals': self.metric_collector.metrics,
            'rates': dict(
                (key, sum(value) / len(value)) for (key, value) in
                self.metric_collector.metric_samples.items()),
            'num_clients': self.metric_collector.num_clients,
        }

    def render_GET(self, request):
        if request.path == '/stats.json':
            request.responseHeaders = Headers({
                'Content-Type': ['application/json']})
            return json.dumps(self.get_stats())
        else:
            request.setResponseCode(404)
            return 'not found'


def makeService(host='127.0.0.1', port=8125, known_fields=None):
    # Attach our report log observer
    metric_collector = MetricCollector(known_fields=known_fields)
    log.addObserver(metric_collector.emit)

    root = Stats(metric_collector)
    site = Site(root)

    def reset_metrics():
        metric_collector.sample()

    loop = task.LoopingCall(reset_metrics)
    loop.start(1)

    service = internet.TCPServer(
        port,
        site,
        interface=host)
    return service
