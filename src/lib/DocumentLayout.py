import os
import tkinter.font
from typing import Any, Literal, TypedDict
from .HTMLParser import Element, Text, HEAD_TAGS

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))
FONTS: dict[
    tuple[str, int, Literal['normal', 'bold'], Literal['roman', 'italic']], 
    tuple[tkinter.font.Font, tkinter.Label]
] = {}
BLOCK_ELEMENTS = [
    "html", "body", "article", "section", "nav", "aside",
    "h1", "h2", "h3", "h4", "h5", "h6", "hgroup", "header",
    "footer", "address", "p", "hr", "pre", "blockquote",
    "ol", "ul", "menu", "li", "dl", "dt", "dd", "figure",
    "figcaption", "main", "div", "table", "form", "fieldset",
    "legend", "details", "summary"
]

word_options = dict[str, Any]
line_display = tuple[int, str, tkinter.font.Font, word_options]
display = tuple[int, int, str, tkinter.font.Font, str]

class Dimensions(TypedDict):
    width: int
    height: int
    hstep: int
    vstep: int

class DocumentLayout:
    def __init__(self, node: Element, dimensions: Dimensions) -> None:
        self.node: Element = node
        self.parent = None
        self.children: list[BlockLayout] = []
        self.dimensions: Dimensions = dimensions
        # ---
        self.x: int
        self.y: int
        self.width: int
        self.height: int

    def __repr__(self) -> str:
        return "<{}> x{} y{} w{} h{}".format(self.node.tag, self.x, self.y, self.width, self.height)

    def layout(self) -> None:
        child = BlockLayout(self.node, self, None, self.dimensions)
        self.children.append(child)
        self.width = self.dimensions['width'] - 2*self.dimensions["hstep"]
        self.x = self.dimensions["hstep"]
        self.y = self.dimensions["vstep"]
        child.layout()
        self.height = child.height  

    def paint(self) -> list['DrawText | DrawRect']:
        return []

class BlockLayout:
    def __init__(
            self, 
            node: Element | Text | list[Element | Text], 
            parent: 'BlockLayout | DocumentLayout', 
            previous: 'BlockLayout | None',
            dimensions: Dimensions
        ) -> None:
        self.dimensions: Dimensions = dimensions
        self.node: Element | Text | list[Element | Text] = node
        if isinstance(self.node, list):
            if len(self.node) == 0: raise ValueError("Cannot passd empty list as node argument")
            if len(self.node) == 1: [self.node] = self.node
        self.parent: 'BlockLayout | DocumentLayout' = parent
        self.previous: 'BlockLayout | None' = previous
        self.children: 'list[BlockLayout]' = []
        self.display_list: list[display] = []
        # ---
        self.x: int
        self.y: int
        self.width: int
        self.height: int

    def __repr__(self) -> str:
            if isinstance(self.node, Element):
                return "<{}> | x{} y{} w{} h{}".format(self.node.tag , self.x, self.y, self.width, self.height)
            elif isinstance(self.node, Text):
                return "{} | x{} y{} w{} h{}".format(self.node.text , self.x, self.y, self.width, self.height)
            else:
                ls = ["<{}>".format(n.tag) if isinstance(n, Element) else "..." for n in self.node]
                return "({}) | x{} y{} w{} h{}".format(', '.join(ls), self.x, self.y, self.width, self.height)

    def layout(self) -> None:
        if self.previous:
            self.y = self.previous.y + self.previous.height
        else:
            self.y = self.parent.y
        self.x = self.parent.x
        # Block width
        if not isinstance(self.node, list) and \
        self.node.style.get("width", "auto") != "auto" and \
        self.node.style["width"].endswith("px"):
            self.width = int(self.node.style["width"][:-2])
            self.width = min(self.width, self.parent.width)
        else:
            self.width = self.parent.width
        # Element specific modifications
        if isinstance(self.node, Element):
            match self.node.tag:
                case "li":
                    self.x += self.dimensions["hstep"]
                case "nav":
                    if self.node.attributes.get("id") == "toc":
                        self.y += self.dimensions["vstep"]
        # ---
        mode = self.layout_mode()
        if mode == "block":
            assert isinstance(self.node, Element) 
            previous = None
            block = []
            for child in self.node.children:
                if isinstance(child, Element) and (child.tag in HEAD_TAGS + ["head"]): continue
                if isinstance(child, Element) and child.tag in BLOCK_ELEMENTS:
                    # Add block of elements
                    if block:
                        next = BlockLayout(block, self, previous, self.dimensions)
                        self.children.append(next)
                        previous = next
                        block = []
                    # Support for run-in headings
                    if child.tag == "p" and \
                    previous and \
                    isinstance(previous.node, Element) and \
                    previous.node.tag == "h6":
                        heading = self.children.pop()
                        assert isinstance(heading.node, Element)
                        next = BlockLayout([heading.node, child], self, heading.previous, self.dimensions)
                        self.children.append(next)
                        previous = next
                        continue
                    # Add block element
                    next = BlockLayout(child, self, previous, self.dimensions)
                    self.children.append(next)
                    previous = next
                else:
                    block.append(child)
            # Adds last block of elements
            if block:
                next = BlockLayout(block, self, previous, self.dimensions)
                self.children.append(next)
                previous = next
                block = []
            # ---
            for child in self.children:
                child.layout()
            # Block height
            if not isinstance(self.node, list) and \
            self.node.style.get("height", "auto") != "auto" and \
            self.node.style["height"].endswith("px"):
                self.height =  int(self.node.style["height"][:-2])
            else:
                self.height = sum([child.height for child in self.children])
            # ---
        else:
            self.cursor_x = 0
            self.cursor_y = 0
            self.line: list[line_display] = []
            for n in self.node if isinstance(self.node, list) else [self.node]:
                self.text_align = n.style["text-align"] 
                self.recurse(n)
            self.flush()
            # Block height
            if not isinstance(self.node, list) and \
            self.node.style.get("height", "auto") != "auto" and \
            self.node.style["height"].endswith("px"):
                self.height =  int(self.node.style["height"][:-2])
            else:
                self.height = self.cursor_y
        
    def layout_mode(self) -> Literal["inline", "block"]:
        if isinstance(self.node, list):
            return "inline"
        elif isinstance(self.node, Text):
            return "inline"
        elif any([isinstance(child, Element) and \
                  child.tag in BLOCK_ELEMENTS \
                  for child in self.node.children]):
            return "block"
        elif self.node.children:
            return "inline"
        else: 
            return "block"

    def paint(self) -> list['DrawText | DrawRect']:
        cmds: list[DrawText | DrawRect] = []
        # Element specific defaults
        if isinstance(self.node, Element):
            match self.node.tag:
                case "nav":
                    if "toc" == self.node.attributes.get("id"):
                        text = " Table of Contents "
                        font = get_font("", 12, "normal", "roman")
                        y1 = self.y - self.dimensions["vstep"]
                        x2, y2 = self.x + font.measure(text), y1 + font.metrics("linespace")
                        rect = DrawRect(self.x, y1, x2, y2, "grey")
                        cmds.append(rect)
                        cmds.append(DrawText(self.x, y1, text, font, "black"))
                    if "links" in self.node.attributes.get("class", "").split():
                        x2, y2 = self.x + self.width, self.y + self.height
                        rect = DrawRect(self.x, self.y, x2, y2, "light grey")
                        cmds.append(rect)
                case "li":
                    x1 = self.x - self.dimensions["hstep"]
                    y1 = self.y + self.height // 2
                    size = 4
                    x2, y2 = x1 + size, y1 + size
                    rect = DrawRect(x1, y1, x2, y2, "black") 
                    cmds.append(rect)
        # Author styles
        for node in self.node if isinstance(self.node, list) else [self.node]:
            if not isinstance(node, Element): continue
            bgcolor = node.style.get("background-color", "transparent")
            if bgcolor != "transparent":
                x2, y2 = self.x + self.width, self.y + self.height
                rect = DrawRect(self.x, self.y, x2, y2, bgcolor)
                cmds.append(rect)
        # Text
        if self.layout_mode() == "inline":
            for x, y, word, font, color in self.display_list:
                cmds.append(DrawText(x, y, word, font, color))
        return cmds

    def recurse(self, node: Element | Text) -> None:
        if isinstance(node, Text):
            # <pre> support
            if node.style["white-space"] == "pre":
                words = node.text.split("\n")
                for idx, word in enumerate(words):
                    self.word(node, word)
                    if idx < len(words) - 1: self.flush()
                return
            # ---
            for word in node.text.split():                
                self.word(node, word)
        else:
            # <br> newline
            if node.tag == "br":
                self.flush()
            # ---
            for child in node.children:
                self.recurse(child)
            # <p> bottom padding
            if node.tag == "p":
                self.flush()
                self.cursor_y += self.dimensions["vstep"]

    def word(self, node: Text, word: str) -> None:
        color = node.style["color"]
        weight = node.style["font-weight"]
        style = node.style["font-style"]
        family  = node.style["font-family"]
        if style == "normal": style = "roman"
        size = int(float(node.style["font-size"][:-2]) * .75)
        options: dict[str, Any] = {
            "vertical-align": node.style["vertical-align"],
            "color": color
        }
        # Font variant
        if node.style["font-variant"] == "small-caps": 
            if word.islower():
                word = word.upper()
                size = int(size * .75)
            elif word != word.upper():
                whsp = node.style["white-space"] 
                node.style["white-space"] = "pre" # Prevents spaces after separated sequences
                for seq in split_small_caps(word):
                    self.word(node, seq)
                node.style["white-space"] = whsp
                return
        # ---
        font = get_font(family, size, weight, style) # type: ignore
        w  = font.measure(word)
        # Auto line breaks
        if self.cursor_x + w > self.width:
            # Soft hyphens support
            if "\N{soft hyphen}" in word:
                seq = word
                remainder = ""
                while "\N{soft hyphen}" in seq and self.cursor_x + w > self.width:
                    seq, r = seq.rsplit("\N{soft hyphen}", 1)
                    if remainder: remainder = "\N{soft hyphen}" + remainder # To save \N position
                    remainder = r + remainder
                    seq_w = font.measure(seq + "-")
                    if self.cursor_x + seq_w > self.width: continue
                    seq += "-" # Adds hyphen at separation point
                    self.line.append((self.cursor_x, seq, font, options))
                    self.flush()
                    word = seq = remainder
                    remainder = ""
                    w = font.measure(word)
            else:
                self.flush()
        self.line.append((self.cursor_x, word, font, options))
        self.cursor_x += w
        if node.style["white-space"] != "pre": self.cursor_x += font.measure(" ")

    def flush(self) -> None:
        if not self.line: return
        # Text alignment
        text_padding = 0
        if self.text_align == "right":
            x, word, font, options = self.line[-1]
            line_end = x + font.measure(word)
            text_padding = self.width - line_end
        elif self.text_align == "center":
            x, word, font, options = self.line[-1]
            line_end = x + font.measure(word)
            text_padding = (self.width - line_end) // 2
        for idx, text in enumerate(self.line):
            self.line[idx] = (text[0] + text_padding, text[1], text[2], text[3])
        # ---
        metrics = [font.metrics() for x, word, font, options in self.line]
        max_ascent = max(metric["ascent"] for metric in metrics)
        baseline = int(self.cursor_y + 1.25 * max_ascent)
        for rel_x, word, font, options in self.line:
            color: str = options["color"]
            x = self.x + rel_x
            y = self.y + baseline - font.metrics("ascent")
            if options["vertical-align"] == "top": y -= font.metrics("ascent") # vertical-align: top
            if "\N{soft hyphen}" in word: word = word.replace("\N{soft hyphen}", "") # Removes visible soft hyphen 
            self.display_list.append((x, y, word, font, color))
        max_descent = max(metric["descent"] for metric in metrics)
        self.cursor_y = int(baseline + 1.25 * max_descent)
        self.cursor_x = 0
        self.line = []
    
class DrawText:
    def __init__(self, x1: int, y1: int, text: str, font: tkinter.font.Font, color: str) -> None:
        self.top: int = y1
        self.left: int = x1
        self.text: str = text
        self.font: tkinter.font.Font = font
        self.bottom: int = y1 + font.metrics("linespace")
        self.color: str = color
        # Emoji handling
        self.image: tkinter.PhotoImage | None = None
        if len(text) == 1 and not text.isalnum() and not text.isascii():
            code = hex(ord(self.text))[2:].upper()
            image_path = os.path.join(BASE_DIR, 'assets', 'emojis', "{}.png".format(code))
            if os.path.isfile(image_path):
                self.image = tkinter.PhotoImage(file=image_path)

    def execute(self, scroll: int, canvas: tkinter.Canvas) -> None:
        # Prints emojis
        if self.image:
            canvas.create_image(self.left, self.top, image=self.image, anchor="nw")
            return
        # Prints text
        canvas.create_text(
            self.left, self.top - scroll,
            text=self.text,
            font=self.font,
            anchor="nw",
            fill=self.color
        )

class DrawRect:
    def __init__(self, x1: int, y1: int, x2: int, y2: int, color: str) -> None:
        self.top: int = y1
        self.left: int = x1 
        self.bottom: int = y2
        self.right: int = x2
        self.color: str = color

    def execute(self, scroll: int, canvas: tkinter.Canvas) -> None:
        canvas.create_rectangle(
            self.left, self.top - scroll,
            self.right, self.bottom - scroll,
            width=0,
            fill=self.color
        )

def get_font(family: str, size: int, weight: Literal['normal', 'bold'], style: Literal['roman', 'italic']) -> tkinter.font.Font:
    key = (family, size, weight, style)
    if key not in FONTS:
        font = tkinter.font.Font(family=family, size=size, weight=weight, slant=style)
        label = tkinter.Label(font=font)
        FONTS[key] = (font, label)
    return FONTS[key][0]

def split_small_caps(text: str) -> list[str]:
    out: list[str] = []
    buffer = ""
    for c in text:
        if not buffer:
            buffer += c
        elif (buffer.islower() and c.islower()) or (not buffer.islower() and not c.islower()):
            buffer += c
        else:
            out.append(buffer)
            buffer = c                
    if buffer: out.append(buffer)
    return out
