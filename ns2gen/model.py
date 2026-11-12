"""Scene model: plain dataclasses + JSON load/save. No GUI imports here."""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional

FORMAT_VERSION = 1

QUEUE_TYPES = ["DropTail", "RED", "FQ", "SFQ", "DRR"]
TCP_VARIANTS = ["TCP", "TCP/Reno", "TCP/Newreno", "TCP/Vegas", "TCP/Sack1"]
ROUTING = ["AODV", "DSDV", "DSR", "TORA"]
MAC_TYPES = ["Mac/802_11", "Mac/Simple"]
PROP_MODELS = ["Propagation/TwoRayGround", "Propagation/FreeSpace", "Propagation/Shadowing"]
IFQ_TYPES = ["Queue/DropTail/PriQueue", "Queue/DropTail", "CMUPriQueue"]
ANTENNAS = ["Antenna/OmniAntenna"]
PHY_TYPES = ["Phy/WirelessPhy"]
CHANNELS = ["Channel/WirelessChannel"]
LL_TYPES = ["LL"]


@dataclass
class Node:
    id: int
    x: float = 0.0
    y: float = 0.0
    label: str = ""


@dataclass
class Link:
    a: int
    b: int
    bandwidth: str = "1Mb"
    delay: str = "10ms"
    queue: str = "DropTail"
    duplex: bool = True
    queue_limit: Optional[int] = None


@dataclass
class Flow:
    """One traffic flow = agent + sink + application + connect."""
    src: int
    dst: int
    proto: str = "TCP"          # "TCP" | "UDP"
    tcp_variant: str = "TCP"    # used when proto == TCP
    app: str = "FTP"            # "FTP" | "CBR"
    start: float = 1.0
    stop: float = 4.0
    packet_size: int = 1000     # CBR only
    rate: str = "500k"          # CBR only (rate_)
    window: Optional[int] = None  # TCP window_ (optional)


@dataclass
class Movement:
    node: int
    time: float
    x: float
    y: float
    speed: float = 5.0


@dataclass
class Settings:
    mode: str = "wired"            # "wired" | "wireless"
    stop_time: float = 5.0
    trace_file: str = "out.tr"
    nam_file: str = "out.nam"
    run_nam: bool = True
    width: float = 800.0           # topology / canvas world size
    height: float = 600.0
    # wireless
    routing: str = "AODV"
    mac: str = "Mac/802_11"
    prop: str = "Propagation/TwoRayGround"
    ifq: str = "Queue/DropTail/PriQueue"
    ifq_len: int = 50
    antenna: str = "Antenna/OmniAntenna"
    phy: str = "Phy/WirelessPhy"
    channel: str = "Channel/WirelessChannel"
    ll: str = "LL"


@dataclass
class Scene:
    settings: Settings = field(default_factory=Settings)
    nodes: List[Node] = field(default_factory=list)
    links: List[Link] = field(default_factory=list)
    flows: List[Flow] = field(default_factory=list)
    movements: List[Movement] = field(default_factory=list)

    # ---- helpers -------------------------------------------------------
    def node_by_id(self, nid: int) -> Optional[Node]:
        for n in self.nodes:
            if n.id == nid:
                return n
        return None

    def next_node_id(self) -> int:
        return max((n.id for n in self.nodes), default=-1) + 1

    def add_node(self, x: float, y: float) -> Node:
        n = Node(self.next_node_id(), x, y)
        self.nodes.append(n)
        return n

    def remove_node(self, nid: int) -> None:
        self.nodes = [n for n in self.nodes if n.id != nid]
        self.links = [l for l in self.links if nid not in (l.a, l.b)]
        self.flows = [f for f in self.flows if nid not in (f.src, f.dst)]
        self.movements = [m for m in self.movements if m.node != nid]

    def find_link(self, a: int, b: int) -> Optional[Link]:
        for l in self.links:
            if (l.a, l.b) == (a, b) or (l.a, l.b) == (b, a):
                return l
        return None

    # ---- persistence ---------------------------------------------------
    def to_dict(self) -> Dict:
        return {
            "format": FORMAT_VERSION,
            "settings": asdict(self.settings),
            "nodes": [asdict(n) for n in self.nodes],
            "links": [asdict(l) for l in self.links],
            "flows": [asdict(f) for f in self.flows],
            "movements": [asdict(m) for m in self.movements],
        }

    @staticmethod
    def from_dict(d: Dict) -> "Scene":
        def build(cls, items):
            names = set(cls.__dataclass_fields__)
            return [cls(**{k: v for k, v in i.items() if k in names}) for i in items]

        s_names = set(Settings.__dataclass_fields__)
        settings = Settings(**{k: v for k, v in d.get("settings", {}).items() if k in s_names})
        return Scene(
            settings=settings,
            nodes=build(Node, d.get("nodes", [])),
            links=build(Link, d.get("links", [])),
            flows=build(Flow, d.get("flows", [])),
            movements=build(Movement, d.get("movements", [])),
        )

    def save(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(self.to_dict(), fh, indent=2)

    @staticmethod
    def load(path: str) -> "Scene":
        with open(path, "r", encoding="utf-8") as fh:
            return Scene.from_dict(json.load(fh))
