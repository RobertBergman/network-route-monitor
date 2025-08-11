# Database Migration Guide

This branch migrates the route monitoring system from file-based storage to a PostgreSQL database with secure password storage.

## Key Changes

### 1. Database Storage
- **Before**: Route snapshots stored as JSON files in `route_snaps/` directory
- **After**: All data stored in PostgreSQL database with proper indexing

### 2. Device Management
- **Before**: Static device list in `poller.py`
- **After**: Devices managed in database with encrypted passwords

### 3. Security
- Passwords are encrypted using Fernet symmetric encryption
- Encryption key stored in `.encryption_key` file (auto-generated)

## Database Schema

### Tables
- `devices` - Network device configurations with encrypted passwords
- `route_snapshots` - RIB route snapshots (JSONB storage)
- `bgp_snapshots` - BGP route snapshots (JSONB storage)
- `route_diffs` - Computed diffs between snapshots

## Setup Instructions

### 1. Install PostgreSQL
```bash
# Ubuntu/Debian
sudo apt-get install postgresql postgresql-client

# macOS
brew install postgresql
```

### 2. Create Database
```bash
# Create database and user
sudo -u postgres psql
CREATE DATABASE routemonitor;
CREATE USER routemonitor WITH PASSWORD 'routemonitor';
GRANT ALL PRIVILEGES ON DATABASE routemonitor TO routemonitor;
\q
```

### 3. Install Python Dependencies
```bash
conda activate route_monitor
pip install -r requirements.txt
```

### 4. Configure Database Connection
```bash
cp .env.example .env
# Edit .env and set DATABASE_URL
DATABASE_URL=postgresql://routemonitor:routemonitor@localhost/routemonitor
```

### 5. Initialize Database
```bash
# Full setup (init + migrate existing data)
python setup_database.py --full-setup

# Or step by step:
python setup_database.py --init              # Create tables
python setup_database.py --migrate-devices   # Import static devices
python setup_database.py --migrate-snapshots # Import existing snapshots
```

## Usage

### Managing Devices

```bash
# Add a device interactively
python setup_database.py --add-device

# List all devices
python setup_database.py --list-devices

# Test device connection
python setup_database.py --test-device
```

### Running the Collector

```bash
# Use the new database-based poller
python poller_db.py --once  # Single collection

# Or run as daemon
python poller_db.py  # Continuous polling
```

### Web UI

```bash
# Start the database-backed API server
uvicorn webui_db:app --host 0.0.0.0 --port 5000

# Access at http://localhost:5000
```

## Migration Commands

```bash
# Migrate from static device configuration
python poller_db.py --migrate-devices

# Migrate from file-based snapshots
python poller_db.py --migrate-snapshots

# Clean up old data (keep last 30 days)
python poller_db.py --cleanup 30
```

## New Files

- `database.py` - SQLAlchemy models and database connection
- `device_manager.py` - Device CRUD operations
- `storage_db.py` - Database-based storage implementation
- `poller_db.py` - Database-aware poller
- `webui_db.py` - Database-backed FastAPI server
- `setup_database.py` - Setup and migration utilities

## Security Notes

1. **Encryption Key**: The `.encryption_key` file is auto-generated on first run. Back it up securely!
2. **Database Credentials**: Use strong passwords in production
3. **Network Access**: Restrict PostgreSQL access to trusted hosts only

## API Changes

The API remains mostly compatible, with these additions:

### Device Management Endpoints
- `POST /api/admin/devices` - Create device
- `PUT /api/admin/devices/{id}` - Update device
- `DELETE /api/admin/devices/{id}` - Delete device
- `POST /api/admin/devices/{id}/enable` - Enable monitoring
- `POST /api/admin/devices/{id}/disable` - Disable monitoring

## Rollback Instructions

If you need to revert to file-based storage:

```bash
# Switch back to main branch
git checkout main

# Continue using original poller
python poller.py
```

Your file-based snapshots remain untouched in `route_snaps/`.