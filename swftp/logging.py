"""
See COPYING for license information.
"""
import sys
import syslog as pysyslog

from twisted.python import syslog
from twisted.python import log

WHITELISTED_LOG_SYSTEMS = ['SwFTP', '-']


def msg(message, *args, **kwargs):
    if not kwargs.get('system'):
        kwargs['system'] = 'SwFTP'
    return log.msg(message, *args, **kwargs)


class LogObserver(object):
    def start(self):
        log.addObserver(self)

    def stop(self):
        log.removeObserver(self)

    def __call__(self, event_dict):
        if any((True for system in WHITELISTED_LOG_SYSTEMS
                if event_dict.get('system', '').startswith(system))) \
                or event_dict.get('isError', False):
            self.obs.emit(event_dict)


class StdOutObserver(LogObserver):
    def __init__(self):
        self.obs = log.FileLogObserver(sys.stdout)


class SysLogObserver(LogObserver):
    facility = pysyslog.LOG_USER

    def __init__(self):
        self.obs = syslog.SyslogObserver('swftp', facility=self.facility)


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
