import os
import tkinter
from .Draw import Draw
from .URL import URL
from .CSSParser import CSSParser, style, cascade_priority
from .HTMLParser import HTMLParser, HTMLSourceParser, Element, Text
from .DocumentLayout import Dimensions, DocumentLayout, BlockLayout, LineLayout, TextLayout

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))
SCROLL_STEP = 100
SCROLLBAR_OFFSET = 2


DEFAULT_STYLE_SHEET = CSSParser(
    open(
        os.path.join(BASE_DIR, "assets", "browser.css")
    ).read()
).parse()

class Tab:
    def __init__(self, dimesnions: Dimensions) -> None:       
        self.url: URL
        self.dimensions: Dimensions = dimesnions
        self.images: list[tkinter.PhotoImage] = []
        self.display_list: list[Draw] = []
        self.scroll = 0
        self.history: list[URL] = []
        
    # --- Event handlers
    def scrollup(self) -> None:
        self.scroll = max(self.scroll - SCROLL_STEP, 0)

    def scrolldown(self) -> None:
        self.scroll = min(self.scroll + SCROLL_STEP, self.display_height())

    def scrollmousewheel_win32(self, delta: int) -> None:
        delta = int(delta / 120) * SCROLL_STEP * -1 # Resets win32 standart 120 step and invert
        if delta < 0: self.scroll = max(self.scroll + delta, 0)
        else: self.scroll = min(self.scroll + delta, self.display_height())

    def scrollmousewheel_darwin(self, delta: int) -> None:
        delta *= SCROLL_STEP # Resets darwin standart 1 step
        if delta < 0: self.scroll = max(self.scroll + delta, 0)
        else: self.scroll = min(self.scroll + delta, self.display_height())

    def configure(self) -> None:
        self.document = DocumentLayout(self.nodes, self.dimensions)
        self.document.layout()
        self.display_list = []
        paint_tree(self.document, self.display_list)

    def click(self, x: int, y: int) -> None:
        y += self.scroll
        objs: list[BlockLayout] = [obj for obj in tree_to_list(self.document, []) 
            if obj.x <= x < obj.x + obj.width
            and obj.y <= y < obj.y + obj.height
        ]
        if not objs: return
        elt: Element | Text | None = objs[-1].node if not isinstance(objs[-1].node, list) else objs[-1].node[-1]
        while elt:
            if isinstance(elt, Text):
                pass
            elif elt.tag == "a" and "href" in elt.attributes:
                url = self.url.resolve(elt.attributes["href"])
                return self.load(url)
            elt = elt.parent

    # --- Functions
    def display_height(self) -> int:
        h = self.document.height - self.dimensions["height"] + self.dimensions["vstep"] * 2
        return max(0, h)

    def draw(self, canvas: tkinter.Canvas, offset: int) -> None:
        # Draws content
        for cmd in self.display_list:
            if cmd.rect.top > self.scroll + self.dimensions["height"]: continue
            if cmd.rect.bottom < self.scroll: continue
            cmd.execute(self.scroll - offset, canvas)
        # Draws scrollbar
        dh = self.display_height()
        if dh > 0:
            ratio = int((self.scroll / dh) * (self.dimensions["height"] - self.dimensions["vstep"]))
            canvas.create_rectangle(
                self.dimensions['width'] - self.dimensions["hstep"] + SCROLLBAR_OFFSET,
                ratio + SCROLLBAR_OFFSET + offset,
                self.dimensions["width"] - SCROLLBAR_OFFSET,
                ratio + self.dimensions["vstep"] - SCROLLBAR_OFFSET + offset,
                fill="blue",
                width=0
            )

    def load(self, url: URL) -> None:
        self.history.append(url)
        self.url = url
        self.scroll = 0
        body = url.request()
        if url.view_source:
            self.nodes = HTMLSourceParser(body).source()
        else:
            self.nodes = HTMLParser(body).parse()
        rules = DEFAULT_STYLE_SHEET.copy()
        sheets: list[Element] = []
        # Gathering style sheets
        for node in tree_to_list(self.nodes, []):
            if (isinstance(node, Element) \
            and node.tag == "link" \
            and node.attributes.get("rel") == "stylesheet" \
            and "href" in node.attributes) \
            or (isinstance(node, Element) \
            and node.tag == "style"):
                sheets.append(node)
        # Parsing style sheets
        for node in sheets:
            body = ""
            if node.tag == "link":
                style_url = url.resolve(node.attributes["href"])
                try: body = style_url.request()
                except: continue
            elif node.tag == "style":
                for child in node.children:
                    if isinstance(child, Text):
                        body += child.text
            rules.extend(CSSParser(body).parse())
        # Styling
        style(self.nodes, sorted(rules, key=cascade_priority))
        self.document = DocumentLayout(self.nodes, self.dimensions)
        self.document.layout()
        self.display_list = []
        paint_tree(self.document, self.display_list)

    def go_back(self) -> None:
        if len(self.history) > 1:
            self.history.pop()
            back = self.history.pop()
            self.load(back)

def tree_to_list(tree, ls: list) -> list:
    ls.append(tree)
    for child in tree.children:
        tree_to_list(child, ls)
    return ls

def print_tree(node, indent=0) -> None:
    print(" " * indent, node)
    for child in node.children:
        print_tree(child, indent+2)

def paint_tree(
layout_object: DocumentLayout | BlockLayout | LineLayout | TextLayout, 
display_list: list[Draw]) -> None:
    display_list.extend(layout_object.paint())
    for child in layout_object.children:
        paint_tree(child, display_list)
