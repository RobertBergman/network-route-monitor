#!/bin/bash
# Docker management script for database-based route monitor

set -e

COMPOSE_FILE="docker-compose.db.yml"
DOCKERFILE="Dockerfile.db"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

print_usage() {
    echo "Usage: $0 {up|down|restart|logs|status|init|add-device|backup|restore}"
    echo ""
    echo "Commands:"
    echo "  up          - Start all services"
    echo "  down        - Stop all services"
    echo "  restart     - Restart all services"
    echo "  logs        - Show logs (optional: service name)"
    echo "  status      - Show service status"
    echo "  init        - Initialize database and migrate data"
    echo "  add-device  - Add a new device interactively"
    echo "  backup      - Backup database"
    echo "  restore     - Restore database from backup"
    echo ""
    echo "Examples:"
    echo "  $0 up"
    echo "  $0 logs poller"
    echo "  $0 add-device"
}

check_docker() {
    if ! command -v docker &> /dev/null; then
        echo -e "${RED}Docker is not installed${NC}"
        exit 1
    fi
    
    if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
        echo -e "${RED}Docker Compose is not installed${NC}"
        exit 1
    fi
}

# Determine docker-compose command
if docker compose version &> /dev/null; then
    DOCKER_COMPOSE="docker compose"
else
    DOCKER_COMPOSE="docker-compose"
fi

up() {
    echo -e "${GREEN}Starting route monitor with database...${NC}"
    $DOCKER_COMPOSE -f $COMPOSE_FILE up -d --build
    echo -e "${GREEN}Services started!${NC}"
    echo ""
    echo "Access points:"
    echo "  - Web UI:       http://localhost:5000"
    echo "  - Prometheus:   http://localhost:9090"
    echo "  - Grafana:      http://localhost:3000 (admin/admin)"
    echo "  - pgAdmin:      http://localhost:8080 (admin@example.com/admin)"
    echo "  - Metrics:      http://localhost:9108/metrics"
}

down() {
    echo -e "${YELLOW}Stopping route monitor...${NC}"
    $DOCKER_COMPOSE -f $COMPOSE_FILE down
    echo -e "${GREEN}Services stopped${NC}"
}

restart() {
    echo -e "${YELLOW}Restarting route monitor...${NC}"
    $DOCKER_COMPOSE -f $COMPOSE_FILE restart
    echo -e "${GREEN}Services restarted${NC}"
}

logs() {
    SERVICE=$1
    if [ -z "$SERVICE" ]; then
        $DOCKER_COMPOSE -f $COMPOSE_FILE logs -f
    else
        $DOCKER_COMPOSE -f $COMPOSE_FILE logs -f $SERVICE
    fi
}

status() {
    echo -e "${GREEN}Service Status:${NC}"
    $DOCKER_COMPOSE -f $COMPOSE_FILE ps
}

init_db() {
    echo -e "${GREEN}Initializing database...${NC}"
    
    # Start only postgres
    $DOCKER_COMPOSE -f $COMPOSE_FILE up -d postgres
    
    # Wait for postgres to be ready
    echo "Waiting for PostgreSQL to be ready..."
    sleep 5
    
    # Run initialization
    $DOCKER_COMPOSE -f $COMPOSE_FILE run --rm db-init
    
    echo -e "${GREEN}Database initialized!${NC}"
}

add_device() {
    echo -e "${GREEN}Adding new device...${NC}"
    
    # Ensure database is running
    $DOCKER_COMPOSE -f $COMPOSE_FILE up -d postgres
    
    # Run interactive device addition
    docker run -it --rm \
        --network route_monitor_route-monitor \
        -e DATABASE_URL=postgresql://routemonitor:routemonitor@postgres/routemonitor \
        -v $(pwd)/.encryption_key:/app/.encryption_key \
        -v $(pwd):/app \
        --build-arg DOCKERFILE=$DOCKERFILE \
        route-monitor_poller \
        python setup_database.py --add-device
}

backup_db() {
    TIMESTAMP=$(date +%Y%m%d_%H%M%S)
    BACKUP_FILE="backup_${TIMESTAMP}.sql"
    
    echo -e "${GREEN}Backing up database to $BACKUP_FILE...${NC}"
    
    docker exec route-db pg_dump -U routemonitor routemonitor > $BACKUP_FILE
    
    echo -e "${GREEN}Backup completed: $BACKUP_FILE${NC}"
}

restore_db() {
    BACKUP_FILE=$1
    
    if [ -z "$BACKUP_FILE" ]; then
        echo -e "${RED}Please provide a backup file${NC}"
        echo "Usage: $0 restore <backup_file>"
        exit 1
    fi
    
    if [ ! -f "$BACKUP_FILE" ]; then
        echo -e "${RED}Backup file not found: $BACKUP_FILE${NC}"
        exit 1
    fi
    
    echo -e "${YELLOW}Restoring database from $BACKUP_FILE...${NC}"
    echo -e "${YELLOW}WARNING: This will overwrite existing data!${NC}"
    read -p "Continue? (y/n) " -n 1 -r
    echo
    
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        docker exec -i route-db psql -U routemonitor routemonitor < $BACKUP_FILE
        echo -e "${GREEN}Restore completed${NC}"
    else
        echo "Restore cancelled"
    fi
}

# Main script
check_docker

case "$1" in
    up)
        up
        ;;
    down)
        down
        ;;
    restart)
        restart
        ;;
    logs)
        logs $2
        ;;
    status)
        status
        ;;
    init)
        init_db
        ;;
    add-device)
        add_device
        ;;
    backup)
        backup_db
        ;;
    restore)
        restore_db $2
        ;;
    *)
        print_usage
        exit 1
        ;;
esac