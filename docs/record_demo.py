#!/usr/bin/env python3
"""Record docs/demo.gif and docs/screenshot-*.png from the real widget on a private Xvfb display.

Run:  xvfb-run -a -s "-screen 0 1280x1000x24" python3 docs/record_demo.py
"""
import math
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tests"))
import ui_test as t  # noqa: E402  (sets up a temp data folder and loads the app)

from PIL import Image  # noqa: E402

import cairo  # noqa: E402

Gtk, Gdk, GLib, rw = t.Gtk, t.Gdk, t.GLib, t.rw
OUT = Path(__file__).resolve().parent
WX, WY = 200, 120          # widget position on the virtual screen
PAD = 36                   # wallpaper margin around the widget in the GIF
GIF_SCALE, SHOT_SCALE = 1.0, 2.0
FRAME_MS = 40

frames, durations = [], []
cursor = {"x": WX + 360, "y": WY + 60, "ripple": None}
canvas = {}


def wallpaper(w, h, scale):
    surf = cairo.ImageSurface(cairo.FORMAT_RGB24, int(w * scale), int(h * scale))
    cr = cairo.Context(surf)
    cr.scale(scale, scale)
    g = cairo.LinearGradient(0, 0, w, h)
    g.add_color_stop_rgb(0, 0.62, 0.72, 0.90)
    g.add_color_stop_rgb(0.55, 0.80, 0.74, 0.92)
    g.add_color_stop_rgb(1, 0.98, 0.82, 0.74)
    cr.set_source(g)
    cr.paint()
    for cx, cy, r, col in ((0.15, 0.85, 0.6, (1.0, 0.86, 0.70)), (0.9, 0.1, 0.5, (0.70, 0.80, 1.0))):
        rg = cairo.RadialGradient(cx * w, cy * h, 0, cx * w, cy * h, r * max(w, h))
        rg.add_color_stop_rgba(0, *col, 0.55)
        rg.add_color_stop_rgba(1, *col, 0)
        cr.set_source(rg)
        cr.paint()
    return surf


def draw_cursor(cr, x, y):
    pts = [(0, 0), (0, 17), (4.2, 13.2), (7, 19.5), (9.8, 18.4), (7.2, 12.2), (12.5, 12.2)]
    cr.save()
    cr.translate(x, y)
    cr.move_to(*pts[0])
    for p in pts[1:]:
        cr.line_to(*p)
    cr.close_path()
    cr.set_source_rgb(0.08, 0.08, 0.08)
    cr.fill_preserve()
    cr.set_source_rgb(1, 1, 1)
    cr.set_line_width(1.4)
    cr.stroke()
    cr.restore()


def compose(scale, rect, with_cursor=True):
    """Paint wallpaper, the visible windows and the cursor for the screen rect (x, y, w, h)."""
    x0, y0, w, h = rect
    key = (scale, w, h)
    if key not in canvas:
        canvas[key] = wallpaper(w, h, scale)
    surf = cairo.ImageSurface(cairo.FORMAT_RGB24, int(w * scale), int(h * scale))
    cr = cairo.Context(surf)
    cr.set_source_surface(canvas[key], 0, 0)
    cr.paint()
    cr.scale(scale, scale)
    for win in [t.win] + ([t.picker()] if t.picker() else []):
        ox, oy = win.get_window().get_origin()[1:]
        cr.save()
        cr.translate(ox - x0, oy - y0)
        win.draw(cr)
        cr.restore()
    if with_cursor:
        rp = cursor["ripple"]
        if rp:
            age = (clock["us"] - rp) / 350000
            if age < 1:
                cr.arc(cursor["x"] - x0, cursor["y"] - y0, 4 + 14 * age, 0, 2 * math.pi)
                cr.set_source_rgba(0.2, 0.2, 0.2, 0.3 * (1 - age))
                cr.fill()
        draw_cursor(cr, cursor["x"] - x0, cursor["y"] - y0)
    surf.flush()
    img = Image.frombuffer("RGB", (surf.get_width(), surf.get_height()), bytes(surf.get_data()),
                           "raw", "BGRX", surf.get_stride(), 1)
    return img.copy()


def gif_rect():
    # Fixed for the whole recording: GIF frames must all be the same size.
    if "gif" not in canvas:
        m = 26  # card margin inside the window
        canvas["gif"] = (WX - PAD + m, WY - PAD + m, 300 + 2 * PAD, 720)  # 300 = widest picker card
    return canvas["gif"]


# Recording runs on a fake clock that moves exactly FRAME_MS per GIF frame, so animations
# that read GLib.get_monotonic_time() come out at true speed even if capture is slow.
clock = {"us": GLib.get_monotonic_time(), "recording": False}
GLib.get_monotonic_time = lambda: clock["us"]
real_pump = t.pump


def settle():
    for w in [t.win] + ([t.picker()] if t.picker() else []):
        w.check_resize()  # finish pending layout so draw() never sees a half-allocated window
    while Gtk.events_pending():
        Gtk.main_iteration_do(False)


def frame():
    """Advance one frame: fake clock + real time, process events, then capture."""
    clock["us"] += FRAME_MS * 1000
    real_pump(FRAME_MS / 1000)
    settle()
    if clock["recording"]:
        frames.append(compose(GIF_SCALE, gif_rect()))
        durations.append(FRAME_MS)


def pump(seconds=0.0):
    for _ in range(max(1, round(seconds * 1000 / FRAME_MS))):
        frame()


t.pump = pump  # xdotool helpers in ui_test pump through here too


def screenshot(name, include_picker=False):
    wins = [t.win] + ([t.picker()] if include_picker and t.picker() else [])
    xs, ys, xe, ye = [], [], [], []
    for w in wins:
        ox, oy = w.get_window().get_origin()[1:]
        xs.append(ox), ys.append(oy)
        xe.append(ox + w.get_allocated_width()), ye.append(oy + w.get_allocated_height())
    m = 4
    rect = (min(xs) - m, min(ys) - m, max(xe) - min(xs) + 2 * m, max(ye) - min(ys) + 2 * m)
    compose(SHOT_SCALE, rect, with_cursor=False).save(OUT / f"screenshot-{name}.png", optimize=True)


def glide(widget, secs=0.55):
    tx, ty = t.center(widget)
    sx, sy = cursor["x"], cursor["y"]
    n = max(1, round(secs * 1000 / FRAME_MS))
    for i in range(1, n + 1):
        k = i / n
        e = k * k * (3 - 2 * k)
        cursor["x"], cursor["y"] = sx + (tx - sx) * e, sy + (ty - sy) * e
        frame()


def click(widget):
    glide(widget)
    t.xdo("mousemove", *t.center(widget))
    cursor["ripple"] = clock["us"]
    t.xdo("click", 1)


def type_into(entry, text):
    for ch in text:
        entry.insert_text(ch, -1)
        entry.set_position(-1)
        pump(0.12)


def main():
    today = date.today()
    later = (datetime.now() + timedelta(hours=2)).replace(minute=0)
    (t.DATA / "items.txt").write_text(
        f"디자인 리뷰 피드백 반영 @{later:%Y-%m-%d %H:%M} -10m\n"
        "택배 반품 접수\n"
        f"엄마 생신 선물 고르기 @{today + timedelta(days=4):%Y-%m-%d}\n"
        f"비타민 먹기 @{today:%Y-%m-%d} 08:30 -10m\n")
    (t.DATA / "done.txt").write_text("치과 예약 확인\n관리비 납부\n")

    prov = Gtk.CssProvider()
    prov.load_from_data(rw.CSS)
    Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), prov, Gtk.STYLE_PROVIDER_PRIORITY_USER)
    t.win = win = rw.Widget()
    win.move(WX, WY)
    win.show_all()
    pump(0.8)
    screenshot("main")

    clock["recording"] = True
    pump(1.2)

    click(win.plus_btn)
    pump(0.3)
    entry = t.find(win.card, Gtk.Entry)
    type_into(entry, "팀 회의 준비 @")
    pump(0.8)
    p = t.picker()
    screenshot("calendar", include_picker=True)
    target = today + timedelta(days=2)
    if target.month != today.month:
        click(t.find(p.box, Gtk.Button, "›"))
    click(next(w for w in t.walk(p.box) if isinstance(w, Gtk.Button) and w.get_label() == str(target.day)
               and w.get_style_context().has_class("day") and not w.get_style_context().has_class("other")))
    pump(0.5)
    click(t.find(p.box, Gtk.Button, "15:00"))
    pump(0.2)
    click(t.find(p.box, Gtk.Button, "30분 전"))
    pump(0.5)
    screenshot("time", include_picker=True)
    click(t.find(p.box, Gtk.Button, "확인"))
    pump(1.1)
    entry.emit("activate")
    pump(1.0)

    click(t.row_check(win, "택배 반품 접수"))
    pump(2.0)
    screenshot("list")

    click(win.done_tab)
    pump(1.3)
    screenshot("done")
    click(t.row_check(win, "택배 반품 접수"))
    pump(2.2)
    click(win.todo_tab)
    pump(1.6)

    pal = Image.new("RGB", (frames[0].width, frames[0].height * 4))
    for i, k in enumerate((0, len(frames) // 3, len(frames) // 2, -1)):
        pal.paste(frames[k], (0, frames[0].height * i))
    pal = pal.quantize(colors=255, method=Image.Quantize.MEDIANCUT)
    gif = [f.quantize(palette=pal, dither=Image.Dither.NONE) for f in frames]
    gif[0].save(OUT / "demo.gif", save_all=True, append_images=gif[1:], duration=durations,
                loop=0, optimize=True, disposal=1)
    print(f"{len(frames)} frames, {frames[0].size}, {(OUT / 'demo.gif').stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
