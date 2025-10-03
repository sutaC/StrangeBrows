var LISTENERS = {};

console = {
    log: function (msg) {
        call_python("log", msg);
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
    child = call_python("removeChild", this.handle, child.handle);
    if (child == null) return null;
    return new Node(child);
};
Object.defineProperty(Node.prototype, "innerHTML", {
    set: function (s) {
        call_python("innerHTML_set", this.handle, s.toString());
    },
});
Object.defineProperty(Node.prototype, "children", {
    get: function () {
        handles = call_python("children_get", this.handle);
        return handles.map(function (h) {
            return new Node(h);
        });
    },
});

document = {
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

function Event(type) {
    this.type = type;
    this.do_default = true;
}
Event.prototype.preventDefault = function () {
    this.do_default = false;
};
