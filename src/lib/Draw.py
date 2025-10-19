import skia
from pathlib import Path
from abc import ABC, abstractmethod
from . import BASE_DIR, IMAGE_CACHE

EMOJIS_PATH = Path(BASE_DIR) / "assets" / "emojis"
NAMED_COLORS = {
    "black": "#000000",
    "white": "#ffffff",
    "red":   "#ff0000",
    "blue": "#0000ff",
    "green": "#00ff00",
    "gray":	"#808080",
    "grey":	"#808080",
    "lightblue": "#add8e6",
    "lightgreen": "#90ee90",
    "orange": "#ffa500",
    "orangered": "#ff4500",
    "yellow": "#ffff00",
    "purple": "#800080",
    "silver": "#c0c0c0",
    "lightgrey": "#d3d3d3",
    "lightgray": "#d3d3d3",

}

class Draw(ABC):
    def __init__(self, rect: skia.Rect, layout = None) -> None:
        from .Layout import Layout
        assert isinstance(layout, Layout | None)
        self.layout: Layout | None = layout
        self.rect: skia.Rect = rect

    @abstractmethod
    def execute(self, canvas: skia.Canvas) -> None:
        pass

class DrawText(Draw):
    def __init__(self, 
    x1: int, 
    y1: int, 
    text: str, 
    font: skia.Font, 
    color: str,
    layout = None, 
    ) -> None:
        from .Layout import linespace
        self.font: skia.Font = font
        self.text: str = text
        rect = skia.Rect.MakeLTRB(
            x1, y1,
            x1 + font.measureText(self.text),
            y1 + linespace(self.font)
        )
        super().__init__(rect=rect, layout=layout)
        self.color: str = color
        # Emoji handling
        self.image: skia.Image | None = None
        if len(self.text) == 1 and not self.text.isalnum() and not self.text.isascii():
            code = hex(ord(self.text))[2:].upper()
            if code in IMAGE_CACHE:
                self.image = IMAGE_CACHE[code]
            else:
                path = EMOJIS_PATH / "{}.png".format(code)
                if path.is_file():
                    self.image = skia.Image.open(str(path))
                    IMAGE_CACHE[code] = self.image

    def __repr__(self) -> str:
        return "DrawText(r'{}' l'{}' / c'{}')".format(
            self.rect, self.layout, self.color 
        )

    def execute(self, canvas: skia.Canvas) -> None:
        if self.image: # Draws Emojis
            canvas.drawImage(self.image, self.rect.left()-1, self.rect.top()+1)
            return
        # Draws text
        paint = skia.Paint(
            AntiAlias=True,
            Color=parse_color(self.color)
        )
        baseline = self.rect.top() - self.font.getMetrics().fAscent
        canvas.drawString(self.text, float(self.rect.left()), baseline, self.font, paint)

class DrawRect(Draw):
    def __init__(self, 
    rect: skia.Rect, 
    color: str,
    layout = None, 
    ) -> None:
        super().__init__(rect=rect, layout=layout)
        self.color: str = color

    def __repr__(self) -> str:
        return "DrawRect(r'{}' l'{}' / c'{}')".format(
            self.rect, self.layout, self.color 
        )

    def execute(self, canvas: skia.Canvas) -> None:
        paint = skia.Paint(
            Color=parse_color(self.color, skia.ColorWHITE)
        )
        canvas.drawRect(self.rect, paint)

class DrawRRect(Draw):
    def __init__(self, 
    rect: skia.Rect, 
    radius: float,
    color: str,
    layout = None, 
    ) -> None:
        super().__init__(rect=rect, layout=layout)
        self.rrect = skia.RRect.MakeRectXY(self.rect, radius, radius)
        self.color: str = color

    def __repr__(self) -> str:
        return "DrawRRect(r'{}' l'{}' / c'{}')".format(
            self.rect, self.layout, self.color
        )

    def execute(self, canvas: skia.Canvas) -> None:
        paint = skia.Paint(
            Color=parse_color(self.color, skia.ColorWHITE)
        )
        canvas.drawRRect(self.rrect, paint)

class DrawOutline(Draw):
    def __init__(self, 
    rect: skia.Rect, 
    color: str, 
    thikness: int,
    layout = None, 
    ) -> None:
        super().__init__(rect=rect, layout=layout)
        self.color: str = color
        self.thikness: int = thikness

    def __repr__(self) -> str:
        return "DrawOutline(r'{}' l'{}' / c'{}' t{})".format(
            self.rect, self.layout, self.color, self.thikness
        )

    def execute(self, canvas: skia.Canvas) -> None:
        paint = skia.Paint(
            Color=parse_color(self.color),
            StrokeWidth=self.thikness,
            Style=skia.Paint.kStroke_Style
        )
        canvas.drawRect(self.rect, paint)

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
        rect = skia.Rect.MakeLTRB(x1, y1, x2, y2)
        super().__init__(rect=rect, layout=layout)
        self.color: str = color
        self.thikness: int = thikness

    def __repr__(self) -> str:
        return "DrawLine(r'{}' l'{}' / c'{}')".format(
            self.rect, self.layout, self.color
        )

    def execute(self, canvas: skia.Canvas) -> None:
        path = skia.Path().moveTo(
            self.rect.left(), self.rect.top()
        ).lineTo(
            self.rect.right(), self.rect.bottom()
        )
        paint = skia.Paint(
            Color=parse_color(self.color),
            StrokeWidth=self.thikness,
            Style=skia.Paint.kStroke_Style
        )
        canvas.drawPath(path, paint)

class Blend(Draw):
    def __init__(
    self, 
    opacity: float, 
    blend_mode: str, 
    children: list[Draw], 
    blur: float = 0.0,
    layout=None
    ) -> None:
        rect = skia.Rect.MakeEmpty()
        super().__init__(rect=rect, layout=layout)
        self.opacity: float = opacity
        self.blend_mode: str = blend_mode
        self.blur: float = blur
        self.should_save: bool = bool(self.blend_mode) or self.opacity < 1 or self.blur > 0
        self.children: list[Draw] = children
        for cmd in self.children:
            self.rect.join(cmd.rect)
        
    def __repr__(self) -> str:
        return "Blend(r'{}' l'{}' / o'{}' b'{}')".format(
            self.rect, self.layout, self.opacity, self.blend_mode
        )

    def execute(self, canvas: skia.Canvas) -> None:
        paint = skia.Paint(
            Alphaf=self.opacity,
            BlendMode=parse_blend_mode(self.blend_mode),
            ImageFilter=skia.ImageFilters.Blur(self.blur, self.blur),
        )
        if self.should_save:
            canvas.saveLayer(None, paint)
        for cmd in self.children:
            cmd.execute(canvas)
        if self.should_save:
            canvas.restore()

def parse_color(color: str, default: skia.Color = skia.ColorBLACK) -> skia.Color:
    if color.startswith("#") and len(color) == 7:
        r = int(color[1:3], 16)
        g = int(color[3:5], 16)
        b = int(color[5:7], 16)
        return skia.Color(r, g, b)
    elif color.startswith("#") and len(color) == 9:
        r = int(color[1:3], 16)
        g = int(color[3:5], 16)
        b = int(color[5:7], 16)
        a = int(color[7:9], 16)
        return skia.Color(r, g, b, a)
    elif color in NAMED_COLORS:
        return parse_color(NAMED_COLORS[color])
    else:
        return default
    
def parse_blend_mode(blend_mode_str: str) -> skia.BlendMode:
    match blend_mode_str:
        case "multiply": return skia.BlendMode.kMultiply
        case "difference": return skia.BlendMode.kDifference
        case "destination-in": return skia.BlendMode.kDstIn
        case "source-over": return skia.BlendMode.kSrcOver
        case _: return skia.BlendMode.kSrcOver