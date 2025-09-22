import os
import tkinter
import tkinter.font
from . import BASE_DIR
from abc import ABC, abstractmethod

class Rect:
    def __init__(self, left: int, top: int, right: int, bottom: int) -> None:
        self.left: int = left
        self.top: int = top
        self.right: int = right
        self.bottom: int = bottom

    def contains_point(self, x: int, y: int) -> bool:
        return x >= self.left and x < self.right \
        and y >= self.top and y < self.bottom

class Draw(ABC):
    def __init__(self) -> None:
        from .Layout import Layout
        self.rect: Rect
        self.layout: Layout | None

    @abstractmethod
    def execute(self, scroll: int, canvas: tkinter.Canvas) -> None:
        pass

class DrawText(Draw):
    def __init__(self, 
    x1: int, 
    y1: int, 
    text: str, 
    font: tkinter.font.Font, 
    color: str,
    layout = None, 
    ) -> None:
        from .Layout import Layout
        assert isinstance(layout, Layout | None)
        self.layout = layout
        self.rect: Rect = Rect(
            x1, y1,
            x1 + font.measure(text),
            y1 + font.metrics("linespace")
        )
        self.text: str = text
        self.font: tkinter.font.Font = font
        self.bottom: int = y1 + font.metrics("linespace")
        self.color: str = color
        # Emoji handling
        self.image: tkinter.PhotoImage | None = None
        if len(text) == 1 and not text.isalnum() and not text.isascii():
            code = hex(ord(self.text))[2:].upper()
            image_path = os.path.join(BASE_DIR, 'assets', 'emojis', "{}.png".format(code))
            if os.path.isfile(image_path):
                self.image = tkinter.PhotoImage(file=image_path)

    def execute(self, scroll: int, canvas: tkinter.Canvas) -> None:
        # Draws emojis
        if self.image:
            canvas.create_image(self.rect.left, self.rect.top, image=self.image, anchor="nw")
            return
        # Checks is color valid
        if not validate_color(self.color, canvas): self.color = "black"
        canvas.create_text(
            self.rect.left, self.rect.top - scroll,
            text=self.text,
            font=self.font,
            anchor="nw",
            fill=self.color
        )

class DrawRect(Draw):
    def __init__(self, 
    rect: Rect, 
    color: str,
    layout = None, 
    ) -> None:
        from .Layout import Layout
        assert isinstance(layout, Layout | None)
        self.layout = layout
        self.rect: Rect = rect
        self.color: str = color

    def execute(self, scroll: int, canvas: tkinter.Canvas) -> None:
        # Checks if color is valid
        if not validate_color(self.color, canvas): self.color = "white"
        canvas.create_rectangle(
            self.rect.left, self.rect.top - scroll,
            self.rect.right, self.rect.bottom - scroll,
            width=0,
            fill=self.color
        )

class DrawOutline(Draw):
    def __init__(self, 
    rect: Rect, 
    color: str, 
    thikness: int,
    layout = None, 
    ) -> None:
        from .Layout import Layout
        assert isinstance(layout, Layout | None)
        self.layout = layout
        self.rect: Rect = rect
        self.color: str = color
        self.thikness: int = thikness

    def execute(self, scroll: int, canvas: tkinter.Canvas) -> None:
        # Checks if color is valid
        if not validate_color(self.color, canvas): self.color = "black"
        canvas.create_rectangle(
            self.rect.left, self.rect.top - scroll,
            self.rect.right, self.rect.bottom - scroll,
            width=self.thikness,
            outline=self.color
        )

class DrawLine(Draw):
    def __init__(self, 
    x1: int, 
    y1: int, 
    x2: int, 
    y2: int, 
    color: str,  
    thikness: int,
    layout = None
    ) -> None:
        from .Layout import Layout
        assert isinstance(layout, Layout | None)
        self.layout = layout
        self.rect: Rect = Rect(x1, y1, x2, y2)
        self.color: str = color
        self.thikness: int = thikness

    def execute(self, scroll: int, canvas: tkinter.Canvas) -> None:
        # Checks if color is valid
        if not validate_color(self.color, canvas): self.color = "black"
        canvas.create_line(
            self.rect.left, self.rect.top - scroll,
            self.rect.right, self.rect.bottom - scroll,
            fill=self.color, width=self.thikness
        )


def validate_color(color: str, widget: tkinter.Widget) -> bool:
    try:
        widget.winfo_rgb(color)
        return True
    except tkinter.TclError:
        return False