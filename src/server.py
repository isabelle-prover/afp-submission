#!/usr/bin/python3

import os
import time
import subprocess
import getpass

from entry import Entry
from container import Container
import config

def main():
    containers = dict()
    attic = Entry.listall()

    while True:
        for name in Entry.listall() - attic:
            if name in containers:
                if not containers[name].check():
                    del containers[name]
                    attic.add(name)
            else:
                e = Entry.find(name)
                if e and e.check_upload():
                    containers[name] = Container(e)
                    containers[name].run()

        time.sleep(config.POLLTIME)

if __name__ == "__main__":
    main()

