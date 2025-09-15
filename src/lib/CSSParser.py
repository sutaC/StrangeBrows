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
# property options-(any if empty) required
SHORTHAND_PROPERTIES = {
    "font": [
        ("font-style", ["italic", "normal"], False),
        ("font-weight", ["bold", "normal"], False),
        ("font-size", [], True),
        ("font-style", [], True),
    ]
}

CSS_rule = tuple['Selector', dict[str, str]]

class Selector(ABC):
    def __init__(self) -> None:
        self.priority: int

    @abstractmethod
    def matches(self, node: Element | Text) -> bool:
        pass

    @abstractmethod
    def __deepcopy__(self) -> 'Selector':
        pass

class TagSelector(Selector):
    def __init__(self, tag: str) -> None:
        self.tag: str = tag
        self.priority = 1

    def __repr__(self) -> str:
        return "*|{}|".format(self.tag)
    
    def __deepcopy__(self) -> 'TagSelector':
        return TagSelector(self.tag)

    def matches(self, node: Element | Text) -> bool:
        return isinstance(node, Element) and self.tag == node.tag

class ClassSelector(Selector):
    def __init__(self, cls: str) -> None:
        self.cls: str = cls.removeprefix(".")
        self.priority = 2

    def __repr__(self) -> str:
        return "*|.{}|".format(self.cls)
    
    def __deepcopy__(self) -> 'ClassSelector':
        return ClassSelector(self.cls)

    def matches(self, node: Element | Text) -> bool:
        return isinstance(node, Element) and self.cls in node.attributes.get("class", "").split()

class IdSelector(Selector):
    def __init__(self, cls: str) -> None:
        self.id: str = cls.removeprefix("#")
        self.priority = 3

    def __repr__(self) -> str:
        return "*|#{}|".format(self.id)
    
    def __deepcopy__(self) -> 'IdSelector':
        return IdSelector(self.id)

    def matches(self, node: Element | Text) -> bool:
        return isinstance(node, Element) and self.id == node.attributes.get("id")

class DescendantSelector(Selector):
    def __init__(self, selectors: list[Selector]) -> None:
        self.selectors: list[Selector] = []
        for selector in selectors:
            if isinstance(selector, DescendantSelector): self.selectors.extend(selector.selectors)
            else: self.selectors.append(selector)
        self.priority: int = sum(s.priority for s in self.selectors)
        
    def __repr__(self) -> str:
        return "*|"+ " ".join(s.__repr__()[2:-1] for s in self.selectors) + "|"

    def __deepcopy__(self) -> 'DescendantSelector':
        return DescendantSelector(self.selectors.copy()) 

    def matches(self, node: Element | Text):
        if not self.selectors[-1].matches(node): return False
        i = len(self.selectors) - 2
        while node.parent and i >= 0:
            if self.selectors[i].matches(node.parent): i -= 1
            node = node.parent
        return i < 0

class SequenceSelector(Selector):
    def __init__(self, selectors: list[Selector]) -> None:
        self.selectors: list[Selector] = []
        for s in selectors:
            if isinstance(s, SequenceSelector): self.selectors.extend(s.selectors)
            else: self.selectors.append(s)
        self.priority: int = sum(s.priority for s in self.selectors)

    def __repr__(self) -> str:
        return "*|"+ "".join(s.__repr__()[2:-1] for s in self.selectors) + "|"
    
    def __deepcopy__(self) -> 'SequenceSelector':
        return SequenceSelector(self.selectors.copy())

    def matches(self, node: Element | Text) -> bool:
        for s in self.selectors:
            if not s.matches(node): return False
        return True

class HasSelector(Selector):
    def __init__(self, parent: Selector, children: list[Selector]) -> None:
        self.parent: Selector = parent
        self.children: list[Selector] = children
        assert not any(isinstance(child, HasSelector) for child in children)
        self.priority: int = parent.priority + sum(child.priority for child in self.children)
        
    def __repr__(self) -> str:
        return "*|" + self.parent.__repr__()[2:-1] + \
        ":has(" + " ".join(child.__repr__()[2:-1] for child in self.children) + ")|"

    def __deepcopy__(self) -> 'HasSelector':
        return HasSelector(self.parent, self.children.copy())
    
    def child_matches(self, node: Element | Text, i=0) -> bool:
        if self.children[i].matches(node):
            if i >= len(self.children) - 1: return True
            if not node.children: return False
            i += 1
        for child in node.children:
            if self.child_matches(child, i): return True
        return False

    def matches(self, node: Element | Text) -> bool:
        if not self.parent.matches(node): return False
        for child in node.children:
            if self.child_matches(child): return True
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
            if self.s[self.i].isalnum() or self.s[self.i] in "#-.%()":
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
        val, _ = self.read_until([";", "}"])
        return prop.casefold(), val
    
    def read_until(self, chars: list[str]) -> tuple[str, str]:
        start = self.i
        while self.i < len(self.s):
            if self.s[self.i] in chars:
                if not (self.i > start):
                    raise Exception("Parsing error")
                return (self.s[start:self.i], self.s[self.i])
            else:
                self.i += 1
        raise Exception("Parsing error")

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
    
    def selector_name(self) -> str:
        name, _ = self.read_until([" ", "{"])
        name = name.casefold()
        # HasSelector support
        if ":has(" in name and not ")" in name:
            try:
                seg, why = self.read_until([")", "{"])
                if why == ")": 
                    name += seg.casefold()
                    seg, _ = self.read_until([" ", "{"])
                    name += seg.casefold()
            except: name = name[:name.find(":has(")]
        return name

    def selector(self) -> Selector:
        name = self.selector_name()
        out = get_selector(name)
        self.whitespace()
        while self.i < len(self.s) and self.s[self.i] != "{":
            name = self.selector_name()
            descendant = get_selector(name)
            out = DescendantSelector([out, descendant])
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
                self.whitespace()
                # !important handling
                important_body: dict[str, str] = {}
                for key in body.copy(): # .copy() to prevent direct dict changing in loop 
                    if body[key].endswith("!important"):
                        value = body.pop(key).removesuffix("!important").rstrip()
                        important_body[key] = value
                if important_body:
                    important_selector = selector.__deepcopy__()
                    important_selector.priority += 10_000
                    rules.append((important_selector, important_body))
                if body: rules.append((selector, body))  
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
        if node.parent and property in node.parent.style:
            node.style[property] = node.parent.style[property]
        else:
            node.style[property] = default_value
    for selector, body in rules:
        if not selector.matches(node): continue
        for property, value in body.items():  
            # shorthand prop support
            if property in SHORTHAND_PROPERTIES: 
                shorthand = SHORTHAND_PROPERTIES[property]
                i = 0
                while i < len(shorthand) - 1:
                    seg, value = value.split(None, 1)
                    ext_prop, vals, req = shorthand[i]
                    while not req and \
                    not (len(vals) == 0) and \
                    not (seg in vals) and \
                    i < len(shorthand) - 1:
                        i += 1
                        ext_prop, vals, req = shorthand[i]
                    node.style[ext_prop] = seg
                    i += 1
                ext_prop = shorthand[i][0]
                node.style[ext_prop] = value
            else:
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

def get_selector(name: str) -> Selector:
    # hasSelector support
    if ":has(" in name:
        if not ")" in name: raise Exception("Parsing error")
        parent, children = name.split(":has(", 1)
        if children.endswith(")"):
            children = children.removesuffix(")")
            rest = ""
        else: children, rest = children.split(")", 1)
        parent_selector = get_selector(parent)
        children_selectors = [get_selector(cname) for cname in children.split()]        
        if children_selectors: combined_selector = HasSelector(parent_selector, children_selectors)
        else: combined_selector = parent_selector
        if rest: combined_selector = SequenceSelector([combined_selector, get_selector(name)])
        return combined_selector
    # SequenceSelector support
    idx = max(name.find("#", 1), name.find(".", 1))     
    if idx > -1:
        return SequenceSelector([
            get_selector(name[:idx]), 
            get_selector(name[idx:])
        ])
    # IdSelector support
    if name.startswith("#"):
        return IdSelector(name)
    # ClassSelector support
    if name.startswith("."):
        return ClassSelector(name)
    # TagSelector support
    return TagSelector(name)