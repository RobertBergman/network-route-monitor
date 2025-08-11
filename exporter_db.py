"""
Prometheus exporter for database-based route monitoring.
"""

import os
import time
from datetime import datetime, timedelta
from typing import Dict, List

from prometheus_client import start_http_server, Gauge, Counter, Info
from dotenv import load_dotenv

from database import get_session
from storage_db import DatabaseStorage
from device_manager import DeviceManager

load_dotenv()

# Metrics
route_count = Gauge('route_count', 'Number of routes in table', ['device', 'vrf', 'afi', 'table'])
bgp_prefix_count = Gauge('bgp_prefix_count', 'Number of BGP prefixes', ['device', 'vrf', 'afi'])
route_changes = Counter('route_changes_total', 'Total route changes', ['device', 'vrf', 'afi', 'table', 'change_type'])
last_collection_time = Gauge('last_collection_timestamp', 'Unix timestamp of last collection', ['device', 'vrf', 'afi', 'table'])
device_status = Gauge('device_enabled', 'Device monitoring status (1=enabled, 0=disabled)', ['device'])
collection_errors = Counter('collection_errors_total', 'Total collection errors', ['device'])

# Info metrics
device_info = Info('device', 'Device information', ['device'])


def export_metrics():
    """Export metrics from database to Prometheus."""
    storage = DatabaseStorage()
    manager = DeviceManager()
    
    try:
        # Get all devices
        devices = manager.get_all_devices(enabled_only=False)
        
        for device in devices:
            # Export device status
            device_status.labels(device=device.name).set(1 if device.enabled else 0)
            
            # Export device info
            device_info.labels(device=device.name).info({
                'hostname': device.hostname,
                'device_type': device.device_type,
                'use_nxapi': str(device.use_nxapi),
            })
            
            if not device.enabled:
                continue
            
            # Get available tables for this device
            tables = storage.get_available_tables(device.name)
            
            for table_type, vrf, afi in tables:
                # Get latest snapshot
                snapshot = storage.get_latest_snapshot(device.name, table_type, vrf, afi)
                
                if snapshot:
                    # Export route count
                    count = len(snapshot)
                    if table_type == "rib":
                        route_count.labels(
                            device=device.name,
                            vrf=vrf,
                            afi=afi,
                            table=table_type
                        ).set(count)
                    else:  # bgp
                        bgp_prefix_count.labels(
                            device=device.name,
                            vrf=vrf,
                            afi=afi
                        ).set(count)
                    
                    # Get latest collection timestamp
                    timestamps = storage.list_snapshots(device.name, table_type, vrf, afi, limit=1)
                    if timestamps:
                        last_collection_time.labels(
                            device=device.name,
                            vrf=vrf,
                            afi=afi,
                            table=table_type
                        ).set(timestamps[0].timestamp())
                
                # Get recent diffs for change metrics
                diffs = storage.get_diffs(device.name, vrf, afi, table_type, limit=10)
                
                for diff in diffs:
                    # Count changes in this diff
                    if diff.get('added'):
                        route_changes.labels(
                            device=device.name,
                            vrf=vrf,
                            afi=afi,
                            table=table_type,
                            change_type='added'
                        )._value._value = len(diff['added'])
                    
                    if diff.get('removed'):
                        route_changes.labels(
                            device=device.name,
                            vrf=vrf,
                            afi=afi,
                            table=table_type,
                            change_type='removed'
                        )._value._value = len(diff['removed'])
                    
                    if diff.get('changed'):
                        route_changes.labels(
                            device=device.name,
                            vrf=vrf,
                            afi=afi,
                            table=table_type,
                            change_type='changed'
                        )._value._value = len(diff['changed'])
    
    finally:
        storage.close()
        manager.close()


def main():
    """Main exporter loop."""
    port = int(os.environ.get("PROM_PORT", "9108"))
    
    # Start Prometheus HTTP server
    start_http_server(port)
    print(f"Prometheus exporter started on port {port}")
    
    # Export metrics every 30 seconds
    while True:
        try:
            export_metrics()
        except Exception as e:
            print(f"Error exporting metrics: {e}")
        
        time.sleep(30)


if __name__ == "__main__":
    main()