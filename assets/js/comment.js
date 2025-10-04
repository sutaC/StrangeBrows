var strong = document.querySelector("strong");
var allow_submit = true;

function lengthCheck() {
    var value = this.getAttribute("value");
    allow_submit = value.length <= 100;
    if (!allow_submit) {
        strong.innerHTML = "Text to long!";
    } else {
        strong.innerHTML = "";
    }
}

var inputs = document.querySelectorAll("input");
for (var i = 0; i < inputs.length; i++) {
    inputs[i].addEventListener("keydown", lengthCheck);
}

var form = document.querySelector("form");
form.addEventListener("submit", function (e) {
    if (!allow_submit) e.preventDefault();
});
