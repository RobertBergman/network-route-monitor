#!/usr/bin/env python
"""Debug script to test NXOS parsing"""

from netmiko import ConnectHandler
import json

NXOS_DEVICE = {
    "device_type": "cisco_nxos",
    "host": "sbx-nxos-mgmt.cisco.com",
    "username": "admin",
    "password": "Admin_1234!",
    "port": 22,
}

def test_json_commands():
    """Test what JSON commands work on the device"""
    print("Testing JSON commands on NXOS...")
    
    conn = ConnectHandler(**NXOS_DEVICE)
    
    commands = [
        "show ip route vrf default | json",
        "show ip route vrf default",
        "show bgp vrf default ipv4 unicast | json",
        "show version | json"
    ]
    
    for cmd in commands:
        print(f"\n{'='*60}")
        print(f"Command: {cmd}")
        print('='*60)
        try:
            output = conn.send_command(cmd)
            
            # Check if it's JSON
            if output.strip().startswith('{') or output.strip().startswith('['):
                print("✓ JSON output detected")
                data = json.loads(output)
                print(f"  Keys: {list(data.keys())[:5]}")
                
                # If it's a route command, show structure
                if 'route' in cmd:
                    if 'TABLE_vrf' in data:
                        print(f"  Has TABLE_vrf structure")
                        vrf_data = data['TABLE_vrf']
                        if 'ROW_vrf' in vrf_data:
                            print(f"    Has ROW_vrf")
                    elif 'vrf' in data:
                        print(f"  Has vrf structure")
            else:
                print("✗ Not JSON output")
                print(f"  First 200 chars: {output[:200]}")
                
        except Exception as e:
            print(f"✗ Command failed: {e}")
    
    conn.disconnect()

if __name__ == "__main__":
    test_json_commands()