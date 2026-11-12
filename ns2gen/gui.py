"""Tkinter GUI for ns2gen. Standard library only."""
from __future__ import annotations

import json
import os
import queue
import shutil
import subprocess
import tempfile
import threading
import tkinter as tk
import tkinter.font as tkfont
from tkinter import filedialog, messagebox, ttk

from . import __version__
from .geometry import Viewport, dist_point_segment, nice_step, offset_segment, trim_segment
from .history import History
from .model import (
    ANTENNAS, CHANNELS, IFQ_TYPES, LL_TYPES, MAC_TYPES, PHY_TYPES, PROP_MODELS,
    QUEUE_TYPES, ROUTING, TCP_VARIANTS, Flow, Link, Movement, Scene,
)
from .tclgen import NAM_COLORS, generate, validate

NODE_R = 15
FLOW_OFFSET = 14
HIT_PX = 6
TOOLS = [
    ("select", "Select / Move"),
    ("node", "Add Node"),
    ("link", "Add Link"),
    ("tcp", "TCP Flow (FTP)"),
    ("udp", "UDP Flow (CBR)"),
    ("delete", "Delete"),
]
TOOL_HINTS = {
    "select": "Click to select, drag nodes to move. Delete key removes selection.",
    "node": "Click on the canvas to add a node.",
    "link": "Click two nodes to connect them.",
    "tcp": "Click source node, then destination node.",
    "udp": "Click source node, then destination node.",
    "delete": "Click a node, link or flow to delete it.",
}
TOOL_CURSORS = {"select": "arrow", "node": "crosshair", "link": "crosshair",
                "tcp": "crosshair", "udp": "crosshair", "delete": "X_cursor"}
DEFAULT_SIZE = {"wired": (800.0, 600.0), "wireless": (500.0, 500.0)}


# ---------------------------------------------------------------------------
# generic modal form dialog
# ---------------------------------------------------------------------------
class FormDialog(tk.Toplevel):
    def __init__(self, parent, title, fields, validator=None):
        super().__init__(parent)
        self.title(title)
        self.transient(parent)
        self.resizable(False, False)
        self.result = None
        self.vars = {}
        self.validator = validator
        body = ttk.Frame(self, padding=12)
        body.pack()
        for r, (key, label, kind, default, values) in enumerate(fields):
            ttk.Label(body, text=label).grid(row=r, column=0, sticky="w", pady=3, padx=(0, 8))
            if kind == "combo":
                var = tk.StringVar(value=str(default))
                w = ttk.Combobox(body, textvariable=var, values=values, state="readonly", width=30)
            elif kind == "check":
                var = tk.BooleanVar(value=bool(default))
                w = ttk.Checkbutton(body, variable=var)
            else:
                var = tk.StringVar(value=str(default))
                w = ttk.Entry(body, textvariable=var, width=32)
            w.grid(row=r, column=1, sticky="ew", pady=3)
            self.vars[key] = var
        btns = ttk.Frame(self, padding=(12, 0, 12, 12))
        btns.pack(fill="x")
        ttk.Button(btns, text="Cancel", command=self.destroy).pack(side="right", padx=4)
        ttk.Button(btns, text="OK", command=self.ok).pack(side="right")
        self.bind("<Return>", lambda e: self.ok())
        self.bind("<Escape>", lambda e: self.destroy())
        self.wait_visibility()
        self.grab_set()

    def ok(self):
        values = {k: v.get() for k, v in self.vars.items()}
        if self.validator:
            err = self.validator(values)
            if err:
                messagebox.showerror("Invalid value", err, parent=self)
                return
        self.result = values
        self.destroy()


def ask_form(parent, title, fields, validator=None):
    dlg = FormDialog(parent, title, fields, validator)
    parent.wait_window(dlg)
    return dlg.result


def fmt(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float):
        return f"{v:g}"
    return str(v)


# ---------------------------------------------------------------------------
# main window
# ---------------------------------------------------------------------------
class App(tk.Tk):
    def __init__(self, path=None):
        super().__init__()
        self.geometry("1280x760")
        self.minsize(900, 560)
        try:
            ttk.Style().theme_use("clam")
        except tk.TclError:
            pass
        self.font_bold = tkfont.nametofont("TkDefaultFont").copy()
        self.font_bold.configure(weight="bold")

        self.scene = Scene()
        self.path = None
        self.dirty = False
        self.history = History()
        self.tool = tk.StringVar(value="select")
        self.sel = None            # ("node"|"link"|"flow", object)
        self.pending = None        # first node id of a two-click tool
        self.drag_node = None
        self._drag_snap = None
        self.vp = None
        self.hit_links = []
        self.hit_flows = []
        self.prop_refresh = []

        self._build_menu()
        self._build_ui()
        self._bind_keys()
        self.protocol("WM_DELETE_WINDOW", self.quit_app)
        if path:
            self.open_path(path)
        self.refresh_all()

    # ------------------------------------------------------------------ UI
    def _build_menu(self):
        m = tk.Menu(self)
        f = tk.Menu(m, tearoff=0)
        f.add_command(label="New", accelerator="Ctrl+N", command=self.new)
        f.add_command(label="Open...", accelerator="Ctrl+O", command=self.open)
        f.add_command(label="Save", accelerator="Ctrl+S", command=self.save)
        f.add_command(label="Save As...", command=self.save_as)
        f.add_separator()
        f.add_command(label="Export TCL...", accelerator="Ctrl+E", command=self.export_tcl)
        f.add_separator()
        f.add_command(label="Quit", accelerator="Ctrl+Q", command=self.quit_app)
        m.add_cascade(label="File", menu=f)
        e = tk.Menu(m, tearoff=0)
        e.add_command(label="Undo", accelerator="Ctrl+Z", command=self.undo)
        e.add_command(label="Redo", accelerator="Ctrl+Y", command=self.redo)
        e.add_separator()
        e.add_command(label="Delete selection", accelerator="Del", command=self.delete_selection)
        m.add_cascade(label="Edit", menu=e)
        s = tk.Menu(m, tearoff=0)
        s.add_command(label="Simulation settings...", accelerator="Ctrl+,", command=self.edit_settings)
        s.add_command(label="Run with ns2", accelerator="Ctrl+R", command=self.run_ns)
        m.add_cascade(label="Simulation", menu=s)
        h = tk.Menu(m, tearoff=0)
        h.add_command(label="About", command=self.about)
        m.add_cascade(label="Help", menu=h)
        self.config(menu=m)

    def _build_ui(self):
        self.status = ttk.Label(self, anchor="w", padding=(8, 3), relief="sunken")
        self.status.pack(side="bottom", fill="x")

        root = ttk.Frame(self)
        root.pack(fill="both", expand=True)

        tb = ttk.Frame(root, padding=6)
        tb.pack(side="left", fill="y")
        ttk.Label(tb, text="Tools", font=self.font_bold).pack(anchor="w", pady=(0, 4))
        self.tool_buttons = {}
        for key, text in TOOLS:
            rb = ttk.Radiobutton(tb, text=text, value=key, variable=self.tool,
                                 command=self.on_tool_change, style="Toolbutton")
            rb.pack(fill="x", pady=2, ipadx=4, ipady=3)
            self.tool_buttons[key] = rb
        ttk.Separator(tb).pack(fill="x", pady=8)
        ttk.Button(tb, text="Settings...", command=self.edit_settings).pack(fill="x", pady=2)
        ttk.Button(tb, text="Export TCL...", command=self.export_tcl).pack(fill="x", pady=2)
        ttk.Button(tb, text="Run with ns2", command=self.run_ns).pack(fill="x", pady=2)

        pw = ttk.PanedWindow(root, orient="horizontal")
        pw.pack(side="left", fill="both", expand=True)

        self.canvas = tk.Canvas(pw, bg="white", highlightthickness=0)
        pw.add(self.canvas, weight=3)

        side = ttk.PanedWindow(pw, orient="vertical")
        pw.add(side, weight=2)
        self.props_frame = ttk.LabelFrame(side, text="Properties", padding=4)
        side.add(self.props_frame, weight=1)
        prev = ttk.LabelFrame(side, text="TCL preview", padding=4)
        side.add(prev, weight=2)

        bar = ttk.Frame(prev)
        bar.pack(side="bottom", fill="x", pady=(4, 0))
        ttk.Button(bar, text="Copy TCL", command=self.copy_tcl).pack(side="right")
        self.preview = tk.Text(prev, wrap="none", width=44, height=14, font="TkFixedFont",
                               state="disabled", background="#f6f6f6")
        ys = ttk.Scrollbar(prev, orient="vertical", command=self.preview.yview)
        xs = ttk.Scrollbar(prev, orient="horizontal", command=self.preview.xview)
        self.preview.configure(yscrollcommand=ys.set, xscrollcommand=xs.set)
        xs.pack(side="bottom", fill="x")
        ys.pack(side="right", fill="y")
        self.preview.pack(side="left", fill="both", expand=True)

        c = self.canvas
        c.bind("<Configure>", lambda e: self.redraw())
        c.bind("<Button-1>", self.on_press)
        c.bind("<B1-Motion>", self.on_drag)
        c.bind("<ButtonRelease-1>", self.on_release)
        c.bind("<Motion>", self.on_motion)
        c.bind("<Delete>", lambda e: self.delete_selection())
        c.bind("<BackSpace>", lambda e: self.delete_selection())
        c.bind("<Escape>", lambda e: self.cancel_pending())

    def _bind_keys(self):
        for seq, fn in (
            ("<Control-n>", self.new), ("<Control-o>", self.open), ("<Control-s>", self.save),
            ("<Control-e>", self.export_tcl), ("<Control-q>", self.quit_app),
            ("<Control-z>", self.undo), ("<Control-y>", self.redo),
            ("<Control-r>", self.run_ns), ("<Control-comma>", self.edit_settings),
        ):
            self.bind(seq, lambda e, fn=fn: fn())

    # ----------------------------------------------------------- state mgmt
    def snapshot(self) -> str:
        return json.dumps(self.scene.to_dict())

    def restore(self, snap: str):
        self.scene = Scene.from_dict(json.loads(snap))
        self.sel = None
        self.pending = None
        self.dirty = True
        self.refresh_all()

    def undo(self):
        snap = self.history.undo(self.snapshot())
        if snap:
            self.restore(snap)

    def redo(self):
        snap = self.history.redo(self.snapshot())
        if snap:
            self.restore(snap)

    def push(self):
        self.history.push(self.snapshot())

    def changed(self):
        self.dirty = True
        self.update_title()
        self.redraw()
        self.refresh_preview()
        self.sync_props()

    def refresh_all(self):
        self.update_title()
        self.update_tools()
        self.redraw()
        self.refresh_preview()
        self.build_props()

    def update_title(self):
        name = os.path.basename(self.path) if self.path else "Untitled"
        self.title(f"{'*' if self.dirty else ''}{name} - ns2gen")

    def update_tools(self):
        wireless = self.scene.settings.mode == "wireless"
        btn = self.tool_buttons["link"]
        btn.state(["disabled"] if wireless else ["!disabled"])
        if wireless and self.tool.get() == "link":
            self.tool.set("select")
        self.on_tool_change()

    def status_msg(self, text: str):
        self.status.configure(text=text)

    def on_tool_change(self):
        self.pending = None
        t = self.tool.get()
        self.canvas.configure(cursor=TOOL_CURSORS.get(t, "arrow"))
        self.status_msg(TOOL_HINTS.get(t, ""))
        self.redraw()

    def cancel_pending(self):
        self.pending = None
        self.canvas.delete("rubber")
        self.redraw()

    def set_sel(self, sel):
        self.sel = sel
        self.redraw()
        self.after_idle(self.build_props)

    # -------------------------------------------------------------- drawing
    def redraw(self):
        c = self.canvas
        c.delete("all")
        w, h = c.winfo_width(), c.winfo_height()
        sc = self.scene
        s = sc.settings
        self.vp = vp = Viewport(s.width, s.height, max(w, 100), max(h, 100))
        x0, y0 = vp.to_canvas(0, s.height)
        x1, y1 = vp.to_canvas(s.width, 0)
        c.create_rectangle(x0, y0, x1, y1, outline="#bbbbbb", fill="#fafafa")
        step = nice_step(vp.scale)
        gx = step
        while gx < s.width:
            px, _ = vp.to_canvas(gx, 0)
            c.create_line(px, y0, px, y1, fill="#eeeeee")
            gx += step
        gy = step
        while gy < s.height:
            _, py = vp.to_canvas(0, gy)
            c.create_line(x0, py, x1, py, fill="#eeeeee")
            gy += step
        c.create_text(x1 - 4, y1 + 12, anchor="e", fill="#888888",
                      text=f"{s.width:g} x {s.height:g}  (grid {step:g})")

        self.hit_links = []
        self.hit_flows = []
        wired = s.mode == "wired"
        pos = {n.id: vp.to_canvas(n.x, n.y) for n in sc.nodes}

        if wired:
            for l in sc.links:
                if l.a not in pos or l.b not in pos:
                    continue
                ax, ay = pos[l.a]
                bx, by = pos[l.b]
                selected = self.sel is not None and self.sel[1] is l
                c.create_line(ax, ay, bx, by, width=4 if selected else 2,
                              fill="#1565c0" if selected else "#555555",
                              arrow=None if l.duplex else "last")
                c.create_text((ax + bx) / 2, (ay + by) / 2 - 10,
                              text=f"{l.bandwidth}, {l.delay}", fill="#333333")
                self.hit_links.append((l, (ax, ay, bx, by)))
        else:
            for n in sc.nodes:
                pts = [pos[n.id]]
                for m in sorted((m for m in sc.movements if m.node == n.id), key=lambda m: m.time):
                    pts.append(vp.to_canvas(m.x, m.y))
                    mx, my = pts[-1]
                    c.create_rectangle(mx - 3, my - 3, mx + 3, my + 3, outline="#888888")
                    c.create_text(mx + 6, my - 8, anchor="w", fill="#888888",
                                  text=f"t={m.time:g}s v={m.speed:g}")
                if len(pts) > 1:
                    flat = [v for p in pts for v in p]
                    c.create_line(*flat, dash=(2, 3), fill="#999999", arrow="last")

        counts = {}
        for i, f in enumerate(sc.flows):
            if f.src not in pos or f.dst not in pos:
                continue
            key = (f.src, f.dst)
            j = counts.get(key, 0)
            counts[key] = j + 1
            d = (FLOW_OFFSET if wired else 0) + j * 8
            ax, ay = pos[f.src]
            bx, by = pos[f.dst]
            seg = trim_segment(*offset_segment(ax, ay, bx, by, d), NODE_R)
            selected = self.sel is not None and self.sel[1] is f
            color = NAM_COLORS[i % len(NAM_COLORS)].lower()
            c.create_line(*seg, dash=(6, 3), width=3 if selected else 2, fill=color, arrow="last")
            c.create_text((seg[0] + seg[2]) / 2, (seg[1] + seg[3]) / 2 - 8, fill=color,
                          text=f"{f.proto}/{f.app}")
            self.hit_flows.append((f, seg))

        for n in sc.nodes:
            cx, cy = pos[n.id]
            selected = self.sel is not None and self.sel[1] is n
            fill = "#ffe082" if self.pending == n.id else "#e3f2fd"
            c.create_oval(cx - NODE_R, cy - NODE_R, cx + NODE_R, cy + NODE_R, fill=fill,
                          outline="#1565c0" if selected else "#333333", width=3 if selected else 1)
            c.create_text(cx, cy, text=str(n.id), font=self.font_bold)
            if n.label:
                c.create_text(cx, cy + NODE_R + 9, text=n.label)

    def hit(self, cx, cy):
        for n in reversed(self.scene.nodes):
            px, py = self.vp.to_canvas(n.x, n.y)
            if (px - cx) ** 2 + (py - cy) ** 2 <= (NODE_R + 2) ** 2:
                return ("node", n)
        for f, seg in self.hit_flows:
            if dist_point_segment(cx, cy, *seg) <= HIT_PX:
                return ("flow", f)
        for l, seg in self.hit_links:
            if dist_point_segment(cx, cy, *seg) <= HIT_PX:
                return ("link", l)
        return None

    # ------------------------------------------------------------- mouse
    def on_press(self, e):
        self.canvas.focus_set()
        if self.vp is None:
            return
        hit = self.hit(e.x, e.y)
        t = self.tool.get()
        if t == "select":
            self.set_sel(hit)
            if hit and hit[0] == "node":
                self.drag_node = hit[1]
                self._drag_snap = self.snapshot()
        elif t == "node":
            if hit and hit[0] == "node":
                self.set_sel(hit)
                return
            x, y = self.vp.clamp(*self.vp.to_world(e.x, e.y))
            self.push()
            n = self.scene.add_node(float(round(x)), float(round(y)))
            self.sel = ("node", n)
            self.changed()
            self.after_idle(self.build_props)
        elif t == "link":
            self.two_click(hit, self.make_link)
        elif t in ("tcp", "udp"):
            self.two_click(hit, lambda a, b: self.make_flow(a, b, t))
        elif t == "delete":
            if hit:
                self.delete_object(hit)

    def on_drag(self, e):
        if self.drag_node is None or self.vp is None:
            return
        if self._drag_snap is not None:
            self.history.push(self._drag_snap)
            self._drag_snap = None
        x, y = self.vp.clamp(*self.vp.to_world(e.x, e.y))
        self.drag_node.x, self.drag_node.y = float(round(x)), float(round(y))
        self.changed()

    def on_release(self, e):
        self.drag_node = None
        self._drag_snap = None

    def on_motion(self, e):
        self.canvas.delete("rubber")
        if self.pending is None or self.vp is None:
            return
        n = self.scene.node_by_id(self.pending)
        if n is None:
            return
        ax, ay = self.vp.to_canvas(n.x, n.y)
        self.canvas.create_line(ax, ay, e.x, e.y, dash=(3, 3), fill="#888888", tags="rubber")

    def two_click(self, hit, action):
        if not hit or hit[0] != "node":
            self.cancel_pending()
            return
        n = hit[1]
        if self.pending is None:
            self.pending = n.id
            self.status_msg("Now click the second node (Esc to cancel).")
            self.redraw()
        elif self.pending == n.id:
            self.cancel_pending()
        else:
            a, self.pending = self.pending, None
            action(a, n.id)

    def make_link(self, a, b):
        existing = self.scene.find_link(a, b)
        if existing:
            self.status_msg("Those nodes are already linked.")
            self.set_sel(("link", existing))
            return
        self.push()
        l = Link(a, b)
        self.scene.links.append(l)
        self.sel = ("link", l)
        self.changed()
        self.after_idle(self.build_props)

    def make_flow(self, a, b, kind):
        st = self.scene.settings.stop_time
        start, stop = round(st * 0.2, 2), round(st * 0.8, 2)
        self.push()
        if kind == "tcp":
            f = Flow(a, b, "TCP", "TCP", "FTP", start, stop)
        else:
            f = Flow(a, b, "UDP", app="CBR", start=start, stop=stop)
        self.scene.flows.append(f)
        self.sel = ("flow", f)
        self.changed()
        self.after_idle(self.build_props)

    # ------------------------------------------------------------ deleting
    def delete_object(self, sel):
        kind, obj = sel
        self.push()
        sc = self.scene
        if kind == "node":
            sc.remove_node(obj.id)
        elif kind == "link":
            sc.links = [l for l in sc.links if l is not obj]
        elif kind == "flow":
            sc.flows = [f for f in sc.flows if f is not obj]
        if self.sel is not None and (self.sel[1] is obj or kind == "node"):
            self.sel = None
        self.changed()
        self.after_idle(self.build_props)

    def delete_selection(self):
        if self.sel:
            self.delete_object(self.sel)

    # -------------------------------------------------- properties panel
    def sync_props(self):
        for fn in self.prop_refresh:
            fn()

    def build_props(self):
        for w in self.props_frame.winfo_children():
            w.destroy()
        self.prop_refresh = []
        if not self.sel:
            ttk.Label(self.props_frame, wraplength=300, justify="left",
                      text="Nothing selected.\nUse the tools on the left to add nodes, links "
                           "and flows, then select an item to edit it.").pack(anchor="w", padx=4, pady=4)
            return
        kind, obj = self.sel
        grid = ttk.Frame(self.props_frame)
        grid.pack(fill="x")
        grid.columnconfigure(1, weight=1)
        self.pf = grid
        row = 0
        wireless = self.scene.settings.mode == "wireless"

        if kind == "node":
            self.add_static(row, "Node", f"{obj.id}"); row += 1
            self.add_entry(row, "Label", self.getter(obj, "label"), self.setter(obj, "label", str)); row += 1
            self.add_entry(row, "X", self.getter(obj, "x"), self.setter(obj, "x", float)); row += 1
            self.add_entry(row, "Y", self.getter(obj, "y"), self.setter(obj, "y", float)); row += 1
        elif kind == "link":
            self.add_static(row, "Link", f"{obj.a} - {obj.b}"); row += 1
            self.add_entry(row, "Bandwidth", self.getter(obj, "bandwidth"), self.setter(obj, "bandwidth", str)); row += 1
            self.add_entry(row, "Delay", self.getter(obj, "delay"), self.setter(obj, "delay", str)); row += 1
            self.add_combo(row, "Queue", QUEUE_TYPES, self.getter(obj, "queue"), self.setter(obj, "queue", str)); row += 1
            self.add_entry(row, "Queue limit", self.getter(obj, "queue_limit"),
                           self.setter(obj, "queue_limit", int, allow_empty=True)); row += 1
            self.add_check(row, "Duplex", obj, "duplex"); row += 1
        elif kind == "flow":
            self.add_static(row, "Flow", f"{obj.src} -> {obj.dst}"); row += 1
            self.add_static(row, "Type", f"{obj.proto} / {obj.app}"); row += 1
            if obj.proto == "TCP":
                self.add_combo(row, "TCP variant", TCP_VARIANTS, self.getter(obj, "tcp_variant"),
                               self.setter(obj, "tcp_variant", str)); row += 1
                self.add_entry(row, "Window", self.getter(obj, "window"),
                               self.setter(obj, "window", int, allow_empty=True)); row += 1
            else:
                self.add_entry(row, "Packet size", self.getter(obj, "packet_size"),
                               self.setter(obj, "packet_size", int)); row += 1
                self.add_entry(row, "Rate", self.getter(obj, "rate"), self.setter(obj, "rate", str)); row += 1
            self.add_entry(row, "Start (s)", self.getter(obj, "start"), self.setter(obj, "start", float)); row += 1
            self.add_entry(row, "Stop (s)", self.getter(obj, "stop"), self.setter(obj, "stop", float)); row += 1

        if kind == "node" and wireless:
            self.build_movements(obj)
        ttk.Button(self.props_frame, text="Delete", command=self.delete_selection).pack(anchor="e", pady=(8, 0))

    def build_movements(self, node):
        box = ttk.LabelFrame(self.props_frame, text="Movements", padding=4)
        box.pack(fill="both", expand=True, pady=(8, 0))
        cols = ("time", "x", "y", "speed")
        tv = ttk.Treeview(box, columns=cols, show="headings", height=4)
        for col in cols:
            tv.heading(col, text=col)
            tv.column(col, width=60, anchor="center")
        tv.pack(fill="both", expand=True)

        def fill():
            tv.delete(*tv.get_children())
            for i, m in enumerate(self.scene.movements):
                if m.node == node.id:
                    tv.insert("", "end", iid=str(i), values=(fmt(m.time), fmt(m.x), fmt(m.y), fmt(m.speed)))

        def add():
            last = max((m.time for m in self.scene.movements if m.node == node.id), default=0.0)
            fields = [("time", "Time (s)", "entry", fmt(last + 1.0), None),
                      ("x", "Target X", "entry", fmt(node.x), None),
                      ("y", "Target Y", "entry", fmt(node.y), None),
                      ("speed", "Speed (m/s)", "entry", "5", None)]

            def check(v):
                try:
                    [float(v[k]) for k in ("time", "x", "y", "speed")]
                except ValueError:
                    return "All values must be numbers."
                return None

            r = ask_form(self, "Add movement", fields, check)
            if r:
                self.push()
                self.scene.movements.append(Movement(node.id, float(r["time"]), float(r["x"]),
                                                     float(r["y"]), float(r["speed"])))
                self.changed()
                fill()

        def remove():
            picked = tv.selection()
            if not picked:
                return
            self.push()
            drop = {int(i) for i in picked}
            self.scene.movements = [m for i, m in enumerate(self.scene.movements) if i not in drop]
            self.changed()
            fill()

        bar = ttk.Frame(box)
        bar.pack(fill="x", pady=(4, 0))
        ttk.Button(bar, text="Add...", command=add).pack(side="left")
        ttk.Button(bar, text="Remove", command=remove).pack(side="left", padx=4)
        fill()

    # field helpers -------------------------------------------------------
    def getter(self, obj, name):
        return lambda: fmt(getattr(obj, name))

    def setter(self, obj, name, conv, allow_empty=False):
        def set_(text):
            text = text.strip()
            try:
                val = None if (allow_empty and text == "") else conv(text)
            except ValueError:
                self.status_msg(f"Bad value for {name}: '{text}'")
                return False
            if getattr(obj, name) == val:
                return True
            self.push()
            setattr(obj, name, val)
            self.changed()
            return True
        return set_

    def add_static(self, row, label, text):
        ttk.Label(self.pf, text=label).grid(row=row, column=0, sticky="w", padx=4, pady=2)
        ttk.Label(self.pf, text=text, font=self.font_bold).grid(row=row, column=1, sticky="w", padx=4, pady=2)

    def add_entry(self, row, label, get, set_):
        ttk.Label(self.pf, text=label).grid(row=row, column=0, sticky="w", padx=4, pady=2)
        var = tk.StringVar(value=get())
        ent = ttk.Entry(self.pf, textvariable=var, width=16)
        ent.grid(row=row, column=1, sticky="ew", padx=4, pady=2)

        def commit(_e=None):
            if var.get() == get():
                return
            if not set_(var.get()):
                var.set(get())

        ent.bind("<Return>", commit)
        ent.bind("<FocusOut>", commit)
        self.prop_refresh.append(lambda: var.set(get()))

    def add_combo(self, row, label, values, get, set_):
        ttk.Label(self.pf, text=label).grid(row=row, column=0, sticky="w", padx=4, pady=2)
        var = tk.StringVar(value=get())
        cb = ttk.Combobox(self.pf, textvariable=var, values=values, state="readonly", width=16)
        cb.grid(row=row, column=1, sticky="ew", padx=4, pady=2)
        cb.bind("<<ComboboxSelected>>", lambda e: set_(var.get()))
        self.prop_refresh.append(lambda: var.set(get()))

    def add_check(self, row, label, obj, name):
        var = tk.BooleanVar(value=bool(getattr(obj, name)))

        def toggle():
            self.push()
            setattr(obj, name, bool(var.get()))
            self.changed()

        ttk.Checkbutton(self.pf, text=label, variable=var, command=toggle).grid(
            row=row, column=0, columnspan=2, sticky="w", padx=4, pady=2)

    # ------------------------------------------------------------ preview
    def refresh_preview(self):
        sc = self.scene
        errs = validate(sc)
        if errs:
            text = "# Cannot generate TCL yet. Fix these first:\n" + "\n".join(f"#  - {e}" for e in errs) + "\n"
        else:
            text = generate(sc)
        top = self.preview.yview()[0]
        self.preview.configure(state="normal")
        self.preview.delete("1.0", "end")
        self.preview.insert("1.0", text)
        self.preview.configure(state="disabled")
        self.preview.yview_moveto(top)
        summary = (f"{sc.settings.mode}  |  {len(sc.nodes)} nodes, {len(sc.links)} links, "
                   f"{len(sc.flows)} flows")
        if errs:
            summary += f"  |  {len(errs)} problem(s)"
        self.status_msg(summary)

    def copy_tcl(self):
        errs = validate(self.scene)
        if errs:
            messagebox.showerror("Cannot copy", "\n".join(errs), parent=self)
            return
        self.clipboard_clear()
        self.clipboard_append(generate(self.scene))
        self.status_msg("TCL copied to clipboard.")

    # ------------------------------------------------------------ settings
    def edit_settings(self):
        s = self.scene.settings
        fields = [
            ("mode", "Mode", "combo", s.mode, ["wired", "wireless"]),
            ("stop_time", "Stop time (s)", "entry", fmt(s.stop_time), None),
            ("trace_file", "Trace file", "entry", s.trace_file, None),
            ("nam_file", "NAM file", "entry", s.nam_file, None),
            ("run_nam", "Open NAM when done", "check", s.run_nam, None),
            ("width", "Topology width", "entry", fmt(s.width), None),
            ("height", "Topology height", "entry", fmt(s.height), None),
            ("routing", "Routing (wireless)", "combo", s.routing, ROUTING),
            ("mac", "MAC (wireless)", "combo", s.mac, MAC_TYPES),
            ("prop", "Propagation (wireless)", "combo", s.prop, PROP_MODELS),
            ("ifq", "Interface queue (wireless)", "combo", s.ifq, IFQ_TYPES),
            ("ifq_len", "Queue length (wireless)", "entry", fmt(s.ifq_len), None),
            ("antenna", "Antenna (wireless)", "combo", s.antenna, ANTENNAS),
            ("phy", "Phy (wireless)", "combo", s.phy, PHY_TYPES),
            ("channel", "Channel (wireless)", "combo", s.channel, CHANNELS),
            ("ll", "Link layer (wireless)", "combo", s.ll, LL_TYPES),
        ]

        def check(v):
            try:
                if float(v["stop_time"]) <= 0 or float(v["width"]) <= 0 or float(v["height"]) <= 0:
                    return "Stop time and topology size must be > 0."
                int(v["ifq_len"])
            except ValueError:
                return "Stop time, size and queue length must be numbers."
            return None

        r = ask_form(self, "Simulation settings", fields, check)
        if not r:
            return
        self.push()
        old_w, old_h, old_mode = s.width, s.height, s.mode
        s.mode = r["mode"]
        s.stop_time = float(r["stop_time"])
        s.trace_file, s.nam_file = r["trace_file"].strip(), r["nam_file"].strip()
        s.run_nam = bool(r["run_nam"])
        s.width, s.height = float(r["width"]), float(r["height"])
        if s.mode != old_mode and (s.width, s.height) == (old_w, old_h):
            s.width, s.height = DEFAULT_SIZE[s.mode]
        s.routing, s.mac, s.prop, s.ifq = r["routing"], r["mac"], r["prop"], r["ifq"]
        s.ifq_len = int(r["ifq_len"])
        s.antenna, s.phy, s.channel, s.ll = r["antenna"], r["phy"], r["channel"], r["ll"]
        rx, ry = s.width / old_w, s.height / old_h
        if rx != 1 or ry != 1:
            for n in self.scene.nodes:
                n.x, n.y = round(n.x * rx, 2), round(n.y * ry, 2)
            for m in self.scene.movements:
                m.x, m.y = round(m.x * rx, 2), round(m.y * ry, 2)
        self.sel = None
        self.dirty = True
        self.refresh_all()

    # --------------------------------------------------------------- files
    def confirm_discard(self) -> bool:
        if not self.dirty:
            return True
        ans = messagebox.askyesnocancel("Unsaved changes", "Save changes first?", parent=self)
        if ans is None:
            return False
        if ans:
            return self.save()
        return True

    def new(self):
        if not self.confirm_discard():
            return
        self.scene = Scene()
        self.path = None
        self.dirty = False
        self.sel = None
        self.history.clear()
        self.refresh_all()

    def open(self):
        if not self.confirm_discard():
            return
        p = filedialog.askopenfilename(parent=self, filetypes=[("ns2gen scene", "*.json"), ("All files", "*.*")])
        if p:
            self.open_path(p)

    def open_path(self, p):
        try:
            self.scene = Scene.load(p)
        except (OSError, ValueError, KeyError, TypeError) as e:
            messagebox.showerror("Cannot open", f"{p}\n\n{e}", parent=self)
            return
        self.path = p
        self.dirty = False
        self.sel = None
        self.history.clear()
        self.refresh_all()

    def save(self) -> bool:
        if not self.path:
            return self.save_as()
        try:
            self.scene.save(self.path)
        except OSError as e:
            messagebox.showerror("Cannot save", str(e), parent=self)
            return False
        self.dirty = False
        self.update_title()
        return True

    def save_as(self) -> bool:
        p = filedialog.asksaveasfilename(parent=self, defaultextension=".json",
                                         filetypes=[("ns2gen scene", "*.json")])
        if not p:
            return False
        self.path = p
        return self.save()

    def export_tcl(self):
        errs = validate(self.scene)
        if errs:
            messagebox.showerror("Cannot export", "Fix these first:\n\n" + "\n".join(errs), parent=self)
            return
        base = os.path.splitext(os.path.basename(self.path))[0] if self.path else "scenario"
        p = filedialog.asksaveasfilename(parent=self, defaultextension=".tcl", initialfile=base + ".tcl",
                                         filetypes=[("TCL script", "*.tcl")])
        if not p:
            return
        try:
            with open(p, "w", encoding="utf-8") as fh:
                fh.write(generate(self.scene))
        except OSError as e:
            messagebox.showerror("Cannot export", str(e), parent=self)
            return
        self.status_msg(f"Exported {p}. Run with: ns {os.path.basename(p)}")

    def quit_app(self):
        if self.confirm_discard():
            self.destroy()

    # ------------------------------------------------------------- run ns2
    def run_ns(self):
        errs = validate(self.scene)
        if errs:
            messagebox.showerror("Cannot run", "Fix these first:\n\n" + "\n".join(errs), parent=self)
            return
        exe = shutil.which("ns")
        if not exe:
            messagebox.showinfo(
                "ns2 not found",
                "The 'ns' program is not in PATH.\nInstall ns2 (and nam) from your distro or build it "
                "from source, then try again.\nYou can still use File > Export TCL.", parent=self)
            return
        workdir = tempfile.mkdtemp(prefix="ns2gen-")
        tcl = os.path.join(workdir, "scenario.tcl")
        with open(tcl, "w", encoding="utf-8") as fh:
            fh.write(generate(self.scene))
        win = tk.Toplevel(self)
        win.title("ns2 output")
        txt = tk.Text(win, width=90, height=24, font="TkFixedFont")
        txt.pack(fill="both", expand=True)
        txt.insert("end", f"$ ns scenario.tcl   (in {workdir})\n\nrunning...\n")
        results = queue.Queue()

        def work():
            log = os.path.join(workdir, "ns.log")
            try:
                with open(log, "w") as lf:
                    p = subprocess.run([exe, tcl], cwd=workdir, stdout=lf, stderr=subprocess.STDOUT, timeout=300)
                with open(log, "r", errors="replace") as lf:
                    results.put((p.returncode, lf.read()))
            except subprocess.TimeoutExpired:
                results.put((-1, "Timed out after 300 s."))
            except OSError as e:
                results.put((-1, str(e)))

        def poll():
            try:
                code, out = results.get_nowait()
            except queue.Empty:
                if win.winfo_exists():
                    win.after(200, poll)
                return
            if win.winfo_exists():
                txt.insert("end", f"{out}\nexit code {code}\nfiles are in {workdir}\n")
                txt.see("end")

        threading.Thread(target=work, daemon=True).start()
        win.after(200, poll)

    def about(self):
        messagebox.showinfo("About ns2gen", f"ns2gen {__version__}\nScenario generator for the ns2 simulator.\n"
                            "Draw a topology, get a TCL script.", parent=self)


def run(path=None):
    App(path).mainloop()
