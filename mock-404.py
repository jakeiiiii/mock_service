"""Fullscreen uuencode viewer.

Reads a file (typically a .zip), encodes it in uuencode format, and displays
the encoded text on a fullscreen Tkinter window one page at a time, advancing
automatically every few seconds until the end of the data is reached.

Usage:
    python uu_viewer.py <path-to-file> [lines_per_screen] [seconds_between]
           [--monitor N] [--list-monitors] [--pages] [--font SIZE]
           [--resend PAGES.json]

Defaults: 26 lines per screen, 0.5 seconds between pages. Page numbers depend
only on the file and the lines per screen, so page 2056 is always the same.
By default the window opens on the monitor containing the mouse pointer.
Use --monitor N (0-based, as printed by --list-monitors) to force one.
Use --pages to print the page count (and total run time) without displaying.
Use --font SIZE to change the point size.
Use --resend PAGES.json to show only some pages again, each with its original
footer (page number, total and crc), e.g. pages the receiver missed. The file
holds page numbers and inclusive ranges, either as a list or under "pages":
    ["2055-2057", "4067-4069", "4649-4652", "10804-10808"]
    {"pages": "2055-2057, 4067-4069, 4649-4652, 10804-10808"}
    {"pages": [2055, [4067, 4069], "10804-10808"]}
Use the same lines per screen as the original run, or the numbers will differ.

Controls:
    Esc / q     quit
    Space       advance to the next page immediately
    Left/Right  go back / forward a page (pauses auto-advance)

Footer:
    page N / TOTAL  crc XXXXXXXX
    XXXXXXXX is the CRC-32 (as in ZIP and zlib.crc32), in uppercase hex, of the
    bytes this page's uuencoded data lines decode to. The begin, "`" and end
    lines carry no data, so a page without data shows crc 00000000. The
    receiver uses it to prove every page was read correctly.
"""

import binascii
import json
import os
import sys
import zlib
import tkinter as tk
import tkinter.font as tkfont

# Defaults; can be overridden on the command line.
_LINES_PER_SCREEN = 26
_SECONDS_BETWEEN = 0.5
_INITIAL_BLACKOUT = 20.0  # seconds of blank screen before the first page

# Display appearance (shared by the fit calculation and the Viewer so they agree).
_FONT_FAMILY = "Courier New"
_FONT_SIZE = 28
_PAD_X = 40  # left/right margin in pixels
_PAD_Y = 10  # top/bottom margin in pixels


def _uuencode(path):
    """Return the uuencoded representation of *path* as a list of text lines."""
    name = os.path.basename(path)
    with open(path, "rb") as fh:
        data = fh.read()

    lines = ["begin 644 %s" % name]
    # uuencode processes the payload in chunks of at most 45 bytes per line.
    for i in range(0, len(data), 45):
        chunk = data[i:i + 45]
        lines.append(binascii.b2a_uu(chunk).decode("ascii").rstrip("\n"))
    lines.append("`")
    lines.append("end")
    return lines


def _page_crc(page):
    """CRC-32 of the bytes that *page*'s uuencoded data lines decode to."""
    crc = 0
    for line in page:
        if line.startswith("begin ") or line in ("`", "end"):
            continue
        crc = zlib.crc32(binascii.a2b_uu(line), crc)
    return crc


def _parse_pages(spec, total):
    """Sorted page numbers from a --resend file's contents.

    Accepts a list or a {"pages": ...} object holding page numbers, [first,
    last] pairs and "first-last" strings, or one comma-separated string.
    """
    if isinstance(spec, dict):
        spec = spec.get("pages", [])
    if isinstance(spec, str):
        spec = [part for part in spec.split(",") if part.strip()]
    if not isinstance(spec, list):
        raise ValueError("expected a list of pages or ranges")
    numbers = set()
    for item in spec:
        if isinstance(item, bool):
            raise ValueError("not a page: %r" % (item,))
        if isinstance(item, int):
            first = last = item
        elif isinstance(item, list) and len(item) == 2 and all(isinstance(n, int) for n in item):
            first, last = item
        elif isinstance(item, str):
            parts = [p.strip() for p in item.split("-")]
            if len(parts) not in (1, 2) or not all(p.isdigit() for p in parts):
                raise ValueError("not a page or range: %r" % item)
            first, last = int(parts[0]), int(parts[-1])
        else:
            raise ValueError("not a page or range: %r" % (item,))
        if first > last:
            raise ValueError("range %d-%d runs backwards" % (first, last))
        if not 1 <= first <= last <= total:
            raise ValueError("pages %d-%d are outside 1-%d" % (first, last, total))
        numbers.update(range(first, last + 1))
    if not numbers:
        raise ValueError("no pages listed")
    return sorted(numbers)


def _paginate(lines, per_screen):
    """Split *lines* into pages of at most *per_screen* lines each."""
    return [lines[i:i + per_screen] for i in range(0, len(lines), per_screen)] or [[]]


def _set_dpi_aware():
    """Make the process DPI aware so Tk coordinates match Win32 pixel rects.

    Without this a scaled secondary monitor reports virtual-desktop
    coordinates that Tk rescales, so the window lands on the wrong screen.
    """
    if sys.platform != "win32":
        return
    import ctypes

    try:
        # PROCESS_PER_MONITOR_DPI_AWARE
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def _list_monitors():
    """Return [(x, y, width, height), ...] for every monitor, primary first."""
    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes

            class _RECT(ctypes.Structure):
                _fields_ = [("left", wintypes.LONG), ("top", wintypes.LONG),
                            ("right", wintypes.LONG), ("bottom", wintypes.LONG)]

            class _MONITORINFO(ctypes.Structure):
                _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", _RECT),
                            ("rcWork", _RECT), ("dwFlags", wintypes.DWORD)]

            user32 = ctypes.windll.user32
            found = []

            proto = ctypes.WINFUNCTYPE(
                wintypes.BOOL, wintypes.HMONITOR, wintypes.HDC,
                ctypes.POINTER(_RECT), wintypes.LPARAM)

            def _cb(handle, _hdc, _rect, _param):
                info = _MONITORINFO()
                info.cbSize = ctypes.sizeof(_MONITORINFO)
                if user32.GetMonitorInfoW(handle, ctypes.byref(info)):
                    r = info.rcMonitor
                    entry = (r.left, r.top, r.right - r.left, r.bottom - r.top)
                    # MONITORINFOF_PRIMARY = 1
                    found.insert(0, entry) if info.dwFlags & 1 else found.append(entry)
                return True

            user32.EnumDisplayMonitors(None, None, proto(_cb), 0)
            if found:
                return found
        except Exception:
            pass

    try:
        from screeninfo import get_monitors

        mons = [(m.x, m.y, m.width, m.height, bool(m.is_primary))
                for m in get_monitors()]
        mons.sort(key=lambda m: not m[4])
        return [m[:4] for m in mons]
    except Exception:
        return []


def _active_monitor(root, index=None):
    """Return (x, y, width, height) of the target monitor.

    Uses *index* when given, otherwise the monitor holding the mouse pointer,
    falling back to the primary screen geometry.
    """
    monitors = _list_monitors()

    if index is not None and monitors:
        return monitors[index % len(monitors)]

    px, py = root.winfo_pointerx(), root.winfo_pointery()
    for x, y, w, h in monitors:
        if x <= px < x + w and y <= py < y + h:
            return x, y, w, h

    if monitors:
        return monitors[0]
    return 0, 0, root.winfo_screenwidth(), root.winfo_screenheight()


def _fit_lines(height):
    """Compute how many content lines fit in *height* pixels.

    Measures the font's actual line height and divides the usable height
    (minus the top and bottom margins) by it. Two lines are held back: one
    for the page-counter footer and one as a safety margin so the bottom
    line is never clipped.
    """
    mono = tkfont.Font(family=_FONT_FAMILY, size=_FONT_SIZE)
    line_height = mono.metrics("linespace")
    usable = height - 2 * _PAD_Y
    return max(1, usable // line_height - 2)


class Viewer:
    def __init__(self, root, pages, delay_ms, blackout_ms=0, monitor=None, shown=None):
        self.root = root
        # *shown* lists the page numbers to display (all of them by default);
        # each keeps its own footer. A leading blank screen provides the
        # initial blackout before content.
        self.total = len(pages)
        self.numbers = [0] + list(shown or range(1, len(pages) + 1))
        self.pages = [[]] + [pages[n - 1] for n in self.numbers[1:]]
        self.crcs = [0] + [_page_crc(page) for page in self.pages[1:]]
        self.delay_ms = delay_ms
        self.blackout_ms = blackout_ms
        self.index = 0
        self.auto = True
        self._after_id = None

        if monitor:
            x, y, w, h = monitor
        else:
            x, y = 0, 0
            w, h = root.winfo_screenwidth(), root.winfo_screenheight()
        # Tk's -fullscreen always snaps to the primary display on Windows, so
        # cover the target monitor with a borderless topmost window instead.
        root.overrideredirect(True)
        root.geometry("%dx%d+%d+%d" % (w, h, x, y))
        root.attributes("-topmost", True)
        root.configure(bg="black")
        root.update_idletasks()
        root.after(10, root.focus_force)

        # Fixed-width font so every character occupies the same cell width.
        mono = tkfont.Font(family=_FONT_FAMILY, size=_FONT_SIZE)
        self.footer = tk.Label(
            root,
            bg="black",
            fg="#ffffff",
            font=mono,
            anchor="w",
            padx=_PAD_X,
            pady=0,
        )
        self.footer.pack(side="bottom", fill="x")
        self.text = tk.Text(
            root,
            bg="black",
            fg="#ffffff",
            insertbackground="black",
            font=mono,
            wrap="none",
            borderwidth=0,
            highlightthickness=0,
            padx=_PAD_X,  # small left/right margin so text isn't flush to the edge
            pady=_PAD_Y,  # top/bottom margin
        )
        self.text.pack(fill="both", expand=True)
        self.text.configure(state="disabled")

        root.bind("<Escape>", lambda e: root.destroy())
        root.bind("q", lambda e: root.destroy())
        root.bind("<space>", lambda e: self._manual(+1))
        root.bind("<Right>", lambda e: self._manual(+1))
        root.bind("<Left>", lambda e: self._manual(-1))

        self._render()
        self._schedule()

    def _render(self):
        body = "\n".join(self.pages[self.index])
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.insert("1.0", body)
        self.text.configure(state="disabled")
        # Index 0 is the blackout page; every other page shows its own number.
        self.footer.configure(
            text="" if self.index == 0
            else "page %d / %d  crc %08X" % (self.numbers[self.index], self.total, self.crcs[self.index]))

    def _schedule(self):
        if self._after_id is not None:
            self.root.after_cancel(self._after_id)
            self._after_id = None
        if self.auto and self.index < len(self.pages) - 1:
            # The blank leading page holds for the blackout duration; the rest
            # advance at the normal interval.
            wait = self.blackout_ms if self.index == 0 else self.delay_ms
            self._after_id = self.root.after(wait, self._auto_advance)

    def _auto_advance(self):
        if self.index < len(self.pages) - 1:
            self.index += 1
            self._render()
        self._schedule()

    def _manual(self, step):
        # Any manual navigation stops the automatic advance.
        self.auto = False
        new = min(max(self.index + step, 0), len(self.pages) - 1)
        if new != self.index:
            self.index = new
            self._render()
        self._schedule()


def main(argv):
    _set_dpi_aware()

    global _FONT_SIZE

    args = list(argv[1:])
    monitor_index = None
    count_only = False

    if "--font" in args:
        i = args.index("--font")
        _FONT_SIZE = int(args[i + 1])
        del args[i:i + 2]

    if "--pages" in args:
        count_only = True
        args.remove("--pages")

    if "--list-monitors" in args:
        for i, (x, y, w, h) in enumerate(_list_monitors()):
            print("%d: %dx%d at (%d,%d)%s" % (i, w, h, x, y, " [primary]" if i == 0 else ""))
        return 0

    if "--monitor" in args:
        i = args.index("--monitor")
        monitor_index = int(args[i + 1])
        del args[i:i + 2]

    resend = None
    if "--resend" in args:
        i = args.index("--resend")
        resend = args[i + 1]
        del args[i:i + 2]

    if not args:
        print(__doc__)
        return 1

    path = args[0]
    if not os.path.isfile(path):
        print("File not found: %s" % path)
        return 1

    seconds = float(args[2]) if len(args) > 2 else _SECONDS_BETWEEN

    root = tk.Tk()
    root.title("uu_viewer")

    monitor = _active_monitor(root, monitor_index)

    # Lines per screen: an explicit command-line value wins; otherwise the
    # fixed default, so the same file always gives the same page numbers.
    per_screen = int(args[1]) if len(args) > 1 else _LINES_PER_SCREEN
    fits = _fit_lines(monitor[3])
    if per_screen > fits:
        print("Warning: %d lines per screen, but only %d fit this monitor; "
              "the bottom lines will be cut off." % (per_screen, fits))

    lines = _uuencode(path)
    pages = _paginate(lines, per_screen)

    shown = None
    if resend:
        try:
            with open(resend, encoding="utf-8") as fh:
                shown = _parse_pages(json.load(fh), len(pages))
        except (OSError, ValueError) as exc:
            print("Cannot use %s: %s" % (resend, exc))
            root.destroy()
            return 1

    if count_only:
        count = len(shown) if shown else len(pages)
        print("%d lines (begin..end), %d lines per page, %d pages"
              % (len(lines), per_screen, len(pages)))
        if shown:
            print("resending %d of them" % count)
        print("run time: %.1fs blackout + %d x %.1fs = %.1fs"
              % (_INITIAL_BLACKOUT, count, seconds,
                 _INITIAL_BLACKOUT + count * seconds))
        root.destroy()
        return 0

    Viewer(root, pages, int(seconds * 1000), int(_INITIAL_BLACKOUT * 1000), monitor, shown)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
