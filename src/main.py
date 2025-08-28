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
display = tuple[int, int, str, tkinter.font.Font]

BASE_DIR = os.path.join(os.path.dirname(__file__), os.pardir)
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
            url = "file://" + os.path.join(BASE_DIR, "assets", "home.html")
        self.url: str = url
        try:
            self.parse(self.url)
        except:
            print("Recived malformed url '{}', unable to continue...".format(self.url))
            self.url = "about:blank"
        atexit.register(self.cleanup)

    def cleanup(self) -> None:
        if self.saved_socket is not None:
            self.saved_socket.close()

    def parse(self, url: str) -> None:
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
            if location.startswith("/"):
                self.path = location
            else:
                self.parse(location)
            return self.request()
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

class Browser:
    def __init__(self, direction: Literal["ltr", "rtl"] = "ltr") -> None:
        self.direction: Literal["ltr", "rtl"] = direction
        self.images: list[tkinter.PhotoImage] = []
        self.width, self.height = WIDTH, HEIGHT
        self.window = tkinter.Tk()
        self.window.title("StrangeBrows")
        self.canvas = tkinter.Canvas(
            self.window,
            width=self.width,
            height=self.height,
        )
        self.canvas.pack(fill="both", expand=1)
        self.display_list: list[display] = []
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
        if self.scroll == 0: return 
        self.scroll -= SCROLL_STEP
        if self.scroll < 0: self.scroll = 0
        self.draw()

    def scrolldown(self, e: tkinter.Event) -> None:
        if self.scroll == self.display_height: return
        self.scroll += SCROLL_STEP
        if self.scroll > self.display_height: self.scroll = self.display_height
        self.draw()

    def scrollmousewheel_win32(self, e: tkinter.Event) -> None:
        if e.delta > 0 and self.scroll == 0: return
        if e.delta < 0 and self.scroll == self.display_height: return
        e.delta = int(e.delta / 120 * SCROLL_STEP) # Resets win32 standart 120 step
        self.scroll -= e.delta
        if self.scroll < 0: self.scroll = 0
        if self.scroll > self.display_height: self.scroll = self.display_height
        self.draw()

    def scrollmousewheel_darwin(self, e: tkinter.Event) -> None:
        if e.delta < 0 and self.scroll == 0: return
        if e.delta > 0 and self.scroll == self.display_height: return
        e.delta = e.delta * SCROLL_STEP # Resets darwin standart 1 step
        self.scroll += e.delta
        if self.scroll < 0: self.scroll = 0
        if self.scroll > self.display_height: self.scroll = self.display_height
        self.draw()

    def configure(self, e: tkinter.Event) -> None:
        if self.width == e.width and self.height == e.height: return
        self.width, self.height = e.width, e.height
        self.display_list = Layout(self.nodes, width=self.width, direction=self.direction).display_list
        self.calculate_display_height()
        self.draw()

    # --- Functions
    def calculate_display_height(self) -> None:
        if len(self.display_list) == 0:
            self.display_height = 0
            return
        self.display_height = self.display_list[-1][1] - self.height + VSTEP * 2
        if self.display_height < 0: self.display_height = 0

    def draw(self) -> None:
        self.canvas.delete("all")
        # Draws content
        for x, y, word, font in self.display_list:
            # Prevents drawing out of bounds
            if y > self.scroll + self.height: continue
            if y + VSTEP < self.scroll: continue
            y = y - self.scroll
            # Prints emojis
            if len(word) == 1 and not word.isalnum() and not word.isascii():
                code = hex(ord(word))[2:].upper()
                image_path = os.path.join(BASE_DIR, 'assets', 'emojis', "{}.png".format(code))
                if os.path.isfile(image_path):
                    image = tkinter.PhotoImage(file=image_path)
                    self.canvas.create_image(x, y, image=image, anchor="nw")
                    self.images.append(image) # Prevents gb collection
                    continue
            # Prints text
            self.canvas.create_text(x, y, text=word, font=font, anchor="nw")
        # Draws scrollbar
        if self.display_height > 0:
            ratio = int((self.scroll / self.display_height) * (self.height - VSTEP))
            self.canvas.create_rectangle(
                self.width - HSTEP + SCROLLBAR_OFFSET,
                ratio + SCROLLBAR_OFFSET,
                self.width - SCROLLBAR_OFFSET,
                ratio + VSTEP - SCROLLBAR_OFFSET,
                fill="blue",
                outline="blue"
            )

    def load(self, url: URL) -> None:
        body = url.request()
        self.nodes = HTMLParser(body).parse(view_source=url.view_source)
        self.display_list = Layout(self.nodes, width=self.width, direction=self.direction).display_list
        self.calculate_display_height()
        self.draw()

class Text:
    def __init__(self, text: str, parent) -> None:
        self.text = text
        self.children = []
        self.parent = parent
        # Handles special chars
        for key in SPECIAL_CHARS:
            if key in self.text:
                self.text = self.text.replace(key, SPECIAL_CHARS[key])

    def __repr__(self) -> str:
        return self.text

class Element:
    def __init__(self, tag: str, attributes: dict[str, str], parent) -> None:
        self.tag = tag
        self.attributes = attributes
        self.children = []
        self.parent = parent

    def __repr__(self) -> str:
        return "<" + self.tag + ">"

class Layout:
    def __init__(self, nodes: Element, width:int=WIDTH, direction: Literal["ltr", "rtl"] = "ltr") -> None:
        self.direction: Literal["ltr", "rtl"] = direction
        self.display_list: list[display] = []
        self.cursor_x = HSTEP
        self.cursor_y = VSTEP
        self.family = "" # Uses default
        self.size = 16
        self.weight: Literal['normal', 'bold'] = "normal"
        self.style: Literal['roman', 'italic'] = "roman"
        self.width = width
        self.line: list[line_display] = []
        self.centered = False
        self.superscript = False
        self.abbr = False
        self.pre = False
        self.recurse(nodes)
        self.flush()

    def recurse(self, tree: Element| Text) -> None:
        if isinstance(tree, Text):
            # <pre> support
            if self.pre:
                words = tree.text.split(r"\n")
                for idx, word in enumerate(words):
                    self.word(word)
                    if idx < len(words) - 1: self.flush()
                return
            # ---
            for word in tree.text.split():
                # <abbr> support
                if self.abbr:
                    for word in split_cases(word):
                        self.word(word)
                    return
                # ---
                self.word(word)
        elif isinstance(tree, Element):
            self.open_tag(tree.tag)
            for child in tree.children:
                self.recurse(child)
            self.close_tag(tree.tag)

    def word(self, word: str) -> None:
        weight = self.weight
        size = self.size
        options: dict[str, Any] = {
            "superscript": self.superscript
        }
        # <abbr> support
        if self.abbr and word.islower():
            word = word.upper()
            weight = "bold"
            if not self.superscript: size = int(size * 0.75)
        # <sup> support
        if self.superscript: size //= 2
        font = get_font(self.family, size, weight, self.style)
        w  = font.measure(word)
        # Auto line breaks
        if self.cursor_x + w > self.width - HSTEP and not self.pre:
            # Soft hyphens support
            if "\N{soft hyphen}" in word:
                seq = word
                remainder = ""
                while "\N{soft hyphen}" in seq and self.cursor_x + w > self.width - HSTEP:
                    seq, r = seq.rsplit("\N{soft hyphen}", 1)
                    if remainder: remainder = "\N{soft hyphen}" + remainder # To save \N position
                    remainder = r + remainder
                    seq_w = font.measure(seq + "-")
                    if self.cursor_x + seq_w > self.width - HSTEP: continue
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
        if not self.pre: self.cursor_x += font.measure(" ")

    def flush(self) -> None:
        if not self.line: return
        # <h1 class="title"> - Centerd line support
        if self.centered:
            x, word, font, opt = self.line[-1]
            line_end = x + font.measure(word)
            padding = (self.width - line_end - HSTEP) // 2
            for idx, text in enumerate(self.line):
                self.line[idx] = (text[0] + padding, text[1], text[2], text[3])
        # right-to-left text direction support
        elif self.direction == "rtl": 
            x, word, font, opt = self.line[-1]
            line_end = x + font.measure(word)
            padding = self.width - line_end - HSTEP
            for idx, text in enumerate(self.line):
                self.line[idx] = (text[0] + padding, text[1], text[2], text[3])
        # ---
        metrics = [font.metrics() for x, word, font, opt in self.line]
        max_ascent = max(metric["ascent"] for metric in metrics)
        baseline = int(self.cursor_y + 1.25 * max_ascent)
        for x, word, font, opt in self.line:
            y = baseline - font.metrics("ascent")
            if opt["superscript"]: y = self.cursor_y + max_ascent // 3 # <sup> support
            if "\N{soft hyphen}" in word: word = word.replace("\N{soft hyphen}", "") # Removes visible soft hyphen 
            self.display_list.append((x, y, word, font))
        max_descent = max(metric["descent"] for metric in metrics)
        self.cursor_y = int(baseline + 1.25 * max_descent)
        self.cursor_x = HSTEP
        self.line = []

    def open_tag(self, tag: str) -> None:
        match tag:
            case "i": self.style = "italic"
            case "b": self.weight = "bold"
            case "small": self.size -= 2
            case "big": self.size += 4
            case "br": 
                if self.pre: return
                self.flush()
            case 'h1': 
                if self.pre: return
                self.flush()
                self.centered = True
            case "sup": self.superscript = True
            case "abbr": self.abbr = True
            case "pre": 
                self.pre = True
                self.family = "Courier New"
                self.flush()

    def close_tag(self, tag: str) -> None:
        match tag:
            case "i": self.style = "roman"
            case "b": self.weight = "normal"
            case "small": self.size += 2
            case "big": self.size -= 4
            case "p": 
                if self.pre: return
                self.flush()
                self.cursor_y += VSTEP
            case "h1":
                if self.pre: return
                if self.centered: self.flush()
                self.centered = False
            case "sup": self.superscript = False
            case "abbr": self.abbr = False
            case "pre": 
                self.pre = False
                self.family = "" # Default font
                self.flush()

class HTMLParser:
    HEAD_TAGS = [
        "base", "basefont", "bgsound", "noscript",
        "link", "meta", "title", "style", "script",
    ]
    
    def __init__(self, body: str) -> None:
        self.body: str = body
        self.unfinished: list[Element] = []

    def parse(self, view_source=False) -> Element:
        if view_source: # view_source support
            root = Element("", {}, None)
            node = Text(self.body, root)
            root.children.append(node)
            return root
        text = ""
        in_tag = False
        for c in self.body:
            if c == "<":
                in_tag = True
                if text: self.add_text(text)
                text = ""
            elif c == ">":
                in_tag = False
                self.add_tag(text)
                text = ""
            elif not in_tag and not c.isalnum() and not c.isascii():
                # Splits text with emojis to handle them 
                self.add_text(text)
                self.add_text(c)
                text = ""
            else:
                text += c
        if not in_tag and text:
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
        if tag.startswith("/"):
            if len(self.unfinished) == 1: return
            node = self.unfinished.pop()
            parent = self.unfinished[-1]
            parent.children.append(node)
        elif tag in SELF_CLOSING_TAGS:
            parent = self.unfinished[-1]
            node = Element(tag, attributes, parent)
            parent.children.append(node)
        else:
            parent = self.unfinished[-1] if self.unfinished else None
            node = Element(tag, attributes, parent)
            self.unfinished.append(node)

    def implicit_tags(self, tag: str | None) -> None:
        while True:
            open_tags = [node.tag for node in self.unfinished]
            if open_tags == [] and tag != "html":
                self.add_tag("html")
            elif open_tags == ["html"] and tag not in ["head", "body", "/html"]:
                if tag in self.HEAD_TAGS:
                    self.add_tag("head")
                else:
                    self.add_tag("body")
            elif open_tags == ["html", "head"] and tag not in ["/head"] + self.HEAD_TAGS:
                self.add_tag("/head")
            else:
                break


    def get_attributes(self, text: str) -> tuple[str, dict[str, str]]:
        parts = text.split()
        tag = parts[0].casefold()
        attributes: dict[str, str] = {}
        for attrpair in parts[1:]:
            if "=" in attrpair:
                key, value = attrpair.split("=", 1)
                if len(value) > 2 and value[0] in ["'", "\""]:
                    value = value[1:-1]
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
        

def get_font(family: str, size: int, weight: Literal['normal', 'bold'], style: Literal['roman', 'italic']) -> tkinter.font.Font:
    key = (family, size, weight, style)
    if key not in FONTS:
        font = tkinter.font.Font(family=family, size=size, weight=weight, slant=style)
        label = tkinter.Label(font=font)
        FONTS[key] = (font, label)
    return FONTS[key][0]

def split_cases(text: str) -> list[str]:
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

def print_tree(node: Element | Text, indent=0) -> None:
    print(" " * indent, node)
    for child in node.children:
        print_tree(child, indent+2)

# --- Start

if __name__ == "__main__":
    parser = ArgumentParser(description="Simple web browser")
    parser.add_argument("url", type=str, help="Url to visit", nargs="?", default="")
    parser.add_argument("--direction", choices=["ltr", "rtl"], help="Text direction on screen", default="ltr")
    args = parser.parse_args()
    Browser(direction=args.direction).load(URL(args.url))
    tkinter.mainloop()