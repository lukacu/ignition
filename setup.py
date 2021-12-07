#!/usr/bin/env python

from distutils.core import setup
import setuptools

setup(name='ignition',
	version='0.2',
	description='Run multiple programs in a specific order and monitor their state',
	author='Luka Cehovin Zajc',
	author_email='luka.cehovin@gmail.com',
	url='https://github.com/lukacu/ignition/',
	packages=['ignition'],
	classifiers=[
	"Programming Language :: Python :: 3",
	"License :: OSI Approved :: BSD License",
	"Operating System :: OS Independent",
	"Development Status :: 4 - Beta",
	],
	python_requires='>=3.5',
	install_requires=["attributee>=0.1.3", "PyYAML>=6.0"],
		entry_points={
		'console_scripts': [
		    'ignite = ignition.__main__:main',
		],
	},
)
