"""Build golden files from the Python reference implementation.

Writes tests/golden/<name>.json plus either <name>.tcl (valid scene) or
<name>.err (expected validation errors, one per line), and g_cases.txt for the
number formatter. The Rust port is tested against these.

Run:  python3 tests/make_golden.py
"""
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))

from ns2gen.model import Scene, Node, Link, Flow, Movement, Settings  # noqa: E402
from ns2gen.tclgen import generate, validate, g  # noqa: E402

OUT = os.path.join(HERE, "golden")


def wired_basic():
    sc = Scene()
    sc.nodes = [Node(0, 100, 300), Node(1, 300, 300), Node(2, 500, 300)]
    sc.links = [Link(0, 1, "2Mb", "10ms"), Link(1, 2, "1Mb", "20ms", "RED", queue_limit=15)]
    sc.flows = [
        Flow(0, 2, "TCP", "TCP/Reno", "FTP", 0.5, 4.0, window=30),
        Flow(2, 0, "UDP", app="CBR", start=1.0, stop=3.0, packet_size=512, rate="300k"),
    ]
    return sc


def wired_all():
    sc = Scene()
    sc.settings = Settings(stop_time=12.5, trace_file="run/a_1.tr", nam_file="run/a_1.nam", run_nam=False)
    sc.nodes = [Node(0, 500, 300, "hub")]
    ring = [(600, 300), (600, 400), (500, 400), (400, 400), (400, 300), (400, 200), (500, 200), (600, 200)]
    for i, (x, y) in enumerate(ring, start=1):
        sc.nodes.append(Node(i, x, y, f"edge {i}" if i in (1, 2) else ""))
    queues = ["DropTail", "RED", "FQ", "SFQ", "DRR", "DropTail", "RED", "FQ"]
    for i in range(1, 9):
        sc.links.append(Link(0, i, f"{i}.5Mb", f"{i}.25ms", queues[i - 1], duplex=(i % 2 == 1),
                             queue_limit=(10 * i if i % 3 == 0 else None)))
    # even-numbered spokes are simplex (hub -> node only), so TCP stays on odd
    # (duplex) nodes; UDP may end on an even node.
    sc.flows = [
        Flow(1, 5, "TCP", "TCP/Reno", "FTP", 0.25, 3.333333, window=20),
        Flow(3, 7, "TCP", "TCP/Newreno", "FTP", 0.5, 4),
        Flow(5, 3, "TCP", "TCP/Vegas", "FTP", 1, 5),
        Flow(7, 1, "TCP", "TCP/Sack1", "FTP", 1, 6),
        Flow(5, 1, "UDP", app="CBR", start=1, stop=12, packet_size=210, rate="1.5m"),
        Flow(1, 2, "UDP", app="CBR", start=2, stop=10, rate="64k"),
        Flow(1, 5, "TCP", "TCP", "FTP", 7, 8),
        Flow(1, 5, "UDP", app="CBR", start=7, stop=8, rate="10"),
        Flow(3, 7, "TCP", "TCP", "FTP", 9, 10),
        Flow(3, 7, "TCP", "TCP", "FTP", 9, 10),
        Flow(0, 4, "UDP", app="CBR", start=9, stop=10, rate="200k"),
    ]
    return sc


def wired_sparse_ids():
    sc = Scene()
    sc.nodes = [Node(9, 50, 50), Node(5, 150, 50, "mid"), Node(2, 250, 150)]
    sc.links = [Link(9, 5), Link(5, 2, "100Kb", "1s")]
    sc.flows = [Flow(9, 2, "TCP", "TCP", "FTP", 1, 4), Flow(2, 9, "UDP", app="CBR", start=0, stop=5)]
    return sc


def wireless_basic():
    sc = Scene()
    sc.settings = Settings(mode="wireless", stop_time=10, width=500, height=500)
    sc.nodes = [Node(0, 50, 50), Node(1, 250, 250), Node(2, 450, 100)]
    sc.flows = [Flow(0, 2, "UDP", app="CBR", start=1, stop=9)]
    sc.movements = [Movement(1, 3, 400, 400, 8)]
    return sc


def wireless_all():
    sc = Scene()
    sc.settings = Settings(mode="wireless", routing="DSDV", mac="Mac/Simple", prop="Propagation/FreeSpace",
                           ifq="Queue/DropTail", ifq_len=100, stop_time=33.33, width=1000.5, height=750,
                           trace_file="w.tr", nam_file="w.nam", run_nam=False)
    sc.nodes = [Node(0, 12.345678, 99.5, "a"), Node(1, 500, 375), Node(3, 1000.5, 750), Node(7, 0, 0)]
    sc.movements = [Movement(1, 20, 100, 100, 2.5), Movement(0, 5.5, 900, 700, 10),
                    Movement(3, 5.5, 10, 10, 0.5), Movement(1, 0, 1, 1, 1)]
    sc.flows = [Flow(0, 3, "TCP", "TCP/Sack1", "FTP", 1, 30, window=8),
                Flow(1, 7, "UDP", app="CBR", start=2, stop=33, packet_size=64, rate="2m")]
    return sc


def err_wired_many():
    sc = wired_basic()
    sc.nodes.append(Node(2, 1, 1))
    sc.links = [Link(0, 1, "fast", "10"), Link(1, 0), Link(0, 0), Link(0, 9), Link(1, 2, "1.Mb", "5 ms", "Foo", queue_limit=0),
                Link(1, 2, "1Gb", "3us")]
    sc.settings.stop_time = -1
    sc.settings.trace_file = "a b.tr"
    sc.settings.nam_file = ""
    return sc


def err_flows_many():
    sc = Scene()
    sc.settings.stop_time = 5
    sc.nodes = [Node(0, 1, 1), Node(1, 2, 2)]
    sc.links = [Link(0, 1)]
    sc.flows = [Flow(0, 0), Flow(0, 7), Flow(0, 1, "ICMP"),
                Flow(0, 1, "TCP", "TCP/Foo", "CBR", window=0),
                Flow(0, 1, "UDP", app="FTP", rate="1.5.5", packet_size=0),
                Flow(0, 1, "TCP", start=-1, stop=-2),
                Flow(0, 1, "UDP", app="CBR", start=1, stop=99, packet_size=70000, rate="5x")]
    return sc


def err_wireless_many():
    sc = Scene()
    sc.settings = Settings(mode="wireless", routing="FOO", mac="x", prop="y", ifq="z", ifq_len=0,
                           antenna="a", phy="p", channel="c", ll="l", stop_time=10, width=100, height=100)
    sc.nodes = [Node(0, -1, 5), Node(1, 50, 500)]
    sc.movements = [Movement(9, 1, 1, 1), Movement(0, 11, 5, 5), Movement(0, -1, 5, 5, 0),
                    Movement(1, 2, 200, 5, -3)]
    return sc


def err_wireless_size():
    sc = Scene()
    sc.settings = Settings(mode="wireless", width=0, height=-5)
    sc.nodes = [Node(0, 0, 0), Node(0, 0, 0)]
    return sc


def err_unreachable():
    sc = wired_basic()
    sc.nodes.append(Node(3, 700, 300))
    sc.flows.append(Flow(0, 3, "TCP", "TCP", "FTP", 1, 2))
    sc.flows.append(Flow(3, 1, "UDP", app="CBR", start=1, stop=2))
    return sc


def err_simplex():
    sc = Scene()
    sc.nodes = [Node(0, 0, 0), Node(1, 100, 0), Node(2, 200, 0)]
    sc.links = [Link(0, 1, duplex=False), Link(1, 2)]
    sc.flows = [
        Flow(0, 2, "UDP", app="CBR", start=1, stop=2),                 # ok: forward path exists
        Flow(2, 0, "UDP", app="CBR", start=1, stop=2),                 # no path: link is one-way
        Flow(0, 2, "TCP", "TCP", "FTP", 1, 2),                         # no ACK path back
        Flow(2, 0, "TCP", "TCP", "FTP", 1, 2),                         # no forward path
    ]
    return sc


def err_no_nodes():
    return Scene()


def err_mode():
    sc = wired_basic()
    sc.settings.mode = "bogus"
    return sc


SCENES = {
    "wired_basic": wired_basic, "wired_all": wired_all, "wired_sparse_ids": wired_sparse_ids,
    "wireless_basic": wireless_basic, "wireless_all": wireless_all,
    "err_wired_many": err_wired_many, "err_flows_many": err_flows_many,
    "err_wireless_many": err_wireless_many, "err_wireless_size": err_wireless_size,
    "err_unreachable": err_unreachable, "err_simplex": err_simplex,
    "err_no_nodes": err_no_nodes, "err_mode": err_mode,
}

G_VALUES = [0.0, 1, 1.5, 100, 123456, 1234567, 999999.5, 0.0001, 0.00001, 1.5e-5, 123456.789, 99999.95,
            0.1 + 0.2, 1 / 3, 200 / 3, 1e6, 1e10, 1e-10, 3.333333, 12.5, 33.33, -2.5, -0.0001234, 1e5,
            100000.5, 0.5, 5.0e-5, 12345.6789, 1e21, 7, 0.30000000000000004, 1000.5, 99999.99, 999999.4]


def main():
    shutil.rmtree(OUT, ignore_errors=True)
    os.makedirs(OUT)
    for name, build in SCENES.items():
        sc = build()
        sc.save(os.path.join(OUT, name + ".json"))
        errs = validate(sc)
        if errs:
            with open(os.path.join(OUT, name + ".err"), "w", encoding="utf-8") as fh:
                fh.write("\n".join(errs) + "\n")
        else:
            with open(os.path.join(OUT, name + ".tcl"), "w", encoding="utf-8") as fh:
                fh.write(generate(sc))
    with open(os.path.join(OUT, "g_cases.txt"), "w", encoding="utf-8") as fh:
        for v in G_VALUES:
            fh.write(f"{v!r}\t{g(v)}\n")
    print(f"wrote {len(SCENES)} scenes + {len(G_VALUES)} number cases to {OUT}")


if __name__ == "__main__":
    main()
