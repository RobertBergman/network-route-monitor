"""
FastAPI server for web UI with database backend.
"""

import os
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from database import get_session
from device_manager import DeviceManager
from storage_db import DatabaseStorage

APP_TITLE = "Route Monitor - Database Edition"

app = FastAPI(title=APP_TITLE)

# Add CORS middleware for web UI
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/devices")
def list_devices():
    """List all enabled devices."""
    manager = DeviceManager()
    try:
        devices = manager.get_all_devices(enabled_only=True)
        return [
            {
                "name": d.name,
                "hostname": d.hostname,
                "device_type": d.device_type,
                "enabled": d.enabled,
                "use_nxapi": d.use_nxapi,
            }
            for d in devices
        ]
    finally:
        manager.close()


@app.get("/api/devices/{device}/tables")
def get_device_tables(device: str):
    """Get available VRF/AFI combinations for a device."""
    storage = DatabaseStorage()
    try:
        tables = storage.get_available_tables(device)
        result = {"rib": [], "bgp": []}
        
        for table_type, vrf, afi in tables:
            entry = {"vrf": vrf, "afi": afi}
            if table_type == "rib" and entry not in result["rib"]:
                result["rib"].append(entry)
            elif table_type == "bgp" and entry not in result["bgp"]:
                result["bgp"].append(entry)
        
        return result
    finally:
        storage.close()


@app.get("/api/devices/{device}/latest")
def get_latest_snapshot(
    device: str,
    table: str = Query(..., description="Table type: 'rib' or 'bgp'"),
    vrf: str = Query(..., description="VRF name"),
    afi: str = Query(..., description="Address family: 'ipv4' or 'ipv6'")
):
    """Get the latest snapshot for a device/table/vrf/afi."""
    storage = DatabaseStorage()
    try:
        data = storage.get_latest_snapshot(device, table, vrf, afi)
        if data is None:
            raise HTTPException(status_code=404, detail="No snapshot found")
        
        # Convert dict to list for API consistency
        routes = list(data.values()) if isinstance(data, dict) else data
        
        return {
            "device": device,
            "table": table,
            "vrf": vrf,
            "afi": afi,
            "routes": routes,
            "count": len(routes)
        }
    finally:
        storage.close()


@app.get("/api/devices/{device}/diffs")
def get_diffs(
    device: str,
    vrf: str = Query(..., description="VRF name"),
    afi: str = Query(..., description="Address family: 'ipv4' or 'ipv6'"),
    table: Optional[str] = Query(None, description="Table type: 'rib' or 'bgp'"),
    limit: int = Query(20, description="Maximum number of diffs to return")
):
    """Get recent diffs for a device/vrf/afi."""
    storage = DatabaseStorage()
    try:
        diffs = storage.get_diffs(device, vrf, afi, table, limit)
        
        # Format for API
        result = []
        for diff in diffs:
            result.append({
                "timestamp": diff["timestamp"],
                "table_type": diff["table_type"],
                "vrf": diff["vrf"],
                "afi": diff["afi"],
                "summary": {
                    "added": len(diff.get("added", [])),
                    "removed": len(diff.get("removed", [])),
                    "changed": len(diff.get("changed", []))
                }
            })
        
        return result
    finally:
        storage.close()


@app.get("/api/devices/{device}/diffs/{timestamp}")
def get_diff_detail(
    device: str,
    timestamp: str,
    vrf: str = Query(..., description="VRF name"),
    afi: str = Query(..., description="Address family: 'ipv4' or 'ipv6'"),
    table: str = Query(..., description="Table type: 'rib' or 'bgp'")
):
    """Get detailed diff for a specific timestamp."""
    storage = DatabaseStorage()
    try:
        # Parse timestamp
        ts = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        
        diff = storage.get_diff_at_time(device, table, vrf, afi, ts)
        if diff is None:
            raise HTTPException(status_code=404, detail="Diff not found")
        
        return diff
    finally:
        storage.close()


@app.get("/api/devices/{device}/history")
def get_history(
    device: str,
    table: str = Query(..., description="Table type: 'rib' or 'bgp'"),
    vrf: str = Query(..., description="VRF name"),
    afi: str = Query(..., description="Address family: 'ipv4' or 'ipv6'"),
    limit: int = Query(100, description="Maximum number of snapshots")
):
    """Get historical snapshot timestamps."""
    storage = DatabaseStorage()
    try:
        timestamps = storage.list_snapshots(device, table, vrf, afi, limit)
        
        return [
            {
                "timestamp": ts.isoformat(),
                "table": table,
                "vrf": vrf,
                "afi": afi
            }
            for ts in timestamps
        ]
    finally:
        storage.close()


@app.get("/api/devices/{device}/snapshot/{timestamp}")
def get_snapshot_at_time(
    device: str,
    timestamp: str,
    table: str = Query(..., description="Table type: 'rib' or 'bgp'"),
    vrf: str = Query(..., description="VRF name"),
    afi: str = Query(..., description="Address family: 'ipv4' or 'ipv6'")
):
    """Get a specific historical snapshot."""
    storage = DatabaseStorage()
    try:
        # Parse timestamp
        ts = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        
        data = storage.get_snapshot_at_time(device, table, vrf, afi, ts)
        if data is None:
            raise HTTPException(status_code=404, detail="Snapshot not found")
        
        # Convert dict to list for API consistency
        routes = list(data.values()) if isinstance(data, dict) else data
        
        return {
            "device": device,
            "table": table,
            "vrf": vrf,
            "afi": afi,
            "timestamp": timestamp,
            "routes": routes,
            "count": len(routes)
        }
    finally:
        storage.close()


@app.get("/api/status")
def get_status():
    """Get system status and statistics."""
    storage = DatabaseStorage()
    manager = DeviceManager()
    try:
        devices = manager.get_all_devices(enabled_only=True)
        
        stats = {
            "devices": len(devices),
            "snapshots": {
                "rib": 0,
                "bgp": 0
            },
            "latest_collections": {}
        }
        
        # Get snapshot counts and latest collection times
        for device in devices:
            # Get latest RIB snapshot time
            rib_times = storage.list_snapshots(device.name, "rib", "default", "ipv4", 1)
            bgp_times = storage.list_snapshots(device.name, "bgp", "default", "ipv4", 1)
            
            if rib_times:
                stats["snapshots"]["rib"] += 1
                latest_time = rib_times[0]
                if device.name not in stats["latest_collections"]:
                    stats["latest_collections"][device.name] = latest_time.isoformat()
                
            if bgp_times:
                stats["snapshots"]["bgp"] += 1
        
        return stats
    finally:
        storage.close()
        manager.close()


# Device management endpoints
@app.post("/api/admin/devices")
def create_device(device_data: Dict[str, Any]):
    """Create a new device."""
    manager = DeviceManager()
    try:
        required = ["name", "hostname", "device_type", "username", "password"]
        for field in required:
            if field not in device_data:
                raise HTTPException(status_code=400, detail=f"Missing required field: {field}")
        
        device = manager.create_device(**device_data)
        return {
            "id": device.id,
            "name": device.name,
            "hostname": device.hostname,
            "created": True
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        manager.close()


@app.put("/api/admin/devices/{device_id}")
def update_device(device_id: int, device_data: Dict[str, Any]):
    """Update a device."""
    manager = DeviceManager()
    try:
        device = manager.update_device(device_id, **device_data)
        if device is None:
            raise HTTPException(status_code=404, detail="Device not found")
        
        return {
            "id": device.id,
            "name": device.name,
            "updated": True
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        manager.close()


@app.delete("/api/admin/devices/{device_id}")
def delete_device(device_id: int):
    """Delete a device and all its data."""
    manager = DeviceManager()
    try:
        success = manager.delete_device(device_id)
        if not success:
            raise HTTPException(status_code=404, detail="Device not found")
        
        return {"deleted": True}
    finally:
        manager.close()


@app.post("/api/admin/devices/{device_id}/enable")
def enable_device(device_id: int):
    """Enable a device for monitoring."""
    manager = DeviceManager()
    try:
        success = manager.enable_device(device_id)
        if not success:
            raise HTTPException(status_code=404, detail="Device not found")
        
        return {"enabled": True}
    finally:
        manager.close()


@app.post("/api/admin/devices/{device_id}/disable")
def disable_device(device_id: int):
    """Disable a device from monitoring."""
    manager = DeviceManager()
    try:
        success = manager.disable_device(device_id)
        if not success:
            raise HTTPException(status_code=404, detail="Device not found")
        
        return {"disabled": True}
    finally:
        manager.close()


# Serve static files for web UI
if os.path.exists("webui"):
    app.mount("/", StaticFiles(directory="webui", html=True), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=5000)