#!/usr/bin/env python3
"""End-to-end UI test: drives the real widget with X input events (xdotool) on a private Xvfb display.

Run:  xvfb-run -a -s "-screen 0 1280x900x24" python3 tests/ui_test.py
Needs xdotool. Uses a temp data folder, so your own reminders are not touched.
"""
import importlib.machinery
import importlib.util
import os
import subprocess
import sys
import tempfile
import time
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(tempfile.mkdtemp(prefix="reminder-test-"))
os.environ["REMINDER_WIDGET_DATA"] = str(DATA)


def load_app():
    loader = importlib.machinery.SourceFileLoader("rw", str(ROOT / "reminder-widget"))
    mod = importlib.util.module_from_spec(importlib.util.spec_from_loader("rw", loader))
    loader.exec_module(mod)
    return mod


rw = load_app()
Gtk, Gdk, GLib = rw.Gtk, rw.Gdk, rw.GLib
notified = []
rw.notify = lambda title, *_: notified.append(title)  # keep test alerts off the real desktop


# ---------- helpers ----------

def pump(seconds=0.0):
    """Run the GTK loop for a while so events, timers and animations happen."""
    end = time.monotonic() + seconds
    while True:
        while Gtk.events_pending():
            Gtk.main_iteration_do(False)
        if time.monotonic() >= end:
            return
        time.sleep(0.005)


def xdo(*args):
    subprocess.run(["xdotool", *map(str, args)], check=True)
    pump(0.15)


def center(widget):
    """Screen coordinates of a widget's center."""
    top = widget.get_toplevel()
    x, y = widget.translate_coordinates(top, widget.get_allocated_width() // 2,
                                        widget.get_allocated_height() // 2)
    ox, oy = top.get_window().get_origin()[1:]
    return ox + x, oy + y


def click(widget):
    xdo("mousemove", *center(widget))
    xdo("click", 1)


def type_text(text):
    # Real key events. xdotool cannot type Hangul on Xvfb, so test text is ASCII.
    xdo("type", "--delay", "30", text)


def walk(widget):
    yield widget
    if isinstance(widget, Gtk.Container):
        for c in widget.get_children():
            yield from walk(c)


def find(root, cls=None, text=None, css=None):
    for w in walk(root):
        if cls and not isinstance(w, cls):
            continue
        if text is not None and not (hasattr(w, "get_label") and w.get_label() == text
                                     or isinstance(w, Gtk.Label) and w.get_text() == text):
            continue
        if css and not w.get_style_context().has_class(css):
            continue
        if w.get_mapped():
            return w
    raise AssertionError(f"widget not found: cls={cls} text={text!r} css={css}")


def row_check(win, title):
    """The circle button on the row whose title is `title`."""
    lab = find(win.card, Gtk.Label, title)
    row = lab
    while not row.get_style_context().has_class("item"):
        row = row.get_parent()
    return next(w for w in row.get_children() if isinstance(w, Gtk.Button))


def picker():
    ps = [w for w in Gtk.Window.list_toplevels() if isinstance(w, rw.DatePicker) and w.get_visible()]
    return ps[0] if ps else None


results = []


def check(name, cond):
    results.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL ") + name, flush=True)


# ---------- test ----------

def main():
    today = date.today()
    soon = datetime.now() + timedelta(minutes=5)
    (DATA / "items.txt").write_text(
        "장보기\n"
        f"회의 자료 @{today + timedelta(days=2):%Y-%m-%d} 10:00 -10m\n"
        f"곧 시작 @{soon:%Y-%m-%d %H:%M} -10m\n")

    prov = Gtk.CssProvider()
    prov.load_from_data(rw.CSS)
    Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), prov, Gtk.STYLE_PROVIDER_PRIORITY_USER)
    win = rw.Widget()
    win.move(100, 100)
    win.show_all()
    pump(0.8)

    check("starts with 3 items", len(win.items) == 3)
    check("timed item shows its due label", find(win.card, Gtk.Label, "⏰ " + rw.due_label(
        datetime.combine(today + timedelta(days=2), datetime.min.time()).replace(hour=10), True)))

    # Alert fires lead minutes before the due time (5 min away, 10 min lead -> now).
    win.tick()
    check("10-minute-early alert fires", notified == ["곧 시작"])

    # Add with + and Enter.
    click(win.plus_btn)
    check("+ opens an entry", win.adding and find(win.card, Gtk.Entry))
    type_text("buy milk")
    xdo("key", "ctrl+Return")
    check("Enter adds the item", "buy milk" in win.items and "buy milk" in rw.load())

    # Esc cancels an add.
    click(win.plus_btn)
    type_text("cancel me")
    xdo("key", "Escape")
    check("Esc cancels the add", not win.adding and "cancel me" not in win.items)

    # Enter on the widget opens an entry; Enter saves and opens the next one; Ctrl+Enter saves and stops.
    xdo("mousemove", *center(win.card))
    xdo("key", "Return")
    check("Enter on the widget opens a new entry", win.adding)
    type_text("first")
    xdo("key", "Return")
    check("Enter saves and opens the next entry", "first" in win.items and win.adding)
    type_text("second")
    xdo("key", "ctrl+Return")
    check("Ctrl+Enter saves and closes", "second" in win.items and not win.adding)

    # "@" opens the calendar; pick a date, a time chip, a lead chip, confirm.
    click(win.plus_btn)
    type_text("team sync ")
    type_text("@")
    pump(0.4)
    p = picker()
    check("@ opens the calendar", p is not None)
    target = today + timedelta(days=3)
    if target.month != today.month:
        click(find(p.box, Gtk.Button, "›"))
    day_btn = next(w for w in walk(p.box) if isinstance(w, Gtk.Button) and w.get_label() == str(target.day)
                   and w.get_style_context().has_class("day") and not w.get_style_context().has_class("other"))
    click(day_btn)
    check("clicking a day opens the time step", p.day == target)
    click(find(p.box, Gtk.Button, "15:00"))
    click(find(p.box, Gtk.Button, "30분 전"))
    check("lead chip is selected", p.lead == 30)
    click(find(p.box, Gtk.Button, "확인"))
    pump(0.3)
    entry = find(win.card, Gtk.Entry)
    check("entry keeps only the title (no @)", entry.get_text() == "team sync")
    check("date pill shows date, time and lead",
          win.hint.get_text() == f"⏰ {rw.due_label(datetime.combine(target, datetime.min.time()).replace(hour=15), True)} · 30분 전 알림")
    xdo("mousemove", *center(entry))
    xdo("key", "ctrl+Return")
    stored = f"team sync @{target:%Y-%m-%d} 15:00 -30m"
    check("dated item is saved", stored in rw.load())

    # Click the text to edit, change it, save.
    click(find(win.card, Gtk.Label, "장보기"))
    entry = find(win.card, Gtk.Entry)
    check("clicking text opens edit", entry.get_text() == "장보기")
    xdo("key", "ctrl+a")
    type_text("groceries 2")
    xdo("key", "Return")
    check("edit replaces the item", "groceries 2" in win.items and "장보기" not in win.items)

    # Check -> fade out -> moves to done list.
    click(row_check(win, "groceries 2"))
    pump(2.2)
    check("checked item leaves the list", "groceries 2" not in win.items)
    check("checked item is in done.txt", rw.load(rw.DONE)[:1] == ["groceries 2"])
    check("animation finished", not win.fading)

    # Several checks in a row do not wait for each other's animation.
    for name in ("multi a", "multi b", "multi c"):
        win.items.append(name)
    rw.save(win.items)
    win.render()
    pump(0.3)
    for name in ("multi a", "multi b", "multi c"):
        click(row_check(win, name))
    check("rapid checks are all accepted", {"multi a", "multi b", "multi c"} <= win.fading | set(win.done))
    pump(2.2)
    check("all rapid checks end in done", {"multi a", "multi b", "multi c"} <= set(win.done)
          and not win.fading and not {"multi a", "multi b", "multi c"} & set(win.items))

    # Trash view and restore.
    click(win.done_tab)
    check("완료 tab opens the done list", win.view == "done")
    click(row_check(win, "groceries 2"))
    pump(2.2)
    check("restore puts it back", "groceries 2" in win.items and "groceries 2" not in win.done)

    # Clear done list needs two clicks.
    click(win.todo_tab)
    check("할 일 tab returns to the list", win.view == "todo")
    click(row_check(win, "buy milk"))
    pump(2.2)
    click(win.done_tab)
    click(win.trash_btn)
    check("first bin click only turns it red", win.confirm_clear
          and win.trash_btn.get_style_context().has_class("armed") and "buy milk" in win.done)
    click(win.trash_btn)
    check("second bin click empties", win.done == [] and rw.load(rw.DONE) == [])
    click(win.todo_tab)
    check("할 일 tab returns after clearing", win.view == "todo")

    # Drag handle and Ctrl-resize reach the window manager calls.
    calls = []
    win.begin_move_drag = lambda *a: calls.append("move")
    win.begin_resize_drag = lambda edge, *a: calls.append(edge)
    head = win.card.get_children()[0]  # header row; drag on its empty middle
    hx, hy = center(head)
    xdo("mousemove", hx + 20, hy)
    xdo("click", 1)
    xdo("keydown", "ctrl")
    xdo("click", 1)
    xdo("keyup", "ctrl")
    check("header drag starts a move", calls[:1] == ["move"])
    tx, ty = center(win.todo_tab)
    xdo("mousemove", tx, ty - win.todo_tab.get_allocated_height() // 2 - 8)
    xdo("click", 1)
    check("press above the tabs also moves", calls[-1] == "move")
    tab_view = win.view
    click(win.done_tab)
    check("tabs still switch instead of moving", calls[-1] == "move" and win.view != tab_view)
    click(win.todo_tab)
    calls.clear()
    xdo("mousemove", hx + 20, hy)
    xdo("click", 1)
    xdo("keydown", "ctrl")
    xdo("click", 1)
    xdo("keyup", "ctrl")
    check("Ctrl+drag resizes only sideways",
          len(calls) == 2 and calls[1] in (Gdk.WindowEdge.EAST, Gdk.WindowEdge.WEST))
    rx, ry = center(row_check(win, "groceries 2"))
    calls.clear()
    xdo("mousemove", rx + 150, ry)
    xdo("click", 1)
    check("press below the list line does not move", "move" not in calls)

    # Height follows the number of items; a widened width is kept.
    win.user_width = 420
    win.render()
    pump(0.3)
    w1, h1 = win.get_size()
    click(win.plus_btn)
    type_text("one more")
    xdo("key", "Return")
    pump(0.3)
    w2, h2 = win.get_size()
    check("adding an item makes the widget taller", h2 > h1)
    check("chosen width is kept", w1 == w2 == 420)

    # Top-bar menu: "항상 위" toggles and is remembered; "종료" is there.
    if win.indicator:
        items = win.indicator.get_menu().get_children()
        check("top-bar menu has 항상 위, 사용법 and 종료",
              [i.get_label() for i in items if i.get_label()] == ["항상 위", "사용법", "종료"])
        items[0].set_active(True)
        check("항상 위 on is saved", win.on_top and (DATA / "on-top").exists())
        items[0].set_active(False)
        check("항상 위 off is saved", not win.on_top and not (DATA / "on-top").exists())

    failed = [n for n, ok in results if not ok]
    print(f"\n{len(results) - len(failed)}/{len(results)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
