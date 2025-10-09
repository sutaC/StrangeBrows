#!/usr/bin/env python3
import sys
import sdl2
import ctypes
import multiprocessing
from lib.URL import URL
from lib.Browser import Browser

def mainloop(browser: Browser) -> None:
    event = sdl2.SDL_Event()
    while True:
        while sdl2.SDL_PollEvent(ctypes.byref(event)) != 0:
            match event.type:
                case sdl2.SDL_QUIT:
                    browser.handle_quit()
                    sdl2.SDL_Quit()
                    sys.exit()
                case sdl2.SDL_MOUSEBUTTONUP:
                    if event.button.button == sdl2.SDL_BUTTON_MIDDLE:
                        browser.handle_middle_click(event.button)
                    else:
                        browser.handle_click(event.button)
                case sdl2.SDL_MOUSEWHEEL:
                    browser.handle_scrollwheel(event.wheel.y)
                case sdl2.SDL_KEYDOWN:
                    match event.key.keysym.sym: 
                        case sdl2.SDLK_RETURN:
                            browser.handle_enter()
                        case sdl2.SDLK_BACKSPACE:
                            browser.handle_backspace()
                        case sdl2.SDLK_DOWN:
                            browser.handle_down()
                        case sdl2.SDLK_UP:
                            browser.handle_up()
                        case sdl2.SDLK_LEFT:
                            browser.handle_left()
                        case sdl2.SDLK_RIGHT:
                            browser.handle_right()
                        case sdl2.SDLK_n: # Ctrl-N
                            if event.key.keysym.mod & (sdl2.KMOD_LCTRL | sdl2.KMOD_RCTRL):
                                # Handles new window
                                p = multiprocessing.Process(target=main)
                                p.start()
                case sdl2.SDL_TEXTINPUT:
                    browser.handle_key(event.text.text.decode())
                case sdl2.SDL_WINDOWEVENT:
                    if event.window.event == sdl2.SDL_WINDOWEVENT_RESIZED:
                        w, h = event.window.data1, event.window.data2
                        browser.handle_configure(w, h)

def main() -> None:
    from argparse import ArgumentParser
    # Multiprocessing setup
    if not multiprocessing.get_start_method(True):
        multiprocessing.set_start_method("spawn")
    # Argument parsing
    parser = ArgumentParser(description="Simple web browser")
    parser.add_argument("url", type=str, help="Url to visit", nargs="?", default="")
    args = parser.parse_args()
    # Initialization
    sdl2.SDL_Init(sdl2.SDL_INIT_EVENTS)
    browser = Browser()
    browser.new_tab(URL(args.url))
    mainloop(browser)

if __name__ == "__main__":
    # Prevents argparse error on multiprocessing in prod build
    multiprocessing.freeze_support()
    main()