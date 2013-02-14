#!/usr/bin/python
from setuptools import setup

name = 'swftp'

short_description = 'SwFTP is an FTP and SFTP interface for Openstack Swift'
long_description = short_description
try:
    long_description = open('README.md').read()
except:
    pass

setup(
    name=name,
    version='1.0.1',
    author='Kevin McDonald',
    author_email='kmcdonald@softlayer.com',
    license='MIT',
    url='https://github.com/softlayer/swftp',
    description=short_description,
    long_description=long_description,
    packages=['swftp', 'swftp/sftp', 'swftp/ftp', 'twisted.plugins'],
    install_requires=[
        'twisted >= 12',
        'pyopenssl',
        'pycrypto',
        'pyasn1',
    ],
    entry_points={
        'console_scripts': ['swftp-ftp = swftp.ftp.service:run',
                            'swftp-sftp = swftp.sftp.service:run'],
    },
    package_data={
        'twisted.plugins': ['twisted/plugins/swftp_ftp.py',
                            'twisted/plugins/swftp_sftp.py']},
    data_files=[
        ('', ['README.md']),
        ('/etc/swftp', ['etc/swftp/swftp.conf']),
    ],
    zip_safe=False,
    classifiers=[
        'Environment :: Console',
        'Programming Language :: Python',
        'Operating System :: OS Independent',
        'Environment :: No Input/Output (Daemon)',
        'Framework :: Twisted',
        'License :: OSI Approved :: MIT License',
        'Topic :: Internet :: File Transfer Protocol (FTP)',
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
