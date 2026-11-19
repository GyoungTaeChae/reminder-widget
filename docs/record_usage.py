#!/usr/bin/env python3
"""Record the short how-to GIFs in docs/usage-*.gif that the README's 사용법 section shows.

Run:  xvfb-run -a -s "-screen 0 1600x1000x24" python3 docs/record_usage.py
"""
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import record_demo as rd  # noqa: E402  (fake clock, frame capture, cursor drawing)

from PIL import Image, ImageDraw, ImageFont  # noqa: E402

t, Gtk, Gdk, rw = rd.t, rd.Gtk, rd.Gdk, rd.rw
OUT = rd.OUT
FONT = ImageFont.truetype("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc", 13, index=1)  # KR face
badge = {"text": None, "until": 0}

# Draw the pressed key as a small dark pill at the bottom of each frame.
base_compose = rd.compose


def compose(scale, rect, with_cursor=True):
    img = base_compose(scale, rect, with_cursor)
    if badge["text"] and rd.clock["us"] < badge["until"]:
        d = ImageDraw.Draw(img)
        w = d.textlength(badge["text"], font=FONT) + 28
        x0, y1 = (img.width - w) / 2, img.height - 16
        d.rounded_rectangle((x0, y1 - 30, x0 + w, y1), radius=15, fill=(30, 30, 34))
        d.text((img.width / 2, y1 - 15), badge["text"], font=FONT, fill=(255, 255, 255), anchor="mm")
    return img


rd.compose = compose


def key(label, xdo_key):
    badge["text"], badge["until"] = label, rd.clock["us"] + 900_000
    rd.pump(0.25)
    t.xdo("key", xdo_key)


def glide_to(x, y, secs=0.5):
    sx, sy = rd.cursor["x"], rd.cursor["y"]
    n = max(1, round(secs * 1000 / rd.FRAME_MS))
    for i in range(1, n + 1):
        k = i / n
        e = k * k * (3 - 2 * k)
        rd.cursor["x"], rd.cursor["y"] = sx + (tx := x - sx) * e, sy + (ty := y - sy) * e
        rd.frame()


def reset(items, done=()):
    (t.DATA / "items.txt").write_text("".join(i + "\n" for i in items))
    (t.DATA / "done.txt").write_text("".join(i + "\n" for i in done))
    win = t.win
    win.items, win.done = rw.load(), rw.load(rw.DONE)
    win.view, win.adding, win.editing, win.confirm_clear = "todo", False, None, False
    win.user_width = 1
    win.move(rd.WX, rd.WY)
    win.render()
    rd.pump(0.3)


def record(name, height, width=300 + 2 * rd.PAD):
    rd.frames.clear()
    rd.durations.clear()
    m = 26
    rd.canvas["gif"] = (rd.WX - rd.PAD + m, rd.WY - rd.PAD + m, width, height)
    rd.cursor.update(x=rd.WX + 330, y=rd.WY + 40, ripple=None)
    rd.clock["recording"] = True


def save(name):
    rd.clock["recording"] = False
    frames = rd.frames
    pal = Image.new("RGB", (frames[0].width, frames[0].height * 3))
    for i, k in enumerate((0, len(frames) // 2, -1)):
        pal.paste(frames[k], (0, frames[0].height * i))
    pal = pal.quantize(colors=255, method=Image.Quantize.MEDIANCUT)
    gif = [f.quantize(palette=pal, dither=Image.Dither.NONE) for f in frames]
    path = OUT / f"usage-{name}.gif"
    gif[0].save(path, save_all=True, append_images=gif[1:], duration=list(rd.durations),
                loop=0, optimize=True, disposal=1)
    print(f"{path.name}: {len(frames)} frames, {frames[0].size}, {path.stat().st_size / 1e6:.2f} MB")


def main():
    prov = Gtk.CssProvider()
    prov.load_from_data(rw.CSS)
    Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), prov, Gtk.STYLE_PROVIDER_PRIORITY_USER)
    t.win = win = rw.Widget()
    win.move(rd.WX, rd.WY)
    win.show_all()
    rd.pump(0.6)
    today = date.today()

    # 추가하기: Enter opens, Enter saves and opens the next, Ctrl+Enter finishes.
    reset(["택배 반품 접수"])
    record("add", 300)
    rd.pump(0.6)
    cx, cy = t.center(win.card)
    glide_to(cx + 60, cy + 10)
    t.xdo("mousemove", cx + 60, cy + 10)
    key("Enter", "Return")
    rd.pump(0.3)
    rd.type_into(win.get_focus(), "우유 사기")
    key("Enter", "Return")
    rd.pump(0.3)
    rd.type_into(win.get_focus(), "세탁소 맡기")
    key("Ctrl + Enter", "ctrl+Return")
    rd.pump(1.4)
    save("add")

    # 날짜 붙이기: "@" opens the calendar, then time and alert.
    reset(["택배 반품 접수"])
    record("date", 560)
    rd.pump(0.5)
    rd.click(win.plus_btn)
    rd.pump(0.2)
    entry = win.get_focus()
    rd.type_into(entry, "팀 회의 @")
    rd.pump(0.7)
    p = t.picker()
    target = today + timedelta(days=2)
    if target.month != today.month:
        rd.click(t.find(p.box, Gtk.Button, "›"))
    rd.click(next(w for w in t.walk(p.box) if isinstance(w, Gtk.Button) and w.get_label() == str(target.day)
                  and w.get_style_context().has_class("day") and not w.get_style_context().has_class("other")))
    rd.pump(0.4)
    rd.click(t.find(p.box, Gtk.Button, "15:00"))
    rd.click(t.find(p.box, Gtk.Button, "30분 전"))
    rd.pump(0.3)
    rd.click(t.find(p.box, Gtk.Button, "확인"))
    rd.pump(0.8)
    t.xdo("mousemove", *t.center(entry))
    key("Ctrl + Enter", "ctrl+Return")
    rd.pump(1.4)
    save("date")

    # 끝낸 일: check a few in a row, restore one, empty the done list with the bin.
    reset(["디자인 리뷰 피드백 반영", "택배 반품 접수", "엄마 생신 선물 고르기", "비타민 먹기"])
    record("done", 300)
    rd.pump(0.5)
    for name in ("택배 반품 접수", "비타민 먹기"):
        rd.click(t.row_check(win, name))
    rd.pump(2.0)
    rd.click(win.done_tab)
    rd.pump(0.6)
    rd.click(t.row_check(win, "비타민 먹기"))
    rd.pump(2.0)
    rd.click(win.trash_btn)
    rd.pump(0.5)
    rd.click(win.trash_btn)
    rd.pump(0.6)
    rd.click(win.todo_tab)
    rd.pump(1.2)
    save("done")

    # 고치기: click the text, change it, Enter.
    reset(["택배 반품 접수", "엄마 생신 선물 고르기"])
    record("edit", 240)
    rd.pump(0.5)
    rd.click(t.find(win.card, Gtk.Label, "택배 반품 접수"))
    rd.pump(0.4)
    entry = win.get_focus()
    entry.set_position(-1)
    rd.type_into(entry, " (편의점)")
    key("Enter", "Return")
    rd.pump(1.3)
    save("edit")

    # 옮기기 · 폭: drag the area above the list line; Ctrl+drag the side to widen.
    # Xvfb has no window manager, so the window follows the fake pointer here by hand.
    reset(["택배 반품 접수", "엄마 생신 선물 고르기"])
    record("move", 300, width=520)
    rd.pump(0.5)
    hx, hy = t.center(win.header)
    hx += 40
    glide_to(hx, hy - 14)
    rd.cursor["ripple"] = rd.clock["us"]
    ox, oy = win.get_position()
    for i in range(1, 16):
        k = i / 15
        e = k * k * (3 - 2 * k)
        rd.cursor["x"], rd.cursor["y"] = hx + 140 * e, hy - 14 + 30 * e
        win.move(ox + int(140 * e), oy + int(30 * e))
        rd.frame()
    rd.pump(0.5)
    w0 = win.get_size()[0]
    rx, ry = win.get_position()[0] + w0 - 34, rd.cursor["y"] + 60
    glide_to(rx, ry)
    badge["text"], badge["until"] = "Ctrl + 드래그", rd.clock["us"] + 1_600_000
    rd.cursor["ripple"] = rd.clock["us"]
    for i in range(1, 16):
        k = i / 15
        e = k * k * (3 - 2 * k)
        rd.cursor["x"] = rx + 70 * e
        win.user_width = w0 + int(70 * e)
        win.resize(win.user_width, 1)
        rd.frame()
    rd.pump(1.2)
    save("move")


if __name__ == "__main__":
    main()
