"""The island: a Dynamic-Island-style pill pinned to the top of the screen (tkinter, stdlib only)."""
import ctypes, math, time, tkinter as tk, webbrowser

KEY = "#010101"  # transparent key: near-black so anti-aliased text edges blend into the pill
PILL, DIM, TXT = "#0b0b0b", "#8a8a8a", "#f5f5f5"
RED, GREY = "#FF5A5A", "#6b6b6b"


def fmt(s):
    m = int(s // 60)
    return f"{m}m" if m < 60 else f"{m // 60}h {m % 60:02d}m"


class Island:
    def __init__(self, live, actions, currency="₹"):
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)  # crisp text on scaled displays
        except Exception:
            pass
        self.live, self.actions, self.cur = live, actions, currency
        r = self.r = tk.Tk()
        r.overrideredirect(True)
        r.attributes("-topmost", True)
        r.attributes("-transparentcolor", KEY)
        r.config(bg=KEY)
        self.k = r.winfo_fpixels("1i") / 96
        self.c = tk.Canvas(r, bg=KEY, highlightthickness=0)
        self.c.pack(fill="both", expand=True)
        self.w, self.h = self.size("pill")
        self.hover, self.toast, self.toast_until, self.seen_client = False, "", 0, None
        r.bind("<Enter>", lambda e: setattr(self, "hover", True))
        r.bind("<Leave>", lambda e: setattr(self, "hover", False))
        self.c.bind("<Button-1>", self.click)
        self.font = lambda size, bold=False: ("Bahnschrift SemiBold" if bold else "Bahnschrift", round(size))
        self.frame()

    def size(self, mode):
        w, h = {"pill": (300, 38), "toast": (340, 44), "open": (460, getattr(self, "open_h", 156))}[mode]
        return w * self.k, h * self.k

    def mode(self):
        if self.hover:
            return "open"
        return "toast" if time.time() < self.toast_until else "pill"

    def state(self):
        L = self.live
        if L.get("paused"):
            return RED, "gone dark", "not tracking"
        if L.get("idle", 0) > 300:
            return GREY, "on a break", "paused while you're away"
        if not L.get("client"):
            return GREY, "lowkey is listening", "first labels in ~1 min"
        return L.get("color", GREY), L["client"], L.get("task", "")

    def frame(self):
        L = self.live
        if L.get("client") and L.get("client") != self.seen_client:
            if self.seen_client is not None:
                self.toast, self.toast_until = f"switched to {L['client']}", time.time() + 2.6
            self.seen_client = L["client"]
        tw, th = self.size(self.mode())
        self.w += (tw - self.w) * 0.28  # spring-ish easing
        self.h += (th - self.h) * 0.28
        x = (self.r.winfo_screenwidth() - self.w) / 2
        self.r.geometry(f"{round(self.w)}x{round(self.h)}+{round(x)}+{round(8 * self.k)}")
        self.draw()
        moving = abs(tw - self.w) > 0.5 or abs(th - self.h) > 0.5
        self.r.after(16 if moving else 120, self.frame)

    def pill(self, x0, y0, x1, y1, r, fill, tags=()):
        """Rounded rect from true circles (tk's smoothed polygons under-round the corners)."""
        c, d = self.c, 2 * r
        for ox, oy in ((x0, y0), (x1 - d, y0), (x0, y1 - d), (x1 - d, y1 - d)):
            c.create_oval(ox, oy, ox + d, oy + d, fill=fill, outline="", tags=tags)
        c.create_rectangle(x0 + r, y0, x1 - r, y1, fill=fill, outline="", tags=tags)
        c.create_rectangle(x0, y0 + r, x1, y1 - r, fill=fill, outline="", tags=tags)

    def draw(self):
        c, k, w, h, L = self.c, self.k, self.w, self.h, self.live
        c.delete("all")
        self.pill(0, 0, w, h, min(h / 2, 24 * k), PILL)
        color, title, sub = self.state()
        pulse = (math.sin(time.time() * 3) + 1) / 2
        rd = (4 + 1.5 * pulse) * k
        cy = min(h / 2, 22 * k)
        c.create_oval(20 * k - rd, cy - rd, 20 * k + rd, cy + rd, fill=color, outline="")
        mode = self.mode()

        if mode == "toast" and h < 70 * k:
            c.create_text(36 * k, h / 2, text=self.toast, fill=TXT, anchor="w", font=self.font(12 * k, True))
            return
        if h < 70 * k:  # collapsed pill
            c.create_text(34 * k, h / 2, text=title, fill=TXT, anchor="w", font=self.font(11.5 * k, True))
            if L.get("client") and not L.get("paused"):
                c.create_text(w - 16 * k, h / 2, text=f"{self.cur}{L.get('money', 0):,.0f}", fill=color,
                              anchor="e", font=self.font(11.5 * k, True))
                c.create_text(w - 76 * k, h / 2, text=fmt(L.get("today_s", 0)), fill=DIM, anchor="e", font=self.font(10.5 * k))
            return

        # expanded: lay out from the real text height so long task lines never overlap
        c.create_text(34 * k, cy, text=title, fill=TXT, anchor="w", font=self.font(13.5 * k, True))
        badge = "DARK" if L.get("paused") else "LIVE"
        c.create_text(w - 18 * k, cy, text=badge, fill=RED if badge == "DARK" else color, anchor="e", font=self.font(10 * k, True))
        task = c.create_text(20 * k, 46 * k, text=sub[:110], fill="#cfcfcf", anchor="nw", width=self.size("open")[0] - 40 * k, font=self.font(11 * k))
        y = c.bbox(task)[3] + 8 * k
        stats = f"today  {fmt(L.get('today_s', 0))}  ·  {self.cur}{L.get('money', 0):,.0f}  ·  {L.get('pending', 0)} to review"
        c.create_text(20 * k, y, text=stats, fill=DIM, anchor="nw", font=self.font(10.5 * k))
        y += 30 * k
        x = 18 * k
        for tag, label, edge in (("dark", "resume" if L.get("paused") else "go dark", RED),
                                 ("personal", "not work", GREY), ("open", "open lowkey", color)):
            bw = (len(label) * 7.4 + 28) * k
            self.pill(x - 1.5 * k, y - 1.5 * k, x + bw + 1.5 * k, y + 29.5 * k, 15.5 * k, edge, tag)  # coloured rim
            self.pill(x, y, x + bw, y + 28 * k, 14 * k, "#1d1d1d", tag)
            c.create_text(x + bw / 2, y + 14 * k, text=label, fill=TXT, font=self.font(10.5 * k, True), tags=tag)
            x += bw + 10 * k
        self.open_h = (y + 42 * k) / k  # next frame grows/shrinks to fit

    def click(self, e):
        tags = self.c.gettags("current")
        if "dark" in tags:
            self.live["paused"] = not self.live.get("paused")
        elif "personal" in tags:
            self.actions["personal"]()
            self.toast, self.toast_until = "marked as a side quest", time.time() + 2
        elif "open" in tags:
            webbrowser.open("http://127.0.0.1:7777")

    def run(self):
        self.r.mainloop()
