"""Scene -> ns2 TCL. Pure functions, no GUI, easy to test."""
from __future__ import annotations

import math
import re
from collections import defaultdict, deque
from typing import Dict, List

from .model import (
    Scene, QUEUE_TYPES, TCP_VARIANTS, ROUTING, MAC_TYPES, PROP_MODELS,
    IFQ_TYPES, ANTENNAS, PHY_TYPES, CHANNELS, LL_TYPES,
)

NAM_COLORS = ["Blue", "Red", "Green", "Orange", "Purple", "Brown", "Magenta", "Cyan"]
ORIENTS = ["right", "right-up", "up", "left-up", "left", "left-down", "down", "right-down"]

_BW_RE = re.compile(r"^\d+(\.\d+)?(b|Kb|Mb|Gb)$")
_DELAY_RE = re.compile(r"^\d+(\.\d+)?(s|ms|us)$")
_RATE_RE = re.compile(r"^\d+(\.\d+)?[kKmMgG]?$")
_FILE_RE = re.compile(r"^[\w./-]+$")


def g(v: float) -> str:
    """Format a number for TCL."""
    return f"{v:g}"


# --------------------------------------------------------------------------
# validation
# --------------------------------------------------------------------------
def validate(scene: Scene) -> List[str]:
    errs: List[str] = []
    s = scene.settings
    ids = [n.id for n in scene.nodes]

    if s.mode not in ("wired", "wireless"):
        errs.append(f"Unknown mode '{s.mode}'.")
        return errs
    if not scene.nodes:
        errs.append("Add at least one node.")
    if len(set(ids)) != len(ids):
        errs.append("Duplicate node ids.")
    if s.stop_time <= 0:
        errs.append("Stop time must be > 0.")
    for what, name in (("Trace file", s.trace_file), ("NAM file", s.nam_file)):
        if not _FILE_RE.match(name or ""):
            errs.append(f"{what} name must use only letters, digits, . _ - /")
    idset = set(ids)

    if s.mode == "wired":
        seen = set()
        for l in scene.links:
            tag = f"Link {l.a}-{l.b}"
            if l.a not in idset or l.b not in idset:
                errs.append(f"{tag}: unknown node.")
                continue
            if l.a == l.b:
                errs.append(f"{tag}: link to itself.")
            key = frozenset((l.a, l.b))
            if key in seen:
                errs.append(f"{tag}: duplicate link.")
            seen.add(key)
            if not _BW_RE.match(l.bandwidth):
                errs.append(f"{tag}: bandwidth '{l.bandwidth}' invalid (e.g. 1Mb, 500Kb).")
            if not _DELAY_RE.match(l.delay):
                errs.append(f"{tag}: delay '{l.delay}' invalid (e.g. 10ms).")
            if l.queue not in QUEUE_TYPES:
                errs.append(f"{tag}: unknown queue '{l.queue}'.")
            if l.queue_limit is not None and l.queue_limit < 1:
                errs.append(f"{tag}: queue limit must be >= 1.")
    else:
        for n in scene.nodes:
            if not (0 <= n.x <= s.width and 0 <= n.y <= s.height):
                errs.append(f"Node {n.id}: position outside topology {g(s.width)}x{g(s.height)}.")
        for opt, allowed in (
            (s.routing, ROUTING), (s.mac, MAC_TYPES), (s.prop, PROP_MODELS),
            (s.ifq, IFQ_TYPES), (s.antenna, ANTENNAS), (s.phy, PHY_TYPES),
            (s.channel, CHANNELS), (s.ll, LL_TYPES),
        ):
            if opt not in allowed:
                errs.append(f"Unsupported option '{opt}'.")
        if s.ifq_len < 1:
            errs.append("Interface queue length must be >= 1.")
        if s.width <= 0 or s.height <= 0:
            errs.append("Topology size must be > 0.")
        for m in scene.movements:
            tag = f"Movement of node {m.node} at {g(m.time)}s"
            if m.node not in idset:
                errs.append(f"{tag}: unknown node.")
            if not (0 <= m.time <= s.stop_time):
                errs.append(f"{tag}: time outside simulation.")
            if m.speed <= 0:
                errs.append(f"{tag}: speed must be > 0.")
            if not (0 <= m.x <= s.width and 0 <= m.y <= s.height):
                errs.append(f"{tag}: target outside topology.")

    for f in scene.flows:
        tag = f"Flow {f.src}->{f.dst}"
        if f.src not in idset or f.dst not in idset:
            errs.append(f"{tag}: unknown node.")
            continue
        if f.src == f.dst:
            errs.append(f"{tag}: source and destination are the same.")
        if f.proto not in ("TCP", "UDP"):
            errs.append(f"{tag}: protocol must be TCP or UDP.")
        if f.proto == "TCP":
            if f.tcp_variant not in TCP_VARIANTS:
                errs.append(f"{tag}: unknown TCP variant '{f.tcp_variant}'.")
            if f.app != "FTP":
                errs.append(f"{tag}: TCP flows carry FTP.")
            if f.window is not None and f.window < 1:
                errs.append(f"{tag}: window must be >= 1.")
        elif f.proto == "UDP":
            if f.app != "CBR":
                errs.append(f"{tag}: UDP flows carry CBR.")
            if not _RATE_RE.match(f.rate):
                errs.append(f"{tag}: rate '{f.rate}' invalid (e.g. 500k, 1m).")
            if not (1 <= f.packet_size <= 65535):
                errs.append(f"{tag}: packet size must be 1..65535.")
        if f.start < 0 or f.stop <= f.start:
            errs.append(f"{tag}: need 0 <= start < stop.")
        if f.stop > s.stop_time:
            errs.append(f"{tag}: stops after simulation end ({g(s.stop_time)}s).")

    if s.mode == "wired" and not errs:
        # directed graph: a simplex link only carries traffic a -> b
        adj: Dict[int, set] = defaultdict(set)
        for l in scene.links:
            adj[l.a].add(l.b)
            if l.duplex:
                adj[l.b].add(l.a)
        for f in scene.flows:
            if not _reachable(adj, f.src, f.dst):
                errs.append(f"Flow {f.src}->{f.dst}: no link path between the nodes.")
            elif f.proto == "TCP" and not _reachable(adj, f.dst, f.src):
                errs.append(f"Flow {f.src}->{f.dst}: TCP needs a return path for ACKs "
                            f"(a one-way link blocks it).")
    return errs


def _reachable(adj, src, dst) -> bool:
    seen, q = {src}, deque([src])
    while q:
        u = q.popleft()
        if u == dst:
            return True
        for v in adj[u]:
            if v not in seen:
                seen.add(v)
                q.append(v)
    return False


# --------------------------------------------------------------------------
# generation
# --------------------------------------------------------------------------
def generate(scene: Scene) -> str:
    errs = validate(scene)
    if errs:
        raise ValueError("\n".join(errs))
    if scene.settings.mode == "wireless":
        return _wireless(scene)
    return _wired(scene)


def _orient(a, b):
    dx, dy = b.x - a.x, b.y - a.y
    if dx == 0 and dy == 0:
        return None
    ang = math.degrees(math.atan2(dy, dx))  # world y is up, like nam
    return ORIENTS[round(ang / 45) % 8]


def _sink_class(variant: str) -> str:
    return "Agent/TCPSink/Sack1" if variant == "TCP/Sack1" else "Agent/TCPSink"


def _flow_block(scene: Scene, node_ref, lines: List[str], nam_colors: bool) -> None:
    """Shared agent/sink/app generation. node_ref(id) -> TCL node expression."""
    counters = {"tcp": 0, "udp": 0}
    for i, f in enumerate(scene.flows):
        if f.proto == "TCP":
            k = counters["tcp"]; counters["tcp"] += 1
            ag, sk, ap = f"tcp{k}", f"sink{k}", f"ftp{k}"
            lines.append(f"# Flow {i + 1}: TCP/FTP  node {f.src} -> node {f.dst}")
            lines.append(f"set {ag} [new Agent/{f.tcp_variant}]")
            lines.append(f"set {sk} [new {_sink_class(f.tcp_variant)}]")
            if f.window:
                lines.append(f"${ag} set window_ {f.window}")
            app_cls = "Application/FTP"
        else:
            k = counters["udp"]; counters["udp"] += 1
            ag, sk, ap = f"udp{k}", f"null{k}", f"cbr{k}"
            lines.append(f"# Flow {i + 1}: UDP/CBR  node {f.src} -> node {f.dst}")
            lines.append(f"set {ag} [new Agent/UDP]")
            lines.append(f"set {sk} [new Agent/Null]")
            app_cls = "Application/Traffic/CBR"
        if nam_colors:
            lines.append(f"${ag} set class_ {i + 1}")
        lines.append(f"$ns attach-agent {node_ref(f.src)} ${ag}")
        lines.append(f"$ns attach-agent {node_ref(f.dst)} ${sk}")
        lines.append(f"$ns connect ${ag} ${sk}")
        lines.append(f"set {ap} [new {app_cls}]")
        if f.proto == "UDP":
            lines.append(f"${ap} set packetSize_ {f.packet_size}")
            lines.append(f"${ap} set rate_ {f.rate}")
        lines.append(f"${ap} attach-agent ${ag}")
        lines.append(f'$ns at {g(f.start)} "${ap} start"')
        lines.append(f'$ns at {g(f.stop)} "${ap} stop"')
        lines.append("")


def _wired(scene: Scene) -> str:
    s = scene.settings
    nodes = sorted(scene.nodes, key=lambda n: n.id)
    idx = {n.id: i for i, n in enumerate(nodes)}
    ref = lambda nid: f"$n{idx[nid]}"
    L: List[str] = ["# Generated by ns2gen (wired scenario)", "", "set ns [new Simulator]", ""]

    if scene.flows:
        for i in range(len(scene.flows)):
            L.append(f"$ns color {i + 1} {NAM_COLORS[i % len(NAM_COLORS)]}")
        L.append("")
    L += [f"set tf [open {s.trace_file} w]", "$ns trace-all $tf",
          f"set nf [open {s.nam_file} w]", "$ns namtrace-all $nf", "",
          "proc finish {} {", "    global ns nf tf", "    $ns flush-trace",
          "    close $nf", "    close $tf"]
    if s.run_nam:
        L.append(f"    exec nam {s.nam_file} &")
    L += ["    exit 0", "}", ""]

    for n in nodes:
        note = f"  ;# {n.label}" if n.label else ""
        L.append(f"set n{idx[n.id]} [$ns node]{note}")
    L.append("")

    for l in scene.links:
        kind = "duplex-link" if l.duplex else "simplex-link"
        L.append(f"$ns {kind} {ref(l.a)} {ref(l.b)} {l.bandwidth} {l.delay} {l.queue}")
        o = _orient(scene.node_by_id(l.a), scene.node_by_id(l.b))
        if o:
            op = "duplex-link-op" if l.duplex else "simplex-link-op"
            L.append(f"$ns {op} {ref(l.a)} {ref(l.b)} orient {o}")
        if l.queue_limit:
            L.append(f"$ns queue-limit {ref(l.a)} {ref(l.b)} {l.queue_limit}")
            if l.duplex:
                L.append(f"$ns queue-limit {ref(l.b)} {ref(l.a)} {l.queue_limit}")
    if scene.links:
        L.append("")

    _flow_block(scene, ref, L, nam_colors=True)
    L += [f'$ns at {g(s.stop_time)} "finish"', "$ns run", ""]
    return "\n".join(L)


def _wireless(scene: Scene) -> str:
    s = scene.settings
    nodes = sorted(scene.nodes, key=lambda n: n.id)
    idx = {n.id: i for i, n in enumerate(nodes)}
    ref = lambda nid: f"$node_({idx[nid]})"
    L: List[str] = ["# Generated by ns2gen (wireless scenario)", ""]
    for key, val in (
        ("chan", s.channel), ("prop", s.prop), ("netif", s.phy), ("mac", s.mac),
        ("ifq", s.ifq), ("ll", s.ll), ("ant", s.antenna), ("ifqlen", s.ifq_len),
        ("nn", len(nodes)), ("rp", s.routing), ("x", g(s.width)), ("y", g(s.height)),
        ("stop", g(s.stop_time)),
    ):
        L.append(f"set val({key}) {val}")
    L += ["", "set ns [new Simulator]",
          f"set tracefd [open {s.trace_file} w]", "$ns trace-all $tracefd",
          f"set namtrace [open {s.nam_file} w]",
          "$ns namtrace-all-wireless $namtrace $val(x) $val(y)", "",
          "set topo [new Topography]", "$topo load_flatgrid $val(x) $val(y)",
          "create-god $val(nn)", "",
          "$ns node-config -adhocRouting $val(rp) \\", "    -llType $val(ll) \\",
          "    -macType $val(mac) \\", "    -ifqType $val(ifq) \\",
          "    -ifqLen $val(ifqlen) \\", "    -antType $val(ant) \\",
          "    -propType $val(prop) \\", "    -phyType $val(netif) \\",
          "    -channelType $val(chan) \\", "    -topoInstance $topo \\",
          "    -agentTrace ON \\", "    -routerTrace ON \\",
          "    -macTrace OFF \\", "    -movementTrace ON", "",
          "proc finish {} {", "    global ns tracefd namtrace",
          "    $ns flush-trace", "    close $tracefd", "    close $namtrace"]
    if s.run_nam:
        L.append(f"    exec nam {s.nam_file} &")
    L += ["    exit 0", "}", ""]

    for n in nodes:
        i = idx[n.id]
        note = f"  ;# {n.label}" if n.label else ""
        L += [f"set node_({i}) [$ns node]{note}",
              f"$node_({i}) random-motion 0",
              f"$node_({i}) set X_ {g(n.x)}",
              f"$node_({i}) set Y_ {g(n.y)}",
              f"$node_({i}) set Z_ 0.0",
              f"$ns initial_node_pos $node_({i}) 30", ""]

    for m in sorted(scene.movements, key=lambda m: m.time):
        L.append(f'$ns at {g(m.time)} "{ref(m.node)} setdest {g(m.x)} {g(m.y)} {g(m.speed)}"')
    if scene.movements:
        L.append("")

    _flow_block(scene, ref, L, nam_colors=False)
    L += ["for {set i 0} {$i < $val(nn)} {incr i} {",
          '    $ns at $val(stop) "$node_($i) reset"', "}",
          '$ns at $val(stop) "finish"', 'puts "Starting simulation..."', "$ns run", ""]
    return "\n".join(L)
