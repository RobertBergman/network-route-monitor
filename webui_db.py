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
from pydantic import BaseModel

from database import get_session
from device_manager import DeviceManager
from storage_db import DatabaseStorage

APP_TITLE = "Route Monitor - Database Edition"

# Pydantic models for request/response
class DeviceCreate(BaseModel):
    name: str
    hostname: str
    device_type: str
    username: str
    password: str
    port: int = 22
    enabled: bool = True
    use_nxapi: bool = False

class DeviceUpdate(BaseModel):
    name: Optional[str] = None
    hostname: Optional[str] = None
    device_type: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    port: Optional[int] = None
    enabled: Optional[bool] = None
    use_nxapi: Optional[bool] = None

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
def list_devices(all_devices: bool = Query(False, description="Include disabled devices")):
    """List all devices."""
    manager = DeviceManager()
    try:
        devices = manager.get_all_devices(enabled_only=not all_devices)
        return [
            {
                "id": d.id,
                "name": d.name,
                "hostname": d.hostname,
                "device_type": d.device_type,
                "username": d.username,
                "port": d.port,
                "enabled": d.enabled,
                "use_nxapi": d.use_nxapi,
                "created_at": d.created_at.isoformat() if d.created_at else None,
                "updated_at": d.updated_at.isoformat() if d.updated_at else None,
            }
            for d in devices
        ]
    finally:
        manager.close()


@app.post("/api/devices")
def create_device(device: DeviceCreate):
    """Create a new device."""
    manager = DeviceManager()
    try:
        new_device = manager.add_device(
            name=device.name,
            hostname=device.hostname,
            device_type=device.device_type,
            username=device.username,
            password=device.password,
            port=device.port,
            enabled=device.enabled,
            use_nxapi=device.use_nxapi,
        )
        return {
            "id": new_device.id,
            "name": new_device.name,
            "hostname": new_device.hostname,
            "device_type": new_device.device_type,
            "username": new_device.username,
            "port": new_device.port,
            "enabled": new_device.enabled,
            "use_nxapi": new_device.use_nxapi,
            "created_at": new_device.created_at.isoformat() if new_device.created_at else None,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        manager.close()


@app.get("/api/devices/{device_name}")
def get_device(device_name: str):
    """Get a specific device by name."""
    manager = DeviceManager()
    try:
        device = manager.get_device(device_name)
        if device is None:
            raise HTTPException(status_code=404, detail="Device not found")
        return {
            "id": device.id,
            "name": device.name,
            "hostname": device.hostname,
            "device_type": device.device_type,
            "username": device.username,
            "port": device.port,
            "enabled": device.enabled,
            "use_nxapi": device.use_nxapi,
            "created_at": device.created_at.isoformat() if device.created_at else None,
            "updated_at": device.updated_at.isoformat() if device.updated_at else None,
        }
    finally:
        manager.close()


@app.put("/api/devices/{device_name}")
def update_device(device_name: str, device: DeviceUpdate):
    """Update an existing device."""
    manager = DeviceManager()
    try:
        # Get existing device
        existing = manager.get_device(device_name)
        if existing is None:
            raise HTTPException(status_code=404, detail="Device not found")
        
        # Update only provided fields
        update_data = device.dict(exclude_unset=True)
        updated_device = manager.update_device(device_name, **update_data)
        
        return {
            "id": updated_device.id,
            "name": updated_device.name,
            "hostname": updated_device.hostname,
            "device_type": updated_device.device_type,
            "username": updated_device.username,
            "port": updated_device.port,
            "enabled": updated_device.enabled,
            "use_nxapi": updated_device.use_nxapi,
            "updated_at": updated_device.updated_at.isoformat() if updated_device.updated_at else None,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        manager.close()


@app.delete("/api/devices/{device_name}")
def delete_device(device_name: str):
    """Delete a device."""
    manager = DeviceManager()
    try:
        success = manager.delete_device(device_name)
        if not success:
            raise HTTPException(status_code=404, detail="Device not found")
        return {"message": f"Device {device_name} deleted successfully"}
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