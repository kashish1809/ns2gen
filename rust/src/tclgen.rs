//! Validation and TCL generation. Mirrors ns2gen/tclgen.py exactly
//! (same error texts, same order, same output bytes).

use std::collections::{HashMap, HashSet, VecDeque};

use crate::model::*;

const NAM_COLORS: &[&str] = &["Blue", "Red", "Green", "Orange", "Purple", "Brown", "Magenta", "Cyan"];
const ORIENTS: &[&str] = &["right", "right-up", "up", "left-up", "left", "left-down", "down", "right-down"];

// ---------------------------------------------------------------- numbers
/// Format like Python's `f"{v:g}"`.
pub fn g(v: f64) -> String {
    if v.is_nan() {
        return "nan".into();
    }
    if v.is_infinite() {
        return if v > 0.0 { "inf".into() } else { "-inf".into() };
    }
    if v == 0.0 {
        return if v.is_sign_negative() { "-0".into() } else { "0".into() };
    }
    let sci = format!("{:.5e}", v);
    let (mant, exp) = sci.split_once('e').expect("exp format");
    let exp: i32 = exp.parse().expect("exp int");
    if exp < -4 || exp >= 6 {
        let sign = if exp < 0 { '-' } else { '+' };
        format!("{}e{}{:02}", strip_zeros(mant), sign, exp.abs())
    } else {
        let decimals = (5 - exp).max(0) as usize;
        strip_zeros(&format!("{:.*}", decimals, v))
    }
}

fn strip_zeros(s: &str) -> String {
    if s.contains('.') {
        s.trim_end_matches('0').trim_end_matches('.').to_string()
    } else {
        s.to_string()
    }
}

// ------------------------------------------------- tiny "regex" matchers
fn digits(s: &str) -> Option<&str> {
    let n = s.bytes().take_while(|b| b.is_ascii_digit()).count();
    if n == 0 { None } else { Some(&s[n..]) }
}

/// Consume `\d+(\.\d+)?` and return the rest.
fn num_prefix(s: &str) -> Option<&str> {
    let rest = digits(s)?;
    if let Some(r) = rest.strip_prefix('.') {
        if let Some(r2) = digits(r) {
            return Some(r2);
        }
    }
    Some(rest)
}

fn num_with_suffix(s: &str, allowed: &[&str]) -> bool {
    num_prefix(s).map_or(false, |rest| allowed.contains(&rest))
}

fn bandwidth_ok(s: &str) -> bool {
    num_with_suffix(s, &["b", "Kb", "Mb", "Gb"])
}

fn delay_ok(s: &str) -> bool {
    num_with_suffix(s, &["s", "ms", "us"])
}

fn rate_ok(s: &str) -> bool {
    num_with_suffix(s, &["", "k", "K", "m", "M", "g", "G"])
}

fn filename_ok(s: &str) -> bool {
    !s.is_empty() && s.chars().all(|c| c.is_alphanumeric() || matches!(c, '_' | '.' | '/' | '-'))
}

fn one_of(v: &str, allowed: &[&str]) -> bool {
    allowed.contains(&v)
}

// ------------------------------------------------------------- validation
pub fn validate(scene: &Scene) -> Vec<String> {
    let mut errs: Vec<String> = Vec::new();
    let s = &scene.settings;
    let ids: Vec<i64> = scene.nodes.iter().map(|n| n.id).collect();
    let idset: HashSet<i64> = ids.iter().copied().collect();

    if s.mode != "wired" && s.mode != "wireless" {
        errs.push(format!("Unknown mode '{}'.", s.mode));
        return errs;
    }
    if scene.nodes.is_empty() {
        errs.push("Add at least one node.".into());
    }
    if idset.len() != ids.len() {
        errs.push("Duplicate node ids.".into());
    }
    if s.stop_time <= 0.0 {
        errs.push("Stop time must be > 0.".into());
    }
    for (what, name) in [("Trace file", &s.trace_file), ("NAM file", &s.nam_file)] {
        if !filename_ok(name) {
            errs.push(format!("{what} name must use only letters, digits, . _ - /"));
        }
    }

    if s.mode == "wired" {
        let mut seen: HashSet<(i64, i64)> = HashSet::new();
        for l in &scene.links {
            let tag = format!("Link {}-{}", l.a, l.b);
            if !idset.contains(&l.a) || !idset.contains(&l.b) {
                errs.push(format!("{tag}: unknown node."));
                continue;
            }
            if l.a == l.b {
                errs.push(format!("{tag}: link to itself."));
            }
            let key = (l.a.min(l.b), l.a.max(l.b));
            if !seen.insert(key) {
                errs.push(format!("{tag}: duplicate link."));
            }
            if !bandwidth_ok(&l.bandwidth) {
                errs.push(format!("{tag}: bandwidth '{}' invalid (e.g. 1Mb, 500Kb).", l.bandwidth));
            }
            if !delay_ok(&l.delay) {
                errs.push(format!("{tag}: delay '{}' invalid (e.g. 10ms).", l.delay));
            }
            if !one_of(&l.queue, QUEUE_TYPES) {
                errs.push(format!("{tag}: unknown queue '{}'.", l.queue));
            }
            if let Some(q) = l.queue_limit {
                if q < 1 {
                    errs.push(format!("{tag}: queue limit must be >= 1."));
                }
            }
        }
    } else {
        for n in &scene.nodes {
            if !(0.0 <= n.x && n.x <= s.width && 0.0 <= n.y && n.y <= s.height) {
                errs.push(format!("Node {}: position outside topology {}x{}.", n.id, g(s.width), g(s.height)));
            }
        }
        let opts: [(&String, &[&str]); 8] = [
            (&s.routing, ROUTING), (&s.mac, MAC_TYPES), (&s.prop, PROP_MODELS), (&s.ifq, IFQ_TYPES),
            (&s.antenna, ANTENNAS), (&s.phy, PHY_TYPES), (&s.channel, CHANNELS), (&s.ll, LL_TYPES),
        ];
        for (opt, allowed) in opts {
            if !one_of(opt, allowed) {
                errs.push(format!("Unsupported option '{opt}'."));
            }
        }
        if s.ifq_len < 1 {
            errs.push("Interface queue length must be >= 1.".into());
        }
        if s.width <= 0.0 || s.height <= 0.0 {
            errs.push("Topology size must be > 0.".into());
        }
        for m in &scene.movements {
            let tag = format!("Movement of node {} at {}s", m.node, g(m.time));
            if !idset.contains(&m.node) {
                errs.push(format!("{tag}: unknown node."));
            }
            if !(0.0 <= m.time && m.time <= s.stop_time) {
                errs.push(format!("{tag}: time outside simulation."));
            }
            if m.speed <= 0.0 {
                errs.push(format!("{tag}: speed must be > 0."));
            }
            if !(0.0 <= m.x && m.x <= s.width && 0.0 <= m.y && m.y <= s.height) {
                errs.push(format!("{tag}: target outside topology."));
            }
        }
    }

    for f in &scene.flows {
        let tag = format!("Flow {}->{}", f.src, f.dst);
        if !idset.contains(&f.src) || !idset.contains(&f.dst) {
            errs.push(format!("{tag}: unknown node."));
            continue;
        }
        if f.src == f.dst {
            errs.push(format!("{tag}: source and destination are the same."));
        }
        if f.proto != "TCP" && f.proto != "UDP" {
            errs.push(format!("{tag}: protocol must be TCP or UDP."));
        }
        if f.proto == "TCP" {
            if !one_of(&f.tcp_variant, TCP_VARIANTS) {
                errs.push(format!("{tag}: unknown TCP variant '{}'.", f.tcp_variant));
            }
            if f.app != "FTP" {
                errs.push(format!("{tag}: TCP flows carry FTP."));
            }
            if let Some(w) = f.window {
                if w < 1 {
                    errs.push(format!("{tag}: window must be >= 1."));
                }
            }
        } else if f.proto == "UDP" {
            if f.app != "CBR" {
                errs.push(format!("{tag}: UDP flows carry CBR."));
            }
            if !rate_ok(&f.rate) {
                errs.push(format!("{tag}: rate '{}' invalid (e.g. 500k, 1m).", f.rate));
            }
            if !(1..=65535).contains(&f.packet_size) {
                errs.push(format!("{tag}: packet size must be 1..65535."));
            }
        }
        if f.start < 0.0 || f.stop <= f.start {
            errs.push(format!("{tag}: need 0 <= start < stop."));
        }
        if f.stop > s.stop_time {
            errs.push(format!("{tag}: stops after simulation end ({}s).", g(s.stop_time)));
        }
    }

    if s.mode == "wired" && errs.is_empty() {
        // directed graph: a simplex link only carries traffic a -> b
        let mut adj: HashMap<i64, Vec<i64>> = HashMap::new();
        for l in &scene.links {
            adj.entry(l.a).or_default().push(l.b);
            if l.duplex {
                adj.entry(l.b).or_default().push(l.a);
            }
        }
        for f in &scene.flows {
            if !reachable(&adj, f.src, f.dst) {
                errs.push(format!("Flow {}->{}: no link path between the nodes.", f.src, f.dst));
            } else if f.proto == "TCP" && !reachable(&adj, f.dst, f.src) {
                errs.push(format!(
                    "Flow {}->{}: TCP needs a return path for ACKs (a one-way link blocks it).",
                    f.src, f.dst
                ));
            }
        }
    }
    errs
}

fn reachable(adj: &HashMap<i64, Vec<i64>>, src: i64, dst: i64) -> bool {
    let mut seen: HashSet<i64> = HashSet::from([src]);
    let mut q = VecDeque::from([src]);
    while let Some(u) = q.pop_front() {
        if u == dst {
            return true;
        }
        if let Some(next) = adj.get(&u) {
            for &v in next {
                if seen.insert(v) {
                    q.push_back(v);
                }
            }
        }
    }
    false
}

// ------------------------------------------------------------- generation
/// Err holds the validation errors joined by newlines.
pub fn generate(scene: &Scene) -> Result<String, String> {
    let errs = validate(scene);
    if !errs.is_empty() {
        return Err(errs.join("\n"));
    }
    Ok(if scene.settings.mode == "wireless" { wireless(scene) } else { wired(scene) })
}

fn orient(a: &Node, b: &Node) -> Option<&'static str> {
    let (dx, dy) = (b.x - a.x, b.y - a.y);
    if dx == 0.0 && dy == 0.0 {
        return None;
    }
    let ang = dy.atan2(dx).to_degrees(); // world y is up, like nam
    let idx = ((ang / 45.0).round_ties_even() as i64).rem_euclid(8) as usize;
    Some(ORIENTS[idx])
}

fn sink_class(variant: &str) -> &'static str {
    if variant == "TCP/Sack1" { "Agent/TCPSink/Sack1" } else { "Agent/TCPSink" }
}

fn flow_block(scene: &Scene, node_ref: &dyn Fn(i64) -> String, l: &mut Vec<String>, nam_colors: bool) {
    let (mut ntcp, mut nudp) = (0usize, 0usize);
    for (i, f) in scene.flows.iter().enumerate() {
        let (ag, sk, ap, app_cls);
        if f.proto == "TCP" {
            let k = ntcp;
            ntcp += 1;
            ag = format!("tcp{k}");
            sk = format!("sink{k}");
            ap = format!("ftp{k}");
            l.push(format!("# Flow {}: TCP/FTP  node {} -> node {}", i + 1, f.src, f.dst));
            l.push(format!("set {ag} [new Agent/{}]", f.tcp_variant));
            l.push(format!("set {sk} [new {}]", sink_class(&f.tcp_variant)));
            if let Some(w) = f.window {
                if w != 0 {
                    l.push(format!("${ag} set window_ {w}"));
                }
            }
            app_cls = "Application/FTP";
        } else {
            let k = nudp;
            nudp += 1;
            ag = format!("udp{k}");
            sk = format!("null{k}");
            ap = format!("cbr{k}");
            l.push(format!("# Flow {}: UDP/CBR  node {} -> node {}", i + 1, f.src, f.dst));
            l.push(format!("set {ag} [new Agent/UDP]"));
            l.push(format!("set {sk} [new Agent/Null]"));
            app_cls = "Application/Traffic/CBR";
        }
        if nam_colors {
            l.push(format!("${ag} set class_ {}", i + 1));
        }
        l.push(format!("$ns attach-agent {} ${ag}", node_ref(f.src)));
        l.push(format!("$ns attach-agent {} ${sk}", node_ref(f.dst)));
        l.push(format!("$ns connect ${ag} ${sk}"));
        l.push(format!("set {ap} [new {app_cls}]"));
        if f.proto == "UDP" {
            l.push(format!("${ap} set packetSize_ {}", f.packet_size));
            l.push(format!("${ap} set rate_ {}", f.rate));
        }
        l.push(format!("${ap} attach-agent ${ag}"));
        l.push(format!("$ns at {} \"${ap} start\"", g(f.start)));
        l.push(format!("$ns at {} \"${ap} stop\"", g(f.stop)));
        l.push(String::new());
    }
}

fn sorted_nodes(scene: &Scene) -> (Vec<&Node>, HashMap<i64, usize>) {
    let mut nodes: Vec<&Node> = scene.nodes.iter().collect();
    nodes.sort_by_key(|n| n.id);
    let idx = nodes.iter().enumerate().map(|(i, n)| (n.id, i)).collect();
    (nodes, idx)
}

fn push_all(l: &mut Vec<String>, lines: &[&str]) {
    l.extend(lines.iter().map(|s| s.to_string()));
}

fn wired(scene: &Scene) -> String {
    let s = &scene.settings;
    let (nodes, idx) = sorted_nodes(scene);
    let r = |nid: i64| format!("$n{}", idx[&nid]);
    let mut l: Vec<String> = Vec::new();
    push_all(&mut l, &["# Generated by ns2gen (wired scenario)", "", "set ns [new Simulator]", ""]);

    if !scene.flows.is_empty() {
        for i in 0..scene.flows.len() {
            l.push(format!("$ns color {} {}", i + 1, NAM_COLORS[i % NAM_COLORS.len()]));
        }
        l.push(String::new());
    }
    l.push(format!("set tf [open {} w]", s.trace_file));
    l.push("$ns trace-all $tf".into());
    l.push(format!("set nf [open {} w]", s.nam_file));
    push_all(&mut l, &["$ns namtrace-all $nf", "", "proc finish {} {", "    global ns nf tf",
                       "    $ns flush-trace", "    close $nf", "    close $tf"]);
    if s.run_nam {
        l.push(format!("    exec nam {} &", s.nam_file));
    }
    push_all(&mut l, &["    exit 0", "}", ""]);

    for n in &nodes {
        let note = if n.label.is_empty() { String::new() } else { format!("  ;# {}", n.label) };
        l.push(format!("set n{} [$ns node]{}", idx[&n.id], note));
    }
    l.push(String::new());

    for lk in &scene.links {
        let kind = if lk.duplex { "duplex-link" } else { "simplex-link" };
        l.push(format!("$ns {kind} {} {} {} {} {}", r(lk.a), r(lk.b), lk.bandwidth, lk.delay, lk.queue));
        if let (Some(a), Some(b)) = (scene.node_by_id(lk.a), scene.node_by_id(lk.b)) {
            if let Some(o) = orient(a, b) {
                let op = if lk.duplex { "duplex-link-op" } else { "simplex-link-op" };
                l.push(format!("$ns {op} {} {} orient {o}", r(lk.a), r(lk.b)));
            }
        }
        if let Some(q) = lk.queue_limit {
            if q != 0 {
                l.push(format!("$ns queue-limit {} {} {q}", r(lk.a), r(lk.b)));
                if lk.duplex {
                    l.push(format!("$ns queue-limit {} {} {q}", r(lk.b), r(lk.a)));
                }
            }
        }
    }
    if !scene.links.is_empty() {
        l.push(String::new());
    }

    flow_block(scene, &r, &mut l, true);
    l.push(format!("$ns at {} \"finish\"", g(s.stop_time)));
    push_all(&mut l, &["$ns run", ""]);
    l.join("\n")
}

fn wireless(scene: &Scene) -> String {
    let s = &scene.settings;
    let (nodes, idx) = sorted_nodes(scene);
    let r = |nid: i64| format!("$node_({})", idx[&nid]);
    let mut l: Vec<String> = Vec::new();
    push_all(&mut l, &["# Generated by ns2gen (wireless scenario)", ""]);
    let vals: Vec<(&str, String)> = vec![
        ("chan", s.channel.clone()), ("prop", s.prop.clone()), ("netif", s.phy.clone()),
        ("mac", s.mac.clone()), ("ifq", s.ifq.clone()), ("ll", s.ll.clone()),
        ("ant", s.antenna.clone()), ("ifqlen", s.ifq_len.to_string()), ("nn", nodes.len().to_string()),
        ("rp", s.routing.clone()), ("x", g(s.width)), ("y", g(s.height)), ("stop", g(s.stop_time)),
    ];
    for (k, v) in vals {
        l.push(format!("set val({k}) {v}"));
    }
    push_all(&mut l, &["", "set ns [new Simulator]"]);
    l.push(format!("set tracefd [open {} w]", s.trace_file));
    l.push("$ns trace-all $tracefd".into());
    l.push(format!("set namtrace [open {} w]", s.nam_file));
    push_all(&mut l, &[
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
        "    $ns flush-trace", "    close $tracefd", "    close $namtrace",
    ]);
    if s.run_nam {
        l.push(format!("    exec nam {} &", s.nam_file));
    }
    push_all(&mut l, &["    exit 0", "}", ""]);

    for n in &nodes {
        let i = idx[&n.id];
        let note = if n.label.is_empty() { String::new() } else { format!("  ;# {}", n.label) };
        l.push(format!("set node_({i}) [$ns node]{note}"));
        l.push(format!("$node_({i}) random-motion 0"));
        l.push(format!("$node_({i}) set X_ {}", g(n.x)));
        l.push(format!("$node_({i}) set Y_ {}", g(n.y)));
        l.push(format!("$node_({i}) set Z_ 0.0"));
        l.push(format!("$ns initial_node_pos $node_({i}) 30"));
        l.push(String::new());
    }

    let mut moves: Vec<&Movement> = scene.movements.iter().collect();
    moves.sort_by(|a, b| a.time.partial_cmp(&b.time).unwrap_or(std::cmp::Ordering::Equal)); // stable
    for m in &moves {
        l.push(format!("$ns at {} \"{} setdest {} {} {}\"", g(m.time), r(m.node), g(m.x), g(m.y), g(m.speed)));
    }
    if !moves.is_empty() {
        l.push(String::new());
    }

    flow_block(scene, &r, &mut l, false);
    push_all(&mut l, &[
        "for {set i 0} {$i < $val(nn)} {incr i} {",
        "    $ns at $val(stop) \"$node_($i) reset\"", "}",
        "$ns at $val(stop) \"finish\"", "puts \"Starting simulation...\"", "$ns run", "",
    ]);
    l.join("\n")
}
