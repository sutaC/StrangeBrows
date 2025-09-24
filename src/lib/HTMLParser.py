SPECIAL_CHARS = {
    "&lt;": "<",
    "&gt;": ">",
    "&quot;": "\"",
    "&shy;": "\N{soft hyphen}",
    "&amp;": "&",
}
TEXT_FORMATTING_TAGS = [
    "b", "i", "small", "big"
]
UNNESTABLE_TAGS = [
    "p", "li"
]
SELF_CLOSING_TAGS = [
    "area", "base", "br", "col", "embed", "hr", "img", "input",
    "link", "meta", "param", "source", "track", "wbr",
]
HEAD_TAGS = [
    "base", "basefont", "bgsound", "noscript",
    "link", "meta", "title", "style", "script",
]

class Text:
    def __init__(self, text: str, parent: 'Element') -> None:
        self.text: str = text
        self.children: list = []
        self.parent: 'Element' = parent
        self.style: dict[str, str] = {}
        self.is_focused = False
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
        self.is_focused: bool = False

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

class HTMLParser:    
    def __init__(self, body: str) -> None:
        self.body: str = body
        self.unfinished: list[Element] = []
        self.open_formatting_tags: list[str] = []
        self.in_pre = False

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
        if not self.in_pre and text.isspace(): return
        self.implicit_tags(None)
        parent = self.unfinished[-1]
        node = Text(text, parent)
        parent.children.append(node)

    def add_tag(self, tag: str) -> None:
        tag, attributes = self.get_attributes(tag)
        if tag.startswith("!"): return
        elif tag == "pre": self.in_pre = True
        elif tag == "/pre": self.in_pre = False
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
