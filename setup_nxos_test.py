#!/usr/bin/env python
"""
Setup script to configure test routes on Cisco DevNet Always-On NXOS
and then test the route monitor against it.

Device: sbx-nxos-mgmt.cisco.com
Username: admin  
Password: Admin_1234!
"""

import os
import sys
import time
from netmiko import ConnectHandler
from parsers import collect_device_tables
from models import AFI4, AFI6

# Always-On NXOS credentials
NXOS_DEVICE = {
    "device_type": "cisco_nxos",
    "host": "sbx-nxos-mgmt.cisco.com",
    "username": "admin",
    "password": "Admin_1234!",
    "port": 22,
}

def setup_test_routes(conn):
    """Configure test routes on NXOS device"""
    print("Setting up test configuration on NXOS...")
    
    # Test configuration commands
    # Note: The sandbox may have restrictions on what can be configured
    test_config = [
        # Create a loopback for testing
        "interface loopback100",
        "description Test interface for route monitor",
        "ip address 192.168.100.1/32",
        "no shutdown",
        
        # Add some static routes for testing
        "ip route 10.99.99.0/24 Null0 name TEST_ROUTE_MONITOR",
        "ip route 10.88.88.0/24 Null0 name TEST_ROUTE_MONITOR_2",
    ]
    
    try:
        output = conn.send_config_set(test_config)
        print(f"Configuration output:\n{output}")
        
        # Save config
        conn.send_command("copy running-config startup-config", expect_string="")
        time.sleep(2)
        
        return True
    except Exception as e:
        print(f"Warning: Could not apply full config (sandbox restrictions): {e}")
        return False

def verify_routes(conn):
    """Verify routes are present"""
    print("\nVerifying routes...")
    
    # Check routing table
    output = conn.send_command("show ip route vrf default | include 10.99.99|10.88.88|192.168.100")
    if output:
        print(f"Found test routes:\n{output}")
        return True
    else:
        print("Test routes not found in routing table")
        return False

def test_collection():
    """Test route collection with our monitor"""
    print("\n" + "="*60)
    print("Testing Route Monitor Collection")
    print("="*60)
    
    # Create device dict for our collector (name is separate)
    device = {
        "device_type": NXOS_DEVICE["device_type"],
        "host": NXOS_DEVICE["host"],
        "username": NXOS_DEVICE["username"],
        "password": NXOS_DEVICE["password"],
        "port": NXOS_DEVICE["port"],
        "name": "nxos-sandbox"
    }
    
    vrfs = ["default"]
    afis = [AFI4]
    
    try:
        # Collect routing tables
        result = collect_device_tables(device, vrfs, afis)
        
        print(f"\nCollection Results:")
        print(f"  Device: {result['device']}")
        print(f"  RIB Entries: {len(result['rib'])}")
        print(f"  BGP Entries: {len(result['bgp'])}")
        
        # Look for our test routes
        test_routes = []
        for entry in result['rib']:
            if '10.99.99' in entry.prefix or '10.88.88' in entry.prefix or '192.168.100' in entry.prefix:
                test_routes.append(entry)
                print(f"\nFound test route: {entry.serialize()}")
        
        if test_routes:
            print(f"\n✓ Successfully found {len(test_routes)} test routes")
            return True
        else:
            print("\n✗ Test routes not found in collected data")
            return False
            
    except Exception as e:
        print(f"\n✗ Collection failed: {e}")
        return False

def cleanup_test_routes(conn):
    """Remove test configuration"""
    print("\nCleaning up test configuration...")
    
    cleanup_config = [
        "no interface loopback100",
        "no ip route 10.99.99.0/24 Null0",
        "no ip route 10.88.88.0/24 Null0",
    ]
    
    try:
        output = conn.send_config_set(cleanup_config)
        print("Test configuration removed")
    except Exception as e:
        print(f"Warning: Could not fully cleanup: {e}")

def main():
    """Main test flow"""
    print("="*60)
    print("NXOS Route Monitor Test with Real Device")
    print("="*60)
    print(f"Target: {NXOS_DEVICE['host']}")
    print()
    
    success = False
    
    try:
        # Connect to device
        print("Connecting to NXOS device...")
        conn = ConnectHandler(**NXOS_DEVICE)
        print("✓ Connected successfully")
        
        # Get device info
        version = conn.send_command("show version | include 'NXOS|uptime'")
        print(f"\nDevice Info:\n{version}")
        
        # Setup test routes
        if setup_test_routes(conn):
            time.sleep(3)  # Wait for routes to propagate
            
            # Verify routes on device
            if verify_routes(conn):
                # Test collection with our monitor
                success = test_collection()
        
        # Cleanup (optional - comment out to keep test routes)
        # cleanup_test_routes(conn)
        
        conn.disconnect()
        
    except Exception as e:
        print(f"\n✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        success = False
    
    print("\n" + "="*60)
    if success:
        print("✓ TEST PASSED - Route monitor successfully collected test routes")
    else:
        print("✗ TEST FAILED - Check output above for details")
    print("="*60)
    
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())