import os
import re
import json
import gzip
from typing import List, Dict, Any, Optional, Tuple

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from storage import device_root, table_dir, latest_path

APP_TITLE = "Routing Table & BGP RIB Change Tracker UI"
SNAPDIR = os.environ.get("SNAPDIR", "./route_snaps")

app = FastAPI(title=APP_TITLE)


def _exists(path: str) -> bool:
    return os.path.exists(path)


def _isdir(path: str) -> bool:
    return os.path.isdir(path)


def list_devices() -> List[str]:
    if not _exists(SNAPDIR):
        return []
    devices = []
    for name in os.listdir(SNAPDIR):
        p = os.path.join(SNAPDIR, name)
        if _isdir(p):
            devices.append(name)
    devices.sort()
    return devices


def _list_files(path: str, pattern: Optional[re.Pattern] = None) -> List[str]:
    if not _exists(path):
        return []
    files = []
    for name in os.listdir(path):
        fp = os.path.join(path, name)
        if os.path.isfile(fp):
            if pattern is None or pattern.match(name):
                files.append(name)
    return files


def scan_tables_for_device(device: str) -> Dict[str, List[Tuple[str, str]]]:
    """
    Return available (vrf, afi) pairs for rib and bgp based on files present.
    """
    out = {"rib": [], "bgp": []}
    pat = re.compile(r"^(?P<vrf>[^.]+)\.(?P<afi>ipv4|ipv6)\.(latest\.json|\d{14}\.json\.gz)$")
    for table in ("rib", "bgp"):
        td = table_dir(SNAPDIR, device, table)
        seen = set()
        for name in _list_files(td, pat):
            m = pat.match(name)
            if not m:
                continue
            vrf = m.group("vrf")
            afi = m.group("afi")
            seen.add((vrf, afi))
        out[table] = sorted(list(seen))
    return out


def read_json(path: str) -> Any:
    if not _exists(path):
        raise FileNotFoundError(path)
    if path.endswith(".gz"):
        with gzip.open(path, "rt") as f:
            return json.load(f)
    with open(path, "r") as f:
        return json.load(f)


def diff_dir(device: str) -> str:
    return os.path.join(device_root(SNAPDIR, device), "diffs")


def list_diffs(device: str, vrf: Optional[str], afi: Optional[str]) -> List[Dict[str, Any]]:
    """
    Return a list of diff metadata entries like:
    [{"vrf":"default","afi":"ipv4","ts":"20250811031450","name":"default.ipv4.20250811031450.json.gz","size":1234}, ...]
    Filterable by vrf/afi if provided.
    """
    dd = diff_dir(device)
    if not _exists(dd):
        return []
    entries = []
    pat = re.compile(r"^(?P<vrf>[^.]+)\.(?P<afi>ipv4|ipv6)\.(?P<ts>\d{14})\.json\.gz$")
    for name in _list_files(dd, pat):
        m = pat.match(name)
        if not m:
            continue
        v = m.group("vrf")
        a = m.group("afi")
        ts = m.group("ts")
        if vrf and v != vrf:
            continue
        if afi and a != afi:
            continue
        fp = os.path.join(dd, name)
        try:
            size = os.path.getsize(fp)
        except Exception:
            size = 0
        entries.append({"vrf": v, "afi": a, "ts": ts, "name": name, "size": size})
    # sort newest first
    entries.sort(key=lambda e: e["ts"], reverse=True)
    return entries


@app.get("/api/health")
def health():
    return {"status": "ok", "snapdir": SNAPDIR, "devices": len(list_devices())}


@app.get("/api/devices")
def api_devices():
    return {"devices": list_devices()}


@app.get("/api/devices/{device}/tables")
def api_device_tables(device: str):
    if device not in list_devices():
        raise HTTPException(status_code=404, detail="Device not found")
    return scan_tables_for_device(device)


@app.get("/api/devices/{device}/latest")
def api_latest(
    device: str,
    table: str = Query(..., pattern="^(rib|bgp)$"),
    vrf: str = Query(...),
    afi: str = Query(..., pattern="^(ipv4|ipv6)$"),
):
    if device not in list_devices():
        raise HTTPException(status_code=404, detail="Device not found")
    if table not in ("rib", "bgp"):
        raise HTTPException(status_code=400, detail="Invalid table")
    lp = latest_path(SNAPDIR, device, table, vrf, afi)
    if not _exists(lp):
        raise HTTPException(status_code=404, detail="Latest snapshot not found")
    try:
        data = read_json(lp)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read latest: {e}")
    return JSONResponse(content=data)


@app.get("/api/devices/{device}/history")
def api_history(
    device: str,
    table: str = Query(..., pattern="^(rib|bgp)$"),
    vrf: str = Query(...),
    afi: str = Query(..., pattern="^(ipv4|ipv6)$"),
    limit: int = Query(20, ge=1, le=500),
):
    if device not in list_devices():
        raise HTTPException(status_code=404, detail="Device not found")
    td = table_dir(SNAPDIR, device, table)
    if not _exists(td):
        return {"items": []}
    pat = re.compile(rf"^{re.escape(vrf)}\.{re.escape(afi)}\.(\d{{14}})\.json\.gz$")
    items = []
    for name in _list_files(td):
        m = pat.match(name)
        if not m:
            continue
        ts = m.group(1)
        fp = os.path.join(td, name)
        try:
            size = os.path.getsize(fp)
        except Exception:
            size = 0
        items.append({"ts": ts, "name": name, "size": size})
    items.sort(key=lambda e: e["ts"], reverse=True)
    return {"items": items[:limit]}


@app.get("/api/devices/{device}/history/{ts}")
def api_history_item(
    device: str,
    ts: str,
    table: str = Query(..., pattern="^(rib|bgp)$"),
    vrf: str = Query(...),
    afi: str = Query(..., pattern="^(ipv4|ipv6)$"),
):
    if device not in list_devices():
        raise HTTPException(status_code=404, detail="Device not found")
    td = table_dir(SNAPDIR, device, table)
    fname = f"{vrf}.{afi}.{ts}.json.gz"
    fp = os.path.join(td, fname)
    if not _exists(fp):
        raise HTTPException(status_code=404, detail="Archive not found")
    try:
        data = read_json(fp)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read archive: {e}")
    return JSONResponse(content=data)


@app.get("/api/devices/{device}/diffs")
def api_diffs_index(
    device: str,
    vrf: Optional[str] = Query(None),
    afi: Optional[str] = Query(None, pattern="^(ipv4|ipv6)$"),
    limit: int = Query(50, ge=1, le=1000),
):
    if device not in list_devices():
        raise HTTPException(status_code=404, detail="Device not found")
    items = list_diffs(device, vrf, afi)
    return {"items": items[:limit]}


@app.get("/api/devices/{device}/diffs/{ts}")
def api_diff_item(
    device: str,
    ts: str,
    vrf: str = Query(...),
    afi: str = Query(..., pattern="^(ipv4|ipv6)$"),
):
    if device not in list_devices():
        raise HTTPException(status_code=404, detail="Device not found")
    dd = diff_dir(device)
    fname = f"{vrf}.{afi}.{ts}.json.gz"
    fp = os.path.join(dd, fname)
    if not _exists(fp):
        raise HTTPException(status_code=404, detail="Diff not found")
    try:
        data = read_json(fp)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read diff: {e}")
    return JSONResponse(content=data)


# Serve static frontend (built assets in ./webui)
# Note: /api/* routes are handled above; all other paths serve index.html
if _exists("webui"):
    app.mount("/", StaticFiles(directory="webui", html=True), name="webui")
