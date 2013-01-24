"""
Defines serviceMaker, which required for automatic twistd integration for
swftp-ftp

See COPYING for license information.
"""
from twisted.application.service import ServiceMaker

serviceMaker = ServiceMaker(
    'swftp-ftp',  # name
    'swftp.ftp.service',  # module
    'An FTP Proxy Interface for Swift',  # description
    'swftp-ftp'  # tap name
)
