# Shared standard-library imports used by the split modules.
import csv
import json
import os
import re
import sys
import select
import shutil
import subprocess
import builtins
import io
import ctypes
import webbrowser
import urllib.parse
import urllib.request
import urllib.error
from datetime import datetime
from collections import Counter

try:
    import termios
    import tty
except ImportError:
    termios = None
    tty = None

try:
    import msvcrt
except ImportError:
    msvcrt = None
