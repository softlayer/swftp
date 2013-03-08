SwFTP
=====
SwFTP is an FTP and SFTP interface for Openstack Object Storage (swift). It will act as a proxy between the FTP/SFTP protocols and OpenStack Object Storage.

Features
--------
* Configurable auth endpoint to use any OpenStack Swift installation.
* Server-wide Configurable HTTP Connection Pool for Swift Communications (size and timeout).
* Support for HTTPS communication to the backend OpenStack Object Storage cluster.
* Configurable welcome message for the FTP server.
* Simple Installation (pip install swftp).
* StatsD Support

Requirements
------------
* Python 2.6-2.7
* OpenSSL/pycrypto
* Twisted/Twisted-Conch
* pyasn1

Getting Started
---------------
### Installing
Install via pip:

```bash
$ pip install swftp
```
Note: If you don't have pip [here's how to install it](http://www.pip-installer.org/en/latest/installing.html).

Install from source:
```bash
$ python setup.py install
```

### Start FTP Server
To run the FTP server, simply run this command. 
```bash
$ swftp-ftp -a http://127.0.0.1:8080/auth/v1.0
2013-02-18 16:28:50-0600 [-] Log opened.
2013-02-18 16:28:50-0600 [-] FTPFactory starting on 5021
2013-02-18 16:28:50-0600 [-] Starting factory <twisted.protocols.ftp.FTPFactory instance at 0x1103fcf80>
```

### Start SFTP Server
The SFTP requires a bit of setup the first time.


You'll need to create a public/private key pair for SSH and move them to the /etc/swftp directory (this location is configurable).
```bash
$ mkdir /etc/swftp
$ ssh-keygen -h -b 2048 -N "" -t rsa -f /etc/swftp/id_rsa
```

After placing the required files, the command to start the server is similar to the FTP one.
```bash
$ swftp-sftp -a http://127.0.0.1:8080/auth/v1.0
2013-02-18 16:29:14-0600 [-] Log opened.
2013-02-18 22:29:14+0000 [-] SSHFactory starting on 5022
```

Configuration
-------------
### Command Line
The command line configuration allows you to speficfy a custom OpenStack Swift Auth URL, as well as the location of the config file (detailed later).

FTP Command-line options:
```bash
$ swftp-ftp --help
Usage: swftp-ftp [options]
Options:
  -c, --config_file=  Location of the swftp config file. [default:
                      /etc/swftp/swftp.conf]
  -a, --auth_url=     Auth Url to use. Defaults to the config file value if it
                      exists. [default: http://127.0.0.1:8080/auth/v1.0]
  -p, --port=         Port to bind to.
  -h, --host=         IP to bind to.
      --version       Display Twisted version and exit.
      --help          Display this help and exit.
```

SFTP Command-line options:
```bash
$ swftp-sftp --help
Usage: swftp-sftp [options]
Options:
  -c, --config_file=  Location of the swftp config file. [default:
                      /etc/swftp/swftp.conf]
  -a, --auth_url=     Auth Url to use. Defaults to the config file value if it
                      exists.[default: http://127.0.0.1:8080/auth/v1.0]
  -p, --port=         Port to bind to.
  -h, --host=         IP to bind to.
      --priv_key=     Private Key Location.
      --pub_key=      Public Key Location.
      --version       Display Twisted version and exit.
      --help          Display this help and exit.
```

### Config File
The default location for the config file is /etc/swftp/swftp.conf.

Here is an example swftp.conf with all defaults:
```
[sftp]
auth_url = http://127.0.0.1:8080/auth/v1.0
host = 0.0.0.0
port = 5022
priv_key = /etc/swftp/id_rsa
pub_key = /etc/swftp/id_rsa.pub
num_persistent_connections = 4
connection_timeout = 240
log_statsd_host = 
log_statsd_port = 8125
log_statsd_sample_rate = 10
log_statsd_metric_prefix = sftp

[ftp]
auth_url = http://127.0.0.1:8080/auth/v1.0
host = 0.0.0.0
port = 5021
num_persistent_connections = 4
connection_timeout = 240
welcome_message = Welcome to SwFTP - An FTP/SFTP interface for Openstack Swift
log_statsd_host = 
log_statsd_port = 8125
log_statsd_sample_rate = 10
log_statsd_metric_prefix = ftp
```

Caveats
-------
* You cannot create top-level files, just directories (because the top level are containers).
* You cannot rename any non-empty directory.
* No recursive delete. Most clients will explicitly delete each file/directory recursively anyway.
* Fake-directories and real objects of the same name will simply display the directory. A lot of clients [actually explode](http://gifsoup.com/webroot/animatedgifs2/1095919_o.gif) if a directory listing has duplicates.

Organization
------------
* etc/: Sample config files
* swftp/: Core/shared code
  * ftp/: FTP server
  * sftp/: SFTP server
  * test/: Unit and functional tests
* twisted/: For the Twisted Plugin System

Packaging/Creating Init Scripts
-------------------------------
Packaged with SwFTP are a set of example init scripts, upstart scripts.

They are all located within the /etc/ directory.

* Upstart
    * /etc/init/swftp-ftp.conf
    * /etc/init/swftp-sftp.conf
* init.d
    * /etc/init/swftp-ftp
    * /etc/init/swftp-sftp
* Supervisor
    * /etc/supervisor/conf.d/swftp.conf

Statsd Support
--------------
Statsd support relies on [txStatsD](https://pypi.python.org/pypi/txStatsD). If the 'log_statsd_host' config value is set, the following paths will be emited into statsd.

### General

* stats.[prefix].egress_bytes
* stats.[prefix].ingress_bytes
* stats.guages.[prefix].clients
* stats.guages.[prefix].proc.threads
* stats.guages.[prefix].proc.cpu.percent
* stats.guages.[prefix].proc.cpu.system
* stats.guages.[prefix].proc.cpu.user
* stats.guages.[prefix].proc.memory.percent
* stats.guages.[prefix].proc.memory.rss
* stats.guages.[prefix].proc.memory.vsize
* stats.guages.[prefix].proc.net.status.[tcp_state]

### SFTP-related

* stats.[prefix].command.getAttrs
* stats.[prefix].command.login
* stats.[prefix].command.logout
* stats.[prefix].command.makeDirectory
* stats.[prefix].command.openDirectory
* stats.[prefix].command.openFile
* stats.[prefix].command.removeDirectory
* stats.[prefix].command.removeFile
* stats.[prefix].command.renameFile

### FTP-related

* stats.[prefix].command.access
* stats.[prefix].command.list
* stats.[prefix].command.login
* stats.[prefix].command.logout
* stats.[prefix].command.makeDirectory
* stats.[prefix].command.openForReading
* stats.[prefix].command.openForWriting
* stats.[prefix].command.removeDirectory
* stats.[prefix].command.removeFile
* stats.[prefix].command.rename
* stats.[prefix].command.stat

License
-------
Copyright (c) 2013 SoftLayer Technologies, Inc.

Permission is hereby granted, free of charge, to any person obtaining a copy of
this software and associated documentation files (the "Software"), to deal in
the Software without restriction, including without limitation the rights to
use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies
of the Software, and to permit persons to whom the Software is furnished to do
so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
