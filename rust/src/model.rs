//! Scene model + JSON conversion. Same file format as the Python version.

use crate::json::{self, Value};

pub const QUEUE_TYPES: &[&str] = &["DropTail", "RED", "FQ", "SFQ", "DRR"];
pub const TCP_VARIANTS: &[&str] = &["TCP", "TCP/Reno", "TCP/Newreno", "TCP/Vegas", "TCP/Sack1"];
pub const ROUTING: &[&str] = &["AODV", "DSDV", "DSR", "TORA"];
pub const MAC_TYPES: &[&str] = &["Mac/802_11", "Mac/Simple"];
pub const PROP_MODELS: &[&str] = &["Propagation/TwoRayGround", "Propagation/FreeSpace", "Propagation/Shadowing"];
pub const IFQ_TYPES: &[&str] = &["Queue/DropTail/PriQueue", "Queue/DropTail", "CMUPriQueue"];
pub const ANTENNAS: &[&str] = &["Antenna/OmniAntenna"];
pub const PHY_TYPES: &[&str] = &["Phy/WirelessPhy"];
pub const CHANNELS: &[&str] = &["Channel/WirelessChannel"];
pub const LL_TYPES: &[&str] = &["LL"];

const FORMAT_VERSION: f64 = 1.0;

#[derive(Debug, Clone, PartialEq)]
pub struct Node {
    pub id: i64,
    pub x: f64,
    pub y: f64,
    pub label: String,
}

#[derive(Debug, Clone, PartialEq)]
pub struct Link {
    pub a: i64,
    pub b: i64,
    pub bandwidth: String,
    pub delay: String,
    pub queue: String,
    pub duplex: bool,
    pub queue_limit: Option<i64>,
}

impl Link {
    pub fn new(a: i64, b: i64) -> Self {
        Link { a, b, bandwidth: "1Mb".into(), delay: "10ms".into(), queue: "DropTail".into(),
               duplex: true, queue_limit: None }
    }
}

#[derive(Debug, Clone, PartialEq)]
pub struct Flow {
    pub src: i64,
    pub dst: i64,
    pub proto: String,
    pub tcp_variant: String,
    pub app: String,
    pub start: f64,
    pub stop: f64,
    pub packet_size: i64,
    pub rate: String,
    pub window: Option<i64>,
}

impl Flow {
    pub fn new(src: i64, dst: i64) -> Self {
        Flow { src, dst, proto: "TCP".into(), tcp_variant: "TCP".into(), app: "FTP".into(),
               start: 1.0, stop: 4.0, packet_size: 1000, rate: "500k".into(), window: None }
    }
}

#[derive(Debug, Clone, PartialEq)]
pub struct Movement {
    pub node: i64,
    pub time: f64,
    pub x: f64,
    pub y: f64,
    pub speed: f64,
}

#[derive(Debug, Clone, PartialEq)]
pub struct Settings {
    pub mode: String,
    pub stop_time: f64,
    pub trace_file: String,
    pub nam_file: String,
    pub run_nam: bool,
    pub width: f64,
    pub height: f64,
    pub routing: String,
    pub mac: String,
    pub prop: String,
    pub ifq: String,
    pub ifq_len: i64,
    pub antenna: String,
    pub phy: String,
    pub channel: String,
    pub ll: String,
}

impl Default for Settings {
    fn default() -> Self {
        Settings {
            mode: "wired".into(), stop_time: 5.0, trace_file: "out.tr".into(), nam_file: "out.nam".into(),
            run_nam: true, width: 800.0, height: 600.0, routing: "AODV".into(), mac: "Mac/802_11".into(),
            prop: "Propagation/TwoRayGround".into(), ifq: "Queue/DropTail/PriQueue".into(), ifq_len: 50,
            antenna: "Antenna/OmniAntenna".into(), phy: "Phy/WirelessPhy".into(),
            channel: "Channel/WirelessChannel".into(), ll: "LL".into(),
        }
    }
}

#[derive(Debug, Clone, Default, PartialEq)]
pub struct Scene {
    pub settings: Settings,
    pub nodes: Vec<Node>,
    pub links: Vec<Link>,
    pub flows: Vec<Flow>,
    pub movements: Vec<Movement>,
}

impl Scene {
    pub fn node_by_id(&self, id: i64) -> Option<&Node> {
        self.nodes.iter().find(|n| n.id == id)
    }

    pub fn next_node_id(&self) -> i64 {
        self.nodes.iter().map(|n| n.id).max().map_or(0, |m| m + 1)
    }

    pub fn add_node(&mut self, x: f64, y: f64) -> i64 {
        let id = self.next_node_id();
        self.nodes.push(Node { id, x, y, label: String::new() });
        id
    }

    /// Remove a node and everything that references it.
    pub fn remove_node(&mut self, id: i64) {
        self.nodes.retain(|n| n.id != id);
        self.links.retain(|l| l.a != id && l.b != id);
        self.flows.retain(|f| f.src != id && f.dst != id);
        self.movements.retain(|m| m.node != id);
    }

    pub fn find_link(&self, a: i64, b: i64) -> Option<usize> {
        self.links.iter().position(|l| (l.a, l.b) == (a, b) || (l.a, l.b) == (b, a))
    }

    pub fn load(path: &str) -> Result<Scene, String> {
        let text = std::fs::read_to_string(path).map_err(|e| format!("{path}: {e}"))?;
        Scene::from_json_str(&text)
    }

    pub fn save(&self, path: &str) -> Result<(), String> {
        std::fs::write(path, self.to_json_string()).map_err(|e| format!("{path}: {e}"))
    }

    pub fn from_json_str(text: &str) -> Result<Scene, String> {
        Scene::from_json(&json::parse(text)?)
    }

    pub fn to_json_string(&self) -> String {
        json::to_string_pretty(&self.to_json())
    }

    // ------------------------------------------------------------------
    pub fn from_json(v: &Value) -> Result<Scene, String> {
        if !matches!(v, Value::Obj(_)) {
            return Err("scene file must be a JSON object".into());
        }
        let mut sc = Scene::default();
        if let Some(s) = v.get("settings") {
            sc.settings = settings_from(s)?;
        }
        for n in arr(v, "nodes")? {
            sc.nodes.push(Node {
                id: int(n, "id", None)?.ok_or("node without id")?,
                x: num(n, "x", 0.0)?,
                y: num(n, "y", 0.0)?,
                label: string(n, "label", "")?,
            });
        }
        for l in arr(v, "links")? {
            sc.links.push(Link {
                a: int(l, "a", None)?.ok_or("link without a")?,
                b: int(l, "b", None)?.ok_or("link without b")?,
                bandwidth: string(l, "bandwidth", "1Mb")?,
                delay: string(l, "delay", "10ms")?,
                queue: string(l, "queue", "DropTail")?,
                duplex: boolean(l, "duplex", true)?,
                queue_limit: int(l, "queue_limit", None)?,
            });
        }
        for f in arr(v, "flows")? {
            sc.flows.push(Flow {
                src: int(f, "src", None)?.ok_or("flow without src")?,
                dst: int(f, "dst", None)?.ok_or("flow without dst")?,
                proto: string(f, "proto", "TCP")?,
                tcp_variant: string(f, "tcp_variant", "TCP")?,
                app: string(f, "app", "FTP")?,
                start: num(f, "start", 1.0)?,
                stop: num(f, "stop", 4.0)?,
                packet_size: int(f, "packet_size", Some(1000))?.unwrap_or(1000),
                rate: string(f, "rate", "500k")?,
                window: int(f, "window", None)?,
            });
        }
        for m in arr(v, "movements")? {
            sc.movements.push(Movement {
                node: int(m, "node", None)?.ok_or("movement without node")?,
                time: num(m, "time", 0.0)?,
                x: num(m, "x", 0.0)?,
                y: num(m, "y", 0.0)?,
                speed: num(m, "speed", 5.0)?,
            });
        }
        Ok(sc)
    }

    pub fn to_json(&self) -> Value {
        let s = &self.settings;
        let st = |x: &str| Value::Str(x.to_string());
        let n = |x: f64| Value::Num(x);
        let settings = Value::Obj(vec![
            ("mode".into(), st(&s.mode)),
            ("stop_time".into(), n(s.stop_time)),
            ("trace_file".into(), st(&s.trace_file)),
            ("nam_file".into(), st(&s.nam_file)),
            ("run_nam".into(), Value::Bool(s.run_nam)),
            ("width".into(), n(s.width)),
            ("height".into(), n(s.height)),
            ("routing".into(), st(&s.routing)),
            ("mac".into(), st(&s.mac)),
            ("prop".into(), st(&s.prop)),
            ("ifq".into(), st(&s.ifq)),
            ("ifq_len".into(), n(s.ifq_len as f64)),
            ("antenna".into(), st(&s.antenna)),
            ("phy".into(), st(&s.phy)),
            ("channel".into(), st(&s.channel)),
            ("ll".into(), st(&s.ll)),
        ]);
        let opt = |x: Option<i64>| x.map_or(Value::Null, |v| Value::Num(v as f64));
        Value::Obj(vec![
            ("format".into(), Value::Num(FORMAT_VERSION)),
            ("settings".into(), settings),
            ("nodes".into(), Value::Arr(self.nodes.iter().map(|x| Value::Obj(vec![
                ("id".into(), n(x.id as f64)), ("x".into(), n(x.x)), ("y".into(), n(x.y)),
                ("label".into(), st(&x.label)),
            ])).collect())),
            ("links".into(), Value::Arr(self.links.iter().map(|x| Value::Obj(vec![
                ("a".into(), n(x.a as f64)), ("b".into(), n(x.b as f64)),
                ("bandwidth".into(), st(&x.bandwidth)), ("delay".into(), st(&x.delay)),
                ("queue".into(), st(&x.queue)), ("duplex".into(), Value::Bool(x.duplex)),
                ("queue_limit".into(), opt(x.queue_limit)),
            ])).collect())),
            ("flows".into(), Value::Arr(self.flows.iter().map(|x| Value::Obj(vec![
                ("src".into(), n(x.src as f64)), ("dst".into(), n(x.dst as f64)),
                ("proto".into(), st(&x.proto)), ("tcp_variant".into(), st(&x.tcp_variant)),
                ("app".into(), st(&x.app)), ("start".into(), n(x.start)), ("stop".into(), n(x.stop)),
                ("packet_size".into(), n(x.packet_size as f64)), ("rate".into(), st(&x.rate)),
                ("window".into(), opt(x.window)),
            ])).collect())),
            ("movements".into(), Value::Arr(self.movements.iter().map(|x| Value::Obj(vec![
                ("node".into(), n(x.node as f64)), ("time".into(), n(x.time)),
                ("x".into(), n(x.x)), ("y".into(), n(x.y)), ("speed".into(), n(x.speed)),
            ])).collect())),
        ])
    }
}

// ---------------------------------------------------------------- helpers
fn settings_from(v: &Value) -> Result<Settings, String> {
    let d = Settings::default();
    Ok(Settings {
        mode: string(v, "mode", &d.mode)?,
        stop_time: num(v, "stop_time", d.stop_time)?,
        trace_file: string(v, "trace_file", &d.trace_file)?,
        nam_file: string(v, "nam_file", &d.nam_file)?,
        run_nam: boolean(v, "run_nam", d.run_nam)?,
        width: num(v, "width", d.width)?,
        height: num(v, "height", d.height)?,
        routing: string(v, "routing", &d.routing)?,
        mac: string(v, "mac", &d.mac)?,
        prop: string(v, "prop", &d.prop)?,
        ifq: string(v, "ifq", &d.ifq)?,
        ifq_len: int(v, "ifq_len", Some(d.ifq_len))?.unwrap_or(d.ifq_len),
        antenna: string(v, "antenna", &d.antenna)?,
        phy: string(v, "phy", &d.phy)?,
        channel: string(v, "channel", &d.channel)?,
        ll: string(v, "ll", &d.ll)?,
    })
}

fn arr<'a>(v: &'a Value, key: &str) -> Result<&'a [Value], String> {
    match v.get(key) {
        None | Some(Value::Null) => Ok(&[]),
        Some(Value::Arr(a)) => Ok(a),
        Some(_) => Err(format!("'{key}' must be a list")),
    }
}

fn num(v: &Value, key: &str, default: f64) -> Result<f64, String> {
    match v.get(key) {
        None => Ok(default),
        Some(Value::Num(n)) => Ok(*n),
        Some(_) => Err(format!("'{key}' must be a number")),
    }
}

/// Integer field. `null`/missing -> `default`.
fn int(v: &Value, key: &str, default: Option<i64>) -> Result<Option<i64>, String> {
    match v.get(key) {
        None | Some(Value::Null) => Ok(default),
        Some(Value::Num(n)) if n.fract() == 0.0 && n.abs() < 9e15 => Ok(Some(*n as i64)),
        Some(_) => Err(format!("'{key}' must be a whole number")),
    }
}

fn string(v: &Value, key: &str, default: &str) -> Result<String, String> {
    match v.get(key) {
        None => Ok(default.to_string()),
        Some(Value::Str(s)) => Ok(s.clone()),
        Some(_) => Err(format!("'{key}' must be a string")),
    }
}

fn boolean(v: &Value, key: &str, default: bool) -> Result<bool, String> {
    match v.get(key) {
        None => Ok(default),
        Some(Value::Bool(b)) => Ok(*b),
        Some(_) => Err(format!("'{key}' must be true or false")),
    }
}
