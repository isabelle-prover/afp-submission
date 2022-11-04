#!/usr/bin/python3

import os
import re
import smtplib
import ssl
from email.mime.text import MIMEText
from email.utils import formatdate

from jinja2 import Environment, FileSystemLoader

import config
from entry import AFPStatus


def email_regex(addr):
    # Regex doesn't allow all valid addresses, but should be good enough for us
    return re.match(r"(^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$)", addr)


def send(tos, ccs, subject, text):
    try:
        if config.MAILSSL:
            smtp = smtplib.SMTP_SSL(host=config.MAILSERVER, port=config.MAILSERVERPORT,
                                    context=ssl.create_default_context())
            smtp.login(config.MAILUSER, config.MAILPASS)
        else:
            smtp = smtplib.SMTP(host=config.MAILSERVER, port=config.MAILSERVERPORT)
    except (smtplib.SMTPException, ssl.SSLError, ConnectionError):
        print("Connection to Mailserver or Authentication on Mailserver failed")
        return
    msg = MIMEText(text)
    msg['Subject'] = subject
    msg['From'] = config.FROM
    msg['Sender'] = config.SENDER
    msg['Date'] = formatdate(localtime=True)
    try:
        if all([email_regex(r) for r in tos + ccs]):
            msg['To'] = ",".join(tos)
            msg['CC'] = ",".join(ccs)
            msg['BCC'] = ",".join(config.ADMINS)
            smtp.sendmail(config.SENDER, tos + config.ADMINS + ccs, msg.as_string())
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
        names = " + ".join(entry.metadata.entries)
        msg = f.read().format(**{'link': link, 'fullname': names})
        send(entry.metadata.contact, [], "[AFP Submission] " + names, msg)


def fill_template(vals, template_file):
    vals['config'] = config
    # load jinja environment, trim_blocks and lstrip_blocks lead to nicer
    # looking files
    j2_env = Environment(loader=FileSystemLoader(config.TEMPLATES),
                         trim_blocks=True,
                         lstrip_blocks=True)
    return j2_env.get_template(template_file).render(vals)


def mail_to_editors(entry):
    tp_vals = dict()
    tp_vals["name"] = entry.name
    tp_vals["link"] = entry.link()
    tp_vals["fullname"] = entry.metadata.entries[0]
    # set status to submitted (even if mail fails)
    entry.signal_afp(AFPStatus.SUBMITTED)
    send(config.EDITORS, entry.metadata.contact, "[AFP Submission] " + tp_vals["fullname"],
         fill_template(tp_vals, "mails/to_editors.mail.tp"))


def submitted(entry):
    build_send_mail(entry, "mails/submitted.mail.tp")


def success(entry):
    build_send_mail(entry, "mails/success.mail.tp")


def failed(entry):
    build_send_mail(entry, "mails/failed.mail.tp")


def killed(entry):
    build_send_mail(entry, "mails/killed.mail.tp")
