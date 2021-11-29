from __future__ import absolute_import

import os
import sys

def is_linux():
    return sys.platform == "linux" or sys.platform == "linux2"

def is_mac():
    return sys.platform == "darwin"

def is_windows():
    return sys.platform == "win32" or sys.platform == "win64"

