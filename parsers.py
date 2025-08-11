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

def discover_vrfs(device_config: Dict) -> List[str]:
    """
    Discover all VRFs configured on a device.
    Returns a list of VRF names including 'default'.
    """
    vrfs = ["default"]  # Always include default VRF
    
    try:
        # Use NX-API if available for NX-OS devices
        if device_config.get("use_nxapi") and device_config.get("device_type") == "cisco_nxos":
            host = device_config.get("host") or device_config.get("hostname")
            username = device_config.get("username")
            password = device_config.get("password")
            
            response = _nxapi_request(host, username, password, ["show vrf"])
            if response and "ins_api" in response:
                outputs = response["ins_api"].get("outputs", {}).get("output", {})
                body = outputs.get("body", {}) if isinstance(outputs, dict) else {}
                
                # Parse VRF table
                vrf_table = body.get("TABLE_vrf", {})
                vrf_rows = vrf_table.get("ROW_vrf", [])
                if isinstance(vrf_rows, dict):
                    vrf_rows = [vrf_rows]
                
                for vrf_row in vrf_rows:
                    vrf_name = vrf_row.get("vrf_name")
                    if vrf_name and vrf_name not in vrfs:
                        vrfs.append(vrf_name)
        else:
            # Use SSH/CLI - filter to only Netmiko-compatible fields
            netmiko_fields = ["host", "hostname", "device_type", "username", "password", "port", 
                              "secret", "verbose", "session_log", "timeout", "auth_timeout", 
                              "banner_timeout", "conn_timeout", "fast_cli"]
            device = {k: v for k, v in device_config.items() if k in netmiko_fields}
            
            # Map hostname to host if needed
            if "hostname" in device and "host" not in device:
                device["host"] = device.pop("hostname")
            
            with ConnectHandler(**device) as conn:
                # Try JSON first
                parsed = _try_json(conn, "show vrf")
                if parsed:
                    # Parse JSON VRF output
                    vrf_table = parsed.get("TABLE_vrf", {})
                    vrf_rows = vrf_table.get("ROW_vrf", [])
                    if isinstance(vrf_rows, dict):
                        vrf_rows = [vrf_rows]
                    
                    for vrf_row in vrf_rows:
                        vrf_name = vrf_row.get("vrf_name")
                        if vrf_name and vrf_name not in vrfs:
                            vrfs.append(vrf_name)
                else:
                    # Fall back to text parsing
                    output = conn.send_command("show vrf")
                    # Simple text parsing for VRF names
                    for line in output.split('\n'):
                        line = line.strip()
                        # Skip headers and empty lines
                        if not line or line.startswith('Name') or line.startswith('---'):
                            continue
                        # VRF name is typically the first column
                        parts = line.split()
                        if parts:
                            vrf_name = parts[0]
                            if vrf_name and vrf_name not in vrfs and not vrf_name.startswith('*'):
                                vrfs.append(vrf_name)
                                
    except Exception as e:
        print(f"Error discovering VRFs: {e}")
        # Return at least default VRF on error
        return ["default"]
    
    return vrfs

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
        row_vrf = table_vrf.get("ROW_vrf", [])
        if not isinstance(row_vrf, list):
            row_vrf = [row_vrf] if row_vrf else []
        for v in row_vrf:
            if v.get("vrf-name-out") != vrf:
                continue
            # IPv4/IPv6 may present as separate tables
            table_af = v.get("TABLE_addrf") or {}
            row_addrf = table_af.get("ROW_addrf") or []
            if not isinstance(row_addrf, list):
                row_addrf = [row_addrf] if row_addrf else []
            for row_af in row_addrf:
                af_n = row_af.get("addrf")
                if (afi == AFI4 and "ipv4" not in af_n) or (afi == AFI6 and "ipv6" not in af_n):
                    continue
                routes = row_af.get("TABLE_prefix", {})
                rows = routes.get("ROW_prefix") or []
                if isinstance(rows, dict):
                    rows = [rows]
                for r in rows:
                    pfx = r.get("ipprefix") or r.get("ip_prefix")
                    # Extract protocol from paths
                    path_table = r.get("TABLE_path", {})
                    path_rows = path_table.get("ROW_path", [])
                    if not isinstance(path_rows, list):
                        path_rows = [path_rows] if path_rows else []
                    
                    proto = ""
                    dist = None
                    met = None
                    best = False
                    nhs = set()
                    
                    for path in path_rows:
                        if not proto and path.get("clientname"):
                            proto = path.get("clientname")
                        if path.get("pref") is not None:
                            dist = int(path.get("pref"))
                        if path.get("metric") is not None:
                            met = int(path.get("metric"))
                        if path.get("ubest") in ("true", True, "1", 1):
                            best = True
                        # Get nexthop
                        nh_ip = path.get("ipnexthop") or path.get("nexthop")
                        if nh_ip:
                            nhs.add(NH(nh=nh_ip, iface=path.get("ifname")))
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
            table_af = v.get("TABLE_afi") or v.get("TABLE_af") or {}
            afrows = table_af.get("ROW_afi") or table_af.get("ROW_af") or []
            if isinstance(afrows, dict):
                afrows = [afrows]
            for af in afrows:
                # Check AFI - can be "1" or 1 for IPv4 or "2" or 2 for IPv6, or text format
                af_value = af.get("afi") or af.get("af")
                af_value_str = str(af_value) if af_value is not None else ""
                if afi == AFI4 and af_value_str not in ("1", "ipv4 unicast") and af_value not in (1, "ipv4 unicast"):
                    continue
                if afi == AFI6 and af_value_str not in ("2", "ipv6 unicast") and af_value not in (2, "ipv6 unicast"):
                    continue
                
                # Navigate deeper structure: TABLE_safi > ROW_safi > TABLE_rd > ROW_rd > TABLE_prefix
                table_safi = af.get("TABLE_safi") or {}
                row_safi = table_safi.get("ROW_safi") or {}
                if isinstance(row_safi, list):
                    row_safi = row_safi[0] if row_safi else {}
                
                table_rd = row_safi.get("TABLE_rd") or {}
                row_rd = table_rd.get("ROW_rd") or {}
                if isinstance(row_rd, list):
                    row_rd = row_rd[0] if row_rd else {}
                
                # Now get the prefix table
                table_r = row_rd.get("TABLE_prefix") or af.get("TABLE_prefix") or {}
                rrows = table_r.get("ROW_prefix") or []
                if isinstance(rrows, dict):
                    rrows = [rrows]
                
                for r in rrows:
                    pfx = r.get("ipprefix") or r.get("ipv6prefix") or r.get("prefix")
                    paths = r.get("TABLE_path", {}).get("ROW_path") or []
                    if isinstance(paths, dict):
                        paths = [paths]
                    for path in paths:
                        comms = normalize_communities(path.get("community"))
                        # Check for best path - can be "bestpath" or True
                        is_best = path.get("best") in ("bestpath", "true", True, 1) or path.get("bestcode") == ">"
                        out.append(BGPEntry(
                            device=device_name, vrf=vrf, afi=afi, prefix=pfx,
                            best=is_best,
                            nh=path.get("ipnexthop") or path.get("nexthop") or path.get("nh"),
                            as_path=str(path.get("aspath") or ""),
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
    device_name = dev.get("name", dev.get("host", "unknown"))
    device_os = "iosxe" if "xe" in dev["device_type"] else "nxos"

    # Create connection dict with only netmiko-compatible fields
    netmiko_fields = ["host", "hostname", "device_type", "username", "password", "port", 
                      "secret", "verbose", "session_log", "timeout", "auth_timeout", 
                      "banner_timeout", "conn_timeout", "fast_cli"]
    conn_params = {k: v for k, v in dev.items() if k in netmiko_fields}
    
    # Map hostname to host if needed
    if "hostname" in conn_params and "host" not in conn_params:
        conn_params["host"] = conn_params.pop("hostname")
    
    conn = ConnectHandler(**conn_params)
    rib_all: List[RIBEntry] = []
    bgp_all: List[BGPEntry] = []

    try:
        for vrf in vrfs:
            for afi in afis:
                # RIB
                rib_cmd = "show ip route vrf {}".format(vrf) if afi == AFI4 else "show ipv6 route vrf {}".format(vrf)
                try:
                    parsed = fetch_parsed(conn, device_name, device_os, rib_cmd, conn_params)
                    rib_all.extend(parse_rib(device_name, device_os, vrf, afi, parsed))
                except Exception:
                    # swallow per-table errors to keep other tables flowing
                    pass

                # BGP
                bgp_cmd = f"show bgp vrf {vrf} {'ipv4 unicast' if afi==AFI4 else 'ipv6 unicast'}"
                try:
                    parsed = fetch_parsed(conn, device_name, device_os, bgp_cmd, conn_params)
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