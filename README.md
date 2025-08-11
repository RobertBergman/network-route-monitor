# Route Monitor - Enterprise Routing & BGP Change Tracker

A lightweight, production-ready toolkit to snapshot, diff, and alert on routing/RIB changes across VRFs and AFIs (IPv4/IPv6) with NX-OS/NX-API optimization.

## Features

- **Multi-vendor support**: IOS-XE, NX-OS with native JSON and NX-API
- **Robust parsing**: Genie/pyATS with JSON CLI preference
- **ECMP-aware**: Stable ECMP set comparison avoiding false positives
- **Per-VRF/AFI tracking**: Separate snapshots and diffs per routing domain
- **Prometheus metrics**: Real-time alerting on route changes
- **NetBox integration**: Optional dynamic inventory discovery
- **Optimized for NX-OS**: Native NX-API support for faster collection

## Quick Start

```bash
# Install dependencies
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your credentials and settings

# Run one-shot collection
python poller.py --once

# Start Prometheus exporter
python exporter.py
# Metrics available at http://localhost:9108/metrics
```

## Configuration

### Environment Variables (.env)

```bash
# Core settings
SNAPDIR=./route_snaps        # Snapshot storage directory
POLL_INTERVAL_SEC=60          # Collection interval
PROM_PORT=9108               # Prometheus metrics port

# Device credentials
NETOPS_USER=readonly_user
NETOPS_PASS=secure_password

# NetBox integration (optional)
USE_NETBOX=false
NB_URL=https://netbox.example.com
NB_TOKEN=your_api_token

# NX-OS optimization
USE_NXAPI=true               # Enable NX-API for Nexus devices
NXAPI_SCHEME=https
NXAPI_PORT=443
NXAPI_VERIFY=false           # For lab environments only
```

## Architecture

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│   Devices   │────▶│    Poller    │────▶│  Storage    │
│ (XE/NX-OS)  │     │ (parsers.py) │     │ (snapshots) │
└─────────────┘     └──────────────┘     └─────────────┘
                            │                     │
                            ▼                     ▼
                    ┌──────────────┐     ┌─────────────┐
                    │   Diffing    │     │  Exporter   │
                    │ (diffing.py) │     │ (metrics)   │
                    └──────────────┘     └─────────────┘
                            │                     │
                            ▼                     ▼
                    ┌──────────────┐     ┌─────────────┐
                    │    Alerts    │     │ Prometheus  │
                    │   (changes)  │     │  /metrics   │
                    └──────────────┘     └─────────────┘
```

## Directory Structure

```
route_snaps/
  <device>/
    rib/
      <vrf>.<afi>.latest.json           # Current snapshot
      <vrf>.<afi>.YYYYMMDDHHMMSS.json.gz # Historical archives
    bgp/
      <vrf>.<afi>.latest.json
      <vrf>.<afi>.YYYYMMDDHHMMSS.json.gz
    diffs/
      <vrf>.<afi>.YYYYMMDDHHMMSS.json.gz # Change records
```

## Metrics & Alerting

### Available Metrics

- `route_count{device,vrf,afi}` - Current RIB route count
- `bgp_best_count{device,vrf,afi}` - BGP best path entries
- `rib_adds_total{device,vrf,afi}` - Route additions counter
- `rib_removes_total{device,vrf,afi}` - Route removals counter
- `bgp_attr_changes_total{device,vrf,afi,attr}` - BGP attribute changes
- `default_nexthop_change_total{device,vrf,afi}` - Default route changes
- `upstream_as_change_total{device,vrf,afi,prefix}` - Upstream AS changes

### Example Prometheus Alerts

```yaml
groups:
  - name: routing_alerts
    rules:
      - alert: RouteTableDrop
        expr: |
          (route_count - route_count offset 10m)
          < -0.2 * ignoring() group_left route_count offset 10m
        annotations:
          summary: "Significant route drop on {{ $labels.device }}"
          
      - alert: DefaultRouteChange
        expr: increase(default_nexthop_change_total[5m]) > 0
        annotations:
          summary: "Default route changed on {{ $labels.device }}"
          
      - alert: BGPChurn
        expr: |
          sum by(device,vrf,afi) 
          (increase(bgp_attr_changes_total[5m])) > 50
        annotations:
          summary: "High BGP churn on {{ $labels.device }}"
```

## Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=. --cov-report=html

# Run specific test suite
pytest tests/test_diffing.py -v

# Performance tests only
pytest tests/test_integration.py::TestPerformanceOptimization -v
```

## Production Deployment

### Systemd Service

```ini
# /etc/systemd/system/route-monitor.service
[Unit]
Description=Route Monitor Exporter
After=network-online.target

[Service]
Type=simple
User=netops
WorkingDirectory=/opt/route-monitor
Environment="PYTHONUNBUFFERED=1"
ExecStart=/opt/route-monitor/venv/bin/python /opt/route-monitor/exporter.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### Security Considerations

1. **Read-only credentials**: Use dedicated read-only accounts
2. **Network segmentation**: Deploy in management network
3. **TLS verification**: Enable `NXAPI_VERIFY=true` in production
4. **Secrets management**: Use vault/secrets manager for credentials
5. **Access control**: Restrict snapshot directory permissions

## Performance Optimization

### For Large Deployments

1. **Enable NX-API** for Nexus devices (10x faster than SSH)
2. **Tune collection intervals** based on network stability
3. **Use parallel collection** for multiple devices
4. **Implement snapshot rotation** to manage disk usage
5. **Consider time-series DB** (InfluxDB/TimescaleDB) for long-term storage

### Benchmarks

- 10,000 routes diff: < 1 second
- NX-API collection: ~2 seconds per device
- SSH collection: ~20 seconds per device
- Memory usage: < 100MB for 50k routes

## Troubleshooting

### Common Issues

1. **Genie parsing failures**
   - Ensure pyATS and genie.libs.parser versions match
   - Check device supports JSON output (`| json`)

2. **NX-API connection errors**
   - Verify `feature nxapi` is enabled on device
   - Check firewall rules for HTTPS (port 443)
   - Test with: `curl -k https://<device>/ins`

3. **High memory usage**
   - Implement snapshot rotation
   - Reduce retention period
   - Consider external storage for archives

## Contributing

1. Fork the repository
2. Create a feature branch
3. Write tests for new functionality
4. Ensure all tests pass
5. Submit a pull request

## License

MIT License - See LICENSE file for details

## Support

- Issues: GitHub Issues
- Documentation: See `project.md` for detailed implementation
- Commercial support: Contact your network vendor