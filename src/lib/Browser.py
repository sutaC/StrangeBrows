import ctypes
import math
import sdl2
import skia
from typing import Literal
from .URL import URL
from .Tab import Tab
from .Chrome import Chrome
from .Layout import Dimensions

class Browser:
    def __init__(self) -> None:
        if sdl2.SDL_BYTEORDER == sdl2.SDL_BIG_ENDIAN:
            self.RED_MASK = 0xff000000
            self.GREEN_MASK = 0x00ff0000
            self.BLUE_MASK = 0x0000ff00
            self.ALPHA_MASK = 0x000000ff
        else:
            self.RED_MASK = 0x000000ff
            self.GREEN_MASK = 0x0000ff00
            self.BLUE_MASK = 0x00ff0000
            self.ALPHA_MASK = 0xff000000
        self.dimensions = Dimensions(
            width=800,
            height=600,
            hstep=13,
            vstep=18,
        )
        self.tabs: list[Tab] = []
        self.active_tab: Tab = Tab(self)
        self.chrome: Chrome = Chrome(self)
        self.focus: str | None = None
        # ---
        self.sdl_window: sdl2.SDL_Window = sdl2.SDL_CreateWindow(b"StrangeBrows",
            sdl2.SDL_WINDOWPOS_CENTERED, sdl2.SDL_WINDOWPOS_CENTERED,
            self.dimensions["width"], self.dimensions["height"], sdl2.SDL_WINDOW_SHOWN
        )
        self.root_surface: skia.Surface = skia.Surface.MakeRaster(
            skia.ImageInfo.Make(
                self.dimensions["width"], self.dimensions["height"],
                ct=skia.kRGBA_8888_ColorType,
                at=skia.kUnpremul_AlphaType
            )
        )
        self.chrome_surface: skia.Surface = skia.Surface(self.dimensions["width"], self.chrome.bottom)
        self.tab_surface: skia.Surface | None = None

    # Handlers
    def handle_quit(self) -> None:
        sdl2.SDL_DestroyWindow(self.sdl_window)

    def handle_up(self) -> None:
        self.active_tab.up()
        self.raster_tab(sb_only=True)
        self.draw()

    def handle_down(self) -> None:
        self.active_tab.down()
        self.raster_tab(sb_only=True)
        self.draw()

    def handle_scrollwheel(self, delta: int) -> None:
        self.active_tab.scrollwheel(delta)
        self.raster_tab(sb_only=True)
        self.draw()

    def handle_configure(self, width: int, height: int) -> None:
        if self.dimensions["width"] == width \
        and self.dimensions["height"] == height : return
        self.dimensions["width"] = width
        self.dimensions["height"] = height
        self.root_surface = skia.Surface.MakeRaster(
            skia.ImageInfo.Make(
                width, height,
                ct=skia.kRGBA_8888_ColorType,
                at=skia.kUnpremul_AlphaType
            )
        )
        self.chrome_surface = skia.Surface(
            self.dimensions["width"], 
            self.chrome.bottom
        )
        self.tab_surface = None # Reset for automatic resize at `self.raster_tab()`
        self.active_tab.configure()
        self.chrome.configure()
        self.raster_chrome()
        self.raster_tab()
        self.draw()

    def handle_click(self, e: sdl2.SDL_MouseButtonEvent) -> None:
        if e.y < self.chrome.bottom:
            self.focus = None
            self.active_tab.blur()
            self.chrome.click(e.x, e.y)
        else:
            self.focus = "content"
            self.chrome.blur()
            tab_y = e.y - self.chrome.bottom
            self.active_tab.click(e.x, tab_y)
        self.raster_chrome()
        self.raster_tab()
        self.draw()

    def handle_middle_click(self, e: sdl2.SDL_MouseButtonEvent) -> None:
        if e.y < self.chrome.bottom: return
        tab_y = e.y - self.chrome.bottom
        url = self.active_tab.middle_click(e.x, tab_y)
        if not url: return
        self.new_tab(url)

    def handle_key(self, char: str) -> None:
        if not (0x20 <= ord(char) < 0x7f): return
        if self.chrome.keypress(char):
            self.raster_chrome()
            self.draw()
        elif self.focus == "content":
            if self.active_tab.keypress(char):
                self.raster_tab()
                self.draw()

    def handle_enter(self) -> None:
        if self.chrome.enter():
            self.raster_chrome()
            self.raster_tab()
            self.draw()
        elif self.focus == "content":
            if self.active_tab.enter():
                self.raster_tab()
                self.draw()

    def handle_backspace(self) -> None:
        if self.chrome.backspace():
            self.raster_chrome()
            self.draw()
        elif self.focus == "content":
            if self.active_tab.backspace():
                self.raster_tab()
                self.draw()

    def handle_left(self) -> None:
        if self.chrome.left():
            self.raster_chrome()
            self.draw()

    def handle_right(self) -> None:
        if self.chrome.right():
            self.raster_chrome()
            self.draw()

    # Methods
    def raster_tab(self, sb_only: bool = False) -> None:
        tab_height = math.ceil(self.active_tab.document.height + 2*self.dimensions["vstep"])
        if self.tab_surface is None or tab_height != self.tab_surface.height():
            self.tab_surface = skia.Surface(self.dimensions["width"], tab_height) 
        assert self.tab_surface is not None
        canvas = self.tab_surface.getCanvas()
        if sb_only: # For scrollbar redraw only
            self.active_tab.raster_scrollbar(canvas)
            return
        canvas.clear(skia.ColorWHITE)
        self.active_tab.raster(canvas)

    def raster_chrome(self) -> None:
        canvas = self.chrome_surface.getCanvas()
        canvas.clear(skia.ColorWHITE)
        for cmd in self.chrome.paint():
            cmd.execute(canvas)

    def draw(self) -> None:
        canvas = self.root_surface.getCanvas()
        canvas.clear(skia.ColorWHITE)
        tab_rect = skia.Rect.MakeLTRB(
            0, self.chrome.bottom, self.dimensions["width"], self.dimensions["height"]
        )
        tab_offset = self.chrome.bottom - self.active_tab.scroll
        canvas.save()
        if self.tab_surface is not None:
            canvas.clipRect(tab_rect)
            canvas.translate(0, tab_offset)
            self.tab_surface.draw(canvas, 0, 0)
            canvas.restore()
        chrome_rect = skia.Rect.MakeLTRB(
            0, 0, self.dimensions["width"], self.chrome.bottom
        )
        canvas.save()
        canvas.clipRect(chrome_rect)
        self.chrome_surface.draw(canvas, 0, 0)
        canvas.restore()
        skia_image = self.root_surface.makeImageSnapshot()
        skia_bytes = skia_image.tobytes()
        depth = 32 # Bites per pixel
        pitch = 4 * self.dimensions["width"]
        sdl_surface = sdl2.SDL_CreateRGBSurfaceFrom(
            skia_bytes, self.dimensions["width"], self.dimensions["height"], depth, pitch,
            self.RED_MASK, self.GREEN_MASK,
            self.BLUE_MASK, self.ALPHA_MASK
        )
        rect = sdl2.SDL_Rect(0, 0, self.dimensions["width"], self.dimensions["height"])
        window_surface = sdl2.SDL_GetWindowSurface(self.sdl_window)
        # SDL_BlitSurface is what accually does copy
        sdl2.SDL_BlitSurface(sdl_surface, rect, window_surface, rect)
        sdl2.SDL_UpdateWindowSurface(self.sdl_window)
    
    def new_tab(self, url: URL) -> None:
        new_tab = Tab(self)
        new_tab.load(url)
        self.set_cursor("LOADING")
        self.active_tab = new_tab
        self.tabs.append(new_tab)
        self.raster_tab()
        self.raster_chrome()
        self.draw()
        self.update_title()
        self.set_cursor("DEFAULT")
        
    def update_title(self) -> None:
        title = self.active_tab.page_title()
        if title is not None: title = "{} – StrangeBrows".format(title)
        else: title = ("StrangeBrows")
        sdl2.SDL_SetWindowTitle(self.sdl_window, title.encode())

    def show_simple_messagebox(self, 
    type: Literal["INFORMATION", "WARNING", "ERROR"], 
    title: str, 
    message: str
    ) -> None:
        match type:
            case "INFORMATION": flags = sdl2.SDL_MESSAGEBOX_INFORMATION
            case "WARNING": flags = sdl2.SDL_MESSAGEBOX_WARNING
            case "ERROR": flags = sdl2.SDL_MESSAGEBOX_ERROR
        code = sdl2.SDL_ShowSimpleMessageBox(
            flags,
            title.encode(),
            message.encode(),
            self.sdl_window
        )
        if code < 0: # Error handling / Fallback
            print(
                "Could not display message box due to error:", 
                sdl2.SDL_GetError(), 
                "Type: {}".format(type),
                "Title: {}".format(title), 
                "Message: {}".format(message), 
                sep="\n"
            )

    def show_yesno_messagebox(self,
    type: Literal["INFORMATION", "WARNING", "ERROR"],
    title: str,
    message: str
    ) -> bool:
        match type:
            case "INFORMATION": flags = sdl2.SDL_MESSAGEBOX_INFORMATION
            case "WARNING": flags = sdl2.SDL_MESSAGEBOX_WARNING
            case "ERROR": flags = sdl2.SDL_MESSAGEBOX_ERROR
        # ctype array of 2 msgboxbuttondata
        buttons = (sdl2.SDL_MessageBoxButtonData * 2)(
            sdl2.SDL_MessageBoxButtonData(
                flags=sdl2.SDL_MESSAGEBOX_BUTTON_RETURNKEY_DEFAULT,
                buttonid=1,
                text=b"Yes"
            ),
            sdl2.SDL_MessageBoxButtonData(
                flags=sdl2.SDL_MESSAGEBOX_BUTTON_ESCAPEKEY_DEFAULT,
                buttonid=0,
                text=b"No"
            )
        )
        box = sdl2.SDL_MessageBoxData(
            flags=flags,
            window=self.sdl_window,
            title=title.encode(),
            message=message.encode(),
            numbuttons=2,
            buttons=buttons,
            colorScheme=None
        )
        btnid = ctypes.c_int()
        code = sdl2.SDL_ShowMessageBox(box, ctypes.byref(btnid))
        if code < 0: # Error handling / Fallback
            print(
                "Could not display message box due to error:", 
                sdl2.SDL_GetError(),
                "Type: {}".format(type),
                "Title: {}".format(title), 
                "Message: {}".format(message),
                "Options: Yes/No (defaulted to No)",
                sep="\n"
            )
            return False # default "No" on error
        return btnid.value == 1 # True if "Yes", False if "No" or closed
    
    def set_cursor(self, type: Literal["DEFAULT", "LOADING"]) -> None:
        match type:
            case "DEFAULT":
                cursor = sdl2.SDL_CreateSystemCursor(sdl2.SDL_SYSTEM_CURSOR_ARROW)
            case "LOADING":
                cursor = sdl2.SDL_CreateSystemCursor(sdl2.SDL_SYSTEM_CURSOR_WAIT)
            case _:
                cursor = sdl2.SDL_CreateSystemCursor(sdl2.SDL_SYSTEM_CURSOR_ARROW)
        sdl2.SDL_SetCursor(cursor)