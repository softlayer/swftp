"""
See COPYING for license information.
"""
import unittest

from swftp.utils import try_datetime_parse


class DateTimeParseTest(unittest.TestCase):
    def test_invalid_date(self):
        result = try_datetime_parse("this isn't a date!")
        self.assertIsNone(result)

    def test_RFC_1123(self):
        result = try_datetime_parse("Thu, 10 Apr 2008 13:30:00 GMT")
        self.assertEqual(result, 1207855800.0)

    def test_RFC_1123_subsecond(self):
        result = try_datetime_parse("Thu, 10 Apr 2008 13:30:00.12345 GMT")
        self.assertEqual(result, 1207855800.0)

    def test_ISO_8601(self):
        result = try_datetime_parse("2008-04-10T13:30:00")
        self.assertEqual(result, 1207852200.0)

    def test_ISO_8601_subsecond(self):
        result = try_datetime_parse("2008-04-10T13:30:00.12345")
        self.assertEqual(result, 1207852200.0)

    def test_universal_sortable(self):
        result = try_datetime_parse("2008-04-10 13:30:00")
        self.assertEqual(result, 1207852200.0)

    def test_universal_sortable_subsecond(self):
        result = try_datetime_parse("2008-04-10 13:30:00.12345")
        self.assertEqual(result, 1207852200.0)

    def test_date_short(self):
        result = try_datetime_parse("2012-04-10")
        self.assertEqual(result, 1334034000.0)
