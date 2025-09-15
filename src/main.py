#!/usr/bin/env python3
import tkinter
from argparse import ArgumentParser
from lib.Browser import Browser
from lib.URL import URL

if __name__ == "__main__":
    parser = ArgumentParser(description="Simple web browser")
    parser.add_argument("url", type=str, help="Url to visit", nargs="?", default="")
    args = parser.parse_args()
    Browser().new_tab(URL(args.url))
    tkinter.mainloop()