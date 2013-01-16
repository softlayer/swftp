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
    version='1.0.0',
    author='Kevin McDonald',
    author_email='kmcdonald@softlayer.com',
    description=short_description,
    long_description=long_description,
    packages=['swftp', 'swftp/sftp', 'swftp/ftp', 'twisted.plugins'],
    install_requires=[
        'twisted >= 12',
        'pyopenssl',
        'pycrypto',
        'pyasn1',
        ],
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
