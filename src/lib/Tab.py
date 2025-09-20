import os
import tkinter
from .URL import URL
from .Draw import Draw
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
        self.forward_history: list[URL] = []
        
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

    def middle_click(self, x: int, y: int) -> URL | None:
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
                return self.url.resolve(elt.attributes["href"])
            elt = elt.parent
        return None

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
                href = elt.attributes["href"]
                if href.startswith("#"): # Fragment link support
                    self.url.fragment = href[1:]
                    node = find_node_by_id(self.url.fragment, self.document)
                    if node is not None: 
                        self.scroll = node.y
                        self.scrollmousewheel_darwin(0) # Prevents overscroll
                else:
                    url = self.url.resolve(href)
                    self.clear_forward()
                    self.load(url)
                return
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
        self.scroll = 0
        self.history.append(url)
        self.url = url
        self.url.storage.add_history(str(self.url))
        body = self.url.request()
        if self.url.view_source:
            self.nodes = HTMLSourceParser(body).source()
        else:
            self.nodes = HTMLParser(body).parse()
        rules = DEFAULT_STYLE_SHEET.copy()
        sheets: list[Element] = []
        # Populating nodes
        for node in tree_to_list(self.nodes, []):
            # Gathering style sheets
            if (isinstance(node, Element) \
            and node.tag == "link" \
            and node.attributes.get("rel") == "stylesheet" \
            and "href" in node.attributes) \
            or (isinstance(node, Element) \
            and node.tag == "style"):
                sheets.append(node)
            # Propagating :visited on <a> tags
            if isinstance(node, Element) \
            and node.tag == "a" \
            and "href" in node.attributes:
                url = self.url.resolve(node.attributes["href"])
                if url.is_valid and url.storage.get_history(str(url)):
                    node.attributes["visited"] = ""
                elif "visited" in node.attributes: 
                    node.attributes.pop("visited")
        # Parsing style sheets
        for node in sheets:
            body = ""
            if node.tag == "link":
                style_url = url.resolve(node.attributes["href"])
                if not style_url.is_valid: continue
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
        # Fragment handling
        if self.url.fragment:
            node = find_node_by_id(self.url.fragment, self.document)
            if node is not None: 
                self.scroll = node.y
                self.scrollmousewheel_darwin(0) # Prevents overscroll
        self.display_list = []
        paint_tree(self.document, self.display_list)

    def can_back(self) -> bool:
        return len(self.history) > 1 

    def can_forward(self) -> bool:
        return bool(self.forward_history)

    def go_back(self) -> None:
        if self.can_back():
            forward = self.history.pop()
            self.forward_history.append(forward)
            back = self.history.pop()
            self.load(back)

    def go_forward(self) -> None:
        if self.can_forward():
            forward = self.forward_history.pop()
            self.load(forward)

    def clear_forward(self) -> None:
        self.forward_history.clear()

    def toggle_bookmark(self) -> None:
        if self.url.storage.get_bookmark(str(self.url)):
            self.url.storage.delete_bookmark(str(self.url))
        else:
            self.url.storage.add_bookmark(str(self.url))
    
    def page_title(self) -> str | None:
        head = self.document.node.children[0]
        for child in head.children:
            if isinstance(child, Element) and child.tag == "title":
                if not child.children: return None
                [text] = child.children
                if isinstance(text, Element): return None
                return text.text
        return None

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

def find_node_by_id(id: str, root: DocumentLayout) -> BlockLayout | None:
    for layout in tree_to_list(root, []):
        if isinstance(layout.node, Element) \
        and "id" in layout.node.attributes \
        and layout.node.attributes["id"] == id:
            return layout
    return None