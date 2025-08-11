# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a production-ready route monitoring system that tracks routing table (RIB) and BGP changes across network devices. It's optimized for Cisco NX-OS with NX-API support but also works with IOS-XE via SSH/CLI.

## Development Environment

### Setup
```bash
# Use the conda environment
conda activate route_monitor

# Or create fresh environment
conda create -n route_monitor python=3.10 -y
conda activate route_monitor
pip install -r requirements.txt

# Configure credentials
cp .env.example .env
# Edit .env with device credentials
```

### Running Tests
```bash
# All tests with coverage
python -m pytest --cov=. --cov-report=term-missing

# Specific test file
python -m pytest tests/test_diffing.py -v

# Test against real NXOS device (DevNet sandbox)
SKIP_REAL_DEVICE_TESTS=false python -m pytest tests/test_real_nxos.py -v -s

# Run the real device integration test
python setup_nxos_test.py  # Tests against sbx-nxos-mgmt.cisco.com
```

### Running the Application
```bash
# One-shot collection (prints JSON report)
python poller.py --once

# Start Prometheus exporter (runs continuously)
python exporter.py
# Metrics at http://localhost:9108/metrics

# Start API server for web UI (FastAPI)
uvicorn webui:app --host 0.0.0.0 --port 5000
# API at http://localhost:5000

# Start web UI (from webui/ directory)
cd webui && python -m http.server 8080
# UI at http://localhost:8080

# Debug parsing for a specific device
python debug_nxos.py   # Tests JSON command support
python debug_parse.py  # Tests parsing logic
```

## Architecture

### Core Data Flow
1. **Collection**: `parsers.py` connects to devices via Netmiko/NX-API and fetches routing data
2. **Parsing**: Device output (JSON preferred) is normalized into `RIBEntry` and `BGPEntry` objects
3. **Storage**: `storage.py` saves snapshots as JSON (latest) and compressed archives (historical)
4. **Diffing**: `diffing.py` compares snapshots to detect adds/removes/changes
5. **Metrics**: `exporter.py` exposes Prometheus metrics for alerting
6. **API**: `api_server.py` provides REST endpoints for snapshot data and diffs
7. **Web UI**: Real-time dashboard showing route changes, device status, and historical trends

### Key Design Decisions

**ECMP Handling**: Routes with multiple next-hops are treated as sets to avoid false-positive changes when next-hop order changes.

**NX-API Optimization**: When `USE_NXAPI=true`, the system uses HTTPS REST API instead of SSH for NX-OS devices (10x faster).

**Parser Strategy**: 
- First tries NX-API (if enabled for NX-OS)
- Then tries CLI with `| json` suffix
- Falls back to Genie/pyATS text parsing

**Storage Structure**:
```
route_snaps/
  <device>/
    rib/
      <vrf>.<afi>.latest.json          # Current snapshot
      <vrf>.<afi>.YYYYMMDDHHMMSS.json.gz  # Archives
    bgp/
      <vrf>.<afi>.latest.json
      <vrf>.<afi>.YYYYMMDDHHMMSS.json.gz
    diffs/
      <vrf>.<afi>.YYYYMMDDHHMMSS.json.gz  # Change records
```

### Critical Code Paths

**Adding NX-OS JSON Support**: The parser in `parsers.py:parse_rib()` handles two JSON structures:
1. Genie format: `parsed["vrf"][vrf]["address_family"]...`
2. NX-API format: `parsed["TABLE_vrf"]["ROW_vrf"]...`

Both formats must handle cases where `ROW_*` fields can be either dict (single entry) or list (multiple entries).

**Device Connection**: `collect_device_tables()` strips the `name` field from device dict before passing to `ConnectHandler` to avoid connection errors.

## Working with Real Devices

### Cisco DevNet Always-On Sandbox
The codebase is tested against:
- Host: `sbx-nxos-mgmt.cisco.com`
- Username: `admin`
- Password: `Admin_1234!`

Use `setup_nxos_test.py` to:
1. Configure test routes on the device
2. Verify collection works
3. Clean up test configuration

### Inventory Sources

**Static** (default): Edit `STATIC_DEVICES` in `poller.py`

**NetBox** (dynamic): Set `USE_NETBOX=true` and configure `NB_URL`/`NB_TOKEN`. Devices are filtered by role (router/core-router/edge-router) or "nexus" tag.

## Common Issues and Solutions

**Parse Failures**: Check if device supports JSON output with `show version | json`. If not, ensure Genie parser version matches device OS version.

**NX-API Connection Errors**: Verify `feature nxapi` is enabled on device. Check HTTPS connectivity to port 443.

**Empty Collection Results**: The parsers silently catch exceptions. Add debug prints in `collect_device_tables()` try/except blocks to see actual errors.

**Mock Test Failures**: Integration tests using mocks are fragile. Focus on `test_real_nxos.py` for validation against actual devices.

## Web UI Frontend

### Overview
The web UI provides real-time monitoring of routing changes across all devices. It auto-refreshes every 10 seconds and displays:
- Device status (collection timestamps, route counts)
- Recent route changes (adds/removes/modifications)
- Visual indicators for change types (green=added, red=removed, yellow=changed)

### API Endpoints

**`GET /api/devices`**: List all devices

**`GET /api/devices/{device}/tables`**: Get available VRF/AFI combinations

**`GET /api/devices/{device}/latest?table=rib&vrf=default&afi=ipv4`**: Get latest snapshot
- `table`: "rib" or "bgp"
- `vrf`: VRF name (e.g., "default")
- `afi`: Address family ("ipv4" or "ipv6")

**`GET /api/devices/{device}/diffs?vrf=default&afi=ipv4`**: List recent diffs
- Returns diff metadata with timestamps

**`GET /api/devices/{device}/diffs/{timestamp}?vrf=default&afi=ipv4`**: Get specific diff

**`GET /api/devices/{device}/history?table=rib&vrf=default&afi=ipv4`**: List historical snapshots
- Returns timestamps of archived snapshots

### Frontend Components

**`webui/index.html`**: Main dashboard layout with Bootstrap 5 styling

**`webui/app.js`**: Vue.js 3 application handling:
- Device status polling
- Change detection and display
- Auto-refresh timer
- Route detail expansion

### Testing Route Changes

To see the UI in action with route changes:
```bash
# Terminal 1: Start API server
uvicorn webui:app --host 0.0.0.0 --port 5000

# Terminal 2: Start web server (optional, API also serves static files)
cd webui && python -m http.server 8080

# Terminal 3: Run initial collection
python poller.py --once

# Terminal 4: Add/remove routes on device
python setup_nxos_test.py  # Adds test routes

# Terminal 5: Collect again to detect changes
python poller.py --once

# View changes in browser at http://localhost:8080 or http://localhost:5000
```

## Performance Considerations

- Collection time: ~2 seconds per device with NX-API, ~20 seconds with SSH
- Diff computation: <1 second for 10,000 routes
- Memory usage: ~100MB for 50,000 routes
- API response time: <100ms for snapshot queries
- UI refresh: 10-second intervals (configurable in app.js)
- Use parallel collection for multiple devices (not implemented, but `asyncio` recommended)