from __future__ import absolute_import

import os
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

    def __init__(self, identifier, command, directory=None, environment={}, **kwargs):
        self.thread = threading.Thread(target=self.run)
        self.thread.daemon = True
        self.identifier = identifier
        self.command = shlex.split(command)
        self.directory = directory
        self.required = kwargs.get("required", False)
        self.restart = kwargs.get("restart", False)
        self.running = False
        self.process = None
        self.environment = os.environ.copy()
        self.environment.update(environment)
        self.console = kwargs.get("console", True)
        self.depends = kwargs.get("depends", [])
        self.delay = kwargs.get("delay", 0)
        self.color = ProgramHandler.color_pool[
            ProgramHandler.color_next % len(ProgramHandler.color_pool)]
        ProgramHandler.color_next = ProgramHandler.color_next + 1
        if self.console and PLATFORM == "linux":
            self.command.insert(0, 'stdbuf')
            self.command.insert(1, '-oL')
        self.observers = []

    def observe(self, observer):
        self.observers.append(observer)

    def start(self):
        if self.running:
            return
        self.thread.start()

    def run(self):
        returncode = 0
        try:
            self.announce("Starting program")
            self.process = subprocess.Popen(self.command, shell=False,
                                            bufsize=0, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                            env=self.environment, cwd=self.directory)
            self.running = True

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
                else:
                    break

            self.process.wait()

            returncode = self.process.returncode
        except OSError as err:
            self.announce("Error: %s" % str(err))

        self.running = False

        if returncode != None:
            self.announce("Program has stopped (exit code %d)" % returncode)
        else:
            self.announce("Execution stopped because of an error")

    def announce(self, message):
        ProgramHandler.mutex.acquire()
        print_colored("[%s]: " % self.identifier.ljust(20, ' '), self.color)
        print message
        ProgramHandler.mutex.release()

    def stop(self):
        if self.process:
            try:
                self.process.terminate()  # send_signal(signal.CTRL_C_EVENT)
            except OSError:
                pass
        self.thread.join(1)

    def valid(self):
        # Is valid if it is running or it was not even executed
        return self.running or not self.process


class ProgramGroup(object):

    def __init__(self, launchfile, parent=None):
        config = json.load(open(launchfile, 'r'))
        self.source = launchfile
        self.programs = {}
        self.parent = parent
        self.plugins = [import_plugin(p) for p in config.get("plugins", [])]
        self.environment = parent.environment.copy() if parent else {}
        self.environment.update(config.get("environment", {}))
        programs = config.get("programs", {})
        for identifier, parameters in programs.items():
            if parameters.get("ignore", False):
                continue
            if isinstance(parameters, basestring):
                root = os.path.dirname(self.source)
                try:
                    item = ProgramGroup(os.path.join(root, parameters), self)
                except ValueError, e:
                    print "Error opening %s: %s" % (os.path.join(root, parameters), e)
                    raise ValueError("Unable to load included launch file")
            else:
                if not parameters.has_key("command"):
                    continue
                tmpenv = parameters.get("environment", {})
                parameters["environment"] = self.environment.copy()
                parameters["environment"].update(tmpenv)
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
        print blocks

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
            # print program.identifier, program.healthy()
            if program.valid():
                valid = valid + 1
            elif getattr(program, "required", True):
                return False
        return valid > 0

    def announce(self, message):
        print_colored(message, RED, True)
        print ""
