import sys
from pathlib import Path

if hasattr(sys, '_MEIPASS'):
    # Running in a PyInstaller bundle
    BASE_DIR = sys._MEIPASS # type: ignore
else:
    # Running in normal Python (development mode) - root directoy of project
    BASE_DIR = Path(__file__).parent.parent.parent
