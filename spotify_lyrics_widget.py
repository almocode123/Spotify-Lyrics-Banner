"""
Spotify Lyrics Banner
-----------------------
A thin, movable, resizable banner window (default: pinned across the
top of the screen) that shows ONE lyric line at a time, vertically
centered no matter the window's height, and transitions to the next
line with a vertical slide, like a slot-machine reel / odometer.
Background color is pulled from the current track's album art. Click
the lyric to seek there.

Setup:
    1. pip install spotipy syncedlyrics pillow requests
    2. Create a Spotify Developer app: https://developer.spotify.com/dashboard
       - Add redirect URI: http://127.0.0.1:8888/callback
       - Paste your Client ID / Client Secret below.
    3. Run: python spotify_lyrics_widget.py
       (Spotify must be actively playing on a device for seeking to work.)

Note on "reserved space" (Windows only): while docked at the top edge,
this registers itself as a Windows "AppBar" — the same mechanism the
taskbar uses — so MAXIMIZED windows will size themselves to avoid it.
It cannot forcibly move windows that are already open and overlapping;
Windows doesn't let any app do that, taskbar included.
"""

import io
import os
import re
import sys
import json
import ctypes
import ctypes.wintypes as wintypes
import threading
import time
import tkinter as tk
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from PIL import Image
import spotipy
from spotipy.oauth2 import SpotifyPKCE
import syncedlyrics
from syncedlyrics.providers import Lrclib, NetEase, Musixmatch

IS_WINDOWS = sys.platform.startswith("win")

# Per-user, writable app data folder — NOT the folder the script/exe lives
# in, since that may be read-only (e.g. installed under Program Files).
APP_DIR = os.path.join(
    os.environ.get("APPDATA") or os.path.expanduser("~"), "SpotifyLyricsBanner"
)
os.makedirs(APP_DIR, exist_ok=True)

# ---- Windows AppBar (SHAppBarMessage) constants/structures ----
ABM_NEW = 0x00000000
ABM_REMOVE = 0x00000001
ABM_QUERYPOS = 0x00000002
ABM_SETPOS = 0x00000003
ABE_TOP = 1


class RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                ("right", ctypes.c_long), ("bottom", ctypes.c_long)]


class APPBARDATA(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_ulong), ("hWnd", wintypes.HWND),
                ("uCallbackMessage", ctypes.c_uint), ("uEdge", ctypes.c_uint),
                ("rc", RECT), ("lParam", ctypes.c_long)]

# ---- Lyrics cache, so a track already looked up loads instantly next time ----
LYRICS_CACHE_PATH = os.path.join(APP_DIR, "lyrics_cache.json")

# syncedlyrics.search() tries providers ONE AT A TIME — if the first one is
# slow or unresponsive, you wait out its full timeout before it even tries
# the next. Instead we query these providers all AT ONCE and take whichever
# answers first, bounded by FETCH_TIMEOUT_SECONDS overall. Megalobiz/Genius
# are skipped — they rarely add coverage the other three don't already have.
PARALLEL_PROVIDER_CLASSES = [Lrclib, NetEase, Musixmatch]
FETCH_TIMEOUT_SECONDS = 6


def load_lyrics_cache():
    try:
        with open(LYRICS_CACHE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_lyrics_cache(cache):
    try:
        with open(LYRICS_CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(cache, f)
    except Exception:
        pass


def fetch_lyrics_parallel(search_term, timeout=FETCH_TIMEOUT_SECONDS):
    """Query all providers concurrently and return the LRC text from
    whichever responds first with synced lyrics — total wait is bounded
    by `timeout`, not by the sum of every provider's own timeout."""
    providers = [cls() for cls in PARALLEL_PROVIDER_CLASSES]
    executor = ThreadPoolExecutor(max_workers=len(providers))
    futures = {executor.submit(p.get_lrc, search_term): p for p in providers}
    result = None
    try:
        for future in as_completed(futures, timeout=timeout):
            try:
                lyrics = future.result()
            except Exception:
                continue
            if lyrics and lyrics.synced:
                result = lyrics.synced
                break
    except TimeoutError:
        pass  # nobody answered in time — treat as "not found" rather than waiting longer
    finally:
        # Don't wait for the slower, losing providers to finish before
        # returning — let them run out in the background and discard them.
        executor.shutdown(wait=False, cancel_futures=True)
    return result


def fetch_lyrics_cached(cache, track_id, search_term):
    """Return LRC text (or None) for this track, using the on-disk cache
    when available so repeat plays skip the network entirely."""
    if track_id in cache:
        return cache[track_id]
    lrc = fetch_lyrics_parallel(search_term)
    cache[track_id] = lrc  # cache misses too, so a "no lyrics" track doesn't get re-searched every time
    save_lyrics_cache(cache)
    return lrc


# ---- Fill this in from your Spotify Developer dashboard ----
SPOTIPY_CLIENT_ID = ""
SPOTIPY_REDIRECT_URI = "http://127.0.0.1:8888/callback"
# ---------------------------------------------------------------

TOKEN_CACHE_PATH = os.path.join(APP_DIR, ".spotify_token_cache")
IS_FIRST_RUN = not os.path.exists(TOKEN_CACHE_PATH)  # checked before spotipy has a chance to create it

sp = spotipy.Spotify(auth_manager=SpotifyPKCE(
    client_id=SPOTIPY_CLIENT_ID,
    redirect_uri=SPOTIPY_REDIRECT_URI,
    scope="user-read-currently-playing user-read-playback-state user-modify-playback-state",
    cache_path=TOKEN_CACHE_PATH,  # saved locally so you only log in once, ever
    open_browser=True,
))

LRC_LINE_RE = re.compile(r"\[(\d+):(\d+(?:\.\d+)?)\](.*)")

SLIDE_DISTANCE = 60   # pixels the reel travels per transition
ANIMATION_STEPS = 15
ANIMATION_DELAY_MS = 15


def parse_lrc(lrc_text):
    """Turn raw LRC text into a sorted list of (seconds, text) tuples."""
    lines = []
    for raw_line in lrc_text.splitlines():
        match = LRC_LINE_RE.match(raw_line.strip())
        if not match:
            continue
        minutes, seconds, text = match.groups()
        total_seconds = int(minutes) * 60 + float(seconds)
        text = text.strip()
        if text:
            lines.append((total_seconds, text))
    lines.sort(key=lambda pair: pair[0])
    return lines


def get_album_color(image_url):
    """Download the album art and return its average RGB color."""
    try:
        response = requests.get(image_url, timeout=5)
        img = Image.open(io.BytesIO(response.content)).convert("RGB")
        img = img.resize((1, 1), Image.LANCZOS)
        return img.getpixel((0, 0))
    except Exception:
        return (25, 25, 25)  # fallback near-black


def scale_color(rgb, factor):
    return tuple(max(0, min(255, int(c * factor))) for c in rgb)


def blend_color(rgb, other, amount):
    """Blend rgb toward other by `amount` (0 = rgb, 1 = other)."""
    return tuple(int(c * (1 - amount) + o * amount) for c, o in zip(rgb, other))


def to_hex(rgb):
    return "#%02x%02x%02x" % rgb


def build_theme_from_album(image_url):
    """Derive a Spotify-style theme (dark muted background + dim text
    color) from an album cover, the same way Spotify tints its lyrics
    view to match the art."""
    avg = get_album_color(image_url)
    background = scale_color(avg, 0.5)          # darken toward Spotify's muted panel look
    dim_text = blend_color(background, (255, 255, 255), 0.35)
    return to_hex(background), to_hex(dim_text)


def ease_out_cubic(t):
    return 1 - (1 - t) ** 3


class LyricsBanner:
    def __init__(self, root):
        self.root = root
        root.title("Lyrics")
        root.attributes("-topmost", True)
        root.overrideredirect(True)   # borderless: no OS title bar, border, or resize handles

        # Default to a thin banner pinned across the top of the screen.
        root.update_idletasks()
        screen_width = root.winfo_screenwidth()
        root.geometry(f"{screen_width}x70+0+0")

        self._min_width = 240
        self._min_height = 48

        # Theme colors, updated per-track from the album art.
        self.bg_color = "#121212"
        self.dim_color = "#727272"
        self.highlight_color = "#ffffff"
        root.configure(bg=self.bg_color)

        # Top bar: track caption on the left, close button on the right.
        # This whole bar (minus the close button) doubles as the drag handle,
        # since overrideredirect removes the OS title bar we'd normally drag.
        self.top_bar = tk.Frame(root, bg=self.bg_color)
        self.top_bar.pack(fill="x")

        self.track_label = tk.Label(
            self.top_bar, text="", font=("Segoe UI", 9, "bold"),
            fg=self.dim_color, bg=self.bg_color
        )
        self.track_label.pack(side="left", padx=(10, 0), pady=4)

        self.close_button = tk.Label(
            self.top_bar, text="\u2715", font=("Segoe UI", 10, "bold"),
            fg=self.dim_color, bg=self.bg_color, cursor="hand2"
        )
        self.close_button.pack(side="right", padx=8, pady=4)
        self.close_button.bind("<Button-1>", lambda e: self._close())
        self.close_button.bind("<Enter>", lambda e: self.close_button.config(fg=self.highlight_color))
        self.close_button.bind("<Leave>", lambda e: self.close_button.config(fg=self.dim_color))

        # The "reel" viewport where lyric lines slide through. The lyric
        # is always vertically centered inside THIS frame, regardless of
        # how tall or short the overall window is.
        self.display_frame = tk.Frame(root, bg=self.bg_color)
        self.display_frame.pack(fill="both", expand=True)
        self.display_frame.bind("<Configure>", self._on_display_resize)

        # Resize grip, bottom-right corner.
        self.resize_grip = tk.Label(
            root, text="\u2921", font=("Segoe UI", 10), fg=self.dim_color, bg=self.bg_color
        )
        try:
            self.resize_grip.configure(cursor="size_nw_se")  # Windows-style diagonal-resize cursor
        except tk.TclError:
            try:
                self.resize_grip.configure(cursor="bottom_right_corner")  # X11 equivalent
            except tk.TclError:
                pass  # fall back to the default cursor rather than crash on an unsupported platform
        self.resize_grip.place(relx=1.0, rely=1.0, anchor="se", x=-2, y=-2)
        self.resize_grip.bind("<ButtonPress-1>", self._start_resize)
        self.resize_grip.bind("<B1-Motion>", self._do_resize)
        self.resize_grip.bind("<ButtonRelease-1>", lambda e: self._update_appbar_position() if self._appbar_registered else None)

        # Dragging: press-and-drag on the top bar or the empty banner
        # background (not on the lyric text itself, which is reserved
        # for click-to-seek) moves the window.
        for draggable in (self.top_bar, self.track_label, self.display_frame):
            draggable.bind("<ButtonPress-1>", self._start_move)
            draggable.bind("<B1-Motion>", self._do_move)
            draggable.bind("<ButtonRelease-1>", lambda e: self._on_drag_release())

        self.line_font = ("Segoe UI", 20, "bold")
        self.status_font = ("Segoe UI", 13)
        self.wrap_width = max(200, screen_width - 80)

        self.active_label = None       # currently showing label
        self._animation_job = None

        self.current_track_id = None
        self.lyric_lines = []          # [(seconds, text), ...]
        self.current_index = -1
        self.lyrics_cache = load_lyrics_cache()

        # Local playback-position tracking, interpolated between polls.
        self.base_progress_ms = 0
        self.base_timestamp = time.time()
        self.is_playing = False
        self._suppress_correction_until = 0.0

        self._appbar_registered = False
        self._hwnd = None

        if IS_FIRST_RUN:
            self.show_line("Opening Spotify in your browser — click Allow to link your account", animate=False, font=self.status_font)
        else:
            self.show_line("Waiting for Spotify...", animate=False)

        threading.Thread(target=self.poll_loop, daemon=True).start()
        self.root.after(200, self._tick)

        self.root.after(150, self._register_appbar)  # slight delay so the HWND is fully realized

    # ---------- window dragging / resizing (replaces what the OS title bar normally does) ----------

    def _start_move(self, event):
        self._drag_start_x = event.x_root
        self._drag_start_y = event.y_root
        self._drag_win_x = self.root.winfo_x()
        self._drag_win_y = self.root.winfo_y()

    def _do_move(self, event):
        dx = event.x_root - self._drag_start_x
        dy = event.y_root - self._drag_start_y
        self.root.geometry(f"+{self._drag_win_x + dx}+{self._drag_win_y + dy}")

    def _start_resize(self, event):
        self._resize_start_x = event.x_root
        self._resize_start_y = event.y_root
        self._resize_start_w = self.root.winfo_width()
        self._resize_start_h = self.root.winfo_height()

    def _do_resize(self, event):
        # Height is now auto-fit to the lyric text (see _fit_window_height),
        # so the grip only changes width — dragging vertically has no effect.
        dx = event.x_root - self._resize_start_x
        new_w = max(self._min_width, self._resize_start_w + dx)
        self.root.geometry(f"{new_w}x{self.root.winfo_height()}")

    def _on_drag_release(self):
        """Dock (reserve space) if dropped at the top edge; otherwise
        undock and float freely, releasing any reserved space."""
        if self.root.winfo_y() <= 5:
            if self._appbar_registered:
                self._update_appbar_position()
            else:
                self._register_appbar()
        else:
            if self._appbar_registered:
                self._unregister_appbar()

    # ---------- reserved screen space (Windows AppBar) ----------

    def _register_appbar(self):
        if not IS_WINDOWS:
            return
        try:
            self._hwnd = self.root.winfo_id()
            abd = APPBARDATA()
            abd.cbSize = ctypes.sizeof(APPBARDATA)
            abd.hWnd = self._hwnd
            abd.uCallbackMessage = 0
            ctypes.windll.shell32.SHAppBarMessage(ABM_NEW, ctypes.byref(abd))
            self._appbar_registered = True
            self._update_appbar_position()
        except Exception as e:
            self.set_track_label(f"Couldn't reserve screen space: {e}")

    def _update_appbar_position(self):
        """Tell Windows to reserve a full-width strip at the top matching
        our current height, and snap our own window to whatever rect
        Windows actually grants (it may be adjusted if something else,
        like the real taskbar, is also docked at that edge)."""
        if not self._appbar_registered:
            return
        try:
            screen_w = self.root.winfo_screenwidth()
            height = self.root.winfo_height()
            abd = APPBARDATA()
            abd.cbSize = ctypes.sizeof(APPBARDATA)
            abd.hWnd = self._hwnd
            abd.uEdge = ABE_TOP
            abd.rc = RECT(0, 0, screen_w, height)
            ctypes.windll.shell32.SHAppBarMessage(ABM_QUERYPOS, ctypes.byref(abd))
            abd.rc.bottom = abd.rc.top + height  # keep our chosen thickness
            ctypes.windll.shell32.SHAppBarMessage(ABM_SETPOS, ctypes.byref(abd))
            w = abd.rc.right - abd.rc.left
            h = abd.rc.bottom - abd.rc.top
            self.root.geometry(f"{w}x{h}+{abd.rc.left}+{abd.rc.top}")
        except Exception as e:
            self.set_track_label(f"Couldn't update reserved space: {e}")

    def _unregister_appbar(self):
        if not self._appbar_registered:
            return
        try:
            abd = APPBARDATA()
            abd.cbSize = ctypes.sizeof(APPBARDATA)
            abd.hWnd = self._hwnd
            ctypes.windll.shell32.SHAppBarMessage(ABM_REMOVE, ctypes.byref(abd))
        except Exception:
            pass
        self._appbar_registered = False

    def _close(self):
        # Always release the reserved space before exiting — otherwise
        # Windows can leave that strip of the desktop work area shrunk
        # even after this program has closed.
        self._unregister_appbar()
        self.root.destroy()

    # ---------- layout ----------

    def _on_display_resize(self, event):
        self.wrap_width = max(120, event.width - 60)
        if self.active_label:
            self.active_label.configure(wraplength=self.wrap_width)
            # A width change can reflow the text onto a different number
            # of lines, so the height needed to show it all can change too.
            self.root.after(1, self._fit_window_height)

    def _fit_window_height(self):
        """Resize the window's height to snugly fit the current lyric,
        with no leftover gap and nothing clipped off — called every time
        the displayed line (or its wrapping) changes."""
        if self.active_label is None:
            return
        self.root.update_idletasks()
        top_h = self.top_bar.winfo_reqheight()
        content_h = self.active_label.winfo_reqheight()
        padding = 16  # a little breathing room around the text
        target_h = max(self._min_height, top_h + content_h + padding)
        current_w = self.root.winfo_width()
        current_h = self.root.winfo_height()
        if abs(target_h - current_h) > 2:
            self.root.geometry(f"{current_w}x{target_h}")
            if self._appbar_registered:
                self._update_appbar_position()

    def set_track_label(self, text):
        self.track_label.config(text=text)

    def apply_theme(self, bg_hex, dim_hex):
        """Re-tint every widget to match the current track's album art,
        the way Spotify's lyrics panel changes color per song."""
        self.bg_color = bg_hex
        self.dim_color = dim_hex
        self.root.configure(bg=bg_hex)
        self.top_bar.configure(bg=bg_hex)
        self.track_label.configure(bg=bg_hex, fg=dim_hex)
        self.close_button.configure(bg=bg_hex, fg=dim_hex)
        self.resize_grip.configure(bg=bg_hex, fg=dim_hex)
        self.display_frame.configure(bg=bg_hex)
        if self.active_label:
            self.active_label.configure(bg=bg_hex, fg=self.highlight_color)

    # ---------- the sliding "reel" display (always vertically centered) ----------

    def show_line(self, text, seconds=None, animate=True, font=None):
        font = font or self.line_font
        new_label = tk.Label(
            self.display_frame, text=text, font=font,
            fg=self.highlight_color, bg=self.bg_color,
            wraplength=self.wrap_width, justify="center"
        )
        if seconds is not None:
            new_label.bind("<Button-1>", lambda e: self.seek_to(seconds))

        old_label = self.active_label
        self.active_label = new_label
        self._fit_window_height()  # resize before placing, so the slide lands in the right spot

        if self._animation_job is not None:
            self.root.after_cancel(self._animation_job)
            self._animation_job = None

        if not animate or old_label is None:
            if old_label is not None:
                old_label.destroy()
            new_label.place(relx=0.5, rely=0.5, anchor="center", y=0)
            return

        new_label.place(relx=0.5, rely=0.5, anchor="center", y=SLIDE_DISTANCE)
        self._animate_transition(old_label, new_label, step=0)

    def _animate_transition(self, old_label, new_label, step):
        t = step / ANIMATION_STEPS
        eased = ease_out_cubic(t)
        offset = SLIDE_DISTANCE * eased

        if old_label is not None and old_label.winfo_exists():
            old_label.place(relx=0.5, rely=0.5, anchor="center", y=-offset)
        if new_label.winfo_exists():
            new_label.place(relx=0.5, rely=0.5, anchor="center", y=SLIDE_DISTANCE - offset)

        if step < ANIMATION_STEPS:
            self._animation_job = self.root.after(
                ANIMATION_DELAY_MS, self._animate_transition, old_label, new_label, step + 1
            )
        else:
            self._animation_job = None
            if old_label is not None and old_label.winfo_exists():
                old_label.destroy()

    def set_status_message(self, text):
        self.lyric_lines = []
        self.current_index = -1
        self.show_line(text, animate=False, font=self.status_font)

    def build_lines(self, lyric_lines):
        self.lyric_lines = lyric_lines
        self.current_index = -1

    # ---------- playback / seeking ----------

    def seek_to(self, seconds):
        # Update instantly so the display reflects the click right away,
        # rather than waiting up to 1s for the next poll.
        self.base_progress_ms = seconds * 1000
        self.base_timestamp = time.time()
        self.is_playing = True
        self._suppress_correction_until = time.time() + 2.0  # ignore stale polls for 2s
        self.highlight_for_progress(seconds)
        try:
            sp.seek_track(position_ms=int(seconds * 1000))
        except Exception as e:
            self.set_track_label(f"Couldn't seek: {e}")

    def _tick(self):
        """Runs on the UI thread every 200ms to smoothly advance playback
        position based on local interpolation, rather than only updating
        once per second when the API responds."""
        if self.is_playing:
            elapsed = time.time() - self.base_timestamp
            estimated_seconds = (self.base_progress_ms / 1000.0) + elapsed
            self.highlight_for_progress(estimated_seconds)
        self.root.after(200, self._tick)

    def highlight_for_progress(self, progress_seconds):
        if not self.lyric_lines:
            return
        new_index = -1
        for i, (seconds, _) in enumerate(self.lyric_lines):
            if seconds <= progress_seconds:
                new_index = i
            else:
                break
        if new_index == self.current_index or new_index == -1:
            return

        self.current_index = new_index
        seconds, text = self.lyric_lines[new_index]
        self.show_line(text, seconds=seconds, animate=True)

    # ---------- polling ----------

    def poll_loop(self):
        while True:
            try:
                request_sent = time.time()
                current = sp.current_playback()
                request_finished = time.time()

                if current and current.get("item"):
                    track = current["item"]
                    track_id = track["id"]
                    is_playing = current.get("is_playing", False)

                    # Assume the reported progress was true at the midpoint of the
                    # request round-trip, and correct for network/API latency.
                    round_trip = request_finished - request_sent
                    reported_progress_ms = current.get("progress_ms", 0)
                    corrected_progress_ms = reported_progress_ms + (round_trip / 2) * 1000 if is_playing else reported_progress_ms

                    if track_id != self.current_track_id:
                        self.current_track_id = track_id
                        name = track["name"]
                        artist = ", ".join(a["name"] for a in track["artists"])
                        self.root.after(0, self.set_track_label, f"{name} — {artist}")
                        self.root.after(0, self.set_status_message, "Loading lyrics...")

                        # Re-tint the whole banner to match this track's album art
                        images = track.get("album", {}).get("images", [])
                        if images:
                            image_url = images[len(images) // 2]["url"]
                            bg_hex, dim_hex = build_theme_from_album(image_url)
                            self.root.after(0, self.apply_theme, bg_hex, dim_hex)

                        lrc = fetch_lyrics_cached(self.lyrics_cache, track_id, f"{name} {artist}")
                        if lrc:
                            parsed = parse_lrc(lrc)
                            if parsed:
                                self.root.after(0, self.build_lines, parsed)
                            else:
                                self.root.after(0, self.set_status_message, "No synced lyrics found.")
                        else:
                            self.root.after(0, self.set_status_message, "No synced lyrics found for this track.")

                    # Don't let a poll that was already in flight during a manual
                    # seek overwrite the fresh position with stale data.
                    if time.time() >= self._suppress_correction_until:
                        self.base_progress_ms = corrected_progress_ms
                        self.base_timestamp = time.time()
                        self.is_playing = is_playing
                else:
                    self.is_playing = False
                    self.root.after(0, self.set_track_label, "Nothing playing")
            except Exception as e:
                self.root.after(0, self.set_track_label, f"Error: {e}")
            time.sleep(1)


if __name__ == "__main__":
    import atexit

    root = tk.Tk()
    app = LyricsBanner(root)
    # Best-effort cleanup even if the process exits some other way
    # (e.g. Ctrl+C in the terminal) rather than via the close button.
    atexit.register(app._unregister_appbar)
    root.mainloop()
