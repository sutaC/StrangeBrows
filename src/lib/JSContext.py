import dukpy
from typing import Any
from . import BASE_DIR
from pathlib import Path
from .CSSParser import CSSParser
from .HTMLParser import HTMLParser, Element

RUNTIME_JS_PATH = Path(BASE_DIR) / "assets" / "js"  / "runtime.js"
RUNTIME_JS = open(RUNTIME_JS_PATH).read()

EVENT_DISPATCH_JS = "new Node(dukpy.handle).dispatchEvent(new Event(dukpy.type))"

class JSContext:
    def __init__(self, tab) -> None:
        from .Tab import Tab
        assert isinstance(tab, Tab)
        self.tab: Tab = tab
        self.interp: dukpy.JSInterpreter = dukpy.JSInterpreter()
        self.node_to_handle: dict[Element, int] = {}
        self.handle_to_node: dict[int, Element] = {}
        self.interp.export_function("log", print)
        self.interp.export_function("querySelectorAll", self.querySelectorAll)
        self.interp.export_function("getAttribute", self.getAttribute)
        self.interp.export_function("innerHTML_set", self.innerHTML_set)
        self.interp.evaljs(RUNTIME_JS)
    
    def run(self, script: str, code: str) -> Any | None:
        try:
            return self.interp.evaljs(code)
        except dukpy.JSRuntimeError as e:
            print("Script", script, "crashed", e)

    def querySelectorAll(self, selector_text: str) -> list[int]:
        from .Tab import tree_to_list
        selector = CSSParser(selector_text).selector()
        nodes = [
            node for node in tree_to_list(self.tab.nodes, [])
            if selector.matches(node)
        ]
        return [self.get_handle(node) for node in nodes]

    
    def getAttribute(self, handle: int, attr: str) -> str: 
        elt = self.handle_to_node[handle]
        val = elt.attributes.get(attr)
        return val if val else ""

    def innerHTML_set(self, handle: int, s: str) -> None:
        doc = HTMLParser("<html><body>" + s + "</body></html>").parse()
        new_nodes = doc.children[0].children
        elt = self.handle_to_node[handle]
        elt.children = new_nodes
        for child in elt.children:
            child.parent = elt
        self.tab.render()

    def get_handle(self, elt: Element) -> int:
        if elt not in self.node_to_handle:
            handle = len(self.node_to_handle)
            self.node_to_handle[elt] = handle
            self.handle_to_node[handle] = elt
        else:
            handle = self.node_to_handle[elt]
        return handle
    
    def dispatch_event(self, type: str, elt: Element) -> bool:
        handle: int = self.node_to_handle.get(elt, -1)
        do_default = self.interp.evaljs(EVENT_DISPATCH_JS, type=type, handle=handle)
        return not do_default
