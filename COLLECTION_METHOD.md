# Route Collection Method

## Overview
The route monitoring system collects routing data from network devices using a hierarchical approach that prioritizes speed and reliability.

## Collection Flow

### 1. Device Connection
The system connects to devices using credentials from the `.env` file or static configuration:
```python
# From poller.py
device = {
    "device_type": "cisco_nxos",
    "host": "sbx-nxos-mgmt.cisco.com",
    "username": "admin",
    "password": "Admin_1234!",
    "name": "sbx-nxos"
}
```

### 2. Collection Methods (Priority Order)

#### Method 1: NX-API REST (Fastest - 10x faster than SSH)
- **When**: `USE_NXAPI=true` and device is NX-OS
- **How**: HTTPS POST to `/ins` endpoint on port 443
- **Commands**: Sent as JSON-RPC with `output_format: "json"`
- **Response**: Native JSON structure directly from device

```python
# From parsers.py:_nxapi_request()
url = "https://sbx-nxos-mgmt.cisco.com:443/ins"
payload = {
    "ins_api": {
        "version": "1.2",
        "type": "cli_show",
        "input": "show ip route vrf CUSTOMER_A",
        "output_format": "json"
    }
}
```

#### Method 2: SSH with JSON Output
- **When**: Device supports `| json` command modifier
- **How**: SSH connection via Netmiko, append `| json` to commands
- **Commands**: `show ip route vrf default | json`
- **Response**: JSON text over SSH, parsed with ujson

```python
# From parsers.py:_try_json()
raw = conn.send_command("show ip route vrf default | json")
if raw.startswith("{"):
    return json.loads(raw)
```

#### Method 3: SSH with Genie Parsing (Fallback)
- **When**: No JSON support available
- **How**: SSH connection, text output parsed by Genie/pyATS
- **Commands**: Standard show commands without modifiers
- **Response**: Text converted to structured data by Genie

```python
# From parsers.py:_parse_with_genie()
raw = conn.send_command("show ip route vrf default")
return genie_device.parse(cmd, output=raw)
```

## Commands Executed

### For RIB Collection:
- IPv4: `show ip route vrf {vrf}`
- IPv6: `show ipv6 route vrf {vrf}`

### For BGP Collection:
- IPv4: `show bgp vrf {vrf} ipv4 unicast`
- IPv6: `show bgp vrf {vrf} ipv6 unicast`

## Data Processing Pipeline

1. **Collection** (`parsers.py:collect_device_tables()`)
   - Connects to device
   - Executes commands for each VRF/AFI combination
   - Returns raw parsed data

2. **Parsing** (`parsers.py:parse_rib()` and `parse_bgp()`)
   - Normalizes different JSON structures (Genie vs NX-API)
   - Handles both dict and list formats for ROW_* fields
   - Extracts relevant fields (prefix, nexthops, protocol, etc.)

3. **Normalization** (`models.py`)
   - Creates `RIBEntry` and `BGPEntry` objects
   - Handles ECMP by storing nexthops as sets
   - Normalizes communities and AS paths

4. **Storage** (`storage.py`)
   - Saves as `latest.json` for current state
   - Archives with timestamp as `.json.gz`
   - Stores diffs in compressed format

## Example Collection Session

```bash
# Current configuration (SSH mode)
$ python debug_nxos.py

Testing NX-OS JSON Support...
Connecting to sbx-nxos-mgmt.cisco.com...
Connected!

Testing: show ip route vrf default | json
✓ JSON supported for this command

Testing: show bgp vrf default ipv4 unicast | json
✓ JSON supported for this command

# Actual collection
$ python poller.py --once

[
  {
    "device": "sbx-nxos",
    "vrfs": {
      "default": {
        "ipv4": {
          "rib": {"adds": [], "rems": [], "chgs": []},
          "bgp": {"adds": [], "rems": [], "chgs": []}
        },
        "ipv6": {
          "rib": {"adds": [], "rems": [], "chgs": []},
          "bgp": {"adds": [], "rems": [], "chgs": []}
        }
      },
      "CUSTOMER_A": {
        "ipv4": {
          "rib": {"adds": [9 routes], "rems": [], "chgs": []},
          "bgp": {"adds": [4 routes], "rems": [], "chgs": []}
        }
      }
    }
  }
]
```

## Performance Characteristics

| Method | Connection Time | Command Execution | Total per Device |
|--------|----------------|-------------------|------------------|
| NX-API | ~0.5s | ~0.3s per command | ~2s |
| SSH + JSON | ~2s | ~2s per command | ~20s |
| SSH + Genie | ~2s | ~3s per command | ~30s |

## Current Production Configuration

Based on the `.env` file, the system is currently using:
- **Method**: SSH with JSON output (Method 2)
- **Device**: sbx-nxos-mgmt.cisco.com
- **VRFs Monitored**: default, CUSTOMER_A
- **AFIs**: IPv4, IPv6
- **Collection Interval**: 60 seconds

## Enabling NX-API for Better Performance

To enable the faster NX-API method:

1. On the NX-OS device:
```bash
configure terminal
feature nxapi
nxapi https port 443
end
```

2. In the `.env` file:
```bash
USE_NXAPI=true
NXAPI_SCHEME=https
NXAPI_PORT=443
NXAPI_VERIFY=false
```

This will reduce collection time from ~20 seconds to ~2 seconds per device.