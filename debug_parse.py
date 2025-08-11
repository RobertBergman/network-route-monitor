#!/usr/bin/env python
"""Debug parsing to see actual data structure"""

from netmiko import ConnectHandler
import json
import pprint

NXOS_DEVICE = {
    "device_type": "cisco_nxos",
    "host": "sbx-nxos-mgmt.cisco.com",
    "username": "admin",
    "password": "Admin_1234!",
    "port": 22,
}

def debug_route_parsing():
    """Debug route table parsing"""
    conn = ConnectHandler(**NXOS_DEVICE)
    
    # Get JSON route table
    output = conn.send_command("show ip route vrf default | json")
    data = json.loads(output)
    
    print("Full JSON structure (first 2000 chars):")
    print(json.dumps(data, indent=2)[:2000])
    
    # Try to parse it
    from parsers import parse_rib
    from models import AFI4
    
    entries = parse_rib("test-device", "nxos", "default", AFI4, data)
    print(f"\nParsed {len(entries)} entries")
    
    if entries:
        print("\nFirst entry:")
        print(entries[0].serialize())
    
    # Let's look at specific routes we added
    print("\n\nLooking for our test routes...")
    cmd = "show ip route 10.99.99.0 | json"
    output = conn.send_command(cmd)
    if output.strip().startswith('{'):
        route_data = json.loads(output)
        print("10.99.99.0 route structure:")
        print(json.dumps(route_data, indent=2)[:1000])
    
    conn.disconnect()

if __name__ == "__main__":
    debug_route_parsing()