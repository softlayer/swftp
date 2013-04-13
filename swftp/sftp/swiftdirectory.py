"""
See COPYING for license information.
"""
from twisted.conch import ls

from swftp.utils import OrderedDict
from swftp.swiftfilesystem import swift_stat


class SwiftDirectory(object):
    "Swift Directory is an iterator that returns a listing of the directory."
    def __init__(self, swiftfilesystem, fullpath):
        self.swiftfilesystem = swiftfilesystem
        self.fullpath = fullpath
        # A lot of clients require . and .. to be within the directory listing
        self.files = OrderedDict(
            [
                ('.', {}),
                ('..', {}),
            ])
        self.done = False

    def get_full_listing(self):
        "Populate the directory listing."
        def cb(results):
            for k, v in results.iteritems():
                self.files[k] = v

        d = self.swiftfilesystem.get_full_listing(self.fullpath)
        d.addCallback(cb)
        return d

    def __iter__(self):
        return self

    def next(self):
        try:
            name, f = self.files.popitem(last=False)
            lstat = swift_stat(**f)
            longname = ls.lsLine(name, lstat)
            return (name, longname, {
                "size": lstat.st_size,
                "uid": lstat.st_uid,
                "gid": lstat.st_gid,
                "permissions": lstat.st_mode,
                "atime": int(lstat.st_atime),
                "mtime": int(lstat.st_mtime)
            })
        except KeyError:
            raise StopIteration

    def close(self):
        self.files = []
        self.offset = 0
