import os, sys
import shlex

class Plugin(object):

	def __init__(self):
		pass

class DebugWrapper(Plugin):

	def __init__(self):
		super(Plugin, self).__init__()
		self._prefix = shlex.split("gdb --batch --quiet -ex run -ex \"bt\" -ex quit --args")

	def on_program_init(self, program, **kwargs):
		program.debug = kwargs.get("debug", False)
		if program.debug:
			program.command = self._prefix + program.command

