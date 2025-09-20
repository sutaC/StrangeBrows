import os
import sys

if hasattr(sys, '_MEIPASS'):
    # Running in a PyInstaller bundle
    BASE_DIR = sys._MEIPASS # type: ignore
else:
    # Running in normal Python (development mode)
    BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))
