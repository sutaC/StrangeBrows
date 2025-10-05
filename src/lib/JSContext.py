import dukpy
from typing import Any
from . import BASE_DIR
from pathlib import Path
from .CSSParser import CSSParser
from .HTMLParser import HTMLParser, Element, Text, parse_to_html

RUNTIME_JS_PATH = Path(BASE_DIR) / "assets" / "js"  / "runtime.js"
RUNTIME_JS = open(RUNTIME_JS_PATH).read()

EVENT_DISPATCH_JS = "new Node(dukpy.handle).dispatchEvent(new Event(dukpy.type))"
ADD_ID_VAR_JS = "globalThis[dukpy.id] = new Node(dukpy.handle)" 
REMOVE_ID_VAR_JS = "delete globalThis[dukpy.id]"

class JSContext:
    def __init__(self, tab) -> None:
        from .Tab import Tab
        assert isinstance(tab, Tab)
        self.tab: Tab = tab
        self.interp: dukpy.JSInterpreter = dukpy.JSInterpreter()
        self.node_to_handle: dict[Element, int] = {}
        self.handle_to_node: dict[int, Element] = {}
        # Exports functions
        self.interp.export_function("log", print)
        self.interp.export_function("querySelector", self.querySelector)
        self.interp.export_function("querySelectorAll", self.querySelectorAll)
        self.interp.export_function("getAttribute", self.getAttribute)
        self.interp.export_function("createElement", self.createElement)
        self.interp.export_function("appendChild", self.appendChild)
        self.interp.export_function("insertBefore", self.insertBefore)
        self.interp.export_function("removeChild", self.removeChild)
        self.interp.export_function("innerHTML_get", self.innerHTML_get)
        self.interp.export_function("innerHTML_set", self.innerHTML_set)
        self.interp.export_function("outerHTML_get", self.outerHTML_get)
        self.interp.export_function("outerHTML_set", self.outerHTML_set)
        self.interp.export_function("children_get", self.children_get)
        self.interp.export_function("parentNode_get", self.parentNode_get)
        self.interp.export_function("id_get", self.id_get)
        self.interp.export_function("id_set", self.id_set)
        self.interp.export_function("toString", self.toString)
        self.interp.export_function("XMLHttpRequest_send", self.XMLHttpRequest_send)
        # Add runtime
        self.interp.evaljs(RUNTIME_JS)
        # Propragates id variables
        self.add_tree_id(self.tab.nodes)
    
    def run(self, script: str, code: str) -> Any | None:
        try:
            return self.interp.evaljs(code)
        except dukpy.JSRuntimeError as e:
            print("Script", script, "crashed", e)

    # Exported functions
    def querySelector(self, selector_text: str) -> int | None:
        from .Tab import tree_to_list
        selector = CSSParser(selector_text).selector()
        for node in tree_to_list(self.tab.nodes, []):
            if selector.matches(node):
                return self.get_handle(node)
        return None

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
        self.add_tree_id(child)
        # Loads new content
        self.load_new_content([child])
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
        self.add_tree_id(insert)
        # Loads new content
        self.load_new_content([insert])
        self.tab.render()

    def removeChild(self, h_parent: int, h_child: int) -> int | None:
        child = self.handle_to_node[h_child]
        parent = self.handle_to_node[h_parent]
        if child not in parent.children: return None
        parent.children.remove(child)
        child.parent = None
        self.remove_tree_id(child)
        self.remove_old_content([child])
        self.tab.render()
        return h_child

    def innerHTML_get(self, handle: int) -> str:
        node = self.handle_to_node[handle]
        return "".join([
            parse_to_html(child) for child in node.children
        ])

    def innerHTML_set(self, handle: int, s: str) -> None:
        doc = HTMLParser("<html><body>" + s + "</body></html>").parse()
        new_nodes = doc.children[0].children
        elt = self.handle_to_node[handle]
        # Removes old references
        for child in elt.children:
            if isinstance(child, Element):
                self.remove_tree_id(child)
            child.parent = None
        self.remove_old_content(elt.children)
        elt.children = new_nodes
        # Adds new references
        for child in elt.children:
            if isinstance(child, Element):
                self.add_tree_id(child)
            child.parent = elt
        # Loads new content
        self.load_new_content(new_nodes)
        self.tab.render()

    def outerHTML_get(self, handle: int) -> str:
        node = self.handle_to_node[handle]
        return parse_to_html(node)
    
    def outerHTML_set(self, handle: int, s: str) -> None:
        elt = self.handle_to_node[handle]
        if not elt.parent: return
        # Adding new nodes
        doc = HTMLParser("<html><body>" + s + "</body></html>").parse()
        new_nodes = doc.children[0].children
        for node in new_nodes:
            assert isinstance(node, Element) or isinstance(node, Text)
            if isinstance(node, Element):
                h_node = self.get_handle(node)
                self.insertBefore(handle, h_node)
            else:
                node.parent = elt.parent
                idx = elt.parent.children.index(elt)
                node.parent.children.insert(idx, node)
        # Removing old node
        h_parent = self.get_handle(elt.parent)
        self.removeChild(h_parent, handle)
        # Loads new content
        self.load_new_content(new_nodes)
        self.tab.render()

    def children_get(self, handle: int) -> list[int]:
        node = self.handle_to_node[handle]
        children = [
            self.get_handle(ch) for ch in node.children
            if isinstance(ch, Element)
        ]
        return children
    
    def parentNode_get(self, handle: int) -> int | None:
        node = self.handle_to_node[handle]
        if node.parent is None: return None
        return  self.get_handle(node.parent)
    
    def id_get(self, handle: int) -> str | None:
        node = self.handle_to_node[handle]
        return node.attributes.get("id")

    def id_set(self, handle: int, s: str) -> None:
        node = self.handle_to_node[handle]
        self.remove_id_var(node)
        if not s: 
            node.attributes.pop("id")
            return
        node.attributes["id"] = s
        self.add_id_var(node)
    
    def toString(self, handle: int) -> str:
        elt = self.handle_to_node[handle]
        return elt.__repr__()

    def dispatch_event(self, type: str, elt: Element) -> bool:
        handle: int = self.node_to_handle.get(elt, -1)
        if handle < 0: return False
        do_default = self.interp.evaljs(EVENT_DISPATCH_JS, type=type, handle=handle)
        return not do_default

    def XMLHttpRequest_send(self, method: str, url: str, body: str | None) -> str:
        full_url = self.tab.url.resolve(url)
        if not self.tab.allowed_request(full_url):
            raise Exception("Cross-origin XHR blocked by CSP")
        if full_url.origin() != self.tab.url.origin():
            raise Exception("Cross-origin XHR request not allowed")
        headers, out = full_url.request(self.tab.url, body)
        return out

    # Inner functions
    def get_handle(self, elt: Element) -> int:
        if elt not in self.node_to_handle:
            handle = len(self.node_to_handle)
            self.node_to_handle[elt] = handle
            self.handle_to_node[handle] = elt
        else:
            handle = self.node_to_handle[elt]
        return handle

    def add_id_var(self, node: Element) -> None:
        if "id" not in node.attributes: return
        id = node.attributes["id"]
        handle = self.get_handle(node)
        self.interp.evaljs(ADD_ID_VAR_JS, id=id, handle=handle)

    def remove_id_var(self, node: Element) -> None:
        if "id" not in node.attributes: return
        id = node.attributes["id"]
        self.interp.evaljs(REMOVE_ID_VAR_JS, id=id)
    
    def add_tree_id(self, node: Element) -> None:
        self.add_id_var(node)
        for child in node.children:
            if isinstance(child, Element):
                self.add_tree_id(child)

    def remove_tree_id(self, node: Element) -> None:
        self.remove_id_var(node)
        for child in node.children:
            if isinstance(child, Element):
                self.remove_tree_id(child)

    def load_new_content(self, new_nodes: list[Element | Text]) -> None:
        from .Tab import tree_to_list
        # Load new content
        for node in new_nodes:
            self.tab.propagate_attributes(node)
            self.tab.load_scripts(node)
        # Check for new sheets
        has_sheets = False
        for node in new_nodes:
            for n in tree_to_list(node, []):
                if isinstance(n, Element) \
                and ((n.tag == "link" \
                and n.attributes.get("rel") == "stylesheet" \
                and "href" in n.attributes \
                ) or (n.tag == "style")):
                    has_sheets = True
                    break
        if has_sheets:
            self.tab.load_sheets()

    def remove_old_content(self, old_nodes: list[Element | Text]) -> None:
        from .Tab import tree_to_list
        # Check for old sheets
        has_sheets = False
        for node in old_nodes:
            for n in tree_to_list(node, []):
                if isinstance(n, Element) \
                and ((n.tag == "link" \
                and n.attributes.get("rel") == "stylesheet" \
                and "href" in n.attributes \
                ) or (n.tag == "style")):
                    has_sheets = True
                    break
        if has_sheets:
            self.tab.load_sheets()
