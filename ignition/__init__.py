from __future__ import absolute_import

import os
import re
import sys
import time
import subprocess
import traceback
import threading
import signal
import json
import shlex

from .graph import toposort

# http://www.pixelbeat.org/programming/stdio_buffering/
BLACK, RED, GREEN, YELLOW, BLUE, MAGENTA, CYAN, WHITE = xrange(30, 38)
LIGHTBLACK, LIGHTRED, LIGHTGREEN, LIGHTYELLOW, LIGHTBLUE, LIGHTMAGENTA, LIGHTCYAN, LIGHTWHITE = xrange(
    90, 98)

# These are the escape sequences need to get colored ouput
RESET_SEQ = "\033[0m"
COLOR_SEQ = "\033[%dm"
BOLD_SEQ = "\033[1m"

if sys.platform == "linux" or sys.platform == "linux2":
    PLATFORM = "linux"
elif sys.platform == "darwin":
    PLATFORM = "osx"
elif sys.platform == "win32":
    PLATFORM = "windows"


def print_colored(message, color=BLACK, bold=False):
    if bold:
        sys.stdout.write(COLOR_SEQ % (color) + BOLD_SEQ)
    else:
        sys.stdout.write(COLOR_SEQ % (color))
    sys.stdout.write(message)
    sys.stdout.write(RESET_SEQ)


def clean_dictionary(dictionary, *keys):
    for key in keys:
        if key in dictionary:
            del dictionary[key]

def import_plugin(cl):
    d = cl.rfind(".")
    classname = cl[d+1:len(cl)]
    m = __import__(cl[0:d], globals(), locals(), [classname])
    return getattr(m, classname)()

def run_plugins(plugins, handle, *args, **kwargs):
    for plugin in plugins:
        if hasattr(plugin, handle):
            getattr(plugin, handle)(*args, **kwargs)

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
        print "Warning: user %s does not exist" % username 
        return (None, "")

def get_groupid(groupname):
    from grp import getgrnam
    if groupname is None:
        return (None, "")
    try:
        return (getgrnam(groupname).gr_gid, groupname)
    except KeyError:
        print "Warning: group %s does not exist" % groupname 
        return (None, "")

def prepare_and_demote(user_uid, user_gid):
    def result():
        os.setpgrp()
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

class ProgramHandler(object):

    mutex = threading.Lock()

    color_pool = (GREEN, YELLOW, BLUE, MAGENTA, CYAN, WHITE, LIGHTBLACK,
                  LIGHTRED, LIGHTGREEN, LIGHTYELLOW, LIGHTBLUE, LIGHTMAGENTA, LIGHTCYAN, LIGHTWHITE)
    color_next = 0

    def __init__(self, identifier, command, directory=None, environment={}, log=None,
        user=None, group=None, **kwargs):
        self.thread = threading.Thread(target=self.run)
        self.thread.daemon = True
        self.identifier = identifier
        self.command = shlex.split(expandvars(command, additional=environment))
        self.directory = expandvars(directory, additional=environment)
        self.required = kwargs.get("required", False)
        self.restart = kwargs.get("restart", False)
        self.running = False
        self.process = None
        self.log = log
        self.environment = os.environ.copy()
        self.environment.update(environment)
        self.console = kwargs.get("console", True)
        self.depends = kwargs.get("depends", [])
        self.user = get_userid(user)
        self.group = get_groupid(group)
        self.delay = kwargs.get("delay", 0)
        self.color = ProgramHandler.color_pool[
            ProgramHandler.color_next % len(ProgramHandler.color_pool)]
        ProgramHandler.color_next = ProgramHandler.color_next + 1
        if self.console and PLATFORM == "linux":
            self.command.insert(0, 'stdbuf')
            self.command.insert(1, '-oL')
        self.observers = []

        if not self.log is None:
            if not os.path.isdir(os.path.dirname(self.log)):
                os.makedirs(os.path.dirname(self.log))

        self.logfile = open(self.log, 'w') if not self.log is None else None
        self.attempts = 0



    def observe(self, observer):
        self.observers.append(observer)

    def start(self):
        if self.running:
            return
        self.thread.start()

    def run(self):
        self.running = True
        while self.running:
            returncode = 0
            try:
                self.attempts = self.attempts + 1
                self.announce("Starting program (attempt %d)" % self.attempts)

                preexec_fn = prepare_and_demote(self.user[0], self.group[0])
                self.process = subprocess.Popen(self.command, shell=False,
                                                bufsize=0, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                                env=self.environment, cwd=self.directory, preexec_fn=preexec_fn)

                self.announce("PID = %d" % self.process.pid)

                while True:
                    logline = self.process.stdout.readline()
                    if logline:
                        if self.console:
                            ProgramHandler.mutex.acquire()
                            print_colored(
                                "[%s]: " % self.identifier.ljust(20, ' '), self.color)
                            # new line is already present
                            sys.stdout.write(logline)
                            ProgramHandler.mutex.release()
                        if not self.logfile is None:
                            self.logfile.write(logline)
                    else:
                        break

                self.process.wait()

                returncode = self.process.returncode
            except OSError as err:
                self.announce("Error: %s" % str(err))

            if returncode != None:
                if returncode < 0:
                    self.announce("Program has stopped (signal %d)" % -returncode)
                else:
                    self.announce("Program has stopped (exit code %d)" % returncode)
            else:
                self.announce("Execution stopped because of an error")

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
        ProgramHandler.mutex.acquire()
        print_colored("[%s]: " % self.identifier.ljust(20, ' '), self.color)
        print message
        if not self.logfile is None:
            self.logfile.write(message)
            self.logfile.write("\n")
        ProgramHandler.mutex.release()

    def stop(self):
        if self.running:
            self.running = False
            try:
                if self.process:
                    self.process.terminate()  # send_signal(signal.CTRL_C_EVENT)
            except OSError:
                pass
        self.thread.join(1)

    def valid(self):
        # Is valid if it is running or it was not even executed
        return self.running or self.attempts == 0


class ProgramGroup(object):

    def __init__(self, launchfile, parent=None):
        config = json.load(open(launchfile, 'r'))
        self.source = launchfile
        self.title = config.get("title", os.path.basename(launchfile))
        self.log = config.get("log", parent.log if not parent is None else None)
        self.user = config.get("user", parent.user if not parent is None else None)
        self.group = config.get("group", parent.group if not parent is None else None)
        self.programs = {}
        self.parent = parent
        self.plugins = [import_plugin(p) for p in config.get("plugins", [])]
        self.environment = mergevars(parent.environment if parent else {}, config.get("environment", {}))
        self.depends = config.get("depends", [])
        programs = config.get("programs", {})

        for identifier, parameters in programs.items():
            if parameters.get("ignore", False):
                continue
            if parameters.has_key("include"):
                root = os.path.dirname(self.source)
                try:
                    item = ProgramGroup(os.path.join(root, parameters["include"]), self)
                except ValueError, e:
                    print "Error opening %s: %s" % (os.path.join(root, parameters["include"]), e)
                    raise ValueError("Unable to load included launch file")
            else:
                if not parameters.has_key("user"):
                    parameters["user"] = self.user
                if not parameters.has_key("group"):
                    parameters["group"] = self.group
                if not parameters.has_key("log") and not self.log is None:
                    parameters["log"] = os.path.join(self.log, "%s.log" % identifier)
                if not parameters.has_key("command"):
                    continue
                parameters["environment"] = mergevars(self.environment, parameters.get("environment", {}))
                item = ProgramHandler(identifier,
                                      **parameters)
                run_plugins(
                    self.plugins, 'on_program_init', item, **parameters)
            self.programs[identifier] = item

        clean_dictionary(config, "plugins", "handle")
        run_plugins(self.plugins, 'on_group_init', self, **config)

        graph = {}
        for i, program in self.programs.items():
            dependencies = set()
            for d in program.depends:
                if not d in self.programs:
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
                self.plugins, 'on_program_start', self.programs[item])
            self.programs[item].start()
            run_plugins(
                self.plugins, 'on_program_started', self.programs[item])
        run_plugins(self.plugins, 'on_group_started', self)

    def stop(self):
        run_plugins(self.plugins, 'on_group_stop', self)
        for item in reversed(self.startup_sequence):
            run_plugins(
                self.plugins, 'on_program_stop', self.programs[item])
            self.programs[item].stop()
            run_plugins(
                self.plugins, 'on_program_stopped', self.programs[item])
        run_plugins(self.plugins, 'on_group_stopped', self)

    def valid(self):
        valid = 0
        for program in self.programs.values():
            if program.valid():
                valid = valid + 1
            elif getattr(program, "required", True):
                return False
        return valid > 0

    def announce(self, message):
        print_colored(message, RED, True)
        print ""
