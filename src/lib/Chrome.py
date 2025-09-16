from .URL import URL
from .DocumentLayout import get_font
from lib.Draw import Draw, Rect, DrawRect, DrawLine, DrawOutline, DrawText 

class Chrome:
    def __init__(self, browser) -> None:
        from .Browser import Browser
        assert isinstance(browser, Browser)
        self.browser: Browser = browser
        self.font = get_font("", 14, "normal", "roman")
        self.font_height = self.font.metrics("linespace")
        self.padding = 5
        self.tabbar_top = 0
        self.tabbar_bottom = self.font_height + 2*self.padding
        plus_width = self.font.measure("+") + 2*self.padding
        self.newtab_rect = Rect(
            self.padding, self.padding,
            self.padding + plus_width,
            self.padding + self.font_height
        )
        self.urlbar_top = self.tabbar_bottom
        self.urlbar_bottom = self.urlbar_top + self.font_height + 2*self.padding
        self.bottom = self.urlbar_bottom
        back_width = self.font.measure("<") + 2*self.padding
        self.back_rect = Rect(
            self.padding,
            self.urlbar_top + self.padding,
            self.padding + back_width,
            self.urlbar_bottom - self.padding
        )
        self.address_rect = Rect(
            self.back_rect.top + self.padding,
            self.urlbar_top + self.padding,
            self.browser.dimensions["width"] - self.padding,
            self.urlbar_bottom - self.padding
        )
        self.focus: str | None = None
        self.address_bar = ""

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
        cmds.append(DrawOutline(self.back_rect, "black", 1))
        cmds.append(DrawText(
            self.back_rect.left + self.padding,
            self.back_rect.top,
            "<", self.font, "black"
        ))
        # New tab button
        cmds.append(DrawOutline(self.newtab_rect, "black", 1))
        cmds.append(DrawText(
            self.newtab_rect.left + self.padding,
            self.newtab_rect.top,
            "+", self.font, "black"
        ))
        # Address bar
        cmds.append(DrawOutline(self.address_rect, "black", 1))
        if self.focus == "address bar":
            cmds.append(DrawText(
                self.address_rect.left + self.padding,
                self.address_rect.top,
                self.address_bar, self.font, "black"
            ))
            w = self.font.measure(self.address_bar)
            cmds.append(DrawLine(
                self.address_rect.left + self.padding + w,
                self.address_rect.top,
                self.address_rect.left + self.padding + w,
                self.address_rect.bottom,
                "red", 1
            ))
        else:
            url = str(self.browser.active_tab.url)
            cmds.append(DrawText(
                self.address_rect.left + self.padding,
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
        elif self.address_rect.contains_point(x, y):
            self.focus = "address bar"
            self.address_bar = ""
        else:
            for i, tab in enumerate(self.browser.tabs):
                if self.tab_rect(i).contains_point(x, y):
                    self.browser.active_tab = tab
                    self.browser.update_title()
                    break
    
    def keypress(self, char: str) -> None:
        if self.focus == "address bar":
            self.address_bar += char

    def enter(self) -> None:
        if self.focus == "address bar":
            self.browser.active_tab.load(URL(self.address_bar))
            self.focus = None

    def backspace(self) -> None:
        if self.focus == "address bar":
            if self.address_bar:
                self.address_bar = self.address_bar[:-1]

    def configure(self) -> None:
        self.address_rect.right = self.browser.dimensions["width"] - self.padding