"""Device management CRUD operations."""

from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from database import Device, get_session


class DeviceManager:
    """Manage network devices in database."""
    
    def __init__(self, session: Optional[Session] = None):
        """Initialize with database session."""
        self.session = session or get_session()
    
    def create_device(
        self,
        name: str,
        hostname: str,
        device_type: str,
        username: str,
        password: str,
        port: int = 22,
        use_nxapi: bool = False,
        enabled: bool = True,
    ) -> Device:
        """Create a new device."""
        device = Device(
            name=name,
            hostname=hostname,
            device_type=device_type,
            username=username,
            port=port,
            use_nxapi=use_nxapi,
            enabled=enabled,
        )
        device.password = password  # This will encrypt it
        
        try:
            self.session.add(device)
            self.session.commit()
            self.session.refresh(device)
            return device
        except IntegrityError:
            self.session.rollback()
            raise ValueError(f"Device with name '{name}' already exists")
    
    def get_device(self, device_id: Optional[int] = None, name: Optional[str] = None) -> Optional[Device]:
        """Get device by ID or name."""
        if device_id:
            return self.session.query(Device).filter_by(id=device_id).first()
        elif name:
            return self.session.query(Device).filter_by(name=name).first()
        return None
    
    def get_all_devices(self, enabled_only: bool = True) -> List[Device]:
        """Get all devices."""
        query = self.session.query(Device)
        if enabled_only:
            query = query.filter_by(enabled=True)
        return query.all()
    
    def update_device(
        self,
        device_id: int,
        **kwargs
    ) -> Optional[Device]:
        """Update device fields."""
        device = self.get_device(device_id=device_id)
        if not device:
            return None
        
        for key, value in kwargs.items():
            if key == "password":
                device.password = value  # Use setter for encryption
            elif hasattr(device, key):
                setattr(device, key, value)
        
        try:
            self.session.commit()
            self.session.refresh(device)
            return device
        except IntegrityError:
            self.session.rollback()
            raise ValueError(f"Update failed - duplicate name or constraint violation")
    
    def delete_device(self, device_id: int) -> bool:
        """Delete a device and all its snapshots."""
        device = self.get_device(device_id=device_id)
        if not device:
            return False
        
        self.session.delete(device)
        self.session.commit()
        return True
    
    def enable_device(self, device_id: int) -> bool:
        """Enable a device for monitoring."""
        device = self.update_device(device_id, enabled=True)
        return device is not None
    
    def disable_device(self, device_id: int) -> bool:
        """Disable a device from monitoring."""
        device = self.update_device(device_id, enabled=False)
        return device is not None
    
    def import_devices(self, devices: List[Dict[str, Any]]) -> List[Device]:
        """Import multiple devices from list of dicts."""
        imported = []
        for device_dict in devices:
            try:
                device = self.create_device(**device_dict)
                imported.append(device)
            except ValueError as e:
                print(f"Skipping device {device_dict.get('name')}: {e}")
        return imported
    
    def export_devices(self, enabled_only: bool = True) -> List[Dict[str, Any]]:
        """Export devices as list of dicts (without passwords)."""
        devices = self.get_all_devices(enabled_only=enabled_only)
        return [
            {
                "id": d.id,
                "name": d.name,
                "hostname": d.hostname,
                "device_type": d.device_type,
                "username": d.username,
                "port": d.port,
                "use_nxapi": d.use_nxapi,
                "enabled": d.enabled,
                "created_at": d.created_at.isoformat(),
                "updated_at": d.updated_at.isoformat(),
            }
            for d in devices
        ]
    
    def close(self):
        """Close database session."""
        self.session.close()


def migrate_from_static_devices(static_devices: List[Dict[str, Any]]) -> None:
    """Migrate devices from static configuration to database."""
    manager = DeviceManager()
    
    for device in static_devices:
        device_copy = device.copy()
        
        # Map field names from static config to database fields
        if "host" in device_copy:
            device_copy["hostname"] = device_copy.pop("host")
        
        if "name" not in device_copy:
            device_copy["name"] = device_copy.get("hostname", "unknown")
        
        # Remove fields not used in database
        device_copy.pop("vrfs", None)
        device_copy.pop("afis", None)
        
        try:
            created = manager.create_device(**device_copy)
            print(f"Migrated device: {created.name}")
        except ValueError as e:
            print(f"Skipping: {e}")
    
    manager.close()