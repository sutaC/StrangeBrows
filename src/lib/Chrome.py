from .URL import URL
from .Layout import get_font
from .Draw import Draw, Rect, DrawRect, DrawLine, DrawOutline, DrawText 

class Chrome:
    def __init__(self, browser) -> None:
        from .Browser import Browser
        assert isinstance(browser, Browser)
        self.browser: Browser = browser
        # Base
        self.font = get_font("", 14, "normal", "roman")
        self.font_height = self.font.metrics("linespace")
        self.padding = 5
        self.tabbar_top = 0
        self.tabbar_bottom = self.font_height + 2*self.padding
        # New tab button
        plus_width = self.font.measure("+") + 2*self.padding
        self.newtab_rect = Rect(
            self.padding, self.padding,
            self.padding + plus_width,
            self.padding + self.font_height
        )
        self.urlbar_top = self.tabbar_bottom
        self.urlbar_bottom = self.urlbar_top + self.font_height + 2*self.padding
        self.bottom = self.urlbar_bottom
        # Back button
        back_width = self.font.measure("<") + 2*self.padding
        self.back_rect = Rect(
            self.padding,
            self.urlbar_top + self.padding,
            self.padding + back_width,
            self.urlbar_bottom - self.padding
        )
        # Forward button
        forward_width = self.font.measure(">") + 2*self.padding
        self.forward_rect = Rect(
            self.back_rect.right + self.padding,
            self.urlbar_top + self.padding,
            self.back_rect.right + self.padding + forward_width,
            self.urlbar_bottom - self.padding
        )
        # Refresh button
        forward_width = self.font.measure("\N{clockwise gapped circle arrow}") + 2*self.padding
        self.refresh_rect = Rect(
            self.forward_rect.right + self.padding,
            self.urlbar_top + self.padding,
            self.forward_rect.right + self.padding + forward_width,
            self.urlbar_bottom - self.padding
        )
        # Bookmark button
        self.bookmark_width = self.font.measure("*") + 2*self.padding
        self.bookmark_rect = Rect(
            self.browser.dimensions["width"] - self.padding - self.bookmark_width,
            self.urlbar_top + self.padding,
            self.browser.dimensions["width"] - self.padding,
            self.urlbar_bottom - self.padding
        )
        # Address bar
        self.address_rect = Rect(
            self.refresh_rect.right + self.padding,
            self.urlbar_top + self.padding,
            self.bookmark_rect.left - self.padding,
            self.urlbar_bottom - self.padding
        )
        self.focus: str | None = None
        self.address_bar: str = ""
        self.cursor_position: int = 0

    def tab_rect(self, i: int) -> 'Rect':
        tabs_start = self.newtab_rect.right + self.padding
        tab_width = self.font.measure("Tab X") + 2*self.padding
        return Rect(
            tabs_start + tab_width * i, self.tabbar_top,
            tabs_start + tab_width * (i + 1), self.tabbar_bottom
        )
    
    def paint(self) -> list[Draw]:
        cmds: list[Draw] = []
        # Background
        cmds.append(DrawRect(
            Rect(0, 0, self.browser.dimensions["width"], self.bottom),
            "white"))
        cmds.append(DrawLine(
            0, self.bottom, self.browser.dimensions["width"], self.bottom,
            "black", 1))
        # Back button
        if not self.browser.active_tab.can_back():
            cmds.append(DrawRect(self.back_rect, "grey"))
        cmds.append(DrawOutline(self.back_rect, "black", 1))
        cmds.append(DrawText(
            self.back_rect.left + self.padding,
            self.back_rect.top,
            "<", self.font, "black"
        ))
        # Forward button
        if not self.browser.active_tab.can_forward():
            cmds.append(DrawRect(self.forward_rect, "grey"))
        cmds.append(DrawOutline(self.forward_rect, "black", 1))
        cmds.append(DrawText(
            self.forward_rect.left + self.padding,
            self.forward_rect.top,
            ">", self.font, "black"
        ))
        # Refresh button
        cmds.append(DrawOutline(self.refresh_rect, "black", 1))
        cmds.append(DrawText(
            self.refresh_rect.left + self.padding,
            self.refresh_rect.top + self.padding,
            "\N{clockwise gapped circle arrow}", self.font, "black"
        ))
        # New tab button
        cmds.append(DrawOutline(self.newtab_rect, "black", 1))
        cmds.append(DrawText(
            self.newtab_rect.left + self.padding,
            self.newtab_rect.top,
            "+", self.font, "black"
        ))
        # Bookmark button
        if self.browser.active_tab.url.storage.get_bookmark(str(self.browser.active_tab.url)):
            # If is bookmarked
            cmds.append(DrawRect(self.bookmark_rect, "yellow"))
        cmds.append(DrawOutline(self.bookmark_rect, "black", 1))
        cmds.append(DrawText(
            self.bookmark_rect.left + self.padding,
            self.bookmark_rect.top,
            "*", self.font, "black"
        ))
        # Address bar
        cmds.append(DrawOutline(self.address_rect, "black", 1))
        connection_type: str
        if self.browser.active_tab.url.is_safe is None:
            connection_type = "\N{circled information source}"
        elif self.browser.active_tab.url.is_safe:
            connection_type = "\N{lock}"
        else:
            connection_type = "\N{open lock}"
        ctw = self.font.measure(connection_type) + 2*self.padding
        cmds.append(DrawText(
            self.address_rect.left + self.padding,
            self.address_rect.top + self.padding,
            connection_type, self.font, "black"
        ))
        if self.focus == "address bar":
            cmds.append(DrawText(
                self.address_rect.left + ctw + self.padding,
                self.address_rect.top,
                self.address_bar, self.font, "black"
            ))
            w = self.font.measure(self.address_bar[:self.cursor_position]) if self.cursor_position > 0 else 0
            cmds.append(DrawLine(
                self.address_rect.left + ctw + self.padding + w,
                self.address_rect.top,
                self.address_rect.left + ctw + self.padding + w,
                self.address_rect.bottom,
                "red", 1
            ))
        else:
            url = str(self.browser.active_tab.url)
            cmds.append(DrawText(
                self.address_rect.left + ctw + self.padding,
                self.address_rect.top,
                url, self.font, "black"
            ))
        # Tabs
        for i, tab in enumerate(self.browser.tabs):
            bounds = self.tab_rect(i)
            cmds.append(DrawLine(
                bounds.left, 0, bounds.left, bounds.bottom,
                "black", 1))
            cmds.append(DrawLine(
                bounds.right, 0, bounds.right, bounds.bottom,
                "black", 1))
            cmds.append(DrawText(
                bounds.left + self.padding, bounds.top + self.padding,
                "Tab {}".format(i), self.font, "black"
            ))
            if tab == self.browser.active_tab:
                cmds.append(DrawLine(
                    0, bounds.bottom, bounds.left, bounds.bottom,
                    "black", 1))
                cmds.append(DrawLine(
                    bounds.right, bounds.bottom, self.browser.dimensions["width"], bounds.bottom,
                    "black", 1))
        return cmds

    def click(self, x: int, y: int) -> None:
        self.focus = None
        if self.newtab_rect.contains_point(x, y):
            self.browser.new_tab(URL("https://browser.engineering/"))
        elif self.back_rect.contains_point(x, y):
            self.browser.active_tab.go_back()
        elif self.forward_rect.contains_point(x, y):
            self.browser.active_tab.go_forward()
        elif self.refresh_rect.contains_point(x, y):
            self.browser.active_tab.refresh()
        elif self.bookmark_rect.contains_point(x, y):
            self.browser.active_tab.toggle_bookmark()
        elif self.address_rect.contains_point(x, y):
            self.focus = "address bar"
            self.address_bar = ""
            self.cursor_position = 0
        else:
            for i, tab in enumerate(self.browser.tabs):
                if self.tab_rect(i).contains_point(x, y):
                    self.browser.active_tab = tab
                    self.browser.update_title()
                    break
    
    def keypress(self, char: str) -> bool:
        if self.focus == "address bar":
            if self.cursor_position == len(self.address_bar):
                self.address_bar += char
            else:
                ls = list(self.address_bar)
                ls.insert(self.cursor_position, char)
                self.address_bar = "".join(ls)
            self.cursor_position += 1
            return True
        return False

    def left(self) -> None:
        if self.focus == "address bar":
            self.cursor_position = max(0, self.cursor_position-1)

    def right(self) -> None:
        if self.focus == "address bar":
            self.cursor_position = min(len(self.address_bar), self.cursor_position+1)

    def enter(self) -> bool:
        if self.focus == "address bar":
            self.browser.active_tab.load(URL(self.address_bar))
            self.browser.update_title()
            self.browser.active_tab.clear_forward()
            self.focus = None
            return True
        return False

    def backspace(self) -> bool:
        if self.focus == "address bar":
            if self.address_bar and self.cursor_position > 0:
                if self.cursor_position == len(self.address_bar):
                    self.address_bar = self.address_bar[:-1]
                else:
                    ls = list(self.address_bar)
                    ls.pop(self.cursor_position-1)
                    self.address_bar = "".join(ls)
                self.cursor_position -= 1
            return True
        return False

    def configure(self) -> None:
        self.bookmark_rect.left = self.browser.dimensions["width"] - self.padding - self.bookmark_width
        self.bookmark_rect.right = self.browser.dimensions["width"] - self.padding
        self.address_rect.right = self.bookmark_rect.left - self.padding
    
    def blur(self) -> None:
        self.focus = None