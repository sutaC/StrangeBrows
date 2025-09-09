from abc import ABC, abstractmethod
from .HTMLParser import Element, Text

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

CSS_rule = tuple['Selector', dict[str, str]]

class Selector(ABC):
    def __init__(self) -> None:
        self.priority: int

    @abstractmethod
    def matches(self, node: Element | Text) -> bool:
        pass

class TagSelector(Selector):
    def __init__(self, tag: str) -> None:
        self.tag: str = tag
        self.priority = 2

    def __repr__(self) -> str:
        return "*|{}|".format(self.tag)

    def matches(self, node: Element | Text) -> bool:
        return isinstance(node, Element) and self.tag == node.tag

class ClassSelector(Selector):
    def __init__(self, cls: str) -> None:
        self.cls: str = cls.removeprefix(".")
        self.priority = 1

    def __repr__(self) -> str:
        return "*|.{}|".format(self.cls)
    
    def matches(self, node: Element | Text) -> bool:
        return isinstance(node, Element) and self.cls in node.attributes.get("class", "").split()

class DescendantSelector(Selector):
    def __init__(self, ancestor: Selector, descendant: Selector) -> None:
        super().__init__()
        self.ancestor: Selector = ancestor
        self.descendant: Selector = descendant
        self.priority = ancestor.priority + descendant.priority

    def __repr__(self) -> str:
        anc = self.ancestor.__repr__()[2:-1]
        des = self.descendant.__repr__()[2:-1]
        return "*|{} {}|".format(anc, des)

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
    
    def selector(self) -> Selector:
        name = self.word().casefold()
        out = ClassSelector(name) if name.startswith(".") else TagSelector(name)
        self.whitespace()
        while self.i < len(self.s) and self.s[self.i] != "{":
            name = self.word()
            descendant = ClassSelector(name) if name.startswith(".") else TagSelector(name)
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