
import shlex
import time

_plugin_cache = {}

def plugin_registry():
    from attributee.containers import ReadonlyMapping
    from importlib.metadata import entry_points
    entrypoints = entry_points().get("ignition", {})
    
    # Only do this once
    if len(_plugin_cache) == 0:
        _plugin_cache["debug"] = Debug
        _plugin_cache["wait"] = Wait
        _plugin_cache["exportenv"] = ExportEnvironment

        for entrypoint in entrypoints:
            plugin = entrypoint.load()
            if issubclass(plugin, Plugin):
                _plugin_cache[entrypoint.name] = plugin

    return ReadonlyMapping(_plugin_cache)

def run_plugins(plugins, hook, *args):
    for plugin in plugins:
        if hasattr(plugin, hook):
            getattr(plugin, hook)(*args)

class Plugin(object):

    def __init__(self):
        pass

    def on_program_init(self, program):
        pass

    def on_program_start(self, program):
        pass

    def on_program_stop(self, program):
        pass

    def on_program_started(self, program):
        pass

    def on_program_stopped(self, program):
        pass

class Debug(Plugin):

    def __init__(self):
        super(Debug, self).__init__()
        # TODO: only if gdb is available?
        self._prefix = "gdb --batch --quiet -ex run -ex \"bt\" -ex quit --args  "

    def on_program_init(self, program):
        program._debug = program.auxiliary.get("debug", False)
        if program._debug:
            program.command = self._prefix + program.command

    def on_program_start(self, program):
        if program._debug:
            program.announce("Entering debug mode: %s" % program.command)

class Wait(Plugin):

    def __init__(self):
        super(Wait, self).__init__()

    def on_program_init(self, program):
        program._wait = program.auxiliary.get("wait", 0)

    def on_program_started(self, program):
        wait = getattr(program, "_wait", 0)
        if wait > 0:
            time.sleep(wait)

    def on_program_stopped(self, program):
        wait = getattr(program, "_wait", 0)
        if wait > 0:
            time.sleep(wait)

class ExportEnvironment(Plugin):

    def __init__(self):
        super(ExportEnvironment, self).__init__()

    def on_program_start(self, program):
        env = " ".join(["\"{}={}\"".format(k, v) for k, v in program.environment.items()])
        if not program.directory is None:
            program.announce("Directory: " + program.directory)
        program.announce("Environment: " + env)
