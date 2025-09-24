import sys
import tkinter 
import multiprocessing
from .URL import URL
from .Tab import Tab
from .Chrome import Chrome
from .Layout import Dimensions

class Browser:
    def __init__(self) -> None:
        self.active_tab: Tab
        self.tabs: list[Tab] = []
        self.dimensions = Dimensions(
            width=800,
            height=600,
            hstep=13,
            vstep=18,
        )
        self.window = tkinter.Tk()
        self.window.title("StrangeBrows")
        self.canvas = tkinter.Canvas(
            self.window,
            width=self.dimensions["width"],
            height=self.dimensions["height"],
            bg="white"
        )
        self.canvas.pack(fill="both", expand=1)
        self.window.bind("<Up>", self.handle_scrollup)
        self.window.bind("<Down>", self.handle_scrolldown)
        self.window.bind("<Left>", self.handle_left)
        self.window.bind("<Right>", self.handle_right)
        self.window.bind("<Configure>", self.handle_configure)
        self.window.bind("<Button-1>", self.handle_click)
        self.window.bind("<Button-2>", self.handle_middle_click)
        self.window.bind("<Key>", self.handle_key)
        self.window.bind("<Return>", self.handle_enter)
        self.window.bind("<BackSpace>", self.handle_backspace)
        self.window.bind("<Control-n>", self.handle_new_window)
        # System dependent
        match sys.platform:
            case 'linux':
                self.window.bind("<Button-4>", self.handle_scrollup)
                self.window.bind("<Button-5>", self.handle_scrolldown)
            case 'darwin':
                self.window.bind("<MouseWheel>", self.handle_scrollmousewheel_darwin)
            case 'win32':
                self.window.bind("<MouseWheel>", self.handle_scrollmousewheel_win32)
            case _:
                raise Exception("Unsuported platform '{}'".format(sys.platform))
        # ---
        self.chrome: Chrome = Chrome(self)
        self.dimensions["height"] -= self.chrome.bottom
        self.focus: str | None = None
        # Multiprocessing setup
        if not multiprocessing.get_start_method(True):
            multiprocessing.set_start_method("spawn")

    def handle_scrollup(self, e: tkinter.Event) -> None:
        self.active_tab.scrollup()
        self.draw()

    def handle_scrolldown(self, e: tkinter.Event) -> None:
        self.active_tab.scrolldown()
        self.draw()

    def handle_scrollmousewheel_win32(self, e: tkinter.Event) -> None:
        self.active_tab.scrollmousewheel_win32(e.delta)
        self.draw()

    def handle_scrollmousewheel_darwin(self, e: tkinter.Event) -> None:
        self.active_tab.scrollmousewheel_darwin(e.delta)
        self.draw()

    def handle_configure(self, e: tkinter.Event) -> None:
        if self.dimensions["width"] == e.width \
        and self.dimensions["height"] == e.height + self.chrome.bottom: return
        self.dimensions["width"] = e.width
        self.dimensions["height"] = e.height - self.chrome.bottom
        self.active_tab.configure()
        self.chrome.configure()
        self.draw()

    def handle_click(self, e: tkinter.Event) -> None:
        if e.y < self.chrome.bottom:
            self.focus = None
            self.chrome.click(e.x, e.y)
        else:
            self.focus = "content"
            self.chrome.blur()
            tab_y = e.y - self.chrome.bottom
            self.active_tab.click(e.x, tab_y)
        self.draw()

    def handle_middle_click(self, e: tkinter.Event) -> None:
        if e.y < self.chrome.bottom: return
        tab_y = e.y - self.chrome.bottom
        url = self.active_tab.middle_click(e.x, tab_y)
        if not url: return
        self.new_tab(url)

    def handle_key(self, e: tkinter.Event) -> None:
        if len(e.char) == 0: return
        if not (0x20 <= ord(e.char) < 0x7f): return
        if self.chrome.keypress(e.char):
            self.draw()
        elif self.focus == "content":
            self.active_tab.keypress(e.char)
            self.draw()

    def handle_enter(self, e: tkinter.Event) -> None:
        self.chrome.enter()
        self.draw()

    def handle_backspace(self, e: tkinter.Event) -> None:
        self.chrome.backspace()
        self.draw()

    def handle_left(self, e: tkinter.Event) -> None:
        self.chrome.left()
        self.draw()

    def handle_right(self, e: tkinter.Event) -> None:
        self.chrome.right()
        self.draw()

    def draw(self) -> None:
        self.canvas.delete("all")
        self.active_tab.draw(self.canvas, self.chrome.bottom)
        for cmd in self.chrome.paint():
            cmd.execute(0, self.canvas)
    
    def new_tab(self, url: URL) -> None:
        new_tab = Tab(self.dimensions)
        new_tab.load(url)
        self.active_tab = new_tab
        self.tabs.append(new_tab)
        self.draw()
        self.update_title()
        
    def update_title(self) -> None:
        title = self.active_tab.page_title()
        if title is not None:
            self.window.title("{} – StrangeBrows".format(title))
        else:
            self.window.title("StrangeBrows")

    def handle_new_window(self, e: tkinter.Event) -> None:
        p = multiprocessing.Process(target=create_new_window)
        p.start()

def create_new_window() -> None:
    Browser().new_tab(URL(""))
    tkinter.mainloop()