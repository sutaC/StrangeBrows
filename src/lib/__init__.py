import sys
from pathlib import Path
from tkinter import PhotoImage

if hasattr(sys, '_MEIPASS'):
    # Running in a PyInstaller bundle
    BASE_DIR = sys._MEIPASS # type: ignore
else:
    # Running in normal Python (development mode) - root directoy of project
    BASE_DIR = Path(__file__).parent.parent.parent

COOKIE_JAR: dict[str, tuple[str, dict[str, str]]] = {}
IMAGE_CACHE: dict[str, PhotoImage] = {}