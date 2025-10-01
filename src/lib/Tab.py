import tkinter
import tkinter.messagebox
import urllib.parse
from .URL import URL
from . import BASE_DIR
from .Draw import Draw
from pathlib import Path
from .CSSParser import CSSParser, style, cascade_priority
from .HTMLParser import HTMLParser, HTMLSourceParser, Element, Text
from .Layout import Dimensions, DocumentLayout, Layout

SCROLL_STEP = 100
SCROLLBAR_OFFSET = 2

# Default style sheets
DEFAULT_STYLE_SHEET_PATH = Path(BASE_DIR) / "assets" / "browser.css"
ss: str = "" 
try: ss = open(DEFAULT_STYLE_SHEET_PATH).read()
except: print("Could not find default style sheets file")
DEFAULT_STYLE_SHEET = CSSParser(ss).parse()

class Tab:
    def __init__(self, window: tkinter.Tk, dimesnions: Dimensions) -> None:
        self.window: tkinter.Tk = window
        self.url: URL
        self.dimensions: Dimensions = dimesnions
        self.images: list[tkinter.PhotoImage] = []
        self.display_list: list[Draw] = []
        self.scroll = 0
        self.history: list[URL] = []
        self.forward_history: list[URL] = []
        self.focus: Element | None = None
        
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
        self.render()

    def middle_click(self, x: int, y: int) -> URL | None:
        y += self.scroll
        objs: list[Layout] = [obj.layout for obj in self.display_list
            if obj.layout is not None
            and obj.layout.x <= x < obj.layout.x + obj.layout.width
            and obj.layout.y <= y < obj.layout.y + obj.layout.height
        ]
        if not objs: return
        elt: Element | Text | None = objs[-1].node if not isinstance(objs[-1].node, list) else objs[-1].node[-1]
        assert isinstance(elt, Element | Text)
        while elt:
            if isinstance(elt, Text):
                pass
            elif elt.tag == "a" and "href" in elt.attributes:
                return self.url.resolve(elt.attributes["href"])
            elt = elt.parent
        return None     

    def click(self, x: int, y: int) -> None:
        y += self.scroll
        objs: list[Layout] = [obj.layout for obj in self.display_list
            if obj.layout is not None
            and obj.layout.x <= x < obj.layout.x + obj.layout.width
            and obj.layout.y <= y < obj.layout.y + obj.layout.height
        ]
        if not objs: return
        elt: Element | Text | None = objs[-1].node if not isinstance(objs[-1].node, list) else objs[-1].node[-1]
        assert isinstance(elt, Element | Text)
        if self.focus: self.focus.is_focused = False
        self.focus = None
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
            elif elt.tag == "input":
                if elt.attributes.get("type") == "checkbox":
                    if "checked" in elt.attributes: 
                        elt.attributes.pop("checked")
                    else: 
                        elt.attributes["checked"] = ""
                else:
                    elt.attributes["value"] = ""
                    self.focus = elt
                    elt.is_focused = True
                self.render()
                return
            elif elt.tag == "button":
                while elt:
                    if elt.tag == "form" and "action" in elt.attributes:
                        return self.submit_form(elt)
                    elt = elt.parent
                if not elt: break
            elt = elt.parent
        self.render()

    def keypress(self, char: str) -> None:
        if self.focus:
            self.focus.attributes["value"] += char
            self.render()

    def enter(self) -> None:
        if self.focus and self.focus.tag == "input": 
            elt = self.focus
            while elt:
                if elt.tag == "form" and "action" in elt.attributes:
                    return self.submit_form(elt)
                elt = elt.parent

    def backspace(self) -> None:
        if self.focus and self.focus.tag == "input":
            text = self.focus.attributes.get("value")
            if not text: return
            text = text[:-1]
            self.focus.attributes["value"] = text
            self.render()

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

    def submit_form(self, elt: Element) -> None:
        inputs = [node for node in tree_to_list(elt, [])
            if isinstance(node, Element)
            and node.tag == "input"
            and "name" in node.attributes]
        body = ""
        for input in inputs:
            # Type dependant
            type = input.attributes.get("type")
            if type == "checkbox" and "checked" not in input.attributes:
                continue
            # Name
            name = input.attributes["name"]
            name = urllib.parse.quote(name)
            # Value
            value = input.attributes.get("value", "")
            if not value and type == "checkbox": value = "on" 
            value = urllib.parse.quote(value)
            # ---
            body += "&" + name + "=" + value
        body = body[1:]
        url  = self.url.resolve(elt.attributes["action"])
        if elt.attributes.get("method", "GET").upper() != "POST":  # Default GET method
            url.path += "?" + body
            body = None
        self.load(url, body)

    def load(self, url: URL, payload: str | None = None) -> None:
        if self.focus: self.focus.is_focused = False
        self.focus = None
        self.scroll = 0
        self.history.append(url)
        self.url = url
        self.url.storage.add_history(str(self.url))
        body = self.url.request(payload)
        if self.url.view_source:
            self.nodes = HTMLSourceParser(body).source()
        else:
            self.nodes = HTMLParser(body).parse()
        self.rules = DEFAULT_STYLE_SHEET.copy()
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
            self.rules.extend(CSSParser(body).parse())
        # Rendering
        self.render()
        # Fragment handling
        if self.url.fragment:
            node = find_node_by_id(self.url.fragment, self.document)
            if node is not None: 
                self.scroll = node.y
                self.scrollmousewheel_darwin(0) # Prevents overscroll

    def render(self) -> None:
        style(self.nodes, sorted(self.rules, key=cascade_priority))
        self.document = DocumentLayout(self.nodes, self.dimensions)
        self.document.layout()
        self.display_list = []
        paint_tree(self.document, self.display_list)

    def blur(self) -> None:
        if not self.focus: return
        self.focus.is_focused = False
        self.focus = None
        self.render()

    def can_back(self) -> bool:
        return len(self.history) > 1 

    def can_forward(self) -> bool:
        return bool(self.forward_history)

    def go_back(self) -> None:
        if not self.can_back(): return
        # Resubmitting form alert
        if self.history[-2].method == "POST":
            box = tkinter.messagebox.Message(
                master=self.window,
                title="Alert",
                type=tkinter.messagebox.YESNO,
                icon=tkinter.messagebox.WARNING,
                message="Are you sure you want to resubmit form?"
            )
            action = box.show()
            if action == "no": return
            forward = self.history.pop()
            self.forward_history.append(forward)
            back = self.history.pop()
            self.load(back, back.payload)
        else:
            forward = self.history.pop()
            self.forward_history.append(forward)
            back = self.history.pop()
            self.load(back)

    def go_forward(self) -> None:
        if not self.can_forward(): return
        # Resubmitting form alert
        if self.forward_history[-1].method == "POST":
            box = tkinter.messagebox.Message(
                master=self.window,
                title="Alert",
                type=tkinter.messagebox.YESNO,
                icon=tkinter.messagebox.WARNING,
                message="Are you sure you want to resubmit form?"
            )
            action = box.show()
            if action == "no": return
            forward = self.forward_history.pop()
            self.load(forward, forward.payload)
        else:
            forward = self.forward_history.pop()
            self.load(forward)

    def clear_forward(self) -> None:
        self.forward_history.clear()

    def refresh(self) -> None:
        self.load(self.url)
        self.history.pop()

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
layout_object: Layout, 
display_list: list[Draw]) -> None:
    if layout_object.should_paint():
        display_list.extend(layout_object.paint())
    for child in layout_object.children:
        paint_tree(child, display_list)

def find_node_by_id(id: str, root: DocumentLayout) -> Layout | None:
    for layout in tree_to_list(root, []):
        if isinstance(layout.node, Element) \
        and "id" in layout.node.attributes \
        and layout.node.attributes["id"] == id:
            return layout
    return None