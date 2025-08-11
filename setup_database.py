#!/usr/bin/env python3
"""
Database setup and migration script for route monitoring system.
"""

import os
import sys
import argparse
from getpass import getpass
from typing import List, Dict, Any

from dotenv import load_dotenv

load_dotenv()


def check_database_connection():
    """Check if database is accessible."""
    from database import get_db_url, init_db
    from sqlalchemy import create_engine, text
    
    db_url = get_db_url()
    print(f"Testing connection to: {db_url.split('@')[1] if '@' in db_url else db_url}")
    
    try:
        engine = create_engine(db_url)
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            print("✓ Database connection successful")
            return True
    except Exception as e:
        print(f"✗ Database connection failed: {e}")
        print("\nPlease ensure PostgreSQL is running and the database exists.")
        print("You can create it with: createdb routemonitor")
        return False


def init_database():
    """Initialize database tables."""
    from database import init_db
    from sqlalchemy import create_engine, text
    from database import get_db_url
    
    print("Initializing database tables...")
    init_db()
    print("✓ Database tables created")
    
    # Apply migrations for VRF columns
    print("Applying schema migrations...")
    db_url = get_db_url()
    engine = create_engine(db_url)
    
    with engine.connect() as conn:
        # Check if VRF columns exist
        result = conn.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'devices' 
            AND column_name IN ('vrfs', 'vrfs_updated_at')
        """))
        
        existing_columns = [row[0] for row in result]
        
        # Add vrfs column if it doesn't exist
        if 'vrfs' not in existing_columns:
            print("  Adding 'vrfs' column to devices table...")
            conn.execute(text("""
                ALTER TABLE devices 
                ADD COLUMN vrfs TEXT
            """))
            conn.commit()
            print("  ✓ Added 'vrfs' column")
        
        # Add vrfs_updated_at column if it doesn't exist
        if 'vrfs_updated_at' not in existing_columns:
            print("  Adding 'vrfs_updated_at' column to devices table...")
            conn.execute(text("""
                ALTER TABLE devices 
                ADD COLUMN vrfs_updated_at TIMESTAMP
            """))
            conn.commit()
            print("  ✓ Added 'vrfs_updated_at' column")
    
    print("✓ Schema migrations applied")


def add_device_interactive():
    """Interactively add a new device."""
    from device_manager import DeviceManager
    
    print("\n=== Add New Device ===")
    
    name = input("Device name (unique identifier): ").strip()
    hostname = input("Hostname/IP address: ").strip()
    
    print("\nDevice types:")
    print("  1. cisco_nxos (Nexus switches)")
    print("  2. cisco_ios (IOS routers/switches)")
    print("  3. cisco_xe (IOS-XE routers)")
    print("  4. cisco_xr (IOS-XR routers)")
    
    device_type_map = {
        "1": "cisco_nxos",
        "2": "cisco_ios", 
        "3": "cisco_xe",
        "4": "cisco_xr"
    }
    
    choice = input("Select device type (1-4): ").strip()
    device_type = device_type_map.get(choice, "cisco_nxos")
    
    username = input("Username: ").strip()
    password = getpass("Password: ")
    
    port = input("SSH port (default: 22): ").strip()
    port = int(port) if port else 22
    
    use_nxapi = False
    if device_type == "cisco_nxos":
        use_nxapi_str = input("Use NX-API instead of SSH? (y/N): ").strip().lower()
        use_nxapi = use_nxapi_str == 'y'
    
    manager = DeviceManager()
    try:
        device = manager.create_device(
            name=name,
            hostname=hostname,
            device_type=device_type,
            username=username,
            password=password,
            port=port,
            use_nxapi=use_nxapi
        )
        print(f"✓ Device '{device.name}' added successfully (ID: {device.id})")
    except ValueError as e:
        print(f"✗ Error: {e}")
    finally:
        manager.close()


def list_devices():
    """List all devices in database."""
    from device_manager import DeviceManager
    
    manager = DeviceManager()
    try:
        devices = manager.get_all_devices(enabled_only=False)
        
        if not devices:
            print("No devices found in database")
            return
        
        print("\n=== Devices in Database ===")
        print(f"{'ID':<5} {'Name':<20} {'Hostname':<30} {'Type':<15} {'Enabled':<8}")
        print("-" * 80)
        
        for d in devices:
            enabled = "Yes" if d.enabled else "No"
            print(f"{d.id:<5} {d.name:<20} {d.hostname:<30} {d.device_type:<15} {enabled:<8}")
    finally:
        manager.close()


def migrate_static_devices():
    """Migrate devices from static configuration."""
    from poller import STATIC_DEVICES
    from device_manager import migrate_from_static_devices
    
    print(f"\nMigrating {len(STATIC_DEVICES)} static devices to database...")
    migrate_from_static_devices(STATIC_DEVICES)
    print("✓ Migration complete")


def migrate_file_snapshots():
    """Migrate file-based snapshots to database."""
    from storage_db import migrate_from_file_storage
    
    snapdir = os.environ.get("SNAPDIR", "./route_snaps")
    
    if not os.path.exists(snapdir):
        print(f"No snapshots found at {snapdir}")
        return
    
    print(f"\nMigrating snapshots from {snapdir} to database...")
    print("This may take a while for large datasets...")
    migrate_from_file_storage(snapdir)
    print("✓ Migration complete")


def test_device_connection():
    """Test connection to a device."""
    from device_manager import DeviceManager
    from parsers import collect_device_tables
    
    manager = DeviceManager()
    try:
        devices = manager.get_all_devices(enabled_only=True)
        
        if not devices:
            print("No enabled devices found")
            return
        
        print("\nSelect a device to test:")
        for i, d in enumerate(devices, 1):
            print(f"  {i}. {d.name} ({d.hostname})")
        
        choice = input("Device number: ").strip()
        try:
            idx = int(choice) - 1
            device = devices[idx]
        except (ValueError, IndexError):
            print("Invalid selection")
            return
        
        print(f"\nTesting connection to {device.name}...")
        dev_dict = device.to_dict()
        
        try:
            tables = collect_device_tables(dev_dict, ["default"], ["ipv4"])
            rib_count = len(tables.get("rib", []))
            bgp_count = len(tables.get("bgp", []))
            
            print(f"✓ Connection successful!")
            print(f"  RIB entries: {rib_count}")
            print(f"  BGP entries: {bgp_count}")
        except Exception as e:
            print(f"✗ Connection failed: {e}")
    finally:
        manager.close()


def main():
    parser = argparse.ArgumentParser(description="Database setup and management for route monitor")
    parser.add_argument("--init", action="store_true", help="Initialize database tables")
    parser.add_argument("--add-device", action="store_true", help="Add a new device interactively")
    parser.add_argument("--list-devices", action="store_true", help="List all devices")
    parser.add_argument("--migrate-devices", action="store_true", help="Migrate static devices to database")
    parser.add_argument("--migrate-snapshots", action="store_true", help="Migrate file snapshots to database")
    parser.add_argument("--test-device", action="store_true", help="Test device connection")
    parser.add_argument("--full-setup", action="store_true", help="Run full setup (init + migrate)")
    
    args = parser.parse_args()
    
    # Check connection first
    if not check_database_connection():
        sys.exit(1)
    
    if args.full_setup:
        init_database()
        migrate_static_devices()
        migrate_file_snapshots()
        list_devices()
    elif args.init:
        init_database()
    elif args.add_device:
        add_device_interactive()
    elif args.list_devices:
        list_devices()
    elif args.migrate_devices:
        migrate_static_devices()
    elif args.migrate_snapshots:
        migrate_file_snapshots()
    elif args.test_device:
        test_device_connection()
    else:
        print("Route Monitor Database Setup")
        print("============================")
        print("\nQuick start:")
        print("  python setup_database.py --full-setup    # Initialize and migrate everything")
        print("\nOr run individual commands:")
        print("  python setup_database.py --init          # Initialize database tables")
        print("  python setup_database.py --add-device    # Add a device interactively")
        print("  python setup_database.py --list-devices  # List all devices")
        print("\nRun with --help for all options")


if __name__ == "__main__":
    main()