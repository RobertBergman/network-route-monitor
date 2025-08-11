"""
poller.py
Periodic collector: polls devices, computes diffs, writes snapshots & diff archives.
Use --once for a single run (prints a JSON report).
"""

import os, time, argparse, gzip
from typing import List, Dict, Any
import ujson as json
from dotenv import load_dotenv

from parsers import collect_device_tables
from storage import (
    ensure_dir, device_root, table_dir, diffs_dir,
    latest_path, ts_gz_path, write_latest, write_gz, read_latest
)
from diffing import rib_diff, bgp_diff
from models import RIBEntry, BGPEntry, AFI4, AFI6

load_dotenv()

SNAPDIR = os.environ.get("SNAPDIR", "./route_snaps")

# --- Static fallback inventory (if not using NetBox) ---
STATIC_DEVICES = [
    # DevNet Always-On NX-OS Sandbox
    {"device_type":"cisco_nxos","host":"sbx-nxos-mgmt.cisco.com","username":"admin",
     "password":"Admin_1234!","name":"sbx-nxos"},
]
STATIC_VRFS = ["default", "CUSTOMER_A"]
STATIC_AFIS = [AFI4, AFI6]

def get_inventory():
    use_nb = os.environ.get("USE_NETBOX", "false").lower() == "true"
    if use_nb:
        from inventory_netbox import inventory
        return list(inventory())
    else:
        out = []
        for d in STATIC_DEVICES:
            out.append({**d, "vrfs": STATIC_VRFS, "afis": STATIC_AFIS})
        return out

def serialize_rib(rows: List[RIBEntry]) -> List[Dict]:
    return [r.serialize() for r in rows]

def serialize_bgp(rows: List[BGPEntry]) -> List[Dict]:
    return [r.serialize() for r in rows]

def collect_and_persist_for_device(dev: Dict) -> Dict[str, Any]:
    device = dev["name"]
    vrfs: List[str] = dev.get("vrfs") or ["default"]
    afis: List[str] = dev.get("afis") or [AFI4, AFI6]

    ensure_dir(device_root(SNAPDIR, device))
    ensure_dir(table_dir(SNAPDIR, device, "rib"))
    ensure_dir(table_dir(SNAPDIR, device, "bgp"))
    ensure_dir(diffs_dir(SNAPDIR, device))

    tables = collect_device_tables(dev, vrfs, afis)
    rib_rows: List[RIBEntry] = tables["rib"]
    bgp_rows: List[BGPEntry] = tables["bgp"]

    report = {"device": device, "vrfs": {}}

    for vrf in vrfs:
        for afi in afis:
            # Filter by vrf/afi
            rib_now = [r for r in rib_rows if r.vrf == vrf and r.afi == afi]
            bgp_now = [b for b in bgp_rows if b.vrf == vrf and b.afi == afi]

            rib_latest = latest_path(SNAPDIR, device, "rib", vrf, afi)
            bgp_latest = latest_path(SNAPDIR, device, "bgp", vrf, afi)

            prev_rib_ser = read_latest(rib_latest) or []
            prev_bgp_ser = read_latest(bgp_latest) or []

            # Re-hydrate is not needed; compare serialized by fields we care about
            rib_d = rib_diff(prev=[], curr=rib_now) if not prev_rib_ser else rib_diff(
                prev=[RIBEntry(
                    device=x["device"], vrf=x["vrf"], afi=x["afi"], prefix=x["prefix"],
                    protocol=x["protocol"], distance=x.get("distance"), metric=x.get("metric"),
                    best=x.get("best", False),
                    nexthops=set([tuple(sorted([(nh["nh"], nh.get("iface")) for nh in x.get("nexthops", [])]))]) and
                              set()  # we won't use this path—see below
                ) for x in []],  # intentionally unused; we compare on serialized rows below
                curr=rib_now
            )
            # Since RIBEntry contains sets of dataclasses, we rely on diffing from current normalized rows
            # and the previous serialized is only used for storage/read. For a complete historical diff on restart,
            # simply using serialized rows in prior run is sufficient when using our diff shape below.

            # Better: load prev serialized and compare as dicts (lightweight)
            prev_rib_simple = prev_rib_ser
            curr_rib_simple = [r.serialize() for r in rib_now]

            # Simple dict-level diff for RIB (same fields as RIBEntry.serialize())
            def rib_simple_diff(prev, curr):
                from itertools import groupby
                import json
                key = lambda e: (e["vrf"], e["afi"], e["prefix"], e["protocol"])
                prev_sorted = sorted(prev, key=key)
                curr_sorted = sorted(curr, key=key)
                adds, rems, chgs = [], [], []
                pi = {key(e): e for e in prev_sorted}
                ci = {key(e): e for e in curr_sorted}
                for k in ci.keys() - pi.keys():
                    adds.append(ci[k])
                for k in pi.keys() - ci.keys():
                    rems.append(pi[k])
                for k in pi.keys() & ci.keys():
                    a, b = pi[k], ci[k]
                    delta = {}
                    if a.get("nexthops") != b.get("nexthops"): delta["nexthops"] = (a.get("nexthops"), b.get("nexthops"))
                    if a.get("distance") != b.get("distance"): delta["distance"] = (a.get("distance"), b.get("distance"))
                    if a.get("metric") != b.get("metric"):     delta["metric"]   = (a.get("metric"), b.get("metric"))
                    if a.get("best") != b.get("best"):         delta["best"]     = (a.get("best"), b.get("best"))
                    if delta:
                        chgs.append({**b, "delta": delta})
                return {"adds": adds, "rems": rems, "chgs": chgs}

            rib_d = rib_simple_diff(prev_rib_simple, curr_rib_simple)

            # BGP simple diff (serialized)
            prev_bgp_simple = prev_bgp_ser
            curr_bgp_simple = [b.serialize() for b in bgp_now]

            def head_as(as_path: str) -> str:
                parts = [p for p in (as_path or "").split() if p.isdigit()]
                return parts[0] if parts else ""

            def bgp_simple_diff(prev, curr):
                key = lambda e: (e["vrf"], e["afi"], e["prefix"])
                pi = {key(e): e for e in prev}
                ci = {key(e): e for e in curr}
                adds, rems, chgs = [], [], []
                for k in ci.keys() - pi.keys():
                    adds.append(ci[k])
                for k in pi.keys() - ci.keys():
                    rems.append(pi[k])
                for k in pi.keys() & ci.keys():
                    a, b = pi[k], ci[k]
                    attrs = ["best","nh","as_path","local_pref","med","origin","communities_hash","peer"]
                    delta = {}
                    for attr in attrs:
                        if a.get(attr) != b.get(attr):
                            delta[attr] = (a.get(attr), b.get(attr))
                    if head_as(a.get("as_path","")) != head_as(b.get("as_path","")):
                        delta["upstream_as"] = (head_as(a.get("as_path","")), head_as(b.get("as_path","")))
                    if delta:
                        chgs.append({**b, "delta": delta})
                return {"adds": adds, "rems": rems, "chgs": chgs}

            bgp_d = bgp_simple_diff(prev_bgp_simple, curr_bgp_simple)

            # Persist latest & archives
            write_latest(rib_latest, curr_rib_simple)
            write_latest(bgp_latest, curr_bgp_simple)

            # Timestamped archives
            write_gz(ts_gz_path(SNAPDIR, device, "rib", vrf, afi), curr_rib_simple)
            write_gz(ts_gz_path(SNAPDIR, device, "bgp", vrf, afi), curr_bgp_simple)

            # Diff archives (compact)
            diff_payload = {"device": device, "vrf": vrf, "afi": afi, "rib": rib_d, "bgp": bgp_d}
            write_gz(os.path.join(diffs_dir(SNAPDIR, device), f"{vrf}.{afi}.{time.strftime('%Y%m%d%H%M%S', time.gmtime())}.json.gz"), diff_payload)

            report["vrfs"].setdefault(vrf, {})[afi] = diff_payload

    return report

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true", help="Run a single collection and print report")
    args = ap.parse_args()

    inv = get_inventory()
    reports = []
    for dev in inv:
        try:
            reports.append(collect_and_persist_for_device(dev))
        except Exception as e:
            reports.append({"device": dev["name"], "error": str(e)})

    if args.once:
        print(json.dumps(reports, indent=2))
    else:
        interval = int(os.environ.get("POLL_INTERVAL_SEC", "60"))
        # Daemon loop
        while True:
            start = time.time()
            inv = get_inventory()
            for dev in inv:
                try:
                    collect_and_persist_for_device(dev)
                except Exception:
                    pass
            elapsed = time.time() - start
            sleep_for = max(1, interval - int(elapsed))
            time.sleep(sleep_for)

if __name__ == "__main__":
    main()