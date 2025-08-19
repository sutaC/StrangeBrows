#!/usr/bin/env python3
import socket
import ssl

class URL:
    def __init__(self, url: str):
        if not url.startswith("data"):
            self.scheme, url = url.split("://", 1)
        else:
            self.scheme, url = url.split(":", 1)
            self.type, self.content = url.split(",", 1)
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
        if self.scheme == "file":
            file = open(self.path, "r")
            content = file.read()
            file.close()
            return content
        elif self.scheme == "data":
            return self.content
        s = socket.socket(
            family=socket.AF_INET, 
            type=socket.SOCK_STREAM, 
            proto=socket.IPPROTO_TCP
        )
        s.connect((self.host, self.port))
        if self.scheme == "https":
            ctx = ssl.create_default_context()
            s = ctx.wrap_socket(s, server_hostname=self.host)
        request_headers = {
            "Host": self.host,
            "Connection": "close",
            "User-Agent": "StrangeBrows"
        }
        request = "GET {} HTTP/1.1\r\n".format(self.path)
        for header in request_headers:
            request += "{}: {}\r\n".format(header, request_headers[header])
        request += "\r\n"
        s.send(request.encode("utf-8"))
        response = s.makefile("r", encoding="utf-8", newline="\r\n")
        statusline = response.readline()
        version, status, explenation = statusline.split(" ", 2)
        response_headers = {}
        while True:
            line = response.readline()
            if line == "\r\n": break
            header, value = line.split(":", 1)
            response_headers[header.casefold()] = value.strip()
        assert "transfer-encoding" not in response_headers
        assert "content-encoding" not in response_headers
        content = response.read()
        s.close()
        return content

def show(body: str) -> None:
    in_tag = False
    for c in body:
        if c == "<":
            in_tag = True
        elif c == ">":
            in_tag = False
        elif not in_tag:
            print(c, end="")

def load(url: URL) -> None:
    body = url.request()
    show(body)

# --- Start

if __name__ == "__main__":
    import sys
    url: str
    if len(sys.argv) > 1:
        url = sys.argv[1]
    else:
        import os
        url = "file://"
        url += os.path.join(os.path.dirname(__file__), os.pardir, "assets", "home.html")
    load(URL(url))