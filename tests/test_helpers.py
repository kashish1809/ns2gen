import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ns2gen.geometry import Viewport, dist_point_segment, offset_segment, trim_segment, nice_step
from ns2gen.history import History

ROOT = os.path.join(os.path.dirname(__file__), "..")


def test_viewport_roundtrip_and_y_up():
    vp = Viewport(500, 400, 700, 600)
    cx, cy = vp.to_canvas(120, 300)
    x, y = vp.to_world(cx, cy)
    assert abs(x - 120) < 1e-9 and abs(y - 300) < 1e-9
    # higher world y -> smaller canvas y (up on screen)
    assert vp.to_canvas(0, 400)[1] < vp.to_canvas(0, 0)[1]
    assert vp.clamp(-5, 999) == (0.0, 400)


def test_segment_helpers():
    assert dist_point_segment(5, 3, 0, 0, 10, 0) == 3
    assert dist_point_segment(-4, 3, 0, 0, 10, 0) == 5  # beyond endpoint
    assert dist_point_segment(1, 1, 2, 2, 2, 2) > 1.4
    ax, ay, bx, by = offset_segment(0, 0, 10, 0, 5)
    assert abs(ay) == 5 and abs(by) == 5 and ax == 0 and bx == 10
    assert trim_segment(0, 0, 100, 0, 15) == (15, 0, 85, 0)
    assert trim_segment(0, 0, 10, 0, 15) == (0, 0, 10, 0)


def test_nice_step():
    assert nice_step(1.0) == 50.0
    assert nice_step(0.1) == 500.0


def test_history():
    h = History()
    assert h.undo("x") is None
    h.push("a"); h.push("b")
    assert h.undo("c") == "b"
    assert h.undo("b") == "a"
    assert h.redo("a") == "b"
    h.push("z")
    assert h.redo("q") is None  # redo cleared by new push


def test_cli_export(tmp_path):
    out = tmp_path / "o.tcl"
    ex = os.path.join(ROOT, "examples", "wired-dumbbell.json")
    r = subprocess.run([sys.executable, "-m", "ns2gen", ex, "--export", str(out)],
                       cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "$ns run" in out.read_text()


def test_cli_export_invalid(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"nodes": [{"id": 0}], "flows": [{"src": 0, "dst": 5}]}))
    r = subprocess.run([sys.executable, "-m", "ns2gen", str(bad), "--export", str(tmp_path / "o.tcl")],
                       cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 1 and "unknown node" in r.stderr
