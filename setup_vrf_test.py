#!/usr/bin/env python3
"""Set up VRF with routes on NX-OS for testing VRF monitoring."""

from netmiko import ConnectHandler
import sys

def setup_vrf_with_routes():
    """Create VRF and add various routes for testing."""
    
    device = {
        'device_type': 'cisco_nxos',
        'host': 'sbx-nxos-mgmt.cisco.com',
        'username': 'admin',
        'password': 'Admin_1234!',
        'port': 22,
    }
    
    print("=" * 60)
    print("Setting up VRF with Routes on NX-OS")
    print("=" * 60)
    
    print("\nConnecting to NX-OS device...")
    conn = ConnectHandler(**device)
    
    # Create VRF and configure interfaces
    print("\n1. Creating VRF 'CUSTOMER_A'...")
    vrf_commands = [
        'configure terminal',
        'vrf context CUSTOMER_A',
        'description Customer A VRF for route monitoring test',
        'rd 65001:100',
        'address-family ipv4 unicast',
        'exit',
        'address-family ipv6 unicast',
        'exit',
        'exit',
        
        # Create loopback interfaces in VRF
        'interface loopback150',
        'description CUSTOMER_A VRF Loopback',
        'vrf member CUSTOMER_A',
        'ip address 192.168.150.1/32',
        'ipv6 address 2001:db8:150::1/128',
        'no shutdown',
        
        'interface loopback151',
        'description CUSTOMER_A VRF Loopback 2',
        'vrf member CUSTOMER_A',
        'ip address 192.168.151.1/32',
        'ipv6 address 2001:db8:151::1/128',
        'no shutdown',
        
        'end'
    ]
    
    output = conn.send_config_set(vrf_commands)
    print("✓ VRF created with loopback interfaces")
    
    # Add IPv4 static routes to VRF
    print("\n2. Adding IPv4 static routes to VRF...")
    ipv4_route_commands = [
        'configure terminal',
        'vrf context CUSTOMER_A',
        'ip route 172.20.0.0/24 Null0 name CUSTOMER_A_NET1',
        'ip route 172.20.1.0/24 Null0 name CUSTOMER_A_NET2',
        'ip route 172.20.2.0/24 Null0 name CUSTOMER_A_NET3',
        'ip route 10.100.0.0/16 Null0 name CUSTOMER_A_SUMMARY',
        'ip route 10.100.10.0/24 Null0 name CUSTOMER_A_SUBNET1',
        'ip route 10.100.20.0/24 Null0 name CUSTOMER_A_SUBNET2',
        'ip route 10.100.30.0/24 Null0 name CUSTOMER_A_SUBNET3',
        'exit',
        'end'
    ]
    
    output = conn.send_config_set(ipv4_route_commands)
    print("✓ Added 7 IPv4 static routes to VRF")
    
    # Add IPv6 static routes to VRF
    print("\n3. Adding IPv6 static routes to VRF...")
    ipv6_route_commands = [
        'configure terminal',
        'vrf context CUSTOMER_A',
        'ipv6 route 2001:db8:a000::/48 Null0 name CUSTOMER_A_V6_SUMMARY',
        'ipv6 route 2001:db8:a001::/64 Null0 name CUSTOMER_A_V6_NET1',
        'ipv6 route 2001:db8:a002::/64 Null0 name CUSTOMER_A_V6_NET2',
        'ipv6 route 2001:db8:a003::/64 Null0 name CUSTOMER_A_V6_NET3',
        'ipv6 route 2001:db8:cafe::/64 Null0 name CUSTOMER_A_V6_SPECIAL',
        'exit',
        'end'
    ]
    
    output = conn.send_config_set(ipv6_route_commands)
    print("✓ Added 5 IPv6 static routes to VRF")
    
    # Configure BGP for VRF
    print("\n4. Configuring BGP for VRF...")
    bgp_commands = [
        'configure terminal',
        'router bgp 64999',
        'vrf CUSTOMER_A',
        'address-family ipv4 unicast',
        'network 172.20.0.0/24',
        'network 172.20.1.0/24',
        'network 172.20.2.0/24',
        'network 10.100.0.0/16',
        'aggregate-address 10.100.0.0/16 summary-only',
        'exit',
        'address-family ipv6 unicast',
        'network 2001:db8:a000::/48',
        'network 2001:db8:a001::/64',
        'network 2001:db8:a002::/64',
        'aggregate-address 2001:db8:a000::/48 summary-only',
        'exit',
        'exit',
        'end'
    ]
    
    output = conn.send_config_set(bgp_commands)
    print("✓ BGP configured for VRF with IPv4 and IPv6 networks")
    
    # Verify VRF routes
    print("\n5. Verifying VRF routes...")
    
    # Check IPv4 routes
    print("\nIPv4 Routes in VRF CUSTOMER_A:")
    ipv4_routes = conn.send_command("show ip route vrf CUSTOMER_A | include /")
    for line in ipv4_routes.split('\n')[:10]:
        if '/' in line:
            print(f"  {line.strip()}")
    
    # Check IPv6 routes
    print("\nIPv6 Routes in VRF CUSTOMER_A:")
    ipv6_routes = conn.send_command("show ipv6 route vrf CUSTOMER_A | include ::")
    for line in ipv6_routes.split('\n')[:10]:
        if '::' in line:
            print(f"  {line.strip()}")
    
    # Check BGP routes
    print("\nBGP IPv4 Routes in VRF CUSTOMER_A:")
    bgp_ipv4 = conn.send_command("show bgp vrf CUSTOMER_A ipv4 unicast | include /")
    for line in bgp_ipv4.split('\n')[:5]:
        if '/' in line:
            print(f"  {line.strip()}")
    
    print("\nBGP IPv6 Routes in VRF CUSTOMER_A:")
    bgp_ipv6 = conn.send_command("show bgp vrf CUSTOMER_A ipv6 unicast | include ::")
    for line in bgp_ipv6.split('\n')[:5]:
        if '::' in line:
            print(f"  {line.strip()}")
    
    conn.disconnect()
    
    print("\n" + "=" * 60)
    print("✓ VRF 'CUSTOMER_A' configured with:")
    print("  - 2 Loopback interfaces (Lo150, Lo151)")
    print("  - 7 IPv4 static routes")
    print("  - 5 IPv6 static routes")
    print("  - BGP configuration with networks and aggregates")
    print("=" * 60)

if __name__ == "__main__":
    setup_vrf_with_routes()