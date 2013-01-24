"""
Defines serviceMaker, which required for automatic twistd integration for
swftp-sftp

See COPYING for license information.
"""
from twisted.application.service import ServiceMaker

serviceMaker = ServiceMaker(
    'swftp-sftp',  # name
    'swftp.sftp.service',  # module
    'An SFTP Proxy Interface for Swift',  # description
    'swftp-sftp'  # tap name
)
