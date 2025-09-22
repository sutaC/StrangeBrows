#!/usr/bin/env python3
import tkinter
from lib.Browser import Browser
from lib.URL import URL

def main() -> None:
    from argparse import ArgumentParser
    parser = ArgumentParser(description="Simple web browser")
    parser.add_argument("url", type=str, help="Url to visit", nargs="?", default="")
    args = parser.parse_args()
    Browser().new_tab(URL(args.url))
    tkinter.mainloop()

if __name__ == "__main__":
    from multiprocessing import freeze_support
    # Prevents argparse error on multiprocessing in prod build
    freeze_support()
    main()