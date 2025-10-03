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
        self.interp.export_function("createElement", self.createElement)
        self.interp.export_function("appendChild", self.appendChild)
        self.interp.export_function("insertBefore", self.insertBefore)
        self.interp.export_function("removeChild", self.removeChild)
        self.interp.export_function("innerHTML_set", self.innerHTML_set)
        self.interp.export_function("children_get", self.children_get)
        self.interp.export_function("toString", self.toString)
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

    def createElement(self, tagName: str) -> int:
        elt = Element(tagName, {}, None)
        handle = self.get_handle(elt)
        return handle

    def appendChild(self, h_parent: int, h_child: int) -> None:
        parent = self.handle_to_node[h_parent]
        child = self.handle_to_node[h_child]
        if child.parent:
            child.parent.children.remove(child)
        child.parent = parent
        parent.children.append(child)
        self.tab.render()

    def insertBefore(self, h_elt: int, h_insert: int) -> None:
        elt = self.handle_to_node[h_elt]
        insert = self.handle_to_node[h_insert]
        parent = elt.parent
        if not parent: return
        idx = parent.children.index(elt)
        if insert.parent:
            insert.parent.children.remove(insert)
        insert.parent = parent
        parent.children.insert(idx, insert)
        self.tab.render()

    def removeChild(self, h_parent: int, h_child: int) -> int | None:
        child = self.handle_to_node[h_child]
        parent = self.handle_to_node[h_parent]
        if child not in parent.children: return None
        parent.children.remove(child)
        child.parent = None
        self.tab.render()
        return h_child

    def innerHTML_set(self, handle: int, s: str) -> None:
        doc = HTMLParser("<html><body>" + s + "</body></html>").parse()
        new_nodes = doc.children[0].children
        elt = self.handle_to_node[handle]
        elt.children = new_nodes
        for child in elt.children:
            child.parent = elt
        self.tab.render()

    def children_get(self, handle: int) -> list[int]:
        node = self.handle_to_node[handle]
        children = [
            self.get_handle(ch) for ch in node.children
            if isinstance(ch, Element)
        ]
        return children
    
    def toString(self, handle: int) -> str:
        elt = self.handle_to_node[handle]
        return elt.__repr__()

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
