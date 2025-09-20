import os
import tkinter
import tkinter.font
from typing import Any, Literal, TypedDict
from .Draw import Draw, DrawText, DrawRect, Rect
from .HTMLParser import Element, Text, HEAD_TAGS

FONTS: dict[
    tuple[str, int, Literal['normal', 'bold'], Literal['roman', 'italic']], 
    tuple[tkinter.font.Font, tkinter.Label]
] = {}

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
        return "DocumentLayout"

    def layout(self) -> None:
        child = BlockLayout(self.node, self, None, self.dimensions)
        self.children.append(child)
        self.width = self.dimensions['width'] - 2*self.dimensions["hstep"]
        self.x = self.dimensions["hstep"]
        self.y = self.dimensions["vstep"]
        child.layout()
        self.height = child.height  

    def paint(self) -> list:
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
        self.children: 'list[BlockLayout | LineLayout]' = []
        # ---
        self.x: int
        self.y: int
        self.width: int
        self.height: int

    def __repr__(self) -> str:
            if isinstance(self.node, Element):
                return "BlockLayout[{}] ({} element)".format(self.layout_mode(), self.node.tag)
            elif isinstance(self.node, Text):
                return "BlockLayout[{}] (\"{}\")".format(self.layout_mode(), self.node.text.strip().replace("\n", " "))
            else:
                ls = [n.tag if isinstance(n, Element) else "..." for n in self.node]
                return "BlockLayout[{}] ({} anonymus)".format(self.layout_mode(), ls)

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
                if isinstance(child, Element) and child.style.get("display") == "block":
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
                        assert isinstance(heading, BlockLayout)
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
        else:
            self.new_line()
            for n in self.node if isinstance(self.node, list) else [self.node]:
                self.text_align = n.style["text-align"] 
                self.recurse(n)
        for child in self.children:
            child.layout()
        # Block height
        if not isinstance(self.node, list) and \
        self.node.style.get("height", "auto") != "auto" and \
        self.node.style["height"].endswith("px"):
            self.height =  int(self.node.style["height"][:-2])
        else:
            self.height = sum([child.height for child in self.children])
        # <p> bottom padding
        if isinstance(self.node, Element) and self.node.tag == "p":
            self.height += self.dimensions["vstep"]
        
    def layout_mode(self) -> Literal["inline", "block"]:
        if isinstance(self.node, list):
            return "inline"
        if self.node.style.get("display") == "block":
            return "block"
        else:
            return "inline"

    def paint(self) -> list[Draw]:
        cmds: list[Draw] = []
        # Element specific defaults
        if isinstance(self.node, Element):
            match self.node.tag:
                case "nav":
                    if "toc" == self.node.attributes.get("id"):
                        text = " Table of Contents "
                        font = get_font("", 12, "normal", "roman")
                        y1 = self.y - self.dimensions["vstep"]
                        x2, y2 = self.x + font.measure(text), y1 + font.metrics("linespace")
                        rect = DrawRect(Rect(self.x, y1, x2, y2), "grey")
                        cmds.append(rect)
                        cmds.append(DrawText(self.x, y1, text, font, "black"))
                    if "links" in self.node.attributes.get("class", "").split():
                        x2, y2 = self.x + self.width, self.y + self.height
                        rect = DrawRect(Rect(self.x, self.y, x2, y2), "light grey")
                        cmds.append(rect)
                case "li":
                    x1 = self.x - self.dimensions["hstep"]
                    y1 = self.y + self.height // 2
                    size = 4
                    x2, y2 = x1 + size, y1 + size
                    rect = DrawRect(Rect(x1, y1, x2, y2), "black") 
                    cmds.append(rect)
        # Author styles
        for node in self.node if isinstance(self.node, list) else [self.node]:
            if not isinstance(node, Element): continue
            bgcolor = node.style.get("background-color", "transparent")
            if bgcolor != "transparent":
                x2, y2 = self.x + self.width, self.y + self.height
                rect = DrawRect(self.self_rect(), bgcolor)
                cmds.append(rect)
        return cmds
    
    def self_rect(self) -> Rect:
        return Rect(self.x, self.y, self.x + self.width, self.y + self.height)

    def recurse(self, node: Element | Text) -> None:
        if isinstance(node, Text):
            # <pre> support
            if node.style["white-space"] == "pre":
                words = node.text.split("\n")
                for idx, word in enumerate(words):
                    self.word(node, word)
                    if idx < len(words) - 1: self.new_line()
                return
            # ---
            for word in node.text.split():
                self.word(node, word)
        else:
            # <br> newline
            if node.tag == "br":
                self.new_line()
            # ---
            for child in node.children:
                self.recurse(child)

    def word(self, node: Text, word: str) -> None:
        # Prop type checking
        weight: Literal["bold", "normal"]
        if node.style["font-weight"] in ["bold", "normal"]: weight = node.style["font-weight"] # type: ignore
        else: weight = "normal"
        # ---
        style: Literal["italic", "roman"]
        if node.style["font-style"] in ["italic", "normal"]: style = node.style["font-style"] # type: ignore
        else: style = "roman"
        if node.style["font-style"] == "normal": style = "roman"
        # ---
        family  = node.style["font-family"]
        try: size = int(float(node.style["font-size"][:-2]) * .75)
        except: size = 16
        # Font variant
        if node.style["font-variant"] == "small-caps": 
            if word.islower():
                size = int(size * .75)
            elif word != word.upper():
                whsp = node.style["white-space"] 
                node.style["white-space"] = "pre" # Prevents spaces after separated sequences
                for seq in split_small_caps(word):
                    self.word(node, seq)
                node.style["white-space"] = whsp
                return
        # ---
        font = get_font(family, size, weight, style)
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
                    line: LineLayout = self.children[-1] # type: ignore
                    previous_word = line.children[-1] if line.children else None
                    new_text = TextLayout(node, seq, line, previous_word)
                    line.children.append(new_text)
                    self.new_line()
                    word = seq = remainder
                    remainder = ""
                    w = font.measure(word)
            else:
                self.new_line()
        line: LineLayout = self.children[-1] # type: ignore
        previous_word = line.children[-1] if line.children else None
        text = TextLayout(node, word, line, previous_word)
        line.children.append(text)
        self.cursor_x += w
        if node.style["white-space"] != "pre": self.cursor_x += font.measure(" ")

    def new_line(self) -> None:
        self.cursor_x = 0
        last_line: LineLayout | None = self.children[-1] if self.children else None # type: ignore
        new_line = LineLayout(self.node, self, last_line) # type: ignore
        self.children.append(new_line)

class LineLayout:
    def __init__(self, \
    node: Text, \
    parent: BlockLayout, \
    previous: 'LineLayout | None') -> None:
        self.node: Text = node
        self.parent: BlockLayout = parent
        self.previous: 'LineLayout | None' = previous
        self.children: list['TextLayout'] = []
        # ---
        self.x: int
        self.y: int
        self.width: int
        self.height: int

    def __repr__(self) -> str:
        return "LineLayout"

    def layout(self) -> None:
        self.width = self.parent.width
        self.x = self.parent.x
        if self.previous:
            self.y = self.previous.y + self.previous.height
        else:
            self.y = self.parent.y
        for word in self.children:
            word.layout()
        if not self.children:
            self.height = 0
            return
        # Text alignment
        text_padding = 0
        last_child = self.children[-1]
        if self.parent.text_align == "right":
            line_end = last_child.x + last_child.font.measure(last_child.word)
            text_padding = self.width - line_end
        elif self.parent.text_align == "center":
            line_end = last_child.x + last_child.font.measure(last_child.word)
            text_padding = (self.width - line_end) // 2
        for word in self.children:
            word.x += text_padding
        # ---
        max_ascent = max([word.font.metrics("ascent") for word in self.children])
        baseline = int(self.y + 1.25 * max_ascent)
        for word in self.children:
            word.y = baseline - word.font.metrics("ascent")
            if word.node.style["vertical-align"] == "top": word.y -= word.font.metrics("ascent") # vertical-align: top
            if "\N{soft hyphen}" in word.word: word.word = word.word.replace("\N{soft hyphen}", "") # Removes visible soft hyphen 
        max_descent = max([word.font.metrics("descent") for word in self.children])
        self.height = int(1.25 * (max_ascent + max_descent))

    def paint(self) -> list:
        return []

class TextLayout:
    def __init__(self, \
    node: Text, \
    word: str, \
    parent: LineLayout, \
    previous: 'TextLayout | None') -> None:
        self.node: Text = node
        self.word: str = word
        self.parent: LineLayout = parent
        self.previous: 'TextLayout | None' = previous
        self.children: list['TextLayout'] = []
        # ---
        self.x: int
        self.y: int
        self.width: int
        self.height: int
        # ---
        self.no_space: bool = self.node.style["white-space"] == "pre"

    def __repr__(self) -> str:
        return "TextLayout (\"{}\")".format(self.word)

    def layout(self) -> None:
        # Prop type checking
        weight: Literal["bold", "normal"]
        if self.node.style["font-weight"] in ["bold", "normal"]: weight = self.node.style["font-weight"] # type: ignore
        else: weight = "normal"
        # ---
        style: Literal["italic", "roman"]
        if self.node.style["font-style"] in ["italic", "normal"]: style = self.node.style["font-style"] # type: ignore
        else: style = "roman"
        if self.node.style["font-style"] == "normal": style = "roman"
        # ---
        family  = self.node.style["font-family"]
        try: size = int(float(self.node.style["font-size"][:-2]) * .75)
        except: size = 16
        # Font variant 
        if self.node.style["font-variant"] == "small-caps" and self.word.islower(): 
            self.word = self.word.upper()
            size = int(size * .75)
        self.font = get_font(family, size, weight, style)
        self.width = self.font.measure(self.word)
        if self.previous:
            space = self.previous.font.measure(" ") if not self.no_space else 0
            self.x = self.previous.x + space + self.previous.width
        else:
            self.x = self.parent.x
        self.height = self.font.metrics("linespace")

    def paint(self) -> list[Draw]:
        color = self.node.style['color']
        return [DrawText(self.x, self.y, self.word, self.font, color)]


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

