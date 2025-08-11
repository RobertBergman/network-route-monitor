"""
poller_db.py
Database-based periodic collector: polls devices from database, computes diffs, stores in database.
Use --once for a single run (prints a JSON report).
"""

import os
import time
import argparse
from datetime import datetime
from typing import List, Dict, Any

import ujson as json
from dotenv import load_dotenv

from parsers import collect_device_tables
from models import RIBEntry, BGPEntry, AFI4, AFI6
from database import get_session
from device_manager import DeviceManager
from storage_db import DatabaseStorage

load_dotenv()


def collect_and_persist_for_device(dev: Dict, storage: DatabaseStorage) -> Dict[str, Any]:
    """Collect routes from device and persist to database."""
    device_name = dev["name"]
    vrfs: List[str] = dev.get("vrfs") or ["default"]
    afis: List[str] = dev.get("afis") or [AFI4, AFI6]
    
    # Collect tables from device
    tables = collect_device_tables(dev, vrfs, afis)
    rib_rows: List[RIBEntry] = tables["rib"]
    bgp_rows: List[BGPEntry] = tables["bgp"]
    
    report = {"device": device_name, "vrfs": {}, "timestamp": datetime.utcnow().isoformat()}
    
    for vrf in vrfs:
        for afi in afis:
            # Filter by vrf/afi
            rib_now = [r for r in rib_rows if r.vrf == vrf and r.afi == afi]
            bgp_now = [b for b in bgp_rows if b.vrf == vrf and b.afi == afi]
            
            # Serialize current data
            curr_rib_data = {r.prefix: r.serialize() for r in rib_now}
            curr_bgp_data = {b.prefix: b.serialize() for b in bgp_now}
            
            # Compute and save diffs
            timestamp = datetime.utcnow()
            
            rib_diff = storage.compute_and_save_diff(
                device_name, "rib", vrf, afi, curr_rib_data, timestamp
            )
            bgp_diff = storage.compute_and_save_diff(
                device_name, "bgp", vrf, afi, curr_bgp_data, timestamp
            )
            
            # Save snapshots
            storage.save_snapshot(device_name, "rib", vrf, afi, curr_rib_data, timestamp)
            storage.save_snapshot(device_name, "bgp", vrf, afi, curr_bgp_data, timestamp)
            
            # Build report
            vrf_afi_report = {
                "rib": {
                    "count": len(rib_now),
                    "diff": rib_diff if rib_diff else {"added": [], "removed": [], "changed": []}
                },
                "bgp": {
                    "count": len(bgp_now),
                    "diff": bgp_diff if bgp_diff else {"added": [], "removed": [], "changed": []}
                }
            }
            
            report["vrfs"].setdefault(vrf, {})[afi] = vrf_afi_report
    
    return report


def get_inventory_from_db(manager: DeviceManager) -> List[Dict]:
    """Get device inventory from database."""
    devices = manager.get_all_devices(enabled_only=True)
    inventory = []
    
    for device in devices:
        dev_dict = device.to_dict()
        # Add all VRFs - could be made configurable per-device
        # For NX-OS, we'll collect from these common VRFs
        dev_dict["vrfs"] = ["default", "AWS", "Azure", "CUSTOMER_A", "D3PQA", "D3Pprod", "ITTD", "NAP", "management"]
        dev_dict["afis"] = [AFI4, AFI6]
        inventory.append(dev_dict)
    
    return inventory


def main():
    ap = argparse.ArgumentParser(description="Database-based route collector")
    ap.add_argument("--once", action="store_true", help="Run a single collection and print report")
    ap.add_argument("--cleanup", type=int, metavar="DAYS", 
                    help="Clean up snapshots older than DAYS")
    ap.add_argument("--migrate-devices", action="store_true",
                    help="Migrate static devices to database")
    ap.add_argument("--migrate-snapshots", action="store_true",
                    help="Migrate file-based snapshots to database")
    args = ap.parse_args()
    
    # Initialize database
    from database import init_db
    init_db()
    
    # Handle migrations
    if args.migrate_devices:
        from poller import STATIC_DEVICES
        from device_manager import migrate_from_static_devices
        print("Migrating static devices to database...")
        migrate_from_static_devices(STATIC_DEVICES)
        print("Migration complete")
        return
    
    if args.migrate_snapshots:
        from storage_db import migrate_from_file_storage
        print("Migrating file-based snapshots to database...")
        migrate_from_file_storage()
        print("Migration complete")
        return
    
    # Handle cleanup
    if args.cleanup:
        storage = DatabaseStorage()
        deleted = storage.cleanup_old_snapshots(args.cleanup)
        print(f"Deleted {deleted} old snapshots/diffs")
        storage.close()
        return
    
    # Main collection logic
    manager = DeviceManager()
    storage = DatabaseStorage()
    
    try:
        inv = get_inventory_from_db(manager)
        
        if not inv:
            print("No devices found in database. Use --migrate-devices or add devices manually.")
            return
        
        if args.once:
            # Single collection run
            reports = []
            for dev in inv:
                try:
                    report = collect_and_persist_for_device(dev, storage)
                    reports.append(report)
                    rib_count = sum(
                        v.get('ipv4', {}).get('rib', {}).get('count', 0) + 
                        v.get('ipv6', {}).get('rib', {}).get('count', 0) 
                        for v in report['vrfs'].values()
                    )
                    bgp_count = sum(
                        v.get('ipv4', {}).get('bgp', {}).get('count', 0) + 
                        v.get('ipv6', {}).get('bgp', {}).get('count', 0) 
                        for v in report['vrfs'].values()
                    )
                    print(f"Collected from {dev['name']}: RIB={rib_count} routes, BGP={bgp_count} prefixes")
                except Exception as e:
                    reports.append({"device": dev["name"], "error": str(e)})
                    print(f"Error collecting from {dev['name']}: {e}")
            
            print("\n" + json.dumps(reports, indent=2))
        else:
            # Daemon mode
            interval = int(os.environ.get("POLL_INTERVAL_SEC", "60"))
            print(f"Starting poller daemon (interval={interval}s)")
            
            while True:
                start = time.time()
                
                # Re-fetch inventory each cycle to pick up changes
                inv = get_inventory_from_db(manager)
                
                for dev in inv:
                    try:
                        report = collect_and_persist_for_device(dev, storage)
                        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] "
                              f"Collected from {dev['name']}")
                    except Exception as e:
                        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] "
                              f"Error collecting from {dev['name']}: {e}")
                
                elapsed = time.time() - start
                sleep_for = max(1, interval - int(elapsed))
                time.sleep(sleep_for)
    
    finally:
        manager.close()
        storage.close()


if __name__ == "__main__":
    main()