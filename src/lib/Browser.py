import tkinter 
import sys
import os
from .URL import URL
from .CSSParser import CSSParser, style, cascade_priority
from .HTMLParser import HTMLParser, HTMLSourceParser, Element
from .DocumentLayout import DrawText, DrawRect, DocumentLayout, BlockLayout, Dimensions

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))
SCROLL_STEP = 100
SCROLLBAR_OFFSET = 2

DEFAULT_STYLE_SHEET = CSSParser(
    open(
        os.path.join(BASE_DIR, "assets", "browser.css")
    ).read()
).parse()

class Browser:
    def __init__(self) -> None:
        self.dimensions = Dimensions(
            width=800,
            height=600,
            hstep=13,
            vstep=18,
        )
        self.images: list[tkinter.PhotoImage] = []
        self.window = tkinter.Tk()
        self.window.title("StrangeBrows")
        self.canvas = tkinter.Canvas(
            self.window,
            width=self.dimensions["width"],
            height=self.dimensions["height"],
            bg="white"
        )
        self.canvas.pack(fill="both", expand=1)
        self.display_list: list[DrawText | DrawRect] = []
        self.scroll = 0
        self.window.bind("<Up>", self.scrollup)
        self.window.bind("<Down>", self.scrolldown)
        self.window.bind("<Configure>", self.configure)
        # System dependent
        match sys.platform:
            case 'linux':
                self.window.bind("<Button-4>", self.scrollup)
                self.window.bind("<Button-5>", self.scrolldown)
            case 'darwin':
                self.window.bind("<MouseWheel>", self.scrollmousewheel_darwin)
            case 'win32':
                self.window.bind("<MouseWheel>", self.scrollmousewheel_win32)
            case _:
                raise Exception("Unsuported platform '{}'".format(sys.platform))

    # --- Event handlers
    def scrollup(self, e: tkinter.Event) -> None:
        self.scroll = max(self.scroll - SCROLL_STEP, 0)
        self.draw()

    def scrolldown(self, e: tkinter.Event) -> None:
        self.scroll = min(self.scroll + SCROLL_STEP, self.display_height())
        self.draw()

    def scrollmousewheel_win32(self, e: tkinter.Event) -> None:
        delta = int(e.delta / 120) * SCROLL_STEP * -1 # Resets win32 standart 120 step and invert
        if delta < 0: self.scroll = max(self.scroll + delta, 0)
        else: self.scroll = min(self.scroll + delta, self.display_height())
        self.draw()

    def scrollmousewheel_darwin(self, e: tkinter.Event) -> None:
        delta = e.delta * SCROLL_STEP # Resets darwin standart 1 step
        if delta < 0: self.scroll = max(self.scroll + delta, 0)
        else: self.scroll = min(self.scroll + delta, self.display_height())
        self.draw()

    def configure(self, e: tkinter.Event) -> None:
        if self.dimensions["width"] == e.width and self.dimensions["height"] == e.height: return
        self.dimensions["width"] = e.width
        self.dimensions["height"] = e.height
        self.document = DocumentLayout(self.nodes, self.dimensions)
        self.document.layout()
        self.display_list = []
        paint_tree(self.document, self.display_list)
        self.draw()

    # --- Functions
    def display_height(self) -> int:
        h = self.document.height - self.dimensions["height"] + self.dimensions["vstep"] * 2
        return max(0, h)

    def draw(self) -> None:
        self.canvas.delete("all")
        # Draws content
        for cmd in self.display_list:
            if cmd.top > self.scroll + self.dimensions["height"]: continue
            if cmd.bottom < self.scroll: continue
            cmd.execute(self.scroll, self.canvas)
        # Draws scrollbar
        dh = self.display_height()
        if dh > 0:
            ratio = int((self.scroll / dh) * (self.dimensions["height"] - self.dimensions["vstep"]))
            self.canvas.create_rectangle(
                self.dimensions['width'] - self.dimensions["hstep"] + SCROLLBAR_OFFSET,
                ratio + SCROLLBAR_OFFSET,
                self.dimensions["width"] - SCROLLBAR_OFFSET,
                ratio + self.dimensions["vstep"] - SCROLLBAR_OFFSET,
                fill="blue",
                width=0
            )

    def load(self, url: URL) -> None:
        body = url.request()
        if url.view_source:
            self.nodes = HTMLSourceParser(body).source()
        else:
            self.nodes = HTMLParser(body).parse()
        rules = DEFAULT_STYLE_SHEET.copy()
        links = [node.attributes["href"]
            for node in tree_to_list(self.nodes, [])
            if isinstance(node, Element)
            and node.tag == "link"
            and node.attributes.get("rel") == "stylesheet"
            and "href" in node.attributes]  
        for link in links:
            style_url = url.resolve(link)
            try:
                body = style_url.request()
            except:
                continue
            rules.extend(CSSParser(body).parse()) 
        style(self.nodes, sorted(rules, key=cascade_priority))
        self.document = DocumentLayout(self.nodes, self.dimensions)
        self.document.layout()
        self.display_list = []
        paint_tree(self.document, self.display_list)  
        self.draw()

def tree_to_list(tree, ls: list) -> list:
    ls.append(tree)
    for child in tree.children:
        tree_to_list(child, ls)
    return ls

def print_tree(node, indent=0) -> None:
    print(" " * indent, node)
    for child in node.children:
        print_tree(child, indent+2)

def paint_tree(layout_object: DocumentLayout | BlockLayout, display_list: list[DrawText | DrawRect]) -> None:
    display_list.extend(layout_object.paint())
    for child in layout_object.children:
        paint_tree(child, display_list)
