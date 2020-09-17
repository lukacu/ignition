
import shlex
import time

class Plugin(object):

    def __init__(self):
        pass

class Debug(Plugin):

    def __init__(self):
        super(Debug, self).__init__()
        self._prefix = shlex.split("gdb --batch --quiet -ex run -ex \"bt\" -ex quit --args")

    def on_program_init(self, program, **kwargs):
        program._debug = kwargs.get("debug", False)
        if program._debug:
            program.command = self._prefix + program.command

    def on_program_start(self, program, **kwargs):
        if program._debug:
            program.announce("Entering debug mode: %s" % program.command)

class Wait(Plugin):

    def __init__(self):
        super(Wait, self).__init__()

    def on_program_init(self, program, **kwargs):
        program._wait = kwargs.get("wait", 0)

    def on_program_started(self, program, **kwargs):
        wait = getattr(program, "_wait", 0)
        if wait > 0:
            time.sleep(wait)

    def on_program_stopped(self, program, **kwargs):
        wait = getattr(program, "_wait", 0)
        if wait > 0:
            time.sleep(wait)

class ExportEnvironment(Plugin):

    def __init__(self):
        super(ExportEnvironment, self).__init__()

    def on_program_start(self, program, **kwargs):
        env = " ".join(["\"{}={}\"".format(k, v) for k, v in program.environment.items()])
        if not program.directory is None:
            program.announce("Directory: " + program.directory)
        program.announce("Environment: " + env)
