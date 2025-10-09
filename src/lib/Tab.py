import skia
import urllib.parse
from pathlib import Path
from .URL import URL
from . import BASE_DIR
from .JSContext import JSContext
from .Layout import DocumentLayout, Layout
from .Draw import Blend, Draw, DrawRRect, DrawRect
from .CSSParser import CSS_rule, CSSParser, style, cascade_priority
from .HTMLParser import HTMLParser, HTMLSourceParser, Element, Text

SCROLL_STEP = 50
SCROLLBAR_OFFSET = 2

# Default style sheets
DEFAULT_STYLE_SHEET_PATH = Path(BASE_DIR) / "assets" / "css" /  "browser.css"
ss: str = "" 
try: ss = open(DEFAULT_STYLE_SHEET_PATH).read()
except: print("Could not find default style sheets file")
DEFAULT_STYLE_SHEET = CSSParser(ss).parse()

class Tab:
    def __init__(self, browser) -> None:
        from .Browser import Browser
        assert isinstance(browser, Browser)
        self.browser: Browser = browser
        self.url: URL = URL("about:blank")
        self.js: JSContext
        self.display_list: list[Draw] = []
        self.scroll = 0
        self.history: list[URL] = []
        self.forward_history: list[URL] = []
        self.focus: Element | None = None
        self.allowed_origins: list[str] | None = None
        self.nodes: Element = Element("html", {}, None)
        self.rules: list[CSS_rule] = DEFAULT_STYLE_SHEET.copy()
        
    # --- Event handlers
    def up(self) -> None:
        self.scroll = max(self.scroll - SCROLL_STEP, 0)

    def down(self) -> None:
        self.scroll = min(self.scroll + SCROLL_STEP, self.display_height())

    def scrollwheel(self, delta: int) -> None:
        delta *= -SCROLL_STEP # Adjusts direction and distance
        if delta < 0: self.scroll = max(self.scroll + delta, 0)
        else: self.scroll = min(self.scroll + delta, self.display_height())

    def configure(self) -> None:
        self.render()

    def middle_click(self, x: int, y: int) -> URL | None:
        y += self.scroll
        objs = self.display_list_xyobjects(x, y)
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
        objs = self.display_list_xyobjects(x, y)
        if not objs: return
        elt: Element | Text | None = objs[-1].node if not isinstance(objs[-1].node, list) else objs[-1].node[-1]
        assert isinstance(elt, Element | Text)
        if self.focus: self.focus.is_focused = False
        self.focus = None
        while elt:
            if isinstance(elt, Text):
                pass
            elif elt.tag == "a" and "href" in elt.attributes:
                if self.js.dispatch_event("click", elt): return
                href = elt.attributes["href"]
                if href.startswith("#"): # Fragment link support
                    self.url.fragment = href[1:]
                    node = find_node_by_id(self.url.fragment, self.document)
                    if node is not None: 
                        self.scroll = node.y
                        self.scrollwheel(0) # Prevents overscroll
                else:
                    url = self.url.resolve(href)
                    self.clear_forward()
                    self.load(url)
                return
            elif elt.tag == "input":
                if self.js.dispatch_event("click", elt): return
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
                if self.js.dispatch_event("click", elt): return
                while elt:
                    if elt.tag == "form" and "action" in elt.attributes:
                        return self.submit_form(elt)
                    elt = elt.parent
                if not elt: break
            elt = elt.parent
        self.render()

    def keypress(self, char: str) -> bool:
        if self.focus:
            if self.js.dispatch_event("keydown", self.focus): return True
            self.focus.attributes["value"] += char
            self.render()
            return True
        return False

    def enter(self) -> bool:
        if self.focus and self.focus.tag == "input": 
            if self.js.dispatch_event("keydown", self.focus): return True
            elt = self.focus
            while elt:
                if elt.tag == "form" and "action" in elt.attributes:
                    self.submit_form(elt)
                    return True
                elt = elt.parent
        return False

    def backspace(self) -> bool:
        if self.focus and self.focus.tag == "input":
            if self.js.dispatch_event("keydown", self.focus): return True
            text = self.focus.attributes.get("value")
            if not text: return False
            text = text[:-1]
            self.focus.attributes["value"] = text
            self.render()
            return True
        return False

    # --- Functions
    def display_list_xyobjects(self, x: int, y: int) -> list[Layout]:
        objs: list[Layout] = []
        for obj in flatten_display_list(self.display_list):
            if obj.layout is not None \
            and obj.layout.x <= x < obj.layout.x + obj.layout.width \
            and obj.layout.y <= y < obj.layout.y + obj.layout.height:
                objs.append(obj.layout)
        return objs

    def display_height(self) -> int:
        h = (
            self.document.height 
            - self.browser.dimensions["height"] 
            + self.browser.chrome.bottom
            + self.browser.dimensions["vstep"] * 2
        )
        return max(0, h)

    def raster(self, canvas: skia.Canvas) -> None:
        for cmd in self.display_list:
            cmd.execute(canvas)
        self.raster_scrollbar(canvas)

    def raster_scrollbar(self, canvas: skia.Canvas) -> None:
        dh = self.display_height()
        # Bg
        sb_rect = skia.Rect.MakeXYWH(
            self.browser.dimensions['width'] - self.browser.dimensions["hstep"], self.scroll,
            self.browser.dimensions["hstep"], dh
        )
        if dh > 0:
            DrawRect(sb_rect, "lightgrey").execute(canvas)
            ratio = int(
                (self.scroll / dh) 
                * (self.browser.dimensions["height"] - self.browser.chrome.bottom - self.browser.dimensions["vstep"])
            )
            scrollbar_rect = skia.Rect.MakeXYWH(
                sb_rect.left() + SCROLLBAR_OFFSET,
                ratio + SCROLLBAR_OFFSET + self.scroll,
                self.browser.dimensions["hstep"] - SCROLLBAR_OFFSET*2,
                self.browser.dimensions["vstep"] - SCROLLBAR_OFFSET*2
            )
            DrawRRect(scrollbar_rect, 3, "grey").execute(canvas)
        else:
            DrawRect(sb_rect, "white").execute(canvas)


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
        if self.js.dispatch_event("submit", elt): return
        self.load(url, body)

    def load(self, url: URL, payload: str | None = None) -> None:
        self.browser.set_cursor("LOADING")
        if self.focus: self.focus.is_focused = False
        self.focus = None
        self.scroll = 0
        self.history.append(url)
        url.storage.add_history(str(url))
        headers, body = url.request(self.url, payload)
        self.allowed_origins = None
        if "content-security-policy" in headers:
            csp = headers["content-security-policy"].split()
            if len(csp) > 0 and csp[0] == "default-src":
                self.allowed_origins = []
                for origin in csp[1:]:
                    self.allowed_origins.append(URL(origin).origin())
        if url.view_source:
            self.nodes = HTMLSourceParser(body).source()
        else:
            self.nodes = HTMLParser(body).parse()
        self.url = url
        # Propagating attributes
        self.propagate_attributes(self.nodes)  
        # Executing JavaScript
        self.js = JSContext(self)
        self.load_scripts(self.nodes)
        # Parsing style sheets
        self.load_sheets()
        # Rendering
        self.render()
        # Fragment handling
        if self.url.fragment:
            node = find_node_by_id(self.url.fragment, self.document)
            if node is not None: 
                self.scroll = node.y
                self.scrollwheel(0) # Prevents overscroll
        # SSL error handling
        if 'x-ssl-error' in headers:
            self.browser.show_simple_messagebox(
                "ERROR", 
                'SSL error', 
                'This connection is not secure!\nPage is not loaded, because SSL certificate error ocurred:\n\n{}'.format(headers["x-ssl-error"]),
            )
        # Update window title
        self.browser.update_title()
        self.browser.set_cursor("DEFAULT")

    def render(self) -> None:
        style(self.nodes, sorted(self.rules, key=cascade_priority))
        self.document = DocumentLayout(self.nodes, self.browser.dimensions)
        self.document.layout()
        self.display_list = []
        paint_tree(self.document, self.display_list)

    def blur(self) -> None:
        if not self.focus: return
        self.focus.is_focused = False
        self.focus = None
        self.render()

    def propagate_attributes(self, nodes: Element | Text) -> None:
        if isinstance(nodes, Text): return
        for node in tree_to_list(nodes, []):
            if isinstance(node, Text): continue
            # Propagating :visited on <a> tags
            if isinstance(node, Element) \
            and node.tag == "a" \
            and "href" in node.attributes:
                url = self.url.resolve(node.attributes["href"])
                if url.is_valid and url.storage.get_history(str(url)):
                    node.attributes["visited"] = ""
                elif "visited" in node.attributes: 
                    node.attributes.pop("visited")

    def load_scripts(self, nodes: Element | Text) -> None:
        if isinstance(nodes, Text): return
        scripts: list[str] = [
            node.attributes["src"] for node in tree_to_list(nodes, []) 
            if isinstance(node, Element)
            and node.tag == "script"
            and "src" in node.attributes
        ]
        for script in scripts:
            script_url = self.url.resolve(script)
            if not self.allowed_request(script_url):
                print("Blocked script", script, "due to csp")
                continue
            try: headers, body = script_url.request(self.url)
            except: continue
            if not script_url.is_valid: continue
            self.js.run(script, body)

    def load_sheets(self) -> None:
        self.rules = DEFAULT_STYLE_SHEET.copy()
        sheets: list[Element] = [
            node for node in tree_to_list(self.nodes, [])
            if isinstance(node, Element) 
            and ((node.tag == "link" 
                    and node.attributes.get("rel") == "stylesheet" 
                    and "href" in node.attributes
                ) or (node.tag == "style")
        )]
        for sheet in sheets:
            body = ""
            if sheet.tag == "link":
                sheet_url = self.url.resolve(sheet.attributes["href"])
                if not self.allowed_request(sheet_url):
                    print("Blocked stylesheet", sheet.attributes["href"], "due to csp")
                    continue
                if not sheet_url.is_valid: continue
                try: headers, body = sheet_url.request(self.url)
                except: continue
            elif sheet.tag == "style":
                for child in sheet.children:
                    if isinstance(child, Text):
                        body += child.text
            
            self.rules.extend(CSSParser(body).parse())
    
    def allowed_request(self, url: URL) -> bool:
        return self.allowed_origins == None \
        or url.origin() in self.allowed_origins

    def can_back(self) -> bool:
        return len(self.history) > 1 

    def can_forward(self) -> bool:
        return bool(self.forward_history)

    def go_back(self) -> None:
        if not self.can_back(): return
        # Resubmitting form alert
        if self.history[-2].method == "POST":
            action = self.browser.show_yesno_messagebox(
                'WARNING',
                'Resubmit form?',
                'Are you sure you want to resubmit form?'
            )
            if not action: return
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
            action = self.browser.show_yesno_messagebox(
                'WARNING',
                'Resubmit form?',
                'Are you sure you want to resubmit form?'
            )
            if not action: return
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
        if not hasattr(self, "document"): return None
        head = self.document.node.children[0]
        for child in head.children:
            if isinstance(child, Element) and child.tag == "title":
                if not child.children: return None
                text = ""
                for ch in child.children:
                    if not isinstance(ch, Text): continue 
                    text += ch.text
                return text if text else None
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

def paint_tree(layout_object: Layout, display_list: list[Draw]) -> None:
    cmds = []
    if layout_object.should_paint():
        cmds = layout_object.paint()
    for child in layout_object.children:
        paint_tree(child, cmds)
    if layout_object.should_paint():
        cmds = layout_object.paint_effects(cmds)
    display_list.extend(cmds)


def find_node_by_id(id: str, root: DocumentLayout) -> Layout | None:
    for layout in tree_to_list(root, []):
        if isinstance(layout.node, Element) \
        and "id" in layout.node.attributes \
        and layout.node.attributes["id"] == id:
            return layout
    return None

def flatten_display_list(dl: list[Draw]) -> list[Draw]:
    out = []
    for elt in dl:
        if isinstance(elt, Blend):
            out.extend(flatten_display_list(elt.children))
        else:
            out.append(elt)
    return out