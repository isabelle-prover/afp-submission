#!/usr/bin/python3

import enum
import json
import os
import re
import tarfile
import zipfile

import config

FMT = re.compile("^[0-9]{2}-[0-9]{2}-[0-9]{4}_[0-9]{2}-[0-9]{2}-[0-9]{2}_[0-9]{3}$")


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


class ResultWriter:
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


class Metadata:
    def __init__(self, entries, contact, comment):
        self.entries = entries
        self.contact = contact
        self.comment = comment

    @staticmethod
    def from_json(info):
        return Metadata(info["entries"], info["notify"], info["comment"])


class ArchiveFile:
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
        raise NotImplementedError()


class TarArchiveFile(ArchiveFile):
    archive_name = "archive.tar.gz"

    def extract(self, dir):
        try:
            with tarfile.open(fileobj=self.fileobj) as t:
                t.extractall(path=dir)
                return True
        except tarfile.TarError:
            return False


class ZipArchiveFile(ArchiveFile):
    archive_name = "archive.zip"

    def extract(self, dir):
        try:
            with zipfile.ZipFile(self.fileobj) as z:
                z.extractall(path=dir)
                return True
        except zipfile.BadZipFile:
            return False


class Entry:
    """ Manage all state about a AFP submission entry.

    All directories and files stored under config.UPLOAD_DIR and
    config.DOWNLOAD_DIR are managed by this class.
    """

    @staticmethod
    def find(name):
        """Checks if the directory is available"""
        if FMT.match(name) is None:
            return None

        if os.path.isfile(os.path.join(config.UPLOAD_DIR, name, "done")):
            return Entry(name)

        return None

    @staticmethod
    def listall():
        return set(os.listdir(config.UPLOAD_DIR))

    def __init__(self, name, metadata=None):
        self.name = name
        if metadata:
            self.metadata = metadata
        else:
            self.read_json()

    def link(self):
        return config.LINKBASE + "submission?id=" + self.name

    # UP part: written by the webserver ############################################################

    def up(self, *names, mode=None):
        name = os.path.join(config.UPLOAD_DIR, self.name, *names)
        if mode:
            return open(name, mode, encoding="utf8")
        else:
            return name

    def signal(self, name, content=None):
        if content is None:
            content = name.upper()
        with self.up(name, mode='w') as f:
            print(content, file=f, flush=True)

    def up_check(self, name):
        return os.path.exists(self.up(name))

    def check_kill(self):
        return self.up_check("kill")

    def signal_afp(self, sub_status):
        with self.up(config.AFP_STATUS_FILENAME, mode='w') as f:
            print(sub_status.name, file=f, flush=True)

    def check_mail(self):
        return self.up_check("mail")

    def open_archive(self):
        try:
            return TarArchiveFile(self.up("archive.tar.gz"), 'rb')
        except FileNotFoundError:
            return ZipArchiveFile(self.up("archive.zip"), 'rb')

    def read_json(self):
        with self.up("info.json", mode='r') as info:
            self.metadata = Metadata.from_json(json.load(info))

    # DOWN part: written by the container manager ##################################################

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
        return s != Result.NOT_FINISHED
