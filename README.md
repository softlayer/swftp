SwFTP
=====
SwFTP is an FTP and SFTP interface for Openstack Object Storage (swift). It will act as a proxy between the FTP/SFTP protocols and OpenStack Object Storage.

Features
--------
* Configurable auth endpoint to use any OpenStack Swift installation
* Server-wide Configurable HTTP Connection Pool for Swift Communications (size and timeout)
* Support for HTTPS communication to the backend OpenStack Object Storage cluster
* Simple Installation `pip install swftp`
* StatsD Support
* Stats Web Interface
* Chef Cookbook: https://github.com/softlayer/chef-swftp

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

Install using git/pip:
```bash
$ pip install -U git+git://github.com/softlayer/swftp.git
```

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
host = 0.0.0.0
port = 5022
priv_key = /etc/swftp/id_rsa
pub_key = /etc/swftp/id_rsa.pub
connection_timeout = 240

auth_url = http://127.0.0.1:8080/auth/v1.0
num_persistent_connections = 20
num_connections_per_session = 10
rewrite_storage_scheme =
rewrite_storage_netloc =
extra_headers = X-Swftp: true, X-Forwarded-Proto: SFTP

log_statsd_host =
log_statsd_port = 8125
log_statsd_sample_rate = 10
log_statsd_metric_prefix = sftp

stats_host =
stats_port = 38022

[ftp]
host = 0.0.0.0
port = 5021
sessions_per_user = 10
connection_timeout = 240
welcome_message = Welcome to SwFTP - An FTP/SFTP interface for Openstack Swift

auth_url = http://127.0.0.1:8080/auth/v1.0
num_persistent_connections = 20
num_connections_per_session = 10
rewrite_storage_scheme =
rewrite_storage_netloc =
extra_headers = X-Swftp: true, X-Forwarded-Proto: SFTP

log_statsd_host =
log_statsd_port = 8125
log_statsd_sample_rate = 10
log_statsd_metric_prefix = ftp

stats_host = 
stats_port = 38021
```

**Server Options**

* **host** - Address that the FTP/SFTP server will listen on.
* **port** - Port that the FTP/SFTP server will listen on.
* **sessions_per_user** - Number of FTP/SFTP sessions per unique swift username to allow.
* **priv_key** - (SFTP Only) - File path to the private SSH key that the SFTP server will use.
* **pub_key** - (SFTP Only) - File path to the public SSH key generated from the private key.
* **session_timeout** - (FTP Only) - Session timeout in seconds. Idle sessions will be closed after this much time.
* **welcome_message** - (FTP Only) - Custom FTP welcome message.

**Swift Options**

* **auth_url** - Auth URL to use to authenticate with the backend swift cluster.
* **num_persistent_connections** - Number of persistent connections to the backend swift cluster for an entire swftp instance.
* **num_connections_per_session** - Number of persistent connections to the backend swift cluster per FTP/SFTP session.
* **connection_timeout** - Connection timeout in seconds to the backend swift cluster.
* **extra_headers** - Extra HTTP headers that are sent to swift cluster.
    * e.g.: extra_headers = X-Swftp: true, X-Forwarded-Proto: SFTP
* **rewrite_storage_scheme** - Rewrite the URL scheme of each storage URL returned from Swift auth to this value.
    * e.g.: rewrite_storage_scheme = https
* **rewrite_storage_netloc** - Rewrite the URL netloc (hostname:port) of each storage URL returned from Swift auth to this value.
    * e.g.: rewrite_storage_netloc = 127.0.0.1:12345

**Stats Options**

* **stats_host** - Address that the HTTP stats interface will listen on.
* **stats_port** - Port that the HTTP stats interface will listen on.
* **log_statsd_host** - statsd hostname.
* **log_statsd_port** - statsd port.
* **log_statsd_sample_rate** - How often in seconds to send metrics to the statsd server.
* **log_statsd_metric_prefix** - Prefix appended to each stat sent to statsd.


Caveats
-------
* You cannot create top-level files, just directories (because the top level are containers).
* You cannot rename any non-empty directory.
* No recursive delete. Most clients will explicitly delete each file/directory recursively anyway.
* Fake-directories and real objects of the same name will simply display the directory. A lot of FTP/SFTP clients [actually explode](http://gifsoup.com/webroot/animatedgifs2/1095919_o.gif) if a directory listing has duplicates.

Project Organization
--------------------
* etc/: Sample config files
* swftp/: Core/shared code
    * ftp/: FTP server
    * sftp/: SFTP server
    * test/: Unit and functional tests
* twisted/: For the Twisted Plugin System

Packaging/Creating Init Scripts
-------------------------------
Packaged with SwFTP are a set of example init scripts, upstart scripts. They are all located within the /etc/ directory in the source.

* Upstart
    * /etc/init/swftp-ftp.conf
    * /etc/init/swftp-sftp.conf
* init.d
    * /etc/init.d/swftp-ftp
    * /etc/init.d/swftp-sftp
* Supervisor
    * /etc/supervisor/conf.d/swftp.conf
* Example swftp.conf file
    * /etc/swftp/swftp.conf.sample

Stats Web Interface
-------------------
The web interface is an HTTP interface that provides a way to get more app-specific metrics. The only format supported currently is JSON. If the 'stats_host' config value is set, the server will listen to that interface.

**http://{stats_host}:{stats_port}/stats.json**

```bash
$ curl http://127.0.0.1:38022/stats.json | python -mjson.tool
{
    "rates": {
        "auth.fail": 0,
        "auth.succeed": 0,
        "command.getAttrs": 0,
        "command.login": 0,
        "command.logout": 9,
        "command.makeDirectory": 0,
        "command.openDirectory": 0,
        "command.openFile": 0,
        "command.removeDirectory": 0,
        "command.removeFile": 0,
        "command.renameFile": 0,
        "num_clients": -9,
        "transfer.egress_bytes": 0,
        "transfer.ingress_bytes": 47662
    },
    "totals": {
        "auth.fail": 0,
        "auth.succeed": 91,
        "command.getAttrs": 15,
        "command.login": 91,
        "command.logout": 91,
        "command.makeDirectory": 0,
        "command.openDirectory": 7,
        "command.openFile": 8,
        "command.removeDirectory": 3,
        "command.removeFile": 0,
        "command.renameFile": 7,
        "num_clients": 0,
        "transfer.egress_bytes": 11567105,
        "transfer.ingress_bytes": 11567105
    }
}
```

Statsd Support
--------------
Statsd support relies on [txStatsD](https://pypi.python.org/pypi/txStatsD). If the 'log_statsd_host' config value is set, the following paths will be emited into statsd.

### General

* stats.[prefix].egress_bytes
* stats.[prefix].ingress_bytes
* stats.gauges.[prefix].clients
* stats.gauges.[prefix].proc.threads
* stats.gauges.[prefix].proc.cpu.percent
* stats.gauges.[prefix].proc.cpu.system
* stats.gauges.[prefix].proc.cpu.user
* stats.gauges.[prefix].proc.memory.percent
* stats.gauges.[prefix].proc.memory.rss
* stats.gauges.[prefix].proc.memory.vsize
* stats.gauges.[prefix].proc.net.status.[tcp_state]

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

Development
-----------
Development works with a fork and pull request process. Feel free submit pull requests.

To run the tests, run
```bash
$ trial swftp
```

To run tests against live swftp servers (ftp and sftp) it requires a test config. The default location is `/etc/swftp/test.conf` but can be set with the SWFTP_TEST_CONFIG_FILE environmental variable. Here is a sample test config

```
[func_test]
auth_host = 127.0.0.1
auth_port = 8080
auth_ssl = no
auth_prefix = /auth/

account = test
username = tester
password = testing

sftp_host = 127.0.0.1
sftp_port = 5022

ftp_host = 127.0.0.1
ftp_port = 5021

```

License
-------
Copyright (c) 2014 SoftLayer Technologies, Inc.

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
