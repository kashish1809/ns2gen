import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from ns2gen.model import Scene, Node, Link, Flow, Movement, Settings
from ns2gen.tclgen import generate, validate


def wired_scene():
    sc = Scene()
    sc.nodes = [Node(0, 100, 300), Node(1, 300, 300), Node(2, 500, 300)]
    sc.links = [Link(0, 1, "2Mb", "10ms"), Link(1, 2, "1Mb", "20ms", "RED", queue_limit=15)]
    sc.flows = [
        Flow(0, 2, "TCP", "TCP/Reno", "FTP", 0.5, 4.0, window=30),
        Flow(2, 0, "UDP", app="CBR", start=1.0, stop=3.0, packet_size=512, rate="300k"),
    ]
    return sc


def wireless_scene():
    sc = Scene()
    sc.settings = Settings(mode="wireless", stop_time=10, width=500, height=500)
    sc.nodes = [Node(0, 50, 50), Node(1, 250, 250), Node(2, 450, 100)]
    sc.flows = [Flow(0, 2, "UDP", app="CBR", start=1, stop=9)]
    sc.movements = [Movement(1, 3, 400, 400, 8)]
    return sc


def test_wired_output():
    t = generate(wired_scene())
    assert t.count("[new Simulator]") == 1
    assert "$ns duplex-link $n0 $n1 2Mb 10ms DropTail" in t
    assert "$ns duplex-link $n1 $n2 1Mb 20ms RED" in t
    assert "$ns queue-limit $n1 $n2 15" in t and "$ns queue-limit $n2 $n1 15" in t
    assert "set tcp0 [new Agent/TCP/Reno]" in t
    assert "$tcp0 set window_ 30" in t
    assert "set sink0 [new Agent/TCPSink]" in t
    assert "set udp0 [new Agent/UDP]" in t
    assert "$cbr0 set packetSize_ 512" in t and "$cbr0 set rate_ 300k" in t
    assert "$ns connect $udp0 $null0" in t
    assert '$ns at 4 "$ftp0 stop"' in t
    assert '$ns at 5 "finish"' in t
    assert t.rstrip().endswith("$ns run")
    assert "orient right" in t  # nodes laid out left to right


def test_braces_balanced():
    for sc in (wired_scene(), wireless_scene()):
        t = generate(sc)
        assert t.count("{") == t.count("}")
        assert t.count("[") == t.count("]")


def test_orient_directions():
    sc = Scene()
    sc.nodes = [Node(0, 0, 0), Node(1, 0, 100), Node(2, 100, 100)]
    sc.links = [Link(0, 1), Link(0, 2)]
    t = generate(sc)
    assert "$n0 $n1 orient up" in t
    assert "$n0 $n2 orient right-up" in t


def test_node_ids_compacted():
    sc = wired_scene()
    sc.remove_node(1)  # ids 0 and 2 remain, links/flows touching 1 gone
    sc.links.append(Link(0, 2))
    sc.flows = [Flow(0, 2, "TCP", "TCP", "FTP", 1, 2)]
    t = generate(sc)
    assert "set n0 [$ns node]" in t and "set n1 [$ns node]" in t
    assert "n2" not in t.split("proc finish")[1].split("$ns run")[0].replace("$ns at", "")


def test_wireless_output():
    t = generate(wireless_scene())
    assert "set val(nn) 3" in t
    assert "create-god $val(nn)" in t
    assert "$node_(1) set X_ 250" in t
    assert '$ns at 3 "$node_(1) setdest 400 400 8"' in t
    assert "$ns attach-agent $node_(0) $udp0" in t
    assert "duplex-link" not in t


def test_run_nam_toggle():
    sc = wired_scene()
    assert "exec nam out.nam &" in generate(sc)
    sc.settings.run_nam = False
    assert "exec nam" not in generate(sc)


@pytest.mark.parametrize("mutate,needle", [
    (lambda s: s.links.__setitem__(0, Link(0, 1, "fast", "10ms")), "bandwidth"),
    (lambda s: s.links.__setitem__(0, Link(0, 1, "1Mb", "10")), "delay"),
    (lambda s: s.links.__setitem__(0, Link(0, 0)), "itself"),
    (lambda s: s.links.append(Link(1, 0)), "duplicate"),
    (lambda s: s.flows.append(Flow(0, 0)), "same"),
    (lambda s: s.flows.append(Flow(0, 2, "TCP", app="CBR")), "carry FTP"),
    (lambda s: s.flows.append(Flow(0, 2, "UDP", app="FTP")), "carry CBR"),
    (lambda s: s.flows.append(Flow(0, 2, "TCP", start=3, stop=2)), "start < stop"),
    (lambda s: s.flows.append(Flow(0, 2, "TCP", start=1, stop=99)), "after simulation end"),
    (lambda s: s.flows.append(Flow(0, 9)), "unknown node"),
    (lambda s: setattr(s.settings, "trace_file", "a b.tr"), "Trace file"),
    (lambda s: setattr(s.settings, "stop_time", 0), "Stop time"),
])
def test_validation_errors(mutate, needle):
    sc = wired_scene()
    mutate(sc)
    errs = validate(sc)
    assert any(needle.lower() in e.lower() for e in errs), errs
    with pytest.raises(ValueError):
        generate(sc)


def test_disconnected_flow_detected():
    sc = wired_scene()
    sc.links = [Link(0, 1)]
    assert any("no link path" in e for e in validate(sc))


def test_simplex_direction_respected():
    sc = Scene()
    sc.nodes = [Node(0, 0, 0), Node(1, 100, 0)]
    sc.links = [Link(0, 1, duplex=False)]
    # UDP forward over a one-way link is fine
    sc.flows = [Flow(0, 1, "UDP", app="CBR", start=1, stop=2)]
    assert validate(sc) == []
    # UDP against the direction: no path
    sc.flows = [Flow(1, 0, "UDP", app="CBR", start=1, stop=2)]
    assert any("no link path" in e for e in validate(sc))
    # TCP needs ACKs back, so one-way link is not enough
    sc.flows = [Flow(0, 1, "TCP", "TCP", "FTP", 1, 2)]
    assert any("return path" in e for e in validate(sc))
    sc.links[0].duplex = True
    assert validate(sc) == []


def test_wireless_validation():
    sc = wireless_scene()
    sc.nodes[0].x = 9999
    sc.movements[0].speed = 0
    errs = " ".join(validate(sc))
    assert "outside topology" in errs and "speed" in errs


def test_json_roundtrip(tmp_path):
    for sc in (wired_scene(), wireless_scene()):
        p = tmp_path / "s.json"
        sc.save(str(p))
        back = Scene.load(str(p))
        assert generate(back) == generate(sc)
        json.loads(p.read_text())


def test_cascade_delete():
    sc = wired_scene()
    sc.remove_node(2)
    assert all(2 not in (l.a, l.b) for l in sc.links)
    assert sc.flows == []
