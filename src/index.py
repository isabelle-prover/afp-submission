#!/usr/bin/python3
# -*- coding: utf-8 -*-
""" AFP Submission system -- CGI interface

This is the CGI interface to the AFP submission system.
"""

# Set locale. For some weird reason it is not set, when called with cgi and the
# encoding then defaults to ascii instead of utf-8.
import locale
locale.setlocale(locale.LC_ALL, 'C.UTF-8')

import config
import cgi

if config.DEBUG:
    import cgitb
    cgitb.enable()

import sys
import os
import os.path
import io
import datetime
import shutil
import configparser
import re
import shutil
import textwrap
import time
from datetime import datetime

import html

from jinja2 import Environment, FileSystemLoader

import mailer
from entry import Entry, Result, Metadata

def fill_template(vals, template_file):
    vals['config'] = config
    # load jinja environment, trim_blocks and lstrip_blocks lead to nicer
    # looking files
    j2_env = Environment(loader = FileSystemLoader(config.TEMPLATES),
                         trim_blocks = True,
                         lstrip_blocks = True)
    return j2_env.get_template(template_file).render(vals)

def print_html_form(metadata):
    print("Content-Type: text/html")
    print()
    tp_vals = {'contact': metadata.contact, 'comment': metadata.comment}
    tp_vals['entries'] = metadata.entries
    print(fill_template(tp_vals, "index.html.tp"))

def collect_form_per_entry(form):
    # find all metadata entries in form data
    keys_per_entry = ['title', 'shortname', 'author', 'topic',
                      'abstract', 'license']
    num_tables = []
    for s in form.getlist('numtable'):
        try:
            i = int(s)
            if i >= 0:
                num_tables.append(i)
        except ValueError:
            pass
    metadata_list = []
    for n in num_tables:
        form_data = dict()
        for k in keys_per_entry:
            input_field = form.getfirst(k + '_' + str(n))
            form_data[k] = (html.escape(input_field)
                            if input_field is not None else None)
        form_data['date'] = datetime.now().strftime("%Y-%m-%d")
        metadata_list.append(form_data)
    return metadata_list

def collect_form_data(form):
    form_data = dict()
    for k in ['comment', 'contact']:
        input_field = form.getfirst(k)
        form_data[k] = (html.escape(input_field)
                        if input_field is not None else None)
    return form_data

def get_archive_file(form):
    return (form['tar'] if 'tar' in form and form['tar'].filename else None)

def save_file(metadata, form_file):
    e = Entry.new(
        metadata,
        form_file.filename,
        form_file.file
    )
    print("Status: 302 New AFP Submission created")
    print("Location: " + e.link())
    print()

def mail_to_editors(e):
    if e.check_mail():
        return
    if e.get_result() != Result.SUCCESS:
        return
    tp_vals = dict()
    tp_vals["name"] = e.name
    tp_vals["submission_url"] = config.SUBMISSION_URL
    tp_vals["fullname"] = [d['title'] for d in e.metadata.entries][0]
    mailer.send(config.EDITORS,
                list(filter(None, re.split(" |,", e.metadata.contact))),
                "[AFP Submission] " + tp_vals["fullname"],
                fill_template(tp_vals, "mails/to_editors.mail.tp"))
    #create empty file "mail" to indicate sent mail
    e.signal_mail()

def show_meta(entry):
    print("Content-Type: text/plain")
    print()
    ini = configparser.SafeConfigParser()
    for sub_entry in entry.metadata.entries:
        entry_name = sub_entry['shortname']
        ini.add_section(entry_name)
        for keyname in ['title', 'author', 'topic']:
            ini.set(entry_name, keyname,
                    html.unescape(sub_entry[keyname]))
        if sub_entry['license'] != 'BSD':
             ini.set(entry_name, 'license', sub_entry['license'])
        try:
            ini.set(entry_name, 'date', sub_entry['date'])
        except KeyError:
            pass
        ini.set(entry_name, 'notify', entry.metadata.contact)
        abstract = textwrap.wrap(sub_entry['abstract'],
                                 break_on_hyphens = False,
                                 break_long_words = False)
        abstract = "\n" + "\n".join(abstract)
        ini.set(entry_name, 'abstract',
                html.unescape(abstract))
    #Replace tabs with two whitespaces
    #since configparser can only write to a file object, we use StringIO
    #the with statement is probably superfluous, but better safe than sorry
    with io.StringIO() as io_str:
        ini.write(io_str)
        out_str = io_str.getvalue()
        out_str = out_str.replace("\t", "  ")
        sys.stdout.write(out_str)


def show_log(entry):
    print("Content-Type: text/html")
    print()
    tp_vals = dict()
    tp_vals['entry'] = entry
    tp_vals['entries'] = entry.metadata.entries
    tp_vals['contact'] = entry.metadata.contact
    tp_vals['comment'] = entry.metadata.comment
    tp_vals['Result'] = Result
    tp_vals['result'] = entry.get_result()
    tp_vals['mail_sent'] = entry.check_mail()
    # read state and log
    try:
        with open(entry.down("isabelle.log"), 'r') as f:
            tp_vals['isalog'] = html.escape(f.read())
    except FileNotFoundError:
        pass
    # write html
    print(fill_template(tp_vals, "log.html.tp"))

def download_tar(entry):
    with entry.open_archive() as af:
        print("Content-Type: " + af.mime_type)
        print("Content-Disposition: attachment; filename=" + af.archive_name)
        print()
        #Flush so headers are before file
        sys.stdout.flush()
        shutil.copyfileobj(af.fileobj, sys.stdout.buffer)

def isabelle_log(entry):
    print("Content-Type: text/plain")
    print()
    try:
        with open(entry.down("isabelle.log"), 'r') as f:
            print(html.escape(f.read()))
    except FileNotFoundError:
        pass

def print_state(entry):
    print("Content-Type: text/plain")
    print()
    print(entry.get_result().name)

def print_checks(entry):
    print("Content-Type: text/plain")
    print()
    try:
        with open(entry.down("checks.log"), 'r') as f:
            print(f.read())
    except FileNotFoundError:
        pass

def return_404(name = None):
    print("Content-Type: text/html")
    print("Status: 404 Not Found")
    print()

    if name:
        print("Entry {} not available anymore.".format(name))
    else:
        print("Not Found")

def main():
    form = cgi.FieldStorage()
    name = form.getfirst('build')
    action = form.getfirst('action')
    if name:
        e = Entry.find(name)
        if e is None:
            return_404(name)
        elif action is None:
            show_log(e)
        elif action == "kill":
            e.signal_kill()
            show_log(e)
        elif action == "metadata":
            show_meta(e)
        elif action == "mail":
            mail_to_editors(e)
            show_log(e)
        elif action == "tar":
            download_tar(e)
        elif action == "isabelle_log":
            isabelle_log(e)
        elif action == "state":
            print_state(e)
        elif action == "checks":
            print_checks(e)
    else:
        form_data_super = collect_form_data(form)
        metadata = Metadata(collect_form_per_entry(form),
                            form_data_super['contact'],
                            form_data_super['comment'])
        archive = get_archive_file(form)
        if metadata.validate() and archive is not None:
            save_file(metadata, archive)
        else:
            print_html_form(metadata)

if __name__ == "__main__":
    main()

