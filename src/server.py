#!/usr/bin/python3

import time

import config
import mailer
from container import Container
from entry import Entry


def main():
    containers = dict()
    attic = Entry.listall()
    mails = set()
    for name in attic:
        e = Entry.find(name)
        if e and not e.check_mail():
            mails.add(e)

    while True:
        for name in Entry.listall() - attic:
            if name in containers:
                # delete finished container
                if not containers[name].check():
                    del containers[name]
                    attic.add(name)
                    mails.add(Entry.find(name))
            else:
                # find all uploaded fresh submissions and start them
                e = Entry.find(name)
                if e:
                    containers[name] = Container(e)
                    containers[name].run()

        for entry in mails.copy():
            if entry.check_mail():
                mails.remove(entry)
                mailer.mail_to_editors(entry)

        time.sleep(config.POLLTIME)


if __name__ == "__main__":
    main()
