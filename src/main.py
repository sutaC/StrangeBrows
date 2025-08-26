#!/usr/bin/env python3
from typing import Literal
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

display = tuple[int, int, str, tkinter.font.Font]

BASE_DIR = os.path.join(os.path.dirname(__file__), os.pardir)
WIDTH, HEIGHT = 800, 600
REDIRECT_LIMIT = 5
HSTEP, VSTEP = 13, 18
SCROLL_STEP = 100
SCROLLBAR_OFFSET = 2
FONTS: dict[
    tuple[int, Literal['normal', 'bold'], Literal['roman', 'italic']], 
    tuple[tkinter.font.Font, tkinter.Label]
] = {}
SPECIAL_CHARS = {
    "&lt;": "<",
    "&gt;": ">",
    "&quot;": "\"",
    "&amp;": "&",
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
    def __init__(self, direction: Literal['ltr', 'rtl'] = 'ltr') -> None:
        self.direction: Literal['ltr', 'rtl'] = direction
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
        self.display_list = Layout(self.tokens, width=self.width, direction=self.direction).display_list
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
        self.tokens = lex(body, view_source=url.view_source)
        self.display_list = Layout(self.tokens, width=self.width, direction=self.direction).display_list
        self.calculate_display_height()
        self.draw()

class Text:
    def __init__(self, text: str) -> None:
        self.text = text
        # Handles special chars
        for key in SPECIAL_CHARS:
            if key in self.text:
                self.text = self.text.replace(key, SPECIAL_CHARS[key])

class Tag:
    def __init__(self, tag: str) -> None:
        self.tag = tag

token = Text | Tag

class Layout:
    def __init__(self, tokens: list[token], width:int=WIDTH, direction:Literal["ltr", "rtl"]="ltr") -> None:
        self.display_list: list[display] = []
        self.cursor_x = HSTEP
        self.cursor_y = VSTEP
        self.weight: Literal['normal', 'bold'] = "normal"
        self.style: Literal['roman', 'italic'] = "roman"
        self.size = 16
        self.width = width
        self.line: list[tuple[int, str, tkinter.font.Font]] = []
        self.direction: Literal["ltr", "rtl"] = direction
        for tok in tokens:
            self.token(tok)
        self.flush()

    def token(self, tok: token) -> None:
        if isinstance(tok, Text):
            for word in tok.text.split():
                self.word(word)
        elif isinstance(tok, Tag):
            match tok.tag:
                case "i": self.style = "italic"
                case "/i": self.style = "roman"
                case "b": self.weight = "bold"
                case "/b": self.weight = "normal"
                case "small": self.size -= 2
                case "/small": self.size += 2
                case "big": self.size += 4
                case "/big": self.size -= 4
                case "br": self.flush()
                case "/p": self.flush(); self.cursor_y += VSTEP

    def word(self, word: str) -> None:
        font = get_font(self.size, self.weight, self.style)
        w  = font.measure(word)
        # Text directtion support
        if (self.direction == "ltr" and self.cursor_x + w > self.width - HSTEP) or \
            (self.direction == "rtl" and self.cursor_x - w < HSTEP):
            self.flush()
        # Text directtion support
        if self.direction == "rtl":
            self.cursor_x -= w + font.measure(" ")
        self.line.append((self.cursor_x, word, font))
        # Text directtion support
        if self.direction == "ltr":
            self.cursor_x += w + font.measure(" ")

    def flush(self) -> None:
        if not self.line: return
        metrics = [font.metrics() for x, word, font, in self.line]
        max_ascent = max(metric["ascent"] for metric in metrics)
        baseline = int(self.cursor_y + 1.25 * max_ascent)
        for x, word, font in self.line:
            y = baseline - font.metrics("ascent")
            self.display_list.append((x, y, word, font))
        max_descent = max(metric["descent"] for metric in metrics)
        self.cursor_y = int(baseline + 1.25 * max_descent)
        # Text directtion support
        if self.direction == "ltr":
            self.cursor_x = HSTEP
        elif self.direction == "rtl":
            self.cursor_x = self.width - HSTEP
        self.line = []

def lex(body: str, view_source = False) -> list[token]:
    out: list[token] = []
    if view_source: return [Text(body)]
    buffer = ""
    in_tag = False
    for c in body:
        if c == "<":
            in_tag = True
            if buffer: out.append(Text(buffer))
            buffer = ""
        elif c == ">":
            in_tag = False
            out.append(Tag(buffer))
            buffer = ""
        elif not in_tag and not c.isalnum() and not c.isascii():
            # Splits text with emojis to handle them 
            out.append(Text(buffer))
            out.append(Text(c))
            buffer = ""
        else:
            buffer += c
    if not in_tag and buffer:
        out.append(Text(buffer))
    return out

def get_font(size: int, weight: Literal['normal', 'bold'], style: Literal['roman', 'italic']) -> tkinter.font.Font:
    key = (size, weight, style)
    if key not in FONTS:
        font = tkinter.font.Font(size=size, weight=weight, slant=style)
        label = tkinter.Label(font=font)
        FONTS[key] = (font, label)
    return FONTS[key][0]

# --- Start

if __name__ == "__main__":
    parser = ArgumentParser(description="Simple web browser")
    parser.add_argument("url", type=str, help="Url to visit", nargs="?", default="")
    parser.add_argument("--direction", choices=["ltr", "rtl"], help="Text display direction", default="ltr")
    args = parser.parse_args()
    Browser(direction=args.direction).load(URL(args.url))
    tkinter.mainloop()