var LISTENERS = {};

console = {
    log: function () {
        for (var i = 0; i < arguments.length; i++) {
            call_python("log", arguments[i]);
        }
    },
};

function Node(handle) {
    this.handle = handle;
}
Node.prototype.getAttribute = function (attr) {
    return call_python("getAttribute", this.handle, attr);
};
Node.prototype.addEventListener = function (type, listener) {
    if (!LISTENERS[this.handle]) LISTENERS[this.handle] = {};
    var dict = LISTENERS[this.handle];
    if (!dict[type]) dict[type] = [];
    var list = dict[type];
    list.push(listener);
};
Node.prototype.dispatchEvent = function (evt) {
    var type = evt.type;
    var handle = this.handle;
    var list = (LISTENERS[handle] && LISTENERS[handle][type]) || [];
    for (var i = 0; i < list.length; i++) {
        list[i].call(this, evt);
    }
    if (evt.do_propagate && this.parentNode) {
        return this.parentNode.dispatchEvent(evt);
    }
    return evt.do_default;
};
Node.prototype.toString = function () {
    return call_python("toString", this.handle);
};
Node.prototype.appendChild = function (child) {
    call_python("appendChild", this.handle, child.handle);
};
Node.prototype.insertBefore = function (elt) {
    call_python("insertBefore", this.handle, elt.handle);
};
Node.prototype.removeChild = function (child) {
    var child = call_python("removeChild", this.handle, child.handle);
    if (child == null) return null;
    return new Node(child);
};
Object.defineProperty(Node.prototype, "innerHTML", {
    get: function () {
        return call_python("innerHTML_get", this.handle);
    },
    set: function (s) {
        call_python("innerHTML_set", this.handle, s.toString());
    },
});
Object.defineProperty(Node.prototype, "outerHTML", {
    get: function () {
        return call_python("outerHTML_get", this.handle);
    },
    set: function (s) {
        call_python("outerHTML_set", this.handle, s.toString());
    },
});
Object.defineProperty(Node.prototype, "children", {
    get: function () {
        var handles = call_python("children_get", this.handle);
        return handles.map(function (h) {
            return new Node(h);
        });
    },
});
Object.defineProperty(Node.prototype, "parentNode", {
    get: function () {
        var handle = call_python("parentNode_get", this.handle);
        if (handle == null) return null;
        return new Node(handle);
    },
});
Object.defineProperty(Node.prototype, "id", {
    get: function () {
        return call_python("id_get", this.handle);
    },
    set: function (s) {
        call_python("id_set", this.handle, s);
    },
});

document = {
    querySelector: function (s) {
        var handle = call_python("querySelector", s);
        if (handle == null) return null;
        return new Node(handle);
    },
    querySelectorAll: function (s) {
        var handles = call_python("querySelectorAll", s);
        return handles.map(function (h) {
            return new Node(h);
        });
    },
    createElement: function (tagName) {
        var handle = call_python("createElement", tagName);
        return new Node(handle);
    },
};
Object.defineProperty(document, "cookie", {
    get: function () {
        return call_python("cookie_get");
    },
    set: function (s) {
        call_python("cookie_set", s);
    },
});

function Event(type) {
    this.type = type;
    this.do_default = true;
    this.do_propagate = true;
}
Event.prototype.preventDefault = function () {
    this.do_default = false;
};
Event.prototype.stopPropagation = function () {
    this.do_propagate = false;
};

function XMLHttpRequest() {}
XMLHttpRequest.prototype.open = function (method, url, is_async) {
    if (is_async) throw new Error("Asynchronus XHR is not supported");
    this.method = method;
    this.url = url;
};
XMLHttpRequest.prototype.send = function (body) {
    this.responseText = call_python(
        "XMLHttpRequest_send",
        this.method,
        this.url,
        body
    );
};
