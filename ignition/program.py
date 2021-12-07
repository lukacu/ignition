
import os
import re
import sys
import time, datetime
import subprocess
import threading
import json
import shlex

from typing import Optional

from attributee import Attributee, Include, List
from attributee.containers import Map
from attributee.object import Object
from attributee.primitives import Boolean, Integer, String
from attributee.io import Serializable

from . import is_linux
from .graph import toposort
from .output import print_colored, RED, GREEN, YELLOW, BLUE, MAGENTA, CYAN, WHITE, LIGHTBLACK, LIGHTRED, LIGHTGREEN, LIGHTYELLOW, LIGHTBLUE, LIGHTMAGENTA, LIGHTCYAN, LIGHTWHITE
from .plugin import run_plugins, Plugin

def clean_dictionary(dictionary, *keys):
    for key in keys:
        if key in dictionary:
            del dictionary[key]

def expandvars(path, default=None, additional={}, skip_escaped=True):
    """Expand environment variables of form $var and ${var}.
       If parameter 'skip_escaped' is True, all escaped variable references
       (i.e. preceded by backslashes) are skipped.
       Unknown variables are set to 'default'. If 'default' is None,
       they are left unchanged.
    """
    if not path:
        return path
    def replace_var(m):
        varname = m.group(2) or m.group(1)
        if additional and varname in additional:
            return additional[varname]
        return os.environ.get(varname, m.group(0) if default is None else default)
    reVar = (r'(?<!\\)' if skip_escaped else '') + r'\$(\w+|\{([^}]*)\})'
    return re.sub(reVar, replace_var, path)

def mergevars(base, update):
    result = dict(base)
    for var in update.keys():
        additional = dict(update)
        del additional[var]
        env = dict(base)
        env.update(additional)
        result[var] = expandvars(update[var], additional=env)
    return result

def get_userid(username):
    from pwd import getpwnam
    if username is None:
        return (None, "")
    try:
        return (getpwnam(username).pw_uid, username)
    except KeyError:
        print("Warning: user %s does not exist" % username)
        return (None, "")

def get_groupid(groupname):
    from grp import getgrnam
    if isinstance(groupname, list):
        gids = [get_groupid(g)[0] for g in groupname]
        if len(gids) == 0:
            return (None, "", [])
        return (gids[0], groupname, gids[1:])
    if groupname is None:
        return (None, "", [])
    try:
        return (getgrnam(groupname).gr_gid, groupname, [])
    except KeyError:
        print("Warning: group %s does not exist" % groupname)
        return (None, "", [])

def prepare_and_demote(user_uid, user_gid, user_groups=[]):
    def result():
        os.setpgrp()
        if len(user_groups) > 0:
            os.setgroups(user_groups)
        if not user_gid is None:
            os.setgid(user_gid)
        if not user_uid is None:
            os.setuid(user_uid)
    return result


class ProgramObserver(object):

    def on_start(self, program):
        pass

    def on_stop(self, program):
        pass

class ProgramHandler(Attributee):

    command = String()
    directory = String(default=None)
    environment = Map(String())

    required = Boolean(default=False)
    restart = Boolean(default=False)

    user = String(default=None)
    group = String(default=None)
    console = String(default=None)
    depends = List(String(), default=[])
    log = String(default=None)
    logappend = Boolean(default=False)

    delay = Integer(val_min=0, default=0)

    mutex = threading.Lock()
    color_pool = (GREEN, YELLOW, BLUE, MAGENTA, CYAN, WHITE, LIGHTBLACK,
                  LIGHTRED, LIGHTGREEN, LIGHTYELLOW, LIGHTBLUE, LIGHTMAGENTA, LIGHTCYAN, LIGHTWHITE)
    color_next = 0

    def __init__(self, *args, _identifier: str = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.thread = threading.Thread(target=self.run)
        self.thread.daemon = True
        self.identifier = _identifier
        self.running = False
        self.process = None

        self._user_id = get_userid(self.user)
        self._group_id = get_groupid(self.group)
        self.color = ProgramHandler.color_pool[
            ProgramHandler.color_next % len(ProgramHandler.color_pool)]
        ProgramHandler.color_next = ProgramHandler.color_next + 1
        self.observers = []
        self.attempts = 0
        self.logfile = None

    def observe(self, observer):
        self.observers.append(observer)

    def start(self):
        if self.running:
            return
        self.thread.start()

    def run(self):
        self.running = True

        if not self.log is None:
            if not os.path.isdir(os.path.dirname(self.log)):
                os.makedirs(os.path.dirname(self.log))

        environment = os.environ.copy()
        environment.update(self.environment)

        environment = {k: expandvars(v) for k, v in environment.items()}

        if self.logappend:
            self.logfile = open(self.log, 'w') if not self.log is None else None
        else:
            self.logfile = open(self.log, 'a') if not self.log is None else None
            if not self.logfile is None:
                self.logfile.write("\n----- Starting log at %s ------\n\n" % datetime.datetime.now())

        while self.running:
            returncode = None
            try:
                self.attempts = self.attempts + 1
                self.announce("Starting program (attempt %d)" % self.attempts)

                full_command = shlex.split(expandvars(self.command, additional=environment))
                full_directory = expandvars(self.directory if self.directory is not None else os.curdir, additional=environment)

                if self.console and is_linux():
                    full_command.insert(0, 'stdbuf')
                    full_command.insert(1, '-oL')

                preexec_fn = prepare_and_demote(self._user_id[0], self._group_id[0], self._group_id[2])

                self.process = subprocess.Popen(full_command, shell=False,
                                                bufsize=0, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                                env=environment, cwd=full_directory, preexec_fn=preexec_fn)

                self.announce("PID = %d" % self.process.pid)

                while True:
                    logline = self.process.stdout.readline()
                    if logline:
                        logline = logline.decode("utf-8")
                        if self.console:
                            ProgramHandler.mutex.acquire()
                            print_colored(
                                "[%s]: " % self.identifier.ljust(20, ' '), self.color)
                            # new line is already present
                            sys.stdout.write(logline)
                            ProgramHandler.mutex.release()
                        if not self.logfile is None:
                            self.logfile.write(logline)
                            self.logfile.flush()
                    else:
                        break

                self.process.wait()

                returncode = self.process.returncode
            except OSError as err:
                returncode = None
                self.announce("Error: %s" % str(err))

            if returncode != None:
                if returncode < 0:
                    self.announce("Program has stopped (signal %d)" % -returncode)
                else:
                    self.announce("Program has stopped (exit code %d)" % returncode)
            else:
                self.announce("Execution stopped because of an error")

            self.process = None

            if not self.running:
                break

            if self.restart is False:
                break

            if not self.restart is True and self.restart == self.attempts:
                self.announce("Maximum numer of attempts reached, giving up.")
                break

            self.announce("Restarting program.")
            time.sleep(1)

    def announce(self, message):
        with ProgramHandler.mutex:
            print_colored("[%s]: " % self.identifier.ljust(20, ' '), self.color)
            print(message)
            if hasattr(self, "logfile") and not self.logfile is None:
                self.logfile.write(message)
                self.logfile.write("\n")

    def stop(self, force=False):
        if self.running and not force:
            self.running = False
            try:
                if self.process:
                    self.announce("Stopping program.")
                    self.process.terminate()  # send_signal(signal.CTRL_C_EVENT)
            except OSError:
                pass
            self.thread.join(5)
        try:
            if self.process:
                self.announce("Escalating, killing program.")
                self.process.kill()
        except OSError:
            pass

    def valid(self):
        # Is valid if it is running or it was not even executed
        return self.running or self.attempts == 0

class ProgramDescription(Include):

    def __init__(self):
        super().__init__(ProgramHandler)

    def coerce(self, value, context):
        if value is None:
            return None
        kwargs = dict(value.items())
        kwargs.setdefault("user", context.parent.user)
        kwargs.setdefault("group", context.parent.group)
        if context.parent.log is not None:
            kwargs.setdefault("log", os.path.join(context.parent.log, "%s.log" % context.key))

        kwargs["environment"] = mergevars(context.parent.environment, kwargs.get("environment", {}))

        if "include" in kwargs:
            include = kwargs["include"]
            root = os.path.dirname(context.parent.source)
            try:
                item = ProgramGroup.read(os.path.join(root, include), _parent=self, **kwargs)
                item.depends = include.depends
            except ValueError as e:
                print("Error opening %s: %s" % (os.path.join(root, include), e))
                raise ValueError("Unable to load included launch file")
        #else:
        #    kwargs.setdefault("logappend", context.parent.logappend)

        return self._acls(**kwargs, _identifier=context.key)

    def dump(self, value: "Attributee"):
        return super().dump(value)

class ProgramGroup(Attributee, Serializable):

    title = String(default="")
    description = String(default="")
    log = String(default=None)
    user = String(default=None)
    group = String(default=None)
    environment = Map(String())
    plugins = List(Object(subclass=Plugin), default=[])
    programs = Map(ProgramDescription())

    def __init__(self, *args, _source: str = None, **kwargs):
        super().__init__(*args, **kwargs)
        self._programs = {}
        self._source = _source

        for identifier, item in self.programs.items():
            if getattr(item, "ignore", False):
                continue
            self._programs[identifier] = item
            run_plugins(self.plugins, 'on_program_init', item)

        run_plugins(self.plugins, 'on_group_init', self)

        graph = {}
        for i, program in self._programs.items():
            dependencies = set()
            for d in program.depends:
                if not d in self._programs:
                    raise ValueError("Dependency %s not defined" % d)
                dependencies.add(d)
            graph[i] = dependencies

        blocks = toposort(graph)
        sequence = []
        for block in blocks:
            sequence.extend(list(block))

        self.startup_sequence = sequence

    def start(self):
        run_plugins(self.plugins, 'on_group_start', self)
        for item in self.startup_sequence:
            run_plugins(
                self.plugins, 'on_program_start', self._programs[item])
            self._programs[item].start()
            run_plugins(
                self.plugins, 'on_program_started', self._programs[item])
        run_plugins(self.plugins, 'on_group_started', self)

    def stop(self, force=False):
        run_plugins(self.plugins, 'on_group_stop', self)
        for item in reversed(self.startup_sequence):
            run_plugins(
                self.plugins, 'on_program_stop', self._programs[item])
            self._programs[item].stop(force)
            run_plugins(
                self.plugins, 'on_program_stopped', self._programs[item])
        run_plugins(self.plugins, 'on_group_stopped', self)

    def valid(self):
        valid = 0
        for program in self._programs.values():
            if program.valid():
                valid = valid + 1
            elif getattr(program, "required", True):
                return False
        return valid > 0

    def announce(self, message):
        print_colored(message, RED, True)
        print("")

    @property
    def source(self):
        return self._source
