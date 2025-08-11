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