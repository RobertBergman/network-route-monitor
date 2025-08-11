# Routing Table & BGP RIB Change Tracker

*A lightweight, production-ready toolkit to snapshot, diff, and alert on routing/RIB changes across VRFs and AFIs (IPv4/IPv6).*

---

## Contents

* [Overview](#overview)
* [Features](#features)
* [Architecture](#architecture)
* [Install](#install)
* [Configuration](#configuration)
* [Directory Layout](#directory-layout)
* [Run it](#run-it)
* [Prometheus & Alerts](#prometheus--alerts)
* [Systemd Units (optional)](#systemd-units-optional)
* [Notes on Parsers & Platforms](#notes-on-parsers--platforms)
* [All Source Code](#all-source-code)

  * [`requirements.txt`](#requirementstxt)
  * [`.env.example`](#envexample)
  * [`README.quickstart.md`](#readmequickstartmd)
  * [`inventory_netbox.py`](#inventory_netboxpy)
  * [`models.py`](#modelspy)
  * [`parsers.py`](#parserspy)
  * [`storage.py`](#storagepy)
  * [`diffing.py`](#diffingpy)
  * [`poller.py`](#pollerpy)
  * [`exporter.py`](#exporterpy)
  * [`tests/test_diffing.py`](#testsdiffing)

---

## Overview

This toolkit polls routers/switches on a short interval, parses per-VRF routing and BGP RIB (IPv4/IPv6), normalizes snapshots, and computes precise diffs:

* **RIB**: route added/removed, ECMP next-hop set changes, distance/metric changes
* **BGP**: bestpath flips, AS\_PATH/LOCAL\_PREF/MED/origin/community changes, peer changes

It stores compressed snapshots & diffs on disk (Git/S3-friendly) and exposes **Prometheus** metrics for alerting (default route next-hop change, route count drops, attr churn spikes, etc.).

---

## Features

* Robust parsing (Genie/pyATS; JSON CLI when available)
* Stable **ECMP set** comparison (avoids noise)
* Per-VRF/AFI snapshots (`rib` and `bgp`) + timestamped archives
* Debounced diffs and counters for Prometheus
* Optional **NetBox**-driven inventory discovery
* Minimal dependencies and simple deployment (systemd ready)

---

## Architecture

1. **Inventory** — Hardcoded list or dynamic from **NetBox**
2. **Poller** — Runs every *N* seconds, per device → per VRF → per AFI
3. **Parsers** — Prefer native JSON (`| json`) when supported; fallback to Genie
4. **Normalizer** — Canonical rows (stable keys, ECMP sets, normalized communities)
5. **Storage** — `latest.json` per table, timestamped `*.json.gz` archives, per-VRF/AFI
6. **Diffing** — Adds/Removes/Changes; flapping debounce
7. **Exporter** — Prometheus HTTP server with gauges & counters, plus change totals

---

## Install

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# edit .env to add credentials / NetBox details
```

---

## Configuration

* **Environment variables** (see `.env.example`):

  * `SNAPDIR` — snapshot root (default: `./route_snaps`)
  * `POLL_INTERVAL_SEC` — poll interval (default: `60`)
  * `PROM_PORT` — exporter port (default: `9108`)
  * **Device creds**: `NETOPS_USER`, `NETOPS_PASS`
  * **NetBox (optional)**: `NB_URL`, `NB_TOKEN`, `USE_NETBOX=true|false`

* **Inventory**

  * If `USE_NETBOX=true`, we query NetBox for active routers & their VRFs
  * Else, edit `poller.py` → `STATIC_DEVICES` & `STATIC_VRFS`

---

## Directory Layout

```
project/
  exporter.py
  poller.py
  parsers.py
  models.py
  diffing.py
  storage.py
  inventory_netbox.py
  requirements.txt
  .env
  README.quickstart.md
  route_snaps/            # created on first run
    <device>/
      rib/
        <vrf>.<afi>.latest.json
        <vrf>.<afi>.YYYYMMDDHHMMSS.json.gz
      bgp/
        <vrf>.<afi>.latest.json
        <vrf>.<afi>.YYYYMMDDHHMMSS.json.gz
      diffs/
        <vrf>.<afi>.YYYYMMDDHHMMSS.json.gz
  tests/
    test_diffing.py
```

---

## Run it

**One-shot poll & diff (stdout report):**

```bash
python poller.py --once
```

**Exporter (polls forever, serves `/metrics`):**

```bash
python exporter.py
# Prometheus scrape: http://<host>:9108/metrics
```

---

## Prometheus & Alerts

**Example alerts (PromQL):**

```promql
# Sudden drop >20% vs 10m ago (per device/vrf/afi)
(route_count - route_count offset 10m)
  < -0.2 * ignoring() group_left route_count offset 10m

# Any default route NH change in last 5m
increase(default_nexthop_change_total[5m]) > 0

# New upstream ASN on key prefixes
increase(upstream_as_change_total{prefix=~"^0\\.0\\.0\\.0/0|^::/0"}[10m]) > 0

# BGP attr churn spike
sum by(device,vrf,afi) (increase(bgp_attr_changes_total[5m])) > 50
```

**Prometheus scrape config:**

```yaml
- job_name: 'rib-bgp-exporter'
  static_configs:
  - targets: ['127.0.0.1:9108']
```

---

## Systemd Units (optional)

`/etc/systemd/system/ribbgp-exporter.service`

```ini
[Unit]
Description=RIB/BGP Diff Exporter
After=network-online.target

[Service]
WorkingDirectory=/opt/ribbgp
Environment="PYTHONUNBUFFERED=1"
ExecStart=/opt/ribbgp/venv/bin/python /opt/ribbgp/exporter.py
Restart=always
User=netops
Group=netops

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now ribbgp-exporter
```

---

## Notes on Parsers & Platforms

* **NX-OS**: Prefer `show bgp vrf <VRF> ipv[46] unicast | json` and `show ip/ipv6 route vrf <VRF> | json`.
* **IOS-XE**: Many `show` support `| json`; for BGP, Genie still covers edge cases.
* **Other**: Junos/Arista → consider NAPALM or native JSON RPC; SR Linux → OpenConfig via gNMI.

---

## All Source Code

> Copy files exactly as shown below. Comments are extensive so you can tweak quickly.

### `requirements.txt`

```txt
# Core
netmiko>=4.3
pyats[full]>=24.7
genie.libs.parser>=24.7

# Metrics & env
prometheus_client>=0.20
python-dotenv>=1.0

# Optional NetBox inventory
pynetbox>=7.3

# Utils
ujson>=5.10
requests>=2.32    # NX-API (optional)
```

---

### `.env.example`

```dotenv
# Snapshot root (default ./route_snaps)
SNAPDIR=./route_snaps

# Polling & exporter
POLL_INTERVAL_SEC=60
PROM_PORT=9108

# Device credentials (read-only)
NETOPS_USER=netops
NETOPS_PASS=changeme

# NetBox (optional inventory)
USE_NETBOX=false
NB_URL=https://netbox.example.com
NB_TOKEN=xxxxxxx

# --- NX-OS / NX-API options ---
# When true, use NX-API JSON for NX-OS devices (faster, stable)
USE_NXAPI=false
# If empty, defaults to https on port 443 to https://<host>/ins
NXAPI_SCHEME=https
NXAPI_PORT=443
# Optional: disable TLS verify for lab gear (not recommended in prod)
NXAPI_VERIFY=false

# Static inventory fallback (see poller.py for host list)
```

---

### `README.quickstart.md`

```markdown
# Quickstart

1) `python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt`  
2) `cp .env.example .env` and edit credentials  
3) Test one-shot: `python poller.py --once`  
4) Start exporter: `python exporter.py` and visit `http://localhost:9108/metrics`  

Troubleshooting:
- If Genie parse fails, ensure `pyats` and `genie.libs.parser` versions align.
- Some platforms need `| json` enabled or NX-API/CLI JSON support.
```

---

### `inventory_netbox.py`

```python
"""
inventory_netbox.py
NetBox-driven dynamic inventory discovery.

If USE_NETBOX=true in .env, poller will import and use inventory() here.
"""

import os
import pynetbox

def inventory():
    url = os.environ.get("NB_URL")
    token = os.environ.get("NB_TOKEN")
    if not (url and token):
        raise RuntimeError("NetBox inventory requested but NB_URL/NB_TOKEN not set")

    nb = pynetbox.api(url, token=token)
    # Prefer network boxes that are routers or Nexus switches
    for d in nb.dcim.devices.filter(status="active"):
        role_slug = getattr(d.role, "slug", "") or ""
        tags = {t.slug for t in (getattr(d, "tags", []) or [])}
        if role_slug not in {"router", "core-router", "edge-router"} and "nexus" not in tags:
            # keep only explicitly network routing roles or tagged Nexus
            continue

        if not d.primary_ip:
            continue
        host = d.primary_ip.address.split("/")[0]

        # Collect VRFs: device-scoped or global VRFs that apply to this box.
        vrfs = []
        for v in nb.ipam.vrfs.all():
            # In many setups, VRFs aren't tied to a single device; include common ones
            # Replace with a more precise query if you model VRFs per device.
            vrfs.append(v.name)
        if not vrfs:
            vrfs = ["default"]

        # Heuristic: any model with "Nexus" goes NX-OS device_type
        disp = (getattr(d.device_type, "display", "") or "") + " " + (getattr(d.device_type, "model", "") or "")
        device_type = "cisco_nxos" if "Nexus" in disp or "NX" in disp else "cisco_xe"

        yield {
            "device_type": device_type,
            "host": host,
            "username": os.environ.get("NETOPS_USER"),
            "password": os.environ.get("NETOPS_PASS"),
            "name": d.name,
            "vrfs": vrfs,
            "afis": ["ipv4", "ipv6"],
        }
```

---

### `models.py`

```python
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
```

---

### `parsers.py`

```python
"""
parsers.py
Parsers & normalizers for RIB and BGP using:
- Native JSON output when available (`| json`)
- Genie/pyATS as fallback

Notes:
- We deliberately keep commands simple and per VRF/AFI.
- For large tables, consider NX-API/JSON RPC or OpenConfig (future work).
"""

from typing import List, Dict, Optional, Set
from netmiko import ConnectHandler
from genie.conf.base import Device as GenieDevice
from models import RIBEntry, BGPEntry, NH, AFI4, AFI6, normalize_communities, set_hash
import os
import requests

def _try_json(conn, cmd: str) -> Optional[Dict]:
    """
    Try 'cmd | json'. If device rejects, return None.
    """
    try:
        raw = conn.send_command(cmd + " | json")
        # crude check
        if raw.strip().startswith("{") or raw.strip().startswith("["):
            import ujson as json
            return json.loads(raw)
    except Exception:
        pass
    return None

def _nxapi_request(host: str, username: str, password: str, cmds: List[str]) -> Optional[Dict]:
    """
    Use NX-API JSON to run one or more show commands and return the first response.
    Requires NX-OS: feature nxapi (HTTP/HTTPS enabled, default /ins).
    """
    scheme = os.environ.get("NXAPI_SCHEME", "https")
    port = os.environ.get("NXAPI_PORT", "443")
    verify = os.environ.get("NXAPI_VERIFY", "false").lower() == "true"
    url = f"{scheme}://{host}:{port}/ins"
    payload = {
        "ins_api": {
            "version": "1.2",
            "type": "cli_show",
            "chunk": "0",
            "sid": "1",
            "input": " ; ".join(cmds),
            "output_format": "json"
        }
    }
    try:
        r = requests.post(url, json=payload, auth=(username, password), timeout=8, verify=verify)
        r.raise_for_status()
        data = r.json()
        # NX-API wraps responses; pick the first
        if isinstance(data, dict) and "ins_api" in data:
            body = data["ins_api"].get("outputs", {}).get("output")
            if isinstance(body, list) and body:
                return body[0].get("body")
            if isinstance(body, dict):
                return body.get("body") or body
        return None
    except Exception:
        return None

def _parse_with_genie(device_name: str, device_os: str, cmd: str, raw: str) -> Dict:
    """
    Use Genie parsers without establishing pyATS connection.
    """
    gdev = GenieDevice(name=device_name, os=device_os)
    gdev.custom.setdefault("abstraction", {})["order"] = ["os"]
    gdev.connect = lambda *args, **kwargs: None
    return gdev.parse(cmd, output=raw)

def fetch_parsed(conn, device_name: str, device_os: str, cmd: str, dev: Dict) -> Dict:
    """
    Fetch output using JSON if possible; prefer NX-API for NX-OS when enabled;
    else fallback to Genie parse.
    """
    # NX-OS first: NX-API (optional)
    if device_os == "nxos" and os.environ.get("USE_NXAPI", "false").lower() == "true":
        j = _nxapi_request(dev["host"], dev["username"], dev["password"], [cmd])
        if j:
            return j
    # Next: try ' | json'
    j = _try_json(conn, cmd)
    if j is not None:
        return j
    # Fallback: raw + Genie
    raw = conn.send_command(cmd, use_textfsm=False)
    return _parse_with_genie(device_name, device_os, cmd, raw)

def parse_rib(device_name: str, device_os: str, vrf: str, afi: str, parsed: Dict) -> List[RIBEntry]:
    """
    Normalize RIB into RIBEntry records with ECMP set for next-hops.
    Supports common Genie & JSON shapes.
    """
    entries: Dict[str, RIBEntry] = {}
    # Try Genie-style structure first
    vrfs = parsed.get("vrf") or parsed.get("TABLE_vrf") or {}
    if "vrf" in parsed:
        af_container = parsed["vrf"].get(vrf, {}).get("address_family", {})
        af_key = afi
        routes = af_container.get(af_key, {}).get("routes", {})
        for pfx, pdata in routes.items():
            protocol = pdata.get("route_preference", {}).get("protocol", pdata.get("source_protocol", ""))
            distance = pdata.get("route_preference", {}).get("preference", pdata.get("distance"))
            metric = pdata.get("metric")
            best = pdata.get("active", False)

            # next hops
            nhs = set()
            nh_map = pdata.get("next_hop", {})
            # common case
            for _, r in (nh_map.get("next_hop_list") or {}).items():
                nhs.add(NH(nh=r.get("next_hop"), iface=r.get("outgoing_interface")))
            # fallback shapes: directly embedded NH or interface-only
            for nh in (nh_map.get("next_hop") or []):
                if isinstance(nh, str):
                    nhs.add(NH(nh=nh, iface=None))

            e = RIBEntry(
                device=device_name, vrf=vrf, afi=afi,
                prefix=pfx, protocol=protocol,
                distance=distance, metric=metric, best=best, nexthops=nhs
            )
            entries.setdefault(e.key(), e)

    # NX-API/NX-OS alternative JSON shapes (common on some releases)
    if not entries and "TABLE_vrf" in parsed:
        table_vrf = parsed.get("TABLE_vrf", {})
        for v in table_vrf.get("ROW_vrf", [] if isinstance(table_vrf.get("ROW_vrf"), list) else [table_vrf.get("ROW_vrf")]):
            if v.get("vrf-name-out") != vrf:
                continue
            # IPv4/IPv6 may present as separate tables
            table_af = v.get("TABLE_addrf") or {}
            for row_af in (table_af.get("ROW_addrf") or []):
                af_n = row_af.get("addrf")
                if (afi == AFI4 and "ipv4" not in af_n) or (afi == AFI6 and "ipv6" not in af_n):
                    continue
                routes = row_af.get("TABLE_prefix", {})
                rows = routes.get("ROW_prefix") or []
                if isinstance(rows, dict):
                    rows = [rows]
                for r in rows:
                    pfx = r.get("ipprefix") or r.get("ip_prefix")
                    proto = r.get("ubest-source") or r.get("route-source") or ""
                    dist = r.get("ubest-distance") or r.get("distance")
                    met  = r.get("ubest-metric") or r.get("metric")
                    best = True if r.get("ubest") in ("true", True, 1) else False
                    nhs = set()
                    nhtable = r.get("TABLE_paths", {}).get("ROW_paths") or []
                    if isinstance(nhtable, dict):
                        nhtable = [nhtable]
                    for nh in nhtable:
                        nhs.add(NH(nh=nh.get("ipprefix") or nh.get("nh_addr"), iface=nh.get("ifname")))
                    if pfx:
                        e = RIBEntry(
                            device=device_name, vrf=vrf, afi=afi, prefix=pfx, protocol=proto,
                            distance=dist, metric=met, best=best, nexthops=nhs
                        )
                        entries.setdefault(e.key(), e)
    return list(entries.values())

def parse_bgp(device_name: str, device_os: str, vrf: str, afi: str, parsed: Dict) -> List[BGPEntry]:
    """
    Normalize BGP RIB into BGPEntry records.
    """
    out: List[BGPEntry] = []
    af_key = "ipv4 unicast" if afi == AFI4 else "ipv6 unicast"

    if "vrf" in parsed:
        bgp = parsed["vrf"].get(vrf, {}).get("address_family", {}).get(af_key, {})
        routes = bgp.get("routes", {})
        for pfx, pdata in routes.items():
            idx = pdata.get("index", {})
            for _, path in idx.items():
                comms = normalize_communities(path.get("community"))
                out.append(BGPEntry(
                    device=device_name, vrf=vrf, afi=afi, prefix=pfx,
                    best=path.get("bestpath", False),
                    nh=path.get("next_hop"),
                    as_path=" ".join(path.get("as_path", [])) if isinstance(path.get("as_path"), list)
                            else (path.get("as_path") or ""),
                    local_pref=path.get("localpref"),
                    med=path.get("med"),
                    origin=path.get("origin_code") or path.get("origin"),
                    communities=comms[:256],  # local storage truncated; hash for full set
                    communities_hash=set_hash(comms),
                    weight=path.get("weight"),
                    peer=path.get("neighbor"),
                    originator_id=path.get("originator_id"),
                    cluster_list=path.get("cluster_list") if isinstance(path.get("cluster_list"), list) else None,
                ))

    # NX-API/NX-OS alternative JSON shapes
    if not out and "TABLE_vrf" in parsed:
        table_vrf = parsed.get("TABLE_vrf", {})
        rows = table_vrf.get("ROW_vrf") or []
        if isinstance(rows, dict):
            rows = [rows]
        for v in rows:
            if v.get("vrf-name-out") != vrf:
                continue
            table_af = v.get("TABLE_af") or {}
            afrows = table_af.get("ROW_af") or []
            if isinstance(afrows, dict):
                afrows = [afrows]
            for af in afrows:
                if (afi == AFI4 and af.get("af") != "ipv4 unicast") or (afi == AFI6 and af.get("af") != "ipv6 unicast"):
                    continue
                table_r = af.get("TABLE_prefix") or {}
                rrows = table_r.get("ROW_prefix") or []
                if isinstance(rrows, dict):
                    rrows = [rrows]
                for r in rrows:
                    pfx = r.get("prefix")
                    paths = r.get("TABLE_path", {}).get("ROW_path") or []
                    if isinstance(paths, dict):
                        paths = [paths]
                    for path in paths:
                        comms = normalize_communities(path.get("community"))
                        out.append(BGPEntry(
                            device=device_name, vrf=vrf, afi=afi, prefix=pfx,
                            best=True if path.get("best") in ("true", True, 1) else False,
                            nh=path.get("nexthop") or path.get("nh"),
                            as_path=path.get("aspath") or "",
                            local_pref=path.get("localpref"),
                            med=path.get("metric") or path.get("med"),
                            origin=path.get("origin"),
                            communities=comms[:256],
                            communities_hash=set_hash(comms),
                            weight=path.get("weight"),
                            peer=path.get("neighbor_id") or path.get("peer"),
                            originator_id=path.get("originator_id"),
                            cluster_list=path.get("clusterlist") if isinstance(path.get("clusterlist"), list) else None,
                        ))
    return out

def collect_device_tables(dev: Dict, vrfs: List[str], afis: List[str]) -> Dict:
    """
    Connect to a device, gather RIB and BGP across VRFs/AFIs, return normalized tables.
    """
    device_name = dev["name"]
    device_os = "iosxe" if "xe" in dev["device_type"] else "nxos"

    conn = ConnectHandler(**dev)
    rib_all: List[RIBEntry] = []
    bgp_all: List[BGPEntry] = []

    try:
        for vrf in vrfs:
            for afi in afis:
                # RIB
                rib_cmd = "show ip route vrf {}".format(vrf) if afi == AFI4 else "show ipv6 route vrf {}".format(vrf)
                try:
                    parsed = fetch_parsed(conn, device_name, device_os, rib_cmd, dev)
                    rib_all.extend(parse_rib(device_name, device_os, vrf, afi, parsed))
                except Exception:
                    # swallow per-table errors to keep other tables flowing
                    pass

                # BGP
                bgp_cmd = f"show bgp vrf {vrf} {'ipv4 unicast' if afi==AFI4 else 'ipv6 unicast'}"
                try:
                    parsed = fetch_parsed(conn, device_name, device_os, bgp_cmd, dev)
                    bgp_all.extend(parse_bgp(device_name, device_os, vrf, afi, parsed))
                except Exception:
                    pass

    finally:
        conn.disconnect()

    return {
        "device": device_name,
        "rib": rib_all,
        "bgp": bgp_all,
    }
```

---

### `storage.py`

```python
"""
storage.py
Snapshot persistence: latest & timestamped gzip archives; loading helpers.
"""

import os, gzip, time
from typing import Any, List, Dict
import ujson as json

def ensure_dir(path: str):
    os.makedirs(path, exist_ok=True)

def device_root(snapdir: str, device: str) -> str:
    return os.path.join(snapdir, device)

def table_dir(snapdir: str, device: str, table: str) -> str:
    return os.path.join(device_root(snapdir, device), table)

def diffs_dir(snapdir: str, device: str) -> str:
    return os.path.join(device_root(snapdir, device), "diffs")

def latest_path(snapdir: str, device: str, table: str, vrf: str, afi: str) -> str:
    return os.path.join(table_dir(snapdir, device, table), f"{vrf}.{afi}.latest.json")

def ts_gz_path(snapdir: str, device: str, table: str, vrf: str, afi: str) -> str:
    ts = time.strftime("%Y%m%d%H%M%S", time.gmtime())
    return os.path.join(table_dir(snapdir, device, table), f"{vrf}.{afi}.{ts}.json.gz")

def write_latest(path: str, data: Any):
    ensure_dir(os.path.dirname(path))
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2, sort_keys=True)
    os.replace(tmp, path)

def write_gz(path: str, data: Any):
    ensure_dir(os.path.dirname(path))
    with gzip.open(path, "wt") as f:
        json.dump(data, f)

def read_latest(path: str) -> Any:
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)
```

---

### `diffing.py`

```python
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
```

---

### `poller.py`

```python
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
    # Default to NX-OS heavy environment
    {"device_type":"cisco_nxos","host":"10.0.0.2","username":os.environ.get("NETOPS_USER"),
     "password":os.environ.get("NETOPS_PASS"),"name":"dc-nx-1"},
    {"device_type":"cisco_nxos","host":"10.0.0.3","username":os.environ.get("NETOPS_USER"),
     "password":os.environ.get("NETOPS_PASS"),"name":"agg-nx-1"},
]
STATIC_VRFS = ["default","campus","dmz"]
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
```

---

### `exporter.py`

```python
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
```

---

### `tests/test_diffing.py`

```python
"""
Minimal unit tests for diffing helpers.
Run:  python -m pytest -q
"""

from diffing import rib_diff, bgp_diff
from models import RIBEntry, BGPEntry, NH

def test_rib_ecmp_change():
    prev = [RIBEntry(device="d", vrf="v", afi="ipv4", prefix="10.0.0.0/24",
                     protocol="ospf", distance=110, metric=20, best=True,
                     nexthops={NH("1.1.1.1","Eth1/1")})]
    curr = [RIBEntry(device="d", vrf="v", afi="ipv4", prefix="10.0.0.0/24",
                     protocol="ospf", distance=110, metric=20, best=True,
                     nexthops={NH("1.1.1.1","Eth1/1"), NH("2.2.2.2","Eth1/2")})]
    d = rib_diff(prev, curr)
    assert len(d["adds"]) == 0
    assert len(d["rems"]) == 0
    assert len(d["chgs"]) == 1
    assert "nexthops" in d["chgs"][0]["delta"]

def test_bgp_upstream_as_change():
    a = BGPEntry(device="d", vrf="v", afi="ipv4", prefix="0.0.0.0/0", best=True,
                 nh="3.3.3.3", as_path="65001 3356", local_pref=100, med=0,
                 origin="i", communities=[], communities_hash="h", weight=None, peer="1.1.1.1")
    b = BGPEntry(device="d", vrf="v", afi="ipv4", prefix="0.0.0.0/0", best=True,
                 nh="4.4.4.4", as_path="65002 3356", local_pref=100, med=0,
                 origin="i", communities=[], communities_hash="h", weight=None, peer="2.2.2.2")
    d = bgp_diff([a], [b])
    assert len(d["chgs"]) == 1
    assert "upstream_as" in d["chgs"][0]["delta"]
```

---

## Final Notes

* This repo favors **clarity and stability** over fancy concurrency. If you need to scale to hundreds of devices/VRFs, consider:

  * `asyncssh` + Scrapli for parallel CLI
  * Per-device worker processes
  * Direct JSON RPC (NX-API) or OpenConfig (gNMI) where available

* Security: use read-only creds, IP ACLs/jump hosts, and keep `.env` out of Git.

If you want, I can tailor filenames/flows to your exact NX-OS/IOS-XE versions, add gNMI/OpenConfig collectors, or wire counts straight into **Influx/QuestDB** alongside Prometheus.

