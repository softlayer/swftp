"""
See COPYING for license information.
"""
from syslog import (
    LOG_USER, LOG_DAEMON, LOG_SYSLOG, LOG_LOCAL0, LOG_LOCAL1, LOG_LOCAL2,
    LOG_LOCAL3, LOG_LOCAL4, LOG_LOCAL5, LOG_LOCAL6, LOG_LOCAL7)

from twisted.python import syslog


class SysLogObserver:
    facility = LOG_USER

    def __init__(self):
        self.obs = syslog.SyslogObserver('swftp', facility=self.facility)

    def __call__(self, event_dict):
        self.obs.emit(event_dict)


class LOG_USER(SysLogObserver):
    facility = LOG_USER


class LOG_DAEMON(SysLogObserver):
    facility = LOG_DAEMON


class LOG_SYSLOG(SysLogObserver):
    facility = LOG_SYSLOG


class LOG_LOCAL0(SysLogObserver):
    facility = LOG_LOCAL0


class LOG_LOCAL1(SysLogObserver):
    facility = LOG_LOCAL1


class LOG_LOCAL2(SysLogObserver):
    facility = LOG_LOCAL2


class LOG_LOCAL3(SysLogObserver):
    facility = LOG_LOCAL3


class LOG_LOCAL4(SysLogObserver):
    facility = LOG_LOCAL4


class LOG_LOCAL5(SysLogObserver):
    facility = LOG_LOCAL5


class LOG_LOCAL6(SysLogObserver):
    facility = LOG_LOCAL6


class LOG_LOCAL7(SysLogObserver):
    facility = LOG_LOCAL7
