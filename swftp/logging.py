"""
See COPYING for license information.
"""
import syslog as pysyslog
from twisted.python import syslog


class SysLogObserver(object):
    facility = pysyslog.LOG_USER

    def __init__(self):
        self.obs = syslog.SyslogObserver('swftp', facility=self.facility)

    def __call__(self, event_dict):
        self.obs.emit(event_dict)


class LOG_USER(SysLogObserver):
    facility = pysyslog.LOG_USER


class LOG_DAEMON(SysLogObserver):
    facility = pysyslog.LOG_DAEMON


class LOG_SYSLOG(SysLogObserver):
    facility = pysyslog.LOG_SYSLOG


class LOG_LOCAL0(SysLogObserver):
    facility = pysyslog.LOG_LOCAL0


class LOG_LOCAL1(SysLogObserver):
    facility = pysyslog.LOG_LOCAL1


class LOG_LOCAL2(SysLogObserver):
    facility = pysyslog.LOG_LOCAL2


class LOG_LOCAL3(SysLogObserver):
    facility = pysyslog.LOG_LOCAL3


class LOG_LOCAL4(SysLogObserver):
    facility = pysyslog.LOG_LOCAL4


class LOG_LOCAL5(SysLogObserver):
    facility = pysyslog.LOG_LOCAL5


class LOG_LOCAL6(SysLogObserver):
    facility = pysyslog.LOG_LOCAL6


class LOG_LOCAL7(SysLogObserver):
    facility = pysyslog.LOG_LOCAL7
