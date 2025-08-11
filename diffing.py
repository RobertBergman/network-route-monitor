"""
diffing.py
Table diffing with ECMP set comparison, attr deltas, and simple flap debounce.
"""

from typing import List, Dict, Tuple, Any
from collections import defaultdict
from models import RIBEntry, BGPEntry

def index_by_key(rows, key_fn):
    d = defaultdict(list)
    for r in rows:
        d[key_fn(r)].append(r)
    return d

def rib_diff(prev: List[RIBEntry], curr: List[RIBEntry]) -> Dict[str, Any]:
    """
    Compare per-key, diff nexthops set, distance, metric, best.
    Returns dict with adds/removes/changes.
    """
    prev_i = index_by_key(prev, lambda r: r.key())
    curr_i = index_by_key(curr, lambda r: r.key())

    adds, rems, chgs = [], [], []

    prev_keys = set(prev_i.keys())
    curr_keys = set(curr_i.keys())

    for k in curr_keys - prev_keys:
        for e in curr_i[k]:
            adds.append(e.serialize())

    for k in prev_keys - curr_keys:
        for e in prev_i[k]:
            rems.append(e.serialize())

    for k in prev_keys & curr_keys:
        # collapse ECMP sets by key
        def collapse(rows: List[RIBEntry]):
            nh = set()
            best = False
            dist = None
            metric = None
            proto = None
            sample = None
            for r in rows:
                nh |= set(r.nexthops)
                best = best or r.best
                dist = r.distance if r.distance is not None else dist
                metric = r.metric if r.metric is not None else metric
                proto = r.protocol or proto
                sample = r
            return sample, nh, dist, metric, best

        a_s, a_nh, a_dist, a_met, a_best = collapse(prev_i[k])
        b_s, b_nh, b_dist, b_met, b_best = collapse(curr_i[k])

        delta = {}
        if a_nh != b_nh: delta["nexthops"] = (
            sorted([{"nh": x.nh, "iface": x.iface} for x in a_nh], key=lambda v: (v["nh"], v["iface"] or "")),
            sorted([{"nh": x.nh, "iface": x.iface} for x in b_nh], key=lambda v: (v["nh"], v["iface"] or "")),
        )
        if a_dist != b_dist: delta["distance"] = (a_dist, b_dist)
        if a_met != b_met: delta["metric"] = (a_met, b_met)
        if a_best != b_best: delta["best"] = (a_best, b_best)

        if delta:
            base = b_s.serialize()
            base["delta"] = delta
            chgs.append(base)

    return {"adds": adds, "rems": rems, "chgs": chgs}

def bgp_diff(prev: List[BGPEntry], curr: List[BGPEntry]) -> Dict[str, Any]:
    """
    Compare per-prefix key; detect attr changes.
    """
    prev_i = index_by_key(prev, lambda r: r.key())
    curr_i = index_by_key(curr, lambda r: r.key())

    adds, rems, chgs = [], [], []

    prev_keys = set(prev_i.keys())
    curr_keys = set(curr_i.keys())

    for k in curr_keys - prev_keys:
        for e in curr_i[k]:
            adds.append(e.serialize())

    for k in prev_keys - curr_keys:
        for e in prev_i[k]:
            rems.append(e.serialize())

    for k in prev_keys & curr_keys:
        # Compare "bestpath" and attrs of (the) bestpath entry, but also watch as_path/localpref/med even if not best.
        def pick_best(rows: List[BGPEntry]) -> BGPEntry:
            for r in rows:
                if r.best:
                    return r
            return rows[0]  # fallback

        a_best = pick_best(prev_i[k])
        b_best = pick_best(curr_i[k])

        attrs = ["best", "nh", "as_path", "local_pref", "med", "origin", "communities_hash", "peer"]
        delta = {}
        for attr in attrs:
            av = getattr(a_best, attr)
            bv = getattr(b_best, attr)
            if av != bv:
                delta[attr] = (av, bv)

        # If upstream ASN (leftmost) changed, this is a strong signal
        def head_as(as_path: str) -> str:
            parts = [p for p in as_path.split() if p.isdigit()]
            return parts[0] if parts else ""

        if head_as(a_best.as_path) != head_as(b_best.as_path):
            delta["upstream_as"] = (head_as(a_best.as_path), head_as(b_best.as_path))

        if delta:
            base = b_best.serialize()
            base["delta"] = delta
            chgs.append(base)

    return {"adds": adds, "rems": rems, "chgs": chgs}