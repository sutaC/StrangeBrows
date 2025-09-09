#!/usr/bin/env python3
from typing import Literal, Any
from argparse import ArgumentParser
from time import time
import socket
import ssl
import os
import sys
import sqlite3
import atexit
import gzip
import tkinter 
import tkinter.font

word_options = dict[str, Any]
line_display = tuple[int, str, tkinter.font.Font, word_options]
display = tuple[int, int, str, tkinter.font.Font, str]
CSS_rule = tuple['TagSelector | DescendantSelector', dict[str, str]]

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
DEFAULT_PAGE_URL = "file://" + os.path.join(BASE_DIR, "assets", "home.html")
WIDTH, HEIGHT = 800, 600
REDIRECT_LIMIT = 5
HSTEP, VSTEP = 13, 18
SCROLL_STEP = 100
SCROLLBAR_OFFSET = 2
FONTS: dict[
    tuple[str, int, Literal['normal', 'bold'], Literal['roman', 'italic']], 
    tuple[tkinter.font.Font, tkinter.Label]
] = {}
SPECIAL_CHARS = {
    "&lt;": "<",
    "&gt;": ">",
    "&quot;": "\"",
    "&shy;": "\N{soft hyphen}",
    "&amp;": "&",
}
SELF_CLOSING_TAGS = [
    "area", "base", "br", "col", "embed", "hr", "img", "input",
    "link", "meta", "param", "source", "track", "wbr",
]
HEAD_TAGS = [
    "base", "basefont", "bgsound", "noscript",
    "link", "meta", "title", "style", "script",
]
UNNESTABLE_TAGS = [
    "p", "li"
]
TEXT_FORMATTING_TAGS = [
    "b", "i", "small", "big"
]
BLOCK_ELEMENTS = [
    "html", "body", "article", "section", "nav", "aside",
    "h1", "h2", "h3", "h4", "h5", "h6", "hgroup", "header",
    "footer", "address", "p", "hr", "pre", "blockquote",
    "ol", "ul", "menu", "li", "dl", "dt", "dd", "figure",
    "figcaption", "main", "div", "table", "form", "fieldset",
    "legend", "details", "summary"
]
INHERITED_PROPERTIES = {
    "font-size": "16px",
    "font-style": "normal",
    "font-weight": "normal",
    "color": "black",
    "font-family": "Arial",
    "text-align": "left",
    "vertical-align": "baseline",
    "font-variant": "normal",
    "white-space": "normal"
}

class Cache:
    def __init__(self, dir: str = ".") -> None:
        self.con = sqlite3.connect(dir)
        cursor = self.con.cursor()
        cursor.execute('CREATE TABLE IF NOT EXISTS responses (url VARCHAR(255), expires INT, body TEXT);')
        self.con.commit()
        cursor.close()
        atexit.register(self.con.close)        

    def add(self, url: str, expires: int, body: str) -> None:
        cursor = self.con.cursor()
        cursor.execute('INSERT INTO responses (url, expires, body) VALUES (?, ?, ?);', [url, expires, body])
        self.con.commit()
        cursor.close()

    def get(self, url: str) -> str | None:
        cursor = self.con.cursor()
        cursor.execute("SELECT expires, body FROM responses WHERE url = ?;", [url])
        data = cursor.fetchone()
        cursor.close()
        if data is None:
            return None
        expires: int
        body: str
        expires, body = data
        now = int(time())
        if now > expires:
            self.delete(url)
            return None
        return body
        
    def delete(self, url: str) -> None:
        cursor = self.con.cursor()
        cursor.execute("DELETE FROM responses WHERE url = ?;", [url])
        self.con.commit()
        cursor.close()

    def clean(self) -> None:
        cursor = self.con.cursor()
        cursor.execute("DELETE FROM responses;")
        self.con.commit()
        cursor.close()

class URL:
    def __init__(self, url: str):
        self.CACHE = Cache(os.path.join(BASE_DIR, "cache.sqlite"))
        self.redirect_count = 0
        self.saved_socket: socket.socket | None = None
        if not url:
            url = DEFAULT_PAGE_URL
        self.url: str = url
        try:
            self.view_source = url.startswith("view-source:")
            if self.view_source:
                url = url[len("view-source:"):]
            if url == "about:blank": return
            if url.startswith("data"):
                self.scheme, url = url.split(":", 1)
                self.type, self.content = url.split(",", 1)
                return            
            self.scheme, url = url.split("://", 1)
            assert self.scheme in ["http", "https", "file", "data"]
            if self.scheme == "http":
                self.port = 80
            elif self.scheme == "https":
                self.port = 443
            if self.scheme == "data": return
            if "/" not in url:
                url = url + "/"
            self.host, url = url.split("/", 1)
            self.path = "/" + url
            if ":" in self.host:
                self.host, port = self.host.split(":", 1)
                self.port = int(port)
        except:
            print("Recived malformed url '{}', unable to continue...".format(self.url))
            self.url = "about:blank"
        atexit.register(self.cleanup)

    def cleanup(self) -> None:
        if self.saved_socket is not None:
            self.saved_socket.close()

    def resolve(self, url: str) -> 'URL':
        if "://" in  url: return URL(url)
        if not url.startswith("/", 1):
            dir, _ = self.path.rsplit("/", 1)
            while url.startswith("../"):
                _, url = url.rsplit("/", 1)
                if "/" in dir:
                    dir, _ = self.path.rsplit("/", 1)
            url = dir + "/" + url
        if url.startswith("//"):
            return URL(self.scheme + ":" + url)
        else:
            return URL(self.scheme + "://" + self.host + ":" + str(self.port) + url)

    def request(self) -> str:
        if self.url == "about:blank":
            return ""
        if self.scheme == "file":
            file = open(self.path, "r")
            content = file.read()
            file.close()
            return content
        elif self.scheme == "data":
            return self.content
        cached_response = self.CACHE.get(self.url)
        if cached_response is not None:
            return cached_response
        s: socket.socket
        if self.saved_socket is not None:
            s = self.saved_socket
        else:
            s = socket.socket(
                family=socket.AF_INET, 
                type=socket.SOCK_STREAM, 
                proto=socket.IPPROTO_TCP
            )
            if self.scheme == "https":
                ctx = ssl.create_default_context()
                s = ctx.wrap_socket(s, server_hostname=self.host)
            self.saved_socket = s
            s.connect((self.host, self.port))
        request_headers = {
            "Host": self.host,
            "Connection": "keep-alive",
            "User-Agent": "StrangeBrows",
            "Accept-Encoding": "gzip"
        }
        request = "GET {} HTTP/1.1\r\n".format(self.path)
        for header in request_headers:
            request += "{}: {}\r\n".format(header, request_headers[header])
        request += "\r\n"
        s.send(request.encode())
        response = s.makefile("rb", encoding="utf-8", newline="\r\n")
        statusline = response.readline().decode()
        version, status, explenation = statusline.split(" ", 2)
        status = int(status)
        response_headers = {}
        while True:
            line = response.readline().decode()
            if line == "\r\n": break
            header, value = line.split(":", 1)
            response_headers[header.casefold()] = value.strip()
        if 300 <= status < 400:
            self.redirect_count += 1
            if self.redirect_count > REDIRECT_LIMIT:
                raise Exception("Reached redirection limit")
            location: str = response_headers["location"]
            new_url = self.resolve(location)
            new_url.saved_socket = self.saved_socket
            new_url.redirect_count = self.redirect_count
            return new_url.request()
        else:
            self.redirect_count = 0
        content: str
        if "content-encoding" in response_headers and response_headers["content-encoding"] == "gzip":
            if "transfer-encoding" in response_headers and response_headers["transfer-encoding"] == "chunked":
                assert "content-length" not in response_headers
                encoded_content = bytearray()
                while True:
                    chunk_length = int(response.readline(), 16)
                    if chunk_length == 0: break
                    encoded_content.extend(response.read(chunk_length))
                    response.readline() # Pass \r\n on chunk end
                content = gzip.decompress(encoded_content).decode()
            else:
                content_length = int(response_headers["content-length"])
                encoded_content = response.read(content_length)
                content = gzip.decompress(encoded_content).decode()
        else:
            content_length = int(response_headers["content-length"])
            content = response.read(content_length).decode()
        if status == 200 and "cache-control" in response_headers:
            cache_control: str = response_headers["cache-control"]
            if cache_control == "no-store":
                pass
            elif cache_control.startswith("max-age"):
                max_age = int(cache_control.split("=", 1)[1])
                assert max_age >= 0
                age = 0
                if "age" in response_headers:
                    age = int(response_headers["age"])
                    assert age >= 0
                expires = int(time()) + max_age - age
                self.CACHE.add(self.url, expires, content)
        return content

class Text:
    def __init__(self, text: str, parent: 'Element') -> None:
        self.text: str = text
        self.children: list = []
        self.parent: 'Element' = parent
        self.style: dict[str, str] = {}
        # Handles special chars
        for key in SPECIAL_CHARS:
            if key in self.text:
                self.text = self.text.replace(key, SPECIAL_CHARS[key])

    def __repr__(self) -> str:
        return self.text

class Element:
    def __init__(self, tag: str, attributes: dict[str, str], parent: 'Element | None') -> None:
        self.tag: str = tag
        self.attributes: dict[str, str] = attributes
        self.children: list['Element | Text'] = []
        self.parent: 'Element | None' = parent
        self.style: dict[str, str] = {}

    def __repr__(self) -> str:
        attr = " "
        for key in self.attributes:
            if self.attributes[key]:
                q = "\""
                if q in self.attributes[key]: q = "'"
                attr += "{}={}{}{}".format(key, q, self.attributes[key], q)
            else:
                attr += key
            attr += " "
        attr = attr[:-1]
        return "<" + self.tag + attr + ">"

class BlockLayout:
    def __init__(
            self, 
            node: Element | Text | list[Element | Text], 
            parent: 'BlockLayout | DocumentLayout', 
            previous: 'BlockLayout | None', 
        ) -> None:
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
                    self.x += HSTEP
                case "nav":
                    if self.node.attributes.get("id") == "toc":
                        self.y += VSTEP
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
                        next = BlockLayout(block, self, previous)
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
                        next = BlockLayout([heading.node, child], self, heading.previous)
                        self.children.append(next)
                        previous = next
                        continue
                    # Add block element
                    next = BlockLayout(child, self, previous)
                    self.children.append(next)
                    previous = next
                else:
                    block.append(child)
            # Adds last block of elements
            if block:
                next = BlockLayout(block, self, previous)
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
                        y1 = self.y - VSTEP
                        x2, y2 = self.x + font.measure(text), y1 + font.metrics("linespace")
                        rect = DrawRect(self.x, y1, x2, y2, "grey")
                        cmds.append(rect)
                        cmds.append(DrawText(self.x, y1, text, font, INHERITED_PROPERTIES["color"]))
                    if "links" in self.node.attributes.get("class", "").split():
                        x2, y2 = self.x + self.width, self.y + self.height
                        rect = DrawRect(self.x, self.y, x2, y2, "light grey")
                        cmds.append(rect)
                case "li":
                    x1 = self.x - HSTEP
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
                self.cursor_y += VSTEP

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

class DocumentLayout:
    def __init__(self, node: Element) -> None:
        self.node: Element = node
        self.parent = None
        self.children: list[BlockLayout] = []
        # ---
        self.x: int
        self.y: int
        self.width: int
        self.height: int

    def __repr__(self) -> str:
        return "<{}> x{} y{} w{} h{}".format(self.node.tag, self.x, self.y, self.width, self.height)

    def layout(self) -> None:
        child = BlockLayout(self.node, self, None)
        self.children.append(child)
        self.width = WIDTH - 2*HSTEP
        self.x = HSTEP
        self.y = VSTEP
        child.layout()
        self.height = child.height  

    def paint(self) -> list['DrawText | DrawRect']:
        return []
    
class HTMLParser:    
    def __init__(self, body: str) -> None:
        self.body: str = body
        self.unfinished: list[Element] = []
        self.open_formatting_tags: list[str] = []

    def parse(self) -> Element:
        text = ""
        in_tag = False
        in_comment = False
        in_script = False
        for c in self.body:
            if in_comment:
                text += c
                if text.endswith("-->"):
                    in_comment = False
                    text = ""
            elif c == "<":
                in_tag = True
                if text: self.add_text(text)
                text = ""
            elif c == ">":
                in_tag = False
                if in_script:
                    if text.casefold().startswith("/script"):
                        in_script = False
                    else:
                        self.add_text("<{}>".format(text))
                        text = ""
                        continue
                elif text.casefold().startswith("script"): in_script = True
                self.add_tag(text)
                text = ""
            elif not in_tag and not c.isalnum() and not c.isascii():
                # Splits text with emojis to handle them 
                self.add_text(text)
                self.add_text(c)
                text = ""
            else:
                text += c
                if in_tag and text.startswith("!--"): in_comment = True
        if not in_tag and not in_comment and text:
            self.add_text(text)
        return self.finish()

    def add_text(self, text: str) -> None:
        if text.isspace(): return
        self.implicit_tags(None)
        parent = self.unfinished[-1]
        node = Text(text, parent)
        parent.children.append(node)

    def add_tag(self, tag: str) -> None:
        tag, attributes = self.get_attributes(tag)
        if tag.startswith("!"): return
        self.implicit_tags(tag)
        parent: Element | None
        if tag.startswith("/"):
            if len(self.unfinished) == 1: return
            tag_name = tag[1:]
            # Mis-nesting support
            is_misnested = tag_name in TEXT_FORMATTING_TAGS and tag_name != self.open_formatting_tags[-1]
            open_tags: list[str] = []
            if is_misnested:
                while self.open_formatting_tags:
                    last_tag = self.open_formatting_tags[-1]
                    if tag_name == last_tag: break
                    self.add_tag("/{}".format(last_tag))
                    open_tags.append(last_tag)
            if tag_name in TEXT_FORMATTING_TAGS and tag_name == self.open_formatting_tags[-1]: 
                self.open_formatting_tags.pop()
            # ---
            node = self.unfinished.pop()
            parent = self.unfinished[-1]
            if tag_name in UNNESTABLE_TAGS:
                while tag_name == parent.tag:
                    if not parent.parent: break
                    parent = parent.parent
            parent.children.append(node)
            # Mis-nesting support
            if is_misnested: 
                for last_tag in reversed(open_tags):
                    self.add_tag(last_tag)
            # ---
        elif tag in SELF_CLOSING_TAGS:
            parent = self.unfinished[-1]
            node = Element(tag, attributes, parent)
            parent.children.append(node)
        else:
            if tag in TEXT_FORMATTING_TAGS: self.open_formatting_tags.append(tag)
            parent = self.unfinished[-1] if self.unfinished else None
            node = Element(tag, attributes, parent)
            self.unfinished.append(node)

    def implicit_tags(self, tag: str | None) -> None:
        while True:
            open_tags = [node.tag for node in self.unfinished]
            if open_tags == [] and tag != "html":
                self.add_tag("html")
            elif open_tags == ["html"] and tag not in ["head", "body", "/html"]:
                if tag in HEAD_TAGS:
                    self.add_tag("head")
                else:
                    self.add_tag("body")
            elif open_tags == ["html", "head"] and tag not in ["/head"] + HEAD_TAGS:
                self.add_tag("/head")
            else:
                break

    def get_attributes(self, text: str) -> tuple[str, dict[str, str]]:
        spl = text.split(None, 1)
        if len(spl) == 1: return (spl[0], {})
        tag, attrstr = spl
        tag = tag.casefold()
        attributes: dict[str, str] = {}
        parts: list[str] = []
        quotes = ""
        buffer = ""
        for c in attrstr:
            if c in ["\"", "'"]:
                if not quotes:
                    quotes = c
                elif c == quotes:
                    parts.append(buffer)
                    buffer = ""
                    quotes = ""
                else:
                    buffer += c
            elif c.isspace() and not quotes:
                parts.append(buffer)
                buffer = ""
            else:
                buffer += c
        if buffer:
            parts.append(buffer)
        for attrpair in parts:
            if not attrpair: continue
            if "=" in attrpair:
                key, value = attrpair.split("=", 1)
                key = key.strip()
                attributes[key.casefold()] = value
            else:
                attributes[attrpair.casefold()] = ""
        return tag, attributes

    def finish(self) -> Element:
        if not self.unfinished:
            self.implicit_tags(None)
        while len(self.unfinished) > 1:
            node = self.unfinished.pop()
            parent = self.unfinished[-1]
            parent.children.append(node)
        return self.unfinished.pop()
        
class HTMLSourceParser(HTMLParser):
    def __init__(self, body: str) -> None:
        super().__init__(body)

    def recurse(self, node: Element | Text, indent = 0) -> None:
        if isinstance(node, Element):
            self.add_text(" " * indent + node.__repr__() + "\n")
        elif isinstance(node, Text):
            self.add_tag("b")
            text = ""
            for line in node.text.split("\n"): 
                text += " " * indent + line.strip() + "\n"
            self.add_text(text)
            self.add_tag("/b")
        for child in node.children:
            self.recurse(child, indent=indent+1)
        if isinstance(node, Element) and node.tag not in SELF_CLOSING_TAGS:
            self.add_text(" " * indent + "</{}>".format(node.tag) + "\n")
        
    def source(self) -> Element:
        nodes = self.parse()
        self.add_tag("pre")
        self.recurse(nodes)
        self.add_tag("/pre")
        return self.finish()

class TagSelector:
    def __init__(self, tag: str) -> None:
        self.tag: str = tag
        self.priority = 1

    def __repr__(self) -> str:
        return "*|{}|".format(self.tag)

    def matches(self, node: Element | Text) -> bool:
        return isinstance(node, Element) and self.tag == node.tag

class DescendantSelector:
    def __init__(self, ancestor: 'TagSelector | DescendantSelector', descendant: TagSelector) -> None:
        self.ancestor: 'TagSelector | DescendantSelector' = ancestor
        self.descendant: TagSelector = descendant
        self.priority = ancestor.priority + descendant.priority

    def __repr__(self) -> str:
        return "*|{} {}|".format(self.ancestor.__repr__()[2:-1], self.descendant.__repr__()[2:-1])

    def matches(self, node: Element | Text):
        if not self.descendant.matches(node): return False
        while node.parent:
            if self.ancestor.matches(node.parent): return True
            node = node.parent
        return False

class CSSParser:
    def __init__(self, s: str) -> None:
        self.s: str = s
        self.i = 0

    def whitespace(self) -> None:
        while self.i < len(self.s) and self.s[self.i].isspace():
            self.i += 1
    
    def word(self) -> str:
        start = self.i
        while self.i < len(self.s):
            if self.s[self.i].isalnum() or self.s[self.i] in "#-.%":
                self.i += 1
            else:
                break
        if not (self.i > start):
            raise Exception("Parsing error")
        return self.s[start:self.i]

    def literal(self, literal: str) -> None:
        if not (self.i < len(self.s)) and (self.s[self.i] == literal):
            raise Exception("Parsing error")
        self.i += 1

    def pair(self) -> tuple[str, str]:
        prop = self.word()
        self.whitespace()
        self.literal(":")
        self.whitespace()
        val = self.word()
        return prop.casefold(), val
    
    def ignore_until(self, chars: list[str]) -> str | None:
        while self.i < len(self.s):
            if self.s[self.i] in chars:
                return self.s[self.i]
            else:
                self.i += 1
        return None

    def body(self) -> dict[str, str]:
        pairs: dict[str, str] = {}
        while self.i < len(self.s) and self.s[self.i] != "}":
            try:
                prop, val = self.pair()
                pairs[prop] = val
                self.whitespace()
                self.literal(";")
                self.whitespace()
            except Exception:
                why = self.ignore_until([";", "}"])
                if why == ";":
                    self.literal(";")
                    self.whitespace()
                else:
                    break
        return pairs
    
    def selector(self) -> TagSelector | DescendantSelector:
        out = TagSelector(self.word().casefold())
        self.whitespace()
        while self.i < len(self.s) and self.s[self.i] != "{":
            tag = self.word()
            descendant = TagSelector(tag.casefold())
            out = DescendantSelector(out, descendant)
            self.whitespace()
        return out
    
    def parse(self) -> list[CSS_rule]:
        rules: list[CSS_rule] = []
        while self.i < len(self.s):
            try:
                self.whitespace()
                selector = self.selector()
                self.literal("{")
                self.whitespace()
                body = self.body()
                self.literal("}")
                rules.append((selector, body))  
            except Exception:
                why = self.ignore_until(["}"])
                if why == "}":
                    self.literal("}")
                    self.whitespace()
                else:
                    break
        return rules

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

# --- 
DEFAULT_STYLE_SHEET = CSSParser(
    open(
        os.path.join(BASE_DIR, "assets", "browser.css")
    ).read()
).parse()

# ---
class Browser:
    def __init__(self) -> None:
        self.images: list[tkinter.PhotoImage] = []
        self.window = tkinter.Tk()
        self.window.title("StrangeBrows")
        self.canvas = tkinter.Canvas(
            self.window,
            width=WIDTH,
            height=HEIGHT,
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
        global WIDTH
        global HEIGHT
        if WIDTH == e.width and HEIGHT == e.height: return
        WIDTH = e.width
        HEIGHT = e.height
        self.document = DocumentLayout(self.nodes)
        self.document.layout()
        self.display_list = []
        paint_tree(self.document, self.display_list)
        self.draw()

    # --- Functions
    def display_height(self) -> int:
        h = self.document.height - HEIGHT + VSTEP*2
        return max(0, h)

    def draw(self) -> None:
        self.canvas.delete("all")
        # Draws content
        for cmd in self.display_list:
            if cmd.top > self.scroll + HEIGHT: continue
            if cmd.bottom < self.scroll: continue
            cmd.execute(self.scroll, self.canvas)
        # Draws scrollbar
        dh = self.display_height()
        if dh > 0:
            ratio = int((self.scroll / dh) * (HEIGHT - VSTEP))
            self.canvas.create_rectangle(
                WIDTH - HSTEP + SCROLLBAR_OFFSET,
                ratio + SCROLLBAR_OFFSET,
                WIDTH - SCROLLBAR_OFFSET,
                ratio + VSTEP - SCROLLBAR_OFFSET,
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
        self.document = DocumentLayout(self.nodes)
        self.document.layout()
        self.display_list = []
        paint_tree(self.document, self.display_list)  
        self.draw()

# ---
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

def style(node: Element | Text, rules: list[CSS_rule]) -> None:
    node.style = {}
    for property, default_value in INHERITED_PROPERTIES.items():
        if node.parent:
            node.style[property] = node.parent.style[property]
        else:
            node.style[property] = default_value
    for selector, body in rules:
        if not selector.matches(node): continue
        for property, value in body.items():
            node.style[property] = value
    if isinstance(node, Element) and "style" in node.attributes:
        pairs = CSSParser(node.attributes["style"]).body()
        for property, value in pairs.items():
            node.style[property] = value
    if node.style["font-size"].endswith("%"):
        if node.parent:
            parent_font_size = node.parent.style["font-size"]
        else:
            parent_font_size = INHERITED_PROPERTIES["font-size"]
        node_pct = float(node.style["font-size"][:-1]) / 100
        parent_px = float(parent_font_size[:-2])
        node.style["font-size"] = str(node_pct * parent_px) + "px"
    for child in node.children:
        style(child, rules)

def cascade_priority(rule: CSS_rule) -> int:
    selector, body = rule
    return selector.priority

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

# --- Start
if __name__ == "__main__":
    parser = ArgumentParser(description="Simple web browser")
    parser.add_argument("url", type=str, help="Url to visit", nargs="?", default="")
    args = parser.parse_args()
    Browser().load(URL(args.url))
    tkinter.mainloop()