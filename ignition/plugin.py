import os, sys
import shlex
import time

class Plugin(object):

	def __init__(self):
		pass

class Debug(Plugin):

	def __init__(self):
		super(Plugin, self).__init__()
		self._prefix = shlex.split("gdb --batch --quiet -ex run -ex \"bt\" -ex quit --args")

	def on_program_init(self, program, **kwargs):
		program.debug = kwargs.get("debug", False)
		if program.debug:
			program.command = self._prefix + program.command

	def on_program_start(self, program, **kwargs):
		if program.debug:
			program.announce("Entering debug mode: %s" % program.command)

class Wait(Plugin):

	def __init__(self):
		super(Plugin, self).__init__()

	def on_program_init(self, program, **kwargs):
		program.wait = kwargs.get("wait", 0)

	def on_program_started(self, program, **kwargs):
		wait = getattr(program, "wait", 0)
		if wait > 0:
			time.sleep(wait)

	def on_program_stopped(self, program, **kwargs):
		wait = getattr(program, "wait", 0)
		if wait > 0:
			time.sleep(wait)


