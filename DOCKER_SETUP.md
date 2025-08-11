# Docker Setup for Route Monitor

This guide explains how to build, run, and deploy the Route Monitor application using Docker and GitHub Container Registry (GHCR).

## Prerequisites

- Docker and Docker Compose installed
- GitHub account with repository access
- GitHub Personal Access Token (PAT) with `write:packages` scope for GHCR

## Local Development

### Building the Docker Image

```bash
# Build the main image
docker build -t route-monitor .

# Or use docker-compose to build all services
docker-compose build
```

### Running with Docker Compose

```bash
# Start all services
docker-compose up -d

# Start specific services
docker-compose up -d poller exporter api

# View logs
docker-compose logs -f poller
docker-compose logs -f api

# Stop all services
docker-compose down
```

### Service Endpoints

- **API Server**: http://localhost:5000
- **Web UI**: http://localhost:5000 (served by API)
- **Prometheus Metrics**: http://localhost:9108/metrics

## GitHub Container Registry (GHCR) Setup

### 1. Enable GitHub Actions

The repository includes a GitHub Actions workflow (`.github/workflows/docker.yml`) that automatically builds and pushes images to GHCR.

### 2. Container Registry Authentication

```bash
# Login to GHCR locally
export CR_PAT=YOUR_GITHUB_TOKEN
echo $CR_PAT | docker login ghcr.io -u YOUR_GITHUB_USERNAME --password-stdin
```

### 3. Manual Push to GHCR

```bash
# Tag the image
docker tag route-monitor ghcr.io/YOUR_GITHUB_USERNAME/route_monitor:latest
docker tag route-monitor ghcr.io/YOUR_GITHUB_USERNAME/route_monitor:v1.0.0

# Push to GHCR
docker push ghcr.io/YOUR_GITHUB_USERNAME/route_monitor:latest
docker push ghcr.io/YOUR_GITHUB_USERNAME/route_monitor:v1.0.0
```

### 4. Automated Builds with GitHub Actions

The workflow triggers on:
- Push to `main` or `database-migration` branches
- Version tags (e.g., `v1.0.0`)
- Pull requests to `main`
- Manual workflow dispatch

Images are tagged with:
- Branch name (e.g., `main`, `database-migration`)
- Version tags (e.g., `v1.0.0`, `v1.0`, `v1`)
- SHA prefix (e.g., `main-abc123`)
- `latest` for the default branch

### 5. Component Images

The workflow also builds specialized images for each component:
- `ghcr.io/YOUR_GITHUB_USERNAME/route_monitor-poller`
- `ghcr.io/YOUR_GITHUB_USERNAME/route_monitor-exporter`
- `ghcr.io/YOUR_GITHUB_USERNAME/route_monitor-api`

## Production Deployment

### Using GHCR Images

Create a `docker-compose.prod.yml`:

```yaml
version: '3.8'

services:
  poller:
    image: ghcr.io/YOUR_GITHUB_USERNAME/route_monitor-poller:latest
    container_name: route-poller
    env_file: .env.prod
    volumes:
      - ./route_snaps:/app/route_snaps
    restart: always

  exporter:
    image: ghcr.io/YOUR_GITHUB_USERNAME/route_monitor-exporter:latest
    container_name: route-exporter
    ports:
      - "9108:9108"
    volumes:
      - ./route_snaps:/app/route_snaps:ro
    restart: always

  api:
    image: ghcr.io/YOUR_GITHUB_USERNAME/route_monitor-api:latest
    container_name: route-api
    ports:
      - "5000:5000"
    volumes:
      - ./route_snaps:/app/route_snaps:ro
    restart: always
```

### Deployment Steps

```bash
# Pull latest images from GHCR
docker-compose -f docker-compose.prod.yml pull

# Start services
docker-compose -f docker-compose.prod.yml up -d

# Update to new version
docker-compose -f docker-compose.prod.yml pull
docker-compose -f docker-compose.prod.yml up -d --force-recreate
```

## Environment Variables

Create a `.env` file for local development or `.env.prod` for production:

```bash
# Device credentials
NETOPS_USER=admin
NETOPS_PASS=your_password

# NX-API settings
USE_NXAPI=true
NXAPI_SCHEME=https
NXAPI_PORT=443
NXAPI_VERIFY=false

# NetBox integration (optional)
USE_NETBOX=false
NB_URL=https://netbox.example.com
NB_TOKEN=your_netbox_token

# Collection settings
POLL_INTERVAL_SEC=60
SNAPDIR=/app/route_snaps

# Prometheus settings
PROM_PORT=9108
```

## Container Management

### Health Checks

```bash
# Check container status
docker-compose ps

# Check container health
docker inspect route-api | jq '.[0].State.Health'
```

### Resource Limits

Add resource constraints in `docker-compose.yml`:

```yaml
services:
  poller:
    deploy:
      resources:
        limits:
          cpus: '0.5'
          memory: 512M
        reservations:
          cpus: '0.25'
          memory: 256M
```

### Persistent Data

Route snapshots are stored in the `./route_snaps` volume mount. Back up this directory regularly:

```bash
# Backup snapshots
tar -czf route_snaps_backup_$(date +%Y%m%d).tar.gz route_snaps/

# Restore snapshots
tar -xzf route_snaps_backup_20240101.tar.gz
```

## Multi-Architecture Builds

The GitHub Actions workflow builds for both `linux/amd64` and `linux/arm64` platforms:

```bash
# Build multi-arch locally
docker buildx create --use
docker buildx build --platform linux/amd64,linux/arm64 -t route-monitor .
```

## Troubleshooting

### View Container Logs

```bash
# All service logs
docker-compose logs

# Specific service with follow
docker-compose logs -f poller

# Last 100 lines
docker-compose logs --tail=100 api
```

### Debug Container Issues

```bash
# Enter container shell
docker exec -it route-poller /bin/bash

# Check environment variables
docker exec route-poller env

# Test connectivity from container
docker exec route-poller python -c "import requests; print(requests.get('https://sbx-nxos-mgmt.cisco.com').status_code)"
```

### Common Issues

1. **Permission denied on route_snaps**: Ensure the directory has proper permissions:
   ```bash
   chmod -R 755 route_snaps/
   ```

2. **Cannot connect to devices**: Check network connectivity and firewall rules. Containers may need host networking:
   ```yaml
   network_mode: host
   ```

3. **GHCR authentication fails**: Ensure your PAT has `write:packages` scope and hasn't expired.

4. **Out of memory**: Increase Docker's memory limit or add resource constraints to containers.

## Security Considerations

1. **Never commit `.env` files** with real credentials
2. **Use secrets management** for production deployments
3. **Run containers as non-root** when possible
4. **Keep base images updated** regularly
5. **Scan images for vulnerabilities**:
   ```bash
   docker scout cves route-monitor
   ```

## CI/CD Integration

The GitHub Actions workflow can be extended to:
- Run tests before building
- Deploy to Kubernetes
- Send notifications on build status
- Trigger downstream deployments

Example: Add testing stage to workflow:

```yaml
test:
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4
    - name: Run tests
      run: |
        docker build -t test-image .
        docker run --rm test-image python -m pytest
```