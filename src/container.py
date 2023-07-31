#!/usr/bin/python3

import logging
import os
import shutil
import subprocess
import threading
import time

import lxc

import config
import mailer
from entry import Result

BASE = lxc.Container(config.BASE_CONTAINER)


class IsabelleRunner:
    """Executes Isabelle in the container"""

    def __init__(self, entry, archive, names, log, checks_f):
        self.entry = entry
        self.archive = archive
        self.result_writer = entry.result_writer()
        self.names = names
        self.log = log
        self.checks_f = checks_f

    def run(self):
        logging.basicConfig(stream=self.log,
                            format="%(message)s",
                            level=logging.INFO)
        logging.info("Extract archive")
        if not self.archive.extract(config.THEORY_DIR):
            logging.warning("Uploaded archive file seems to be broken.")
            self.result_writer(Result.FAILED)
            return
        os.environ["HOME"] = config.CONTAINER_DIR

        logging.info("Checking for hidden files")
        found = False
        for path, dirs, files in os.walk(config.THEORY_DIR):
            for dn in dirs:
                if dn.startswith("."):
                    logging.warning("Found hidden directory: " + os.path.join(path, dn))
                    found = True
            for fn in files:
                if fn.startswith("."):
                    logging.warning("Found hidden file: " + os.path.join(path, fn))
                    found = True
        if found:
            self.result_writer(Result.FAILED)
            return
        else:
            logging.info("Found no hidden files or directories")

        if not set(os.listdir(config.THEORY_DIR)) == set(self.names):
            logging.warning("Directory names do not correspond to entry names.")
            logging.warning("  Expected: " + ", ".join(self.names))
            logging.warning("  Got: " + ", ".join(os.listdir(config.THEORY_DIR)))

        def run_proc(proc):
            for line in proc.stdout:
                if not line.strip().startswith("Presenting "):
                    logging.info(line.strip())
            rc = proc.wait()
            if rc != 0:
                self.result_writer(Result.FAILED)
                return False
            else:
                return True

        logging.info("Running session checks...")

        with open(os.path.join(config.THEORY_DIR, "ROOTS"), mode='w') as f:
            f.write("\n".join(self.names))

        # TODO fix lxc problem
        # sleep to prevent spurious tmp error
        time.sleep(3)

        if not run_proc(subprocess.Popen(
                [config.ISABELLE_PATH, "afp_check_roots", "-D" + config.THEORY_DIR],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True)):
            return

        logging.info("Start Isabelle...")
        if not run_proc(subprocess.Popen(
                [config.ISABELLE_PATH, "build", "-d", "$AFP", "-d" + config.THEORY_DIR]
                + config.ISABELLE_SETTINGS
                + self.names,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True)):
            return

        logging.info("Checking AFP Guidelines...")
        if not run_proc(subprocess.Popen(
                [config.ISABELLE_PATH, "lint", "-d", "$AFP", "-d" + config.THEORY_DIR,
                 "-o", "lint_bundles=afp_mandatory", "-f", "error", "-r", "afp"]
                + self.names,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True)):
            return

        logging.info("Linting for maintainable and readable proofs...")
        run_proc(subprocess.Popen(
                [config.ISABELLE_PATH, "lint", "-d", "$AFP", "-d" + config.THEORY_DIR,
                 "-o", "lint_bundles=foundational,non_interactive_addon",
                 "-o", "lints_disabled=implicit_rule,lemma_transforming_attribute,auto_structural_composition",
                 "-r", "afp"]
                + self.names,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True))

        # All checks succeeded
        self.result_writer(Result.SUCCESS)


##TODO: catch ALL (yes, all) possible errors :)
class Container:
    def __init__(self, entry):
        self.entry = entry
        self.lxc = None
        self.thread = None

    def run(self):
        self.prepare()
        self.thread = threading.Thread(target=self.execute, name=self.entry.name, daemon=True)
        self.thread.start()

    def check(self):
        """Check if container is still running and if not perform final actions"""
        if self.entry.check_kill():
            self.stop()
            self.thread.join()
            self.thread = None
            rw = self.entry.result_writer()
            rw(Result.FAILED)
            self.finish()
            return False

        elif not self.thread.is_alive():
            self.finish()
            return False

        return True

    def path_in_container(self, path):
        # remove slash at the beginning of path
        path = path[1:] if path[0] == "/" else path
        return os.path.join(config.CONTAINERS_PATH, self.lxc.name, config.CONTAINER_ROOT, path)

    # PRIVATE

    def finish(self):
        self.mail()
        if config.CLEANUP_CONTAINER:
            self.lxc.destroy()
        print("Finished build: " + self.entry.name)

    def start(self):
        return self.lxc.start()

    def stop(self):
        return self.lxc.stop()

    def mail(self):
        s = self.entry.get_result()
        if s is Result.SUCCESS:
            mailer.success(self.entry)
        elif s is Result.FAILED:
            if self.entry.check_kill():
                mailer.killed(self.entry)
            else:
                mailer.failed(self.entry)

    def prepare(self):
        os.mkdir(self.entry.down())
        self.lxc = BASE.clone(self.entry.name, bdevtype="overlayfs", flags=lxc.LXC_CLONE_SNAPSHOT)
        self.start()
        self.lxc.attach_wait(self.setup_container_root_inside)
        self.stop()

    def setup_container_root_inside(self):
        # Fixes /etc/hosts
        with open("/etc/hosts", 'a') as f:
            f.write("127.0.1.1 {:s}".format(self.entry.name))

    # IN THREAD

    def execute(self):
        print("Start build: " + self.entry.name)
        mailer.submitted(self.entry)
        self.start()
        with self.entry.open_archive() as af, \
                open(self.entry.down("isabelle.log"), 'w', buffering=1) as l, \
                open(self.entry.down("checks.log"), 'w', buffering=1) as cl:
            runner = IsabelleRunner(self.entry, af, self.entry.metadata.entries, l, cl)
            self.lxc.attach_wait(runner.run, env_policy=lxc.LXC_ATTACH_CLEAR_ENV,
                                 uid=1000, gid=1000)
        self.stop()
        # Get browser_info out of container
        if self.entry.get_result() is Result.SUCCESS:
            dst = os.path.join(config.BROWSER_INFO_DIR, self.entry.name)
            shutil.copytree(self.path_in_container(config.ISABELLE_BROWSER_INFO), dst)
            # remove superfluous index.html
            try:
                os.remove(os.path.join(dst, "index.html"))
            except FileNotFoundError:
                pass
