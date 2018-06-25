#!/usr/bin/python3

from email.mime.text import MIMEText
from email.utils import formatdate
import os
import re
import smtplib
import ssl

import config

def email_regex(addr):
    # Regex doesnt allow all valid mailaddresses, but should be good enough for
    # us
    return re.match(r"(^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$)", addr)

def send(tos, ccs, subject, text):
    try:
        if config.MAILSSL:
            smtp = smtplib.SMTP_SSL(host = config.MAILSERVER, port = config.MAILSERVERPORT, 
                                    context = ssl.create_default_context())
            smtp.login(config.MAILUSER, config.MAILPASS)
        else:
            smtp = smtplib.SMTP(host = config.MAILSERVER, port = config.MAILSERVERPORT)
    except (smtplib.SMTPException, ssl.SSLError, ConnectionError):
        print("Connection to Mailserver or Authentication on Mailserver failed")
        return
    msg = MIMEText(text)
    msg['Subject'] = subject
    msg['From'] = config.SENDER
    msg['Date'] = formatdate(localtime = True)
    try:
        if (all([email_regex(r) for r in tos + ccs])):
            msg['To'] = ",".join(tos)
            msg['CC'] = ",".join(ccs)
            msg['BCC'] = ",".join(config.ADMINS)
            smtp.sendmail(config.SENDER, tos + config.ADMINS + ccs,
                          msg.as_string())
        else:
            msg['To'] = ",".join(config.ADMINS)
            print("Addresses don't fit regex: " + str(tos) + str(ccs))
            smtp.sendmail(config.SENDER, config.ADMINS, msg.as_string())
    except smtplib.SMTPException:
        print("Cannot send email: SMTP Error")
    smtp.quit()

def build_send_mail(entry, template):
    with open(os.path.join(config.TEMPLATES, template), 'r') as f:
        link = entry.link()
        names = " + ".join([e['title'] for e in entry.metadata.entries])
        msg = f.read().format(**{'link': link, 'fullname': names})
        send(list(filter(None, re.split(" |,", entry.metadata.contact))), [],
             "[AFP Submission] " + names, msg)

def submitted(entry):
    build_send_mail(entry, "mails/submitted.mail.tp")

def success(entry):
    build_send_mail(entry, "mails/success.mail.tp")

def failed(entry):
    build_send_mail(entry, "mails/failed.mail.tp")

def killed(entry):
    build_send_mail(entry, "mails/killed.mail.tp")

