"""
See COPYING for license information.
"""
import json
from copy import copy

from twisted.internet import task
from twisted.web.server import Site
from twisted.web.resource import Resource
from twisted.web.http_headers import Headers
from twisted.application import internet

from swftp.utils import MetricCollector


class Stats(Resource):
    """ Stats resource

    Routes:
        GET /stats.json

    """
    isLeaf = True

    def __init__(self, metric_collector, known_fields=None):
        self.metric_collector = metric_collector
        self.known_fields = known_fields or []

    def _populate_known_fields(self, d, default=0):
        for field in self.known_fields:
            d[field] = d.get(field, default)

    def get_stats(self):
        totals = copy(self.metric_collector.totals)
        samples = copy(self.metric_collector.samples)
        self._populate_known_fields(totals, 0)
        self._populate_known_fields(samples, [0])
        return {
            'totals': totals,
            'rates': dict(
                (key, sum(value) / len(value)) for (key, value) in
                samples.items()),
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
    metric_collector = MetricCollector()
    metric_collector.start()

    root = Stats(metric_collector, known_fields=known_fields)
    site = Site(root)

    def sample_metrics():
        metric_collector.sample()

    loop = task.LoopingCall(sample_metrics)
    loop.start(1)

    service = internet.TCPServer(
        port,
        site,
        interface=host)
    return service
