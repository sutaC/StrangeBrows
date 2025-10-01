#!/usr/bin/env python3
import re
import socket
import urllib.parse

TOPICS: dict[str, list[str]] = {"Guest book": ['Pavel was here']}

def show_topics() -> str:
    out = "<!doctype html>"
    out += "<h1>Message board</h1>"
    out += "<form action=add method=post>"
    out += "<p><input name=topic required></p>"
    out += "<p><button>Add topic</button></p>"
    out += "</form>"
    out += "<h2>Topics</h2>"
    for topic in TOPICS.keys():
        parsed = urllib.parse.quote(topic)
        out += '<p><a href="/topic/{}">{}</a></p>'.format(parsed, topic)
    return out

def show_comments(topic: str) -> str:
    if topic not in TOPICS: return ""
    parsed = urllib.parse.quote(topic)
    out = "<!doctype html>"
    out += "<h1>" + topic + "</h1>"
    out += '<a href="/">Home</a>'
    out += '<form action="/topic/' + parsed + '/add" method=post>'
    out += "<p><input name=comment required></p>"
    out += "<p><button>Add comment</button></p>"
    out += "</form>"
    for entry in TOPICS[topic]:
        out += "<p>" + entry + "</p>"
    return out

def form_decode(body: str | None) -> dict[str, str]:
    if not body: return {}
    params: dict[str, str] = {}
    for field in body.split("&"):
        name, value = field.split("=", 1)
        name = urllib.parse.unquote_plus(name)
        value = urllib.parse.unquote_plus(value)
        params[name] = value
    return params

def add_topic(params: dict[str, str]) -> str:
    if 'topic' in params:
        topic = params['topic']
        if not topic: return show_topics()
        if topic in TOPICS: return show_comments(topic)
        TOPICS[topic] = []
        return show_comments(topic)
    return show_topics()

def add_entry(topic: str, params: dict[str, str]) -> str:
    if topic not in TOPICS: return ""
    if 'comment' in params:
        if not params["comment"]: return show_comments(topic)
        TOPICS[topic].append(params["comment"])
    else:
        return show_topics()
    return show_comments(topic)

def not_found(url: str, method: str) -> str:
    out = "<!doctype html>"
    out += "<h1>{} {} not found!</h1>".format(method, url)
    return out

def do_request(
method: str, 
url: str, 
headers: dict[str, str], 
body: str | None
) -> tuple[str, str]:
    if url != "/": 
        url = url.rstrip("/")
    # Routes
    if method == "GET" and url == "/": # /
        return "200 OK", show_topics()
    elif method == "POST" and url == "/add": # /add
        params = form_decode(body)
        return "200 OK", add_topic(params)
    elif method == "GET" and re.match(r"^\/topic\/[\w,%,+]+$", url): # /topic/[name]
        topic = url.removeprefix("/topic/")
        topic = urllib.parse.unquote_plus(topic)
        if topic not in TOPICS: print(topic, TOPICS); return "404 Not Found", not_found(url, method)
        return "200 OK", show_comments(topic)
    elif method == "POST" and re.match(r"^\/topic\/[\w,%,+]+\/add$", url): # /topic/[name]/add
        params = form_decode(body)
        topic = url.removeprefix("/topic/").removesuffix("/add")
        topic = urllib.parse.unquote_plus(topic)
        if topic not in TOPICS: return "404 Not Found", not_found(url, method) 
        return "200 OK", add_entry(topic, params)
    else:
        return "404 Not Found", not_found(url, method)

def handle_connection(conx: socket.socket) -> None:
    req = conx.makefile("rb")
    reqline = req.readline().decode()
    method, url, version = reqline.split(" ", 2)
    assert method in ["GET", "POST"]
    headers: dict[str, str] = {}
    while True:
        line = req.readline().decode()
        if line == "\r\n": break
        header, value = line.split(":", 1)
        headers[header.casefold()] = value.strip()
    if 'content-length' in headers:
        length = int(headers['content-length'])
        body = req.read(length).decode()
    else:
        body = None
    status, body  = do_request(method, url, headers, body)
    response = "HTTP/1.0 {}\r\n".format(status)
    response += "Contrnt-Length: {}\r\n".format(len(body.encode()))
    response += "\r\n" + body
    conx.send(response.encode())
    conx.close()

def main() -> None:
    s = socket.socket(
        family=socket.AF_INET,
        type=socket.SOCK_STREAM,
        proto=socket.IPPROTO_TCP
    )
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    port = 8000
    s.bind(('', port))
    s.listen()
    print("[INFO]: Listening on http://127.0.0.1:{}".format(port))
    while True:
        conx, addr = s.accept()
        try:
            handle_connection(conx)
        except Exception as e:
            print("Error ocurred: {}".format(e))
            conx.close()

if __name__ == "__main__":
    main()