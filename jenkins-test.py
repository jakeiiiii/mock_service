"""Custom visual lock screen — pure black overlay, password-dismissed.

Coexists with mock_service.py (which keeps Teams green via SendInput).
This overlay does NOT touch Windows screensaver or session-lock state.
"""

import ctypes
import hashlib
import json
import secrets
import sys
import tkinter as tk
from pathlib import Path
from tkinter import simpledialog, messagebox

CONFIG_PATH = Path(__file__).parent / "not_idle_config.json"


def _set_dpi_aware():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except (AttributeError, OSError):
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except (AttributeError, OSError):
            pass


def _hash(password: str, salt: str) -> str:
    return hashlib.sha256((salt + password).encode("utf-8")).hexdigest()


def _load_config():
    if not CONFIG_PATH.exists():
        return None
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def _save_config(salt: str, hashed: str):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump({"salt": salt, "hash": hashed}, f)


def _first_run_setup() -> dict:
    root = tk.Tk()
    root.withdraw()
    try:
        while True:
            pw1 = simpledialog.askstring(
                "not-idle — set password",
                "Set a password to unlock the screen:",
                show="*",
                parent=root,
            )
            if pw1 is None:
                sys.exit(0)
            if not pw1:
                messagebox.showerror("Error", "Password cannot be empty.", parent=root)
                continue
            pw2 = simpledialog.askstring(
                "not-idle — confirm password",
                "Re-enter the password:",
                show="*",
                parent=root,
            )
            if pw2 is None:
                sys.exit(0)
            if pw1 != pw2:
                messagebox.showerror("Error", "Passwords do not match.", parent=root)
                continue
            salt = secrets.token_hex(16)
            hashed = _hash(pw1, salt)
            _save_config(salt, hashed)
            return {"salt": salt, "hash": hashed}
    finally:
        root.destroy()


def _virtual_screen_rect():
    """Return (x, y, width, height) of the rectangle covering all monitors."""
    user32 = ctypes.windll.user32
    SM_XVIRTUALSCREEN = 76
    SM_YVIRTUALSCREEN = 77
    SM_CXVIRTUALSCREEN = 78
    SM_CYVIRTUALSCREEN = 79
    x = user32.GetSystemMetrics(SM_XVIRTUALSCREEN)
    y = user32.GetSystemMetrics(SM_YVIRTUALSCREEN)
    w = user32.GetSystemMetrics(SM_CXVIRTUALSCREEN)
    h = user32.GetSystemMetrics(SM_CYVIRTUALSCREEN)
    return x, y, w, h


def _lock(config: dict):
    salt = config["salt"]
    expected = config["hash"]

    root = tk.Tk()
    root.withdraw()

    x, y, w, h = _virtual_screen_rect()

    overlay = tk.Toplevel(root)
    overlay.overrideredirect(True)
    overlay.attributes("-topmost", True)
    overlay.geometry(f"{w}x{h}+{x}+{y}")
    overlay.configure(bg="black")
    overlay.config(cursor="none")
    overlay.focus_force()
    overlay.grab_set()

    buffer = []

    def reassert_topmost():
        overlay.attributes("-topmost", False)
        overlay.attributes("-topmost", True)
        overlay.after(2000, reassert_topmost)

    def on_key(event):
        if event.keysym == "Return":
            attempt = "".join(buffer)
            buffer.clear()
            if _hash(attempt, salt) == expected:
                root.destroy()
            else:
                overlay.configure(bg="#1a0000")
                overlay.after(120, lambda: overlay.configure(bg="black"))
        elif event.keysym == "BackSpace":
            if buffer:
                buffer.pop()
        elif event.keysym == "Escape":
            buffer.clear()
        elif event.char and event.char.isprintable():
            buffer.append(event.char)

    overlay.bind_all("<Key>", on_key)
    overlay.after(2000, reassert_topmost)
    root.mainloop()


def main():
    _set_dpi_aware()
    if len(sys.argv) > 1 and sys.argv[1] == "--reset":
        if CONFIG_PATH.exists():
            CONFIG_PATH.unlink()
        config = _first_run_setup()
    else:
        config = _load_config() or _first_run_setup()
    _lock(config)


if __name__ == "__main__":
    main()
