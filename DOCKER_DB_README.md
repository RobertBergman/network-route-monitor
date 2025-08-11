# Docker Deployment with Database

The database-based version includes PostgreSQL for data storage, with optional Prometheus, Grafana, and pgAdmin for monitoring and management.

## Quick Start

### 1. Prerequisites
- Docker and Docker Compose installed
- At least 2GB of available RAM
- Ports 5000, 15432, 9108, 9090, 3000, 8080 available (or modify in docker-compose.db.yml)

### 2. Configuration
```bash
# Copy and edit environment file
cp .env.example .env
# Edit .env with your settings (optional, defaults work)
```

### 3. Start Services
```bash
# Using the convenience script
./docker-db.sh up

# Or manually with docker-compose
docker-compose -f docker-compose.db.yml up -d
```

### 4. Access Services

| Service | URL | Default Credentials |
|---------|-----|-------------------|
| Web UI | http://localhost:5000 | N/A |
| PostgreSQL | localhost:15432 | routemonitor/routemonitor |
| Prometheus | http://localhost:9090 | N/A |
| Grafana | http://localhost:3000 | admin/admin |
| pgAdmin | http://localhost:8080 | admin@example.com/admin |
| Metrics | http://localhost:9108/metrics | N/A |

## Management Commands

### Using the Convenience Script

```bash
# Start all services
./docker-db.sh up

# Stop all services
./docker-db.sh down

# Restart services
./docker-db.sh restart

# View logs
./docker-db.sh logs          # All services
./docker-db.sh logs poller   # Specific service

# Check status
./docker-db.sh status

# Initialize database
./docker-db.sh init

# Add a device interactively
./docker-db.sh add-device

# Backup database
./docker-db.sh backup

# Restore database
./docker-db.sh restore backup_20240101_120000.sql
```

### Manual Docker Commands

```bash
# Start services
docker-compose -f docker-compose.db.yml up -d

# Stop services
docker-compose -f docker-compose.db.yml down

# View logs
docker-compose -f docker-compose.db.yml logs -f poller

# Execute commands in containers
docker exec -it route-poller-db python setup_database.py --list-devices
docker exec -it route-db psql -U routemonitor

# Backup database
docker exec route-db pg_dump -U routemonitor routemonitor > backup.sql

# Restore database
docker exec -i route-db psql -U routemonitor routemonitor < backup.sql
```

## Service Architecture

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Web UI    │────▶│   FastAPI   │────▶│ PostgreSQL  │
│  (Browser)  │     │   (API)     │     │  Database   │
└─────────────┘     └─────────────┘     └─────────────┘
                            │                    ▲
                            │                    │
┌─────────────┐     ┌─────────────┐            │
│ Prometheus  │────▶│  Exporter   │────────────┘
└─────────────┘     └─────────────┘            │
       │                                        │
       ▼                                        │
┌─────────────┐     ┌─────────────┐            │
│   Grafana   │     │   Poller    │────────────┘
└─────────────┘     └─────────────┘
```

## Services Description

### Core Services

- **postgres**: PostgreSQL database for storing device configs, snapshots, and diffs
- **poller**: Collects routing data from devices and stores in database
- **api**: FastAPI server providing REST API and serving web UI
- **exporter**: Prometheus metrics exporter reading from database

### Optional Services

- **prometheus**: Time-series metrics collection
- **grafana**: Visualization dashboards
- **pgadmin**: Web-based PostgreSQL administration

### Utility Services

- **db-init**: One-time database initialization and migration (runs once)

## Data Persistence

Data is persisted using Docker volumes:

- `postgres-data`: PostgreSQL database files
- `grafana-data`: Grafana dashboards and settings
- `prometheus-data`: Prometheus metrics data
- `pgadmin-data`: pgAdmin configuration

The encryption key (`.encryption_key`) is mounted as a file and shared between services.

## Environment Variables

Key environment variables (set in `.env`):

```bash
# Database
DB_PASSWORD=routemonitor         # PostgreSQL password

# Monitoring
POLL_INTERVAL_SEC=60             # Collection interval
PROM_PORT=9108                   # Prometheus exporter port

# Device Connection
USE_NXAPI=false                  # Use NX-API for Nexus devices
NXAPI_VERIFY=false              # SSL verification for NX-API

# Admin Interfaces
GRAFANA_PASSWORD=admin           # Grafana admin password
PGADMIN_EMAIL=admin@example.com  # pgAdmin login email
PGADMIN_PASSWORD=admin           # pgAdmin password
```

## Scaling Considerations

### Resource Requirements

- PostgreSQL: 512MB RAM minimum
- Poller: 256MB RAM per device
- API: 256MB RAM
- Exporter: 128MB RAM
- Grafana: 256MB RAM
- Prometheus: 512MB RAM

### Performance Tuning

For large deployments (>100 devices):

1. Increase PostgreSQL resources:
```yaml
postgres:
  environment:
    - POSTGRES_SHARED_BUFFERS=256MB
    - POSTGRES_WORK_MEM=4MB
  deploy:
    resources:
      limits:
        memory: 2G
```

2. Add database indexes (already included in schema)

3. Consider running multiple poller instances for different device groups

## Troubleshooting

### Database Connection Issues
```bash
# Check PostgreSQL is running
docker-compose -f docker-compose.db.yml ps postgres

# Test database connection (inside container)
docker exec -it route-db psql -U routemonitor -c "SELECT 1"

# Connect from host machine (port 15432)
psql -h localhost -p 15432 -U routemonitor -d routemonitor

# View database logs
docker-compose -f docker-compose.db.yml logs postgres
```

**Note:** PostgreSQL is exposed on port 15432 (not 5432) to avoid conflicts with any existing PostgreSQL installation.

### Poller Issues
```bash
# Check poller logs
docker-compose -f docker-compose.db.yml logs poller

# Test device connectivity
docker exec -it route-poller-db python setup_database.py --test-device

# List devices
docker exec -it route-poller-db python setup_database.py --list-devices
```

### Web UI Issues
```bash
# Check API logs
docker-compose -f docker-compose.db.yml logs api

# Test API endpoint
curl http://localhost:5000/api/devices
```

## Migration from File-Based System

If you have existing data in the file-based system:

```bash
# 1. Ensure old snapshots exist
ls -la route_snaps/

# 2. Start database
./docker-db.sh up postgres

# 3. Run migration
docker-compose -f docker-compose.db.yml run --rm db-init

# This will:
# - Initialize database schema
# - Import devices from STATIC_DEVICES
# - Migrate snapshots from route_snaps/
```

## Backup and Recovery

### Automated Backup
```bash
# Create backup
./docker-db.sh backup

# Schedule daily backups with cron
0 2 * * * /path/to/route_monitor/docker-db.sh backup
```

### Manual Backup
```bash
# Full database dump
docker exec route-db pg_dump -U routemonitor routemonitor > backup_$(date +%Y%m%d).sql

# Backup encryption key (CRITICAL!)
cp .encryption_key .encryption_key.backup
```

### Recovery
```bash
# Restore from backup
./docker-db.sh restore backup_20240101.sql

# Restore encryption key
cp .encryption_key.backup .encryption_key
```

## Security Notes

1. **Change default passwords** in production
2. **Backup encryption key** (`.encryption_key`) - losing this means losing access to device passwords
3. **Use SSL/TLS** for PostgreSQL in production
4. **Restrict network access** using Docker networks
5. **Regular backups** of both database and encryption key

## Monitoring

### Prometheus Queries

```promql
# Total routes per device
sum(route_count) by (device)

# Route changes in last hour
increase(route_changes_total[1h])

# Devices not collecting
time() - last_collection_timestamp > 300
```

### Grafana Dashboard

Import the included dashboard from `grafana/dashboards/` or create custom dashboards.

## Upgrading

To upgrade the system:

```bash
# 1. Backup data
./docker-db.sh backup

# 2. Pull latest code
git pull

# 3. Rebuild and restart
./docker-db.sh down
./docker-db.sh up
```