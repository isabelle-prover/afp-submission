#!/usr/bin/python3

import configparser
import os
import random
import enum
import re
from datetime import datetime
import shutil
import tarfile
import zipfile

import config

FMT = re.compile("^[0-9]{8}-[0-9]{6}_[0-9]{4}$")

class Result(enum.Enum):
    NOT_FINISHED = 0
    SUCCESS = 1
    FAILED = 2

    def __str__(self):
        if self == Result.NOT_FINISHED:
            return "RUNNING"
        elif self == Result.SUCCESS:
            return "SUCCESSFUL BUILD"
        else:
            return "FAILED"

# TODO is this class still used?
class ResultWriter():
    def __init__(self, f):
        self.result_file = f

    def __call__(self, res):
        print(res.name, file=self.result_file)
        self.result_file.close()
        self.result_file = None

class AFPStatus(enum.Enum):
    SUBMITTED = 0
    PROCESSING = 1
    REJECTED = 2
    ADDED = 3

class Metadata():
    def __init__(self, entries, contact, comment):
        self.entries = entries
        self.contact = contact
        self.comment = comment

    def validate(self):
        if not self.entries or not self.contact:
            return False
        for entry in self.entries:
            for _key, value in entry.items():
                if not value:
                    return False
        return True

    def to_ini(self, entry_name):
        ini = configparser.SafeConfigParser()
        ini.add_section(entry_name)
        ini.set(entry_name, 'contact', self.contact)
        ini.set(entry_name, 'comment', self.comment)
        for entry in self.entries:
            ini.add_section(entry['shortname'])
            for key, value in entry.items():
                ini.set(entry['shortname'], key, value)
        return ini

    @staticmethod
    def from_ini(ini, entry_name):
        entries = [dict(ini[s]) for s in ini
                                if s != "DEFAULT" and s != entry_name]
        return Metadata(entries, ini[entry_name]['contact'],
                        ini[entry_name]['comment'])

class ArchiveFile():
    """ Simple class with file object and flag to show if tar or zip """

    mime_type = None
    archive_name = None

    def __init__(self, filename, mode):
        self.filename = filename
        self.fileobj = open(filename, mode)

    def __enter__(self):
        return self

    def __exit__(self, t, v, traceback):
        self.fileobj.close()

    def extract(self, dir):
        raise Unimplemented()

class TarArchiveFile(ArchiveFile):
    mime_type = "application/x-tar"
    archive_name = "theory.tar.gz"

    def extract(self, dir):
        try:
            with tarfile.open(fileobj = self.fileobj) as t:
                t.extractall(path = dir)
                return True
        except tarfile.TarError:
            return False

class ZipArchiveFile(ArchiveFile):
    mime_type = "application/zip"
    archive_name = "theory.zip"

    def extract(self, dir):
        try:
            with zipfile.ZipFile(self.fileobj) as z:
                z.extractall(path = dir)
                return True
        except zipfile.BadZipFile:
            return False

class Entry:
    """ Manage all state about a AFP submission entry.

    All directories and files stored under config.UPLOAD_DIR and
    config.DOWNLOAD_DIR are managed by this class.
    """

    @staticmethod
    def new(metadata, filename_archive, archive_stream):
        "Creates a new entry"
        rand = random.SystemRandom()
        nounce = rand.randint(0, 9999)
        tm = datetime.now()
        ## the following needs to match FMT
        name = "{}_{:04d}".format(tm.strftime("%Y%m%d-%H%M%S"), nounce)

        e = Entry(name, metadata)
        os.mkdir(e.up())
        e.write_ini()

        if filename_archive.endswith(".zip"):
            archive_name = "archive.zip"
        else:
            archive_name = "archive.tar.gz"

        with open(e.up(archive_name), 'wb') as f:
            shutil.copyfileobj(archive_stream, f)

        e.signal_upload()
        return e

    @staticmethod
    def find(name):
        "Checks if the directory is available"
        if FMT.match(name) is None:
            return None

        if os.path.isdir(os.path.join(config.UPLOAD_DIR, name)):
            return Entry(name)

        return None

    @staticmethod
    def listall():
        return set(os.listdir(config.UPLOAD_DIR))

    def __init__ (self, name, metadata = None):
        self.name = name
        if metadata:
            self.metadata = metadata
        else:
            self.read_ini()

    def link(self, action=None):
        l = config.LINKBASE + "index?build=" + self.name
        if action:
            l = l + "&action=" + action
        return l


    ## UP part: written by the webserver

    # TODO: rewrite function to two functions, one returing file path
    # one returing file pointer
    def up(self, *names, mode = None):
        name = os.path.join(config.UPLOAD_DIR, self.name, *names)
        if mode:
            return open(name, mode, encoding = "utf8")
        else:
            return name

    def signal(self, name, content=None):
        if content is None:
            content = name.upper()
        with self.up(name, mode='w') as f:
            print(content, file=f, flush=True)

    def del_signal(self, name):
        if os.path.exists(self.up(name)):
            os.remove(self.up(name))

    def up_check(self, name):
        return os.path.exists(self.up(name))

    def signal_kill(self):
        self.signal("kill")

    def check_kill(self):
        return self.up_check("kill")

    def signal_upload(self):
        self.signal("done")

    def check_upload(self):
        return self.up_check("done")

    def signal_mail(self):
        self.signal("mail")

    def signal_afp(self, sub_status):
        try:
            s = AFPStatus[sub_status]
            with self.up(config.AFP_STATUS_FILENAME, mode='w') as f:
                print(s.name, file=f, flush=True)
        except KeyError:
            pass

    def check_afp(self):
        try:
            with self.up(config.AFP_STATUS_FILENAME, mode='r') as f:
                return AFPStatus[f.read().strip()]
        except:
            return AFPStatus.SUBMITTED

    def check_mail(self):
        return self.up_check("mail")

    def open_archive(self):
        try:
            return TarArchiveFile(self.up("archive.tar.gz"), 'rb')
        except FileNotFoundError:
            return ZipArchiveFile(self.up("archive.zip"), 'rb')

    def open_ini(self, mode = None):
        return self.up("info.ini", mode=mode)

    def write_ini(self):
        ini = self.metadata.to_ini(self.name)
        with self.open_ini('w') as f:
            ini.write(f)

    def read_ini(self):
        ini = configparser.SafeConfigParser()
        ini.read(self.open_ini())
        self.metadata = Metadata.from_ini(ini, self.name)

    ## DOWN part: written by the container manager

    def down(self, *names, mode=None):
        name = os.path.join(config.DOWNLOAD_DIR, self.name, *names)
        if mode:
            return open(name, mode)
        else:
            return name

    def down_check(self, name):
        return os.path.exists(self.down(name))

    def get_result(self):
        try:
            with self.down("result", mode="rt") as f:
                return Result[f.read().strip()]
        except:
            return Result.NOT_FINISHED

    def result_writer(self):
        return ResultWriter(self.down("result", mode="wt"))

    def is_terminated(self):
        s = self.get_result()
        return (s != Result.NOT_FINISHED)

