#!/usr/bin/python
from setuptools import setup, find_packages
import sys

from swftp import VERSION

short_description = '''SwFTP is an FTP and SFTP interface for Openstack Object
Storage (swift)'''
long_description = short_description
try:
    long_description = open('README.md').read()
except:
    pass

requires = ['twisted >= 12.1', 'pyopenssl', 'pycrypto', 'pyasn1', 'psutil']

if sys.version_info < (2, 7):
    requires.append('ordereddict')

setup(
    name='swftp',
    version=VERSION,
    author='Kevin McDonald',
    author_email='kmcdonald@softlayer.com',
    license='MIT',
    url='https://github.com/softlayer/swftp',
    description=short_description,
    long_description=long_description,
    packages=find_packages() + ['twisted.plugins'],
    install_requires=requires,
    entry_points={
        'console_scripts': ['swftp-ftp = swftp.ftp.service:run',
                            'swftp-sftp = swftp.sftp.service:run'],
    },
    package_data={
        'twisted.plugins': ['twisted/plugins/swftp_ftp.py',
                            'twisted/plugins/swftp_sftp.py'],
        'swftp.test': ['test.conf', 'test_id_rsa', 'test_id_rsa.pub'],
    },
    data_files=[
        ('', ['README.md']),
        ('', ['etc/swftp/swftp.conf.sample']),
    ],
    zip_safe=False,
    classifiers=[
        'Environment :: Console',
        'Operating System :: OS Independent',
        'Environment :: No Input/Output (Daemon)',
        'Framework :: Twisted',
        'License :: OSI Approved :: MIT License',
        'Topic :: Internet :: File Transfer Protocol (FTP)',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2.6',
        'Programming Language :: Python :: 2.7',
    ],
)

# Make Twisted regenerate the dropin.cache, if possible.  This is necessary
# because in a site-wide install, dropin.cache cannot be rewritten by
# normal users.
try:
    from twisted.plugin import IPlugin, getPlugins
except ImportError:
    pass
else:
    list(getPlugins(IPlugin))
