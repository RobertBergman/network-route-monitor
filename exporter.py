"""
exporter.py
Prometheus exporter: periodically polls devices, updates metrics, and serves /metrics.
"""

import os, time, threading
from typing import Dict, Any
from prometheus_client import start_http_server, Gauge, Counter
from dotenv import load_dotenv
from poller import get_inventory, collect_and_persist_for_device
from storage import latest_path, read_latest

load_dotenv()

POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL_SEC", "60"))
PROM_PORT = int(os.environ.get("PROM_PORT", "9108"))

# Gauges (current snapshot)
ROUTE_COUNT = Gauge("route_count", "RIB route count", ["device","vrf","afi"])
BGP_BEST_COUNT = Gauge("bgp_best_count", "BGP bestpath entries", ["device","vrf","afi"])

# Counters (churn)
RIB_ADDS = Counter("rib_adds_total", "RIB adds", ["device","vrf","afi"])
RIB_REMS = Counter("rib_removes_total", "RIB removes", ["device","vrf","afi"])
BGP_ATTR_CHG = Counter("bgp_attr_changes_total", "BGP attribute changes", ["device","vrf","afi","attr"])
DEFAULT_NH_CHG = Counter("default_nexthop_change_total", "Default route nexthop change", ["device","vrf","afi"])
UPSTREAM_AS_CHG = Counter("upstream_as_change_total", "Upstream ASN change", ["device","vrf","afi","prefix"])

def is_default(prefix: str) -> bool:
    return prefix in ("0.0.0.0/0", "::/0")

def update_metrics(report: Dict[str, Any]):
    device = report.get("device")
    for vrf, afis in report.get("vrfs", {}).items():
        for afi, payload in afis.items():
            rib = payload["rib"]
            bgp = payload["bgp"]

            # Gauges
            # RIB count: use current latest snapshot for accuracy
            try:
                rib_latest = latest_path(os.environ.get("SNAPDIR","./route_snaps"), device, "rib", vrf, afi)
                rib_snap = read_latest(rib_latest) or []
                rib_count = len({(e["prefix"], e["protocol"]) for e in rib_snap})
            except Exception:
                rib_count = 0
            ROUTE_COUNT.labels(device=device, vrf=vrf, afi=afi).set(rib_count)

            # BGP best count: read from latest snapshot
            try:
                bgp_latest = latest_path(os.environ.get("SNAPDIR","./route_snaps"), device, "bgp", vrf, afi)
                bgp_snap = read_latest(bgp_latest) or []
                best_count = sum(1 for e in bgp_snap if e.get("best"))
            except Exception:
                best_count = 0
            BGP_BEST_COUNT.labels(device=device, vrf=vrf, afi=afi).set(best_count)

            # Counters
            RIB_ADDS.labels(device=device, vrf=vrf, afi=afi).inc(len(rib.get("adds", [])))
            RIB_REMS.labels(device=device, vrf=vrf, afi=afi).inc(len(rib.get("rems", [])))

            for chg in bgp.get("chgs", []):
                delta = chg.get("delta", {})
                for k in ("best","nh","as_path","local_pref","med","origin","communities_hash","peer"):
                    if k in delta:
                        BGP_ATTR_CHG.labels(device=device, vrf=vrf, afi=afi, attr=k).inc()
                if "upstream_as" in delta:
                    UPSTREAM_AS_CHG.labels(device=device, vrf=vrf, afi=afi, prefix=chg.get("prefix","")).inc()

                if is_default(chg.get("prefix","")) and "nh" in delta:
                    DEFAULT_NH_CHG.labels(device=device, vrf=vrf, afi=afi).inc()

def worker():
    while True:
        inv = get_inventory()
        for dev in inv:
            try:
                report = collect_and_persist_for_device(dev)
                update_metrics(report)
            except Exception:
                # don't crash exporter on device error
                pass
        time.sleep(POLL_INTERVAL)

def main():
    start_http_server(PROM_PORT)
    t = threading.Thread(target=worker, daemon=True)
    t.start()
    # Run forever
    t.join()

if __name__ == "__main__":
    main()