"""
models.py
Shared data structures, normalization helpers, and constants.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional, Set
import hashlib
import json

AFI4 = "ipv4"
AFI6 = "ipv6"

@dataclass(frozen=True)
class NH:
    nh: str
    iface: Optional[str]

def normalize_communities(comms) -> List[str]:
    """
    Normalize BGP communities to a sorted list of strings.
    Supports std/ext/large forms; input can be list/str/mixed.
    """
    if not comms:
        return []
    if isinstance(comms, str):
        items = [c.strip() for c in comms.split() if c.strip()]
    elif isinstance(comms, list):
        items = []
        for c in comms:
            if c is None:
                continue
            items.extend(str(c).split())
    else:
        items = [str(comms)]
    return sorted(set(items))

def set_hash(values: List[str]) -> str:
    """
    Return a stable hash for potentially large lists (e.g., communities).
    """
    m = hashlib.sha256()
    for v in values:
        m.update(v.encode())
        m.update(b"\x00")
    return m.hexdigest()

@dataclass
class RIBEntry:
    device: str
    vrf: str
    afi: str
    prefix: str
    protocol: str
    distance: Optional[int]
    metric: Optional[int]
    best: bool
    nexthops: Set[NH] = field(default_factory=set)

    def key(self) -> Tuple[str, str, str, str]:
        return (self.vrf, self.afi, self.prefix, self.protocol)

    def serialize(self) -> Dict:
        return {
            "device": self.device,
            "vrf": self.vrf,
            "afi": self.afi,
            "prefix": self.prefix,
            "protocol": self.protocol,
            "distance": self.distance,
            "metric": self.metric,
            "best": self.best,
            "nexthops": sorted([{"nh": n.nh, "iface": n.iface} for n in self.nexthops], key=lambda x: (x["nh"], x["iface"] or "")),
        }

@dataclass
class BGPEntry:
    device: str
    vrf: str
    afi: str
    prefix: str
    best: bool
    nh: Optional[str]
    as_path: str
    local_pref: Optional[int]
    med: Optional[int]
    origin: Optional[str]
    communities: List[str]
    communities_hash: str
    weight: Optional[int]
    peer: Optional[str]
    originator_id: Optional[str] = None
    cluster_list: Optional[List[str]] = None

    def key(self) -> Tuple[str, str, str]:
        # Path-ID can be added here if your platform exposes it consistently.
        return (self.vrf, self.afi, self.prefix)

    def serialize(self) -> Dict:
        data = {
            "device": self.device,
            "vrf": self.vrf,
            "afi": self.afi,
            "prefix": self.prefix,
            "best": self.best,
            "nh": self.nh,
            "as_path": self.as_path,
            "local_pref": self.local_pref,
            "med": self.med,
            "origin": self.origin,
            "communities": self.communities[:64],  # truncate for readability
            "communities_hash": self.communities_hash,
            "weight": self.weight,
            "peer": self.peer,
        }
        if self.originator_id:
            data["originator_id"] = self.originator_id
        if self.cluster_list:
            data["cluster_list"] = self.cluster_list
        return data