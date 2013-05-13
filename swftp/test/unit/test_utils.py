"""
See COPYING for license information.
"""
import unittest
import os
import time

from twisted.python import log

from swftp.utils import (
    try_datetime_parse, MetricCollector, parse_key_value_config)


class MetricCollectorTest(unittest.TestCase):
    def setUp(self):
        self.c = MetricCollector()

    def test_init(self):
        c = MetricCollector(10)
        self.assertEqual(c.sample_size, 10)
        self.assertEqual(c.current, {})
        self.assertEqual(c.totals, {})
        self.assertEqual(c.samples, {})

        c = MetricCollector(20)
        self.assertEqual(c.sample_size, 20)

    def test_emit(self):
        self.c.emit({'metric': 'some_metric'})
        self.assertEqual(self.c.current['some_metric'], 1)

        self.c.emit({'metric': 'some_metric', 'count': 10})
        self.assertEqual(self.c.current['some_metric'], 11)

    def test_add_metric(self):
        self.c.add_metric('some_metric')
        self.assertEqual(self.c.current['some_metric'], 1)
        self.assertEqual(self.c.totals['some_metric'], 1)

        self.c.add_metric('some_metric', count=10)
        self.assertEqual(self.c.current['some_metric'], 11)
        self.assertEqual(self.c.totals['some_metric'], 11)

    def test_sample(self):
        self.c.add_metric('some_metric')
        self.c.sample()
        self.assertEqual(self.c.samples['some_metric'], [1])

        self.c.add_metric('some_metric')
        self.c.sample()
        self.assertEqual(self.c.samples['some_metric'], [1, 1])

        for i in range(15):
            self.c.add_metric('some_metric', count=i)
            self.c.sample()
        self.assertEqual(self.c.samples['some_metric'], range(4, 15))

    def test_attach_logger(self):
        self.c.start()
        self.assertIn(self.c.emit, log.theLogPublisher.observers)
        self.c.stop()
        self.assertNotIn(self.c.emit, log.theLogPublisher.observers)


class DateTimeParseTest(unittest.TestCase):
    def setUp(self):
        os.environ['TZ'] = 'GMT'
        time.tzset()

    def test_invalid_date(self):
        result = try_datetime_parse("this isn't a date!")
        self.assertIsNone(result)

    def test_RFC_1123(self):
        result = try_datetime_parse("Thu, 10 Apr 2008 13:30:00 GMT")
        self.assertEqual(result, 1207834200.0)

    def test_RFC_1123_subsecond(self):
        result = try_datetime_parse("Thu, 10 Apr 2008 13:30:00.12345 GMT")
        self.assertEqual(result, 1207834200.0)

    def test_ISO_8601(self):
        result = try_datetime_parse("2008-04-10T13:30:00")
        self.assertEqual(result, 1207834200.0)

    def test_ISO_8601_subsecond(self):
        result = try_datetime_parse("2008-04-10T13:30:00.12345")
        self.assertEqual(result, 1207834200.0)

    def test_universal_sortable(self):
        result = try_datetime_parse("2008-04-10 13:30:00")
        self.assertEqual(result, 1207834200.0)

    def test_universal_sortable_subsecond(self):
        result = try_datetime_parse("2008-04-10 13:30:00.12345")
        self.assertEqual(result, 1207834200.0)

    def test_date_short(self):
        result = try_datetime_parse("2012-04-10")
        self.assertEqual(result, 1334016000.0)


class ParseKeyValueConfigTest(unittest.TestCase):
    def test_single(self):
        res = parse_key_value_config('test: 1')
        self.assertEqual(res, {'test': '1'})

    def test_multiple(self):
        res = parse_key_value_config('test: 1, test2: 2')
        self.assertEqual(res, {'test': '1', 'test2': '2'})

    def test_empty(self):
        res = parse_key_value_config('')
        self.assertEqual(res, {})

    def test_duplicate(self):
        res = parse_key_value_config('test: 1, test: 2')
        self.assertEqual(res, {'test': '2'})

    def test_whitespace(self):
        res = parse_key_value_config('  test    : 1   ,   test2     :  2   ')
        self.assertEqual(res, {'test': '1', 'test2': '2'})
