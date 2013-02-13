SwFTP
=====
SwFTP is an FTP and SFTP interface for Openstack Object Storage (swift). It will act as a proxy between the FTP/SFTP protocols and OpenStack Object Storage.

Features
--------
* Configurable auth endpoint to use any OpenStack Swift installation.
* Configurable welcome message for the FTP server.
* Support for HTTPS communication to the backend OpenStack Object Storage cluster.
* Server-wide Configurable HTTP Connection Pool for Swift Communications (size and timeout).
* Simple Installation (pip install swftp).

Getting Started
---------------
### Installing
Install via pip:
```
$ pip install swftp
```

Install from source:
```
$ python setup.py install
```

### Start FTP Server
To run the FTP server with twistd, simply run this command. 
```
$ twistd swftp-ftp -a http://127.0.0.1:8080/auth/v1.0
```

### Start SFTP Server
The SFTP requires a bit of setup the first time.


You'll need to create a public/private key pair for SSH and move them to the /etc/swift directory (configurable).
```
$ mkdir /etc/swift
$ ssh-keygen -h -b 2048 -N "" -t rsa -f /etc/swift/id_rsa
```

After placing the required files, the command to start the server is similar to the FTP one.
```
$ twistd swftp-sftp -a http://127.0.0.1:8080/auth/v1.0
```

Configuration
-------------
### Command Line
The command line configuration allows you to speficfy a custom OpenStack Swift Auth URL, as well as the location of the config file (detailed later).

SFTP Command-line options:
```
$twistd swftp-sftp --help
Usage: twistd [options] swftp-sftp [options]
Options:
  -c, --config_file=  Location of the swftp config file. [default:
                      /etc/swift/swftp.conf]
  -a, --auth_url=     Auth Url to use. Defaults to the config file value if it
                      exists.[default: http://127.0.0.1:8080/auth/v1.0]
  -p, --port=         Port to bind to.
  -h, --host=         IP to bind to.
      --priv_key=     Private Key Location.
      --pub_key=      Public Key Location.
      --version       Display Twisted version and exit.
      --help          Display this help and exit.
```

FTP Command-line options:
```
twistd swftp-ftp --help
Usage: twistd [options] swftp-ftp [options]
Options:
  -c, --config_file=  Location of the swftp config file. [default:
                      /etc/swift/swftp.conf]
  -a, --auth_url=     Auth Url to use. Defaults to the config file value if it
                      exists. [default: http://127.0.0.1:8080/auth/v1.0]
  -p, --port=         Port to bind to.
  -h, --host=         IP to bind to.
      --version       Display Twisted version and exit.
      --help          Display this help and exit.
```


In addition to the app-specific options twistd adds options. Below are some of the most common options. To see all of them use `twistd --help`.
```
Usage: twistd [options]
Options:
  -n, --nodaemon       don't daemonize, don't use default umask of 0077
      --syslog         Log to syslog, not to file
  -l, --logfile=       log to a specified file, - for stdout
      --pidfile=       Name of the pidfile [default: twistd.pid]
  -u, --uid=           The uid to run as.
  -g, --gid=           The gid to run as.
```

### Config File
The default location for the config file is /etc/swift/swftp.conf.

Here is an example swftp.conf with all defaults:
```
[sftp]
auth_url = http://127.0.0.1:8080/auth/v1.0
host = 0.0.0.0
port = 5022
priv_key = /etc/swift/id_rsa
pub_key = /etc/swift/id_rsa.pub
num_persistent_connections = 4
connection_timeout = 240

[ftp]
auth_url = http://127.0.0.1:8080/auth/v1.0
host = 0.0.0.0
port = 5021
num_persistent_connections = 4
connection_timeout = 240
welcome_message = Welcome to SwFTP - An FTP/SFTP interface for Openstack Swift
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
* twisted/: For Twisted Plugin System


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
