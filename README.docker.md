# Route Monitor - Docker Deployment

This guide covers deploying the Route Monitor system using Docker and docker-compose.

## Quick Start

1. **Configure environment**:
```bash
cp .env.docker .env
# Edit .env with your device credentials
```

2. **Configure devices** (edit `poller.py`):
```python
STATIC_DEVICES = [
    {"device_type":"cisco_nxos","host":"10.0.0.1","username":"admin",
     "password":"password","name":"router1"},
]
```

3. **Start services**:
```bash
# Development mode (minimal services)
make dev

# Production mode (all services)
make prod
```

## Architecture

The Docker setup includes the following services:

### Core Services
- **poller**: Collects routing data from network devices
- **api**: REST API server (FastAPI)
- **exporter**: Prometheus metrics exporter

### Production Services (docker-compose.prod.yml)
- **nginx**: Reverse proxy and static file server
- **prometheus**: Metrics collection
- **grafana**: Visualization dashboards

## File Structure

```
route_monitor/
├── docker-compose.yml          # Development setup
├── docker-compose.prod.yml     # Production setup
├── Dockerfile                   # Application container
├── .dockerignore               # Build exclusions
├── .env                        # Environment configuration
├── nginx.conf                  # Nginx configuration
├── prometheus.yml              # Prometheus configuration
├── Makefile                    # Management commands
└── route_snaps/                # Persistent data (mounted volume)
    └── <device>/
        ├── rib/
        ├── bgp/
        └── diffs/
```

## Data Persistence

All route snapshots are stored in `./route_snaps` which is mounted as a volume:

```yaml
volumes:
  - ./route_snaps:/app/route_snaps
```

This ensures data persists across container restarts.

## Management Commands

```bash
# Build images
make build

# Start services
make up          # Development
make prod        # Production

# View logs
make logs        # Development
make prod-logs   # Production

# Stop services
make down        # Development
make prod-down   # Production

# Backup data
make backup

# Access container shell
make shell-poller
make shell-api

# Restart specific service
docker-compose restart poller
```

## Accessing Services

### Development Mode
- Web UI: http://localhost:5000
- API: http://localhost:5000/api/
- Metrics: http://localhost:9108/metrics

### Production Mode
- Web UI: http://localhost
- API: http://localhost/api/
- Prometheus: http://localhost:9090
- Grafana: http://localhost:3000 (admin/admin)

## Environment Variables

Key configuration options in `.env`:

```bash
# Polling interval (seconds)
POLL_INTERVAL_SEC=60

# Device credentials
NETOPS_USER=admin
NETOPS_PASS=password

# NetBox integration (optional)
USE_NETBOX=false
NB_URL=https://netbox.example.com
NB_TOKEN=your-token

# NX-API optimization
USE_NXAPI=true
NXAPI_SCHEME=https
NXAPI_PORT=443
```

## Adding Devices

### Option 1: Edit poller.py
```python
STATIC_DEVICES = [
    {"device_type":"cisco_nxos","host":"10.0.0.1","username":"admin",
     "password":"password","name":"core-sw1"},
    {"device_type":"cisco_ios","host":"10.0.0.2","username":"admin",
     "password":"password","name":"edge-rt1"},
]
```

### Option 2: Use NetBox
```bash
# In .env
USE_NETBOX=true
NB_URL=https://your-netbox.com
NB_TOKEN=your-api-token
```

## Monitoring & Alerting

### Prometheus Queries

```promql
# Route changes per device
route_changes_total{device="router1"}

# Current route count
route_count{device="router1",table="rib",vrf="default"}

# Collection failures
route_collection_errors_total
```

### Grafana Dashboards

1. Access Grafana: http://localhost:3000
2. Default credentials: admin/admin
3. Import dashboard from `grafana/dashboards/`

## Troubleshooting

### Check service status
```bash
docker-compose ps
```

### View logs
```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f poller
```

### Debug collection issues
```bash
# Access poller shell
docker-compose exec poller /bin/bash

# Test device connectivity
python debug_nxos.py

# Run one-shot collection
python poller.py --once
```

### Common Issues

1. **No data collected**:
   - Check device credentials in `.env`
   - Verify network connectivity to devices
   - Check poller logs: `docker-compose logs poller`

2. **API not accessible**:
   - Ensure port 5000 is not in use
   - Check API logs: `docker-compose logs api`

3. **Permission denied on route_snaps**:
   ```bash
   chmod -R 755 route_snaps/
   ```

## Production Deployment

For production environments:

1. Use `docker-compose.prod.yml`
2. Configure proper secrets management
3. Set up SSL/TLS with nginx
4. Configure Grafana alerts
5. Implement log aggregation
6. Set up automated backups

```bash
# Start production stack
docker-compose -f docker-compose.prod.yml up -d

# Scale poller if needed
docker-compose -f docker-compose.prod.yml scale poller=2
```

## Backup & Restore

### Backup
```bash
make backup
# Creates: route_snaps_backup_YYYYMMDD_HHMMSS.tar.gz
```

### Restore
```bash
tar -xzf route_snaps_backup_20240811_120000.tar.gz
```

## Security Considerations

1. **Secrets Management**:
   - Never commit `.env` files
   - Use Docker secrets in production
   - Consider HashiCorp Vault integration

2. **Network Isolation**:
   - Use dedicated Docker network
   - Implement firewall rules
   - Use read-only mounts where possible

3. **Container Security**:
   - Run as non-root user
   - Use minimal base images
   - Regularly update dependencies

## Support

For issues or questions:
1. Check logs: `make logs`
2. Review documentation: `CLAUDE.md`
3. Test connectivity: `python debug_nxos.py`