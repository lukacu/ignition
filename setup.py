#!/usr/bin/env python

from distutils.core import setup

setup(name='Ignition',
	version='0.1.8',
	description='Run multiple programs in a specific order and monitor their state',
	author='Luka Cehovin',
	author_email='luka.cehovin@gmail.com',
	url='https://github.com/lukacu/ignition/',
	packages=['ignition'],
	scripts=["bin/ignite"],
    requires=[],
)
