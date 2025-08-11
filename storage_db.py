"""Database-based storage for route snapshots and diffs."""

import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple

from sqlalchemy.orm import Session
from sqlalchemy import desc, and_

from database import (
    get_session, Device, RouteSnapshot, BGPSnapshot, RouteDiff
)


class DatabaseStorage:
    """Store route snapshots and diffs in database."""
    
    def __init__(self, session: Optional[Session] = None):
        """Initialize with database session."""
        self.session = session or get_session()
    
    def save_snapshot(
        self,
        device_name: str,
        table_type: str,  # "rib" or "bgp"
        vrf: str,
        afi: str,
        data: Dict[str, Any],
        timestamp: Optional[datetime] = None
    ) -> None:
        """Save a snapshot to database."""
        timestamp = timestamp or datetime.utcnow()
        
        # Get device
        device = self.session.query(Device).filter_by(name=device_name).first()
        if not device:
            raise ValueError(f"Device '{device_name}' not found in database")
        
        # Count routes
        route_count = len(data)
        
        # Choose the right model
        if table_type == "rib":
            snapshot = RouteSnapshot(
                device_id=device.id,
                vrf=vrf,
                afi=afi,
                timestamp=timestamp,
                data=data,
                route_count=route_count
            )
        elif table_type == "bgp":
            snapshot = BGPSnapshot(
                device_id=device.id,
                vrf=vrf,
                afi=afi,
                timestamp=timestamp,
                data=data,
                route_count=route_count
            )
        else:
            raise ValueError(f"Invalid table_type: {table_type}")
        
        self.session.add(snapshot)
        self.session.commit()
    
    def get_latest_snapshot(
        self,
        device_name: str,
        table_type: str,
        vrf: str,
        afi: str
    ) -> Optional[Dict[str, Any]]:
        """Get the latest snapshot for a device/vrf/afi combination."""
        device = self.session.query(Device).filter_by(name=device_name).first()
        if not device:
            return None
        
        if table_type == "rib":
            snapshot = self.session.query(RouteSnapshot).filter(
                and_(
                    RouteSnapshot.device_id == device.id,
                    RouteSnapshot.vrf == vrf,
                    RouteSnapshot.afi == afi
                )
            ).order_by(desc(RouteSnapshot.timestamp)).first()
        elif table_type == "bgp":
            snapshot = self.session.query(BGPSnapshot).filter(
                and_(
                    BGPSnapshot.device_id == device.id,
                    BGPSnapshot.vrf == vrf,
                    BGPSnapshot.afi == afi
                )
            ).order_by(desc(BGPSnapshot.timestamp)).first()
        else:
            return None
        
        return snapshot.data if snapshot else None
    
    def get_snapshot_at_time(
        self,
        device_name: str,
        table_type: str,
        vrf: str,
        afi: str,
        timestamp: datetime
    ) -> Optional[Dict[str, Any]]:
        """Get a specific snapshot by timestamp."""
        device = self.session.query(Device).filter_by(name=device_name).first()
        if not device:
            return None
        
        if table_type == "rib":
            snapshot = self.session.query(RouteSnapshot).filter(
                and_(
                    RouteSnapshot.device_id == device.id,
                    RouteSnapshot.vrf == vrf,
                    RouteSnapshot.afi == afi,
                    RouteSnapshot.timestamp == timestamp
                )
            ).first()
        elif table_type == "bgp":
            snapshot = self.session.query(BGPSnapshot).filter(
                and_(
                    BGPSnapshot.device_id == device.id,
                    BGPSnapshot.vrf == vrf,
                    BGPSnapshot.afi == afi,
                    BGPSnapshot.timestamp == timestamp
                )
            ).first()
        else:
            return None
        
        return snapshot.data if snapshot else None
    
    def list_snapshots(
        self,
        device_name: str,
        table_type: str,
        vrf: str,
        afi: str,
        limit: int = 100
    ) -> List[datetime]:
        """List available snapshot timestamps."""
        device = self.session.query(Device).filter_by(name=device_name).first()
        if not device:
            return []
        
        if table_type == "rib":
            snapshots = self.session.query(RouteSnapshot.timestamp).filter(
                and_(
                    RouteSnapshot.device_id == device.id,
                    RouteSnapshot.vrf == vrf,
                    RouteSnapshot.afi == afi
                )
            ).order_by(desc(RouteSnapshot.timestamp)).limit(limit).all()
        elif table_type == "bgp":
            snapshots = self.session.query(BGPSnapshot.timestamp).filter(
                and_(
                    BGPSnapshot.device_id == device.id,
                    BGPSnapshot.vrf == vrf,
                    BGPSnapshot.afi == afi
                )
            ).order_by(desc(BGPSnapshot.timestamp)).limit(limit).all()
        else:
            return []
        
        return [s[0] for s in snapshots]
    
    def save_diff(
        self,
        device_name: str,
        table_type: str,
        vrf: str,
        afi: str,
        diff: Dict[str, Any],
        timestamp: Optional[datetime] = None
    ) -> None:
        """Save a diff to database."""
        timestamp = timestamp or datetime.utcnow()
        
        device = self.session.query(Device).filter_by(name=device_name).first()
        if not device:
            raise ValueError(f"Device '{device_name}' not found in database")
        
        diff_entry = RouteDiff(
            device_id=device.id,
            vrf=vrf,
            afi=afi,
            table_type=table_type,
            timestamp=timestamp,
            added=diff.get("added", []),
            removed=diff.get("removed", []),
            changed=diff.get("changed", [])
        )
        
        self.session.add(diff_entry)
        self.session.commit()
    
    def get_diffs(
        self,
        device_name: str,
        vrf: str,
        afi: str,
        table_type: Optional[str] = None,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """Get recent diffs for a device/vrf/afi."""
        device = self.session.query(Device).filter_by(name=device_name).first()
        if not device:
            return []
        
        query = self.session.query(RouteDiff).filter(
            and_(
                RouteDiff.device_id == device.id,
                RouteDiff.vrf == vrf,
                RouteDiff.afi == afi
            )
        )
        
        if table_type:
            query = query.filter(RouteDiff.table_type == table_type)
        
        diffs = query.order_by(desc(RouteDiff.timestamp)).limit(limit).all()
        
        return [d.to_dict() for d in diffs]
    
    def get_diff_at_time(
        self,
        device_name: str,
        table_type: str,
        vrf: str,
        afi: str,
        timestamp: datetime
    ) -> Optional[Dict[str, Any]]:
        """Get a specific diff by timestamp."""
        device = self.session.query(Device).filter_by(name=device_name).first()
        if not device:
            return None
        
        diff = self.session.query(RouteDiff).filter(
            and_(
                RouteDiff.device_id == device.id,
                RouteDiff.table_type == table_type,
                RouteDiff.vrf == vrf,
                RouteDiff.afi == afi,
                RouteDiff.timestamp == timestamp
            )
        ).first()
        
        return diff.to_dict() if diff else None
    
    def cleanup_old_snapshots(self, days_to_keep: int = 30) -> int:
        """Delete snapshots older than specified days."""
        cutoff_date = datetime.utcnow() - timedelta(days=days_to_keep)
        
        # Delete old RIB snapshots
        rib_deleted = self.session.query(RouteSnapshot).filter(
            RouteSnapshot.timestamp < cutoff_date
        ).delete()
        
        # Delete old BGP snapshots
        bgp_deleted = self.session.query(BGPSnapshot).filter(
            BGPSnapshot.timestamp < cutoff_date
        ).delete()
        
        # Delete old diffs
        diff_deleted = self.session.query(RouteDiff).filter(
            RouteDiff.timestamp < cutoff_date
        ).delete()
        
        self.session.commit()
        
        return rib_deleted + bgp_deleted + diff_deleted
    
    def get_available_tables(self, device_name: str) -> List[Tuple[str, str, str]]:
        """Get list of (table_type, vrf, afi) tuples available for a device."""
        device = self.session.query(Device).filter_by(name=device_name).first()
        if not device:
            return []
        
        tables = []
        
        # Get RIB tables
        rib_tables = self.session.query(
            RouteSnapshot.vrf,
            RouteSnapshot.afi
        ).filter(
            RouteSnapshot.device_id == device.id
        ).distinct().all()
        
        for vrf, afi in rib_tables:
            tables.append(("rib", vrf, afi))
        
        # Get BGP tables
        bgp_tables = self.session.query(
            BGPSnapshot.vrf,
            BGPSnapshot.afi
        ).filter(
            BGPSnapshot.device_id == device.id
        ).distinct().all()
        
        for vrf, afi in bgp_tables:
            tables.append(("bgp", vrf, afi))
        
        return tables
    
    def compute_and_save_diff(
        self,
        device_name: str,
        table_type: str,
        vrf: str,
        afi: str,
        current_data: Dict[str, Any],
        timestamp: Optional[datetime] = None
    ) -> Optional[Dict[str, Any]]:
        """Compute diff against previous snapshot and save if changes exist."""
        previous_data = self.get_latest_snapshot(device_name, table_type, vrf, afi)
        
        if previous_data is None:
            # First snapshot, no diff to compute
            return None
        
        # Simple dict-based diff
        prev_keys = set(previous_data.keys())
        curr_keys = set(current_data.keys())
        
        added = []
        removed = []
        changed = []
        
        # Find added routes
        for key in curr_keys - prev_keys:
            added.append(current_data[key])
        
        # Find removed routes
        for key in prev_keys - curr_keys:
            removed.append(previous_data[key])
        
        # Find changed routes
        for key in prev_keys & curr_keys:
            if previous_data[key] != current_data[key]:
                changed_entry = current_data[key].copy() if isinstance(current_data[key], dict) else current_data[key]
                if isinstance(changed_entry, dict):
                    changed_entry['_previous'] = previous_data[key]
                changed.append(changed_entry)
        
        diff = {
            "added": added,
            "removed": removed,
            "changed": changed
        }
        
        # Only save if there are changes
        if diff["added"] or diff["removed"] or diff["changed"]:
            self.save_diff(device_name, table_type, vrf, afi, diff, timestamp)
            return diff
        
        return None
    
    def close(self):
        """Close database session."""
        self.session.close()


def migrate_from_file_storage(file_storage_path: str = "route_snaps") -> None:
    """Migrate existing file-based snapshots to database."""
    import os
    import gzip
    from pathlib import Path
    
    storage = DatabaseStorage()
    base_path = Path(file_storage_path)
    
    if not base_path.exists():
        print(f"No existing storage found at {file_storage_path}")
        return
    
    for device_dir in base_path.iterdir():
        if not device_dir.is_dir():
            continue
        
        device_name = device_dir.name
        print(f"Migrating device: {device_name}")
        
        # Check if device exists in database
        device = storage.session.query(Device).filter_by(name=device_name).first()
        if not device:
            print(f"  Device {device_name} not in database, skipping")
            continue
        
        # Migrate RIB snapshots
        rib_dir = device_dir / "rib"
        if rib_dir.exists():
            for snapshot_file in rib_dir.glob("*.json*"):
                # Parse filename: <vrf>.<afi>.YYYYMMDDHHMMSS.json.gz or <vrf>.<afi>.latest.json
                parts = snapshot_file.stem.split(".")
                if len(parts) < 3:
                    continue
                
                vrf = parts[0]
                afi = parts[1]
                
                if "latest" in snapshot_file.name:
                    continue  # Skip latest files, use archives
                
                # Parse timestamp
                try:
                    timestamp_str = parts[2]
                    timestamp = datetime.strptime(timestamp_str, "%Y%m%d%H%M%S")
                except:
                    continue
                
                # Load data
                try:
                    if snapshot_file.suffix == ".gz":
                        with gzip.open(snapshot_file, "rt") as f:
                            data = json.load(f)
                    else:
                        with open(snapshot_file, "r") as f:
                            data = json.load(f)
                    
                    storage.save_snapshot(device_name, "rib", vrf, afi, data, timestamp)
                    print(f"  Migrated RIB snapshot: {vrf}.{afi} @ {timestamp}")
                except Exception as e:
                    print(f"  Error migrating {snapshot_file}: {e}")
        
        # Migrate BGP snapshots
        bgp_dir = device_dir / "bgp"
        if bgp_dir.exists():
            for snapshot_file in bgp_dir.glob("*.json*"):
                parts = snapshot_file.stem.split(".")
                if len(parts) < 3:
                    continue
                
                vrf = parts[0]
                afi = parts[1]
                
                if "latest" in snapshot_file.name:
                    continue
                
                try:
                    timestamp_str = parts[2]
                    timestamp = datetime.strptime(timestamp_str, "%Y%m%d%H%M%S")
                except:
                    continue
                
                try:
                    if snapshot_file.suffix == ".gz":
                        with gzip.open(snapshot_file, "rt") as f:
                            data = json.load(f)
                    else:
                        with open(snapshot_file, "r") as f:
                            data = json.load(f)
                    
                    storage.save_snapshot(device_name, "bgp", vrf, afi, data, timestamp)
                    print(f"  Migrated BGP snapshot: {vrf}.{afi} @ {timestamp}")
                except Exception as e:
                    print(f"  Error migrating {snapshot_file}: {e}")
    
    storage.close()
    print("Migration complete")