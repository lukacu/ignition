#!/usr/bin/env python

from distutils.core import setup

setup(name='Ignition',
	version='0.2',
	description='Run multiple programs in a specific order and monitor their state',
	author='Luka Cehovin Zajc',
	author_email='luka.cehovin@gmail.com',
	url='https://github.com/lukacu/ignition/',
	packages=['ignition'],
	scripts=["bin/ignite"],
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: BSD License",
        "Operating System :: OS Independent",
        "Development Status :: 4 - Beta",
    ],
    python_requires='>=3.5',
    requires=["attributee>=0.1.3"],
    entry_points={
        'console_scripts': [
            'ignite = ignition.__main__:main',
        ],
    },
)
