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