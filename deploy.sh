#!/bin/bash

# Route Monitor Deployment Script
# This script pulls the latest Docker images from GHCR and deploys the application

set -e

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
REGISTRY="ghcr.io"
REPO="robertbergman/network-route-monitor"
COMPOSE_FILE="docker-compose.prod.yml"
ENV_FILE=".env"

# Function to print colored messages
print_message() {
    local color=$1
    local message=$2
    echo -e "${color}${message}${NC}"
}

# Function to check prerequisites
check_prerequisites() {
    print_message "$YELLOW" "🔍 Checking prerequisites..."
    
    # Check if Docker is installed
    if ! command -v docker &> /dev/null; then
        print_message "$RED" "❌ Docker is not installed. Please install Docker first."
        exit 1
    fi
    
    # Check if Docker Compose is installed
    if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
        print_message "$RED" "❌ Docker Compose is not installed. Please install Docker Compose first."
        exit 1
    fi
    
    # Check if compose file exists
    if [ ! -f "$COMPOSE_FILE" ]; then
        print_message "$RED" "❌ $COMPOSE_FILE not found in current directory."
        exit 1
    fi
    
    # Check if .env file exists
    if [ ! -f "$ENV_FILE" ]; then
        print_message "$YELLOW" "⚠️  .env file not found. Creating from .env.example..."
        if [ -f ".env.example" ]; then
            cp .env.example .env
            print_message "$GREEN" "✅ Created .env file. Please edit it with your settings."
            exit 0
        else
            print_message "$RED" "❌ .env.example not found. Cannot create .env file."
            exit 1
        fi
    fi
    
    print_message "$GREEN" "✅ Prerequisites check passed."
}

# Function to pull latest images
pull_images() {
    print_message "$YELLOW" "🐳 Pulling latest Docker images from GHCR..."
    
    # Define images to pull (database-backed versions)
    IMAGES=(
        "${REGISTRY}/${REPO}-db:latest"
        "${REGISTRY}/${REPO}-grafana:latest"
    )
    
    # Pull each image
    for image in "${IMAGES[@]}"; do
        print_message "$YELLOW" "  Pulling $image..."
        if docker pull "$image"; then
            print_message "$GREEN" "  ✅ Successfully pulled $image"
        else
            print_message "$RED" "  ❌ Failed to pull $image"
            exit 1
        fi
    done
    
    print_message "$GREEN" "✅ All images pulled successfully."
}

# Function to stop existing containers
stop_containers() {
    print_message "$YELLOW" "🛑 Stopping existing containers..."
    
    # Try docker compose (v2) first, then fall back to docker-compose (v1)
    if docker compose version &> /dev/null; then
        COMPOSE_CMD="docker compose"
    else
        COMPOSE_CMD="docker-compose"
    fi
    
    if $COMPOSE_CMD -f "$COMPOSE_FILE" ps -q | grep -q .; then
        $COMPOSE_CMD -f "$COMPOSE_FILE" down
        print_message "$GREEN" "✅ Existing containers stopped."
    else
        print_message "$YELLOW" "ℹ️  No existing containers to stop."
    fi
}

# Function to start containers
start_containers() {
    print_message "$YELLOW" "🚀 Starting containers..."
    
    # Try docker compose (v2) first, then fall back to docker-compose (v1)
    if docker compose version &> /dev/null; then
        COMPOSE_CMD="docker compose"
    else
        COMPOSE_CMD="docker-compose"
    fi
    
    # Start containers in detached mode
    if $COMPOSE_CMD -f "$COMPOSE_FILE" up -d; then
        print_message "$GREEN" "✅ Containers started successfully."
    else
        print_message "$RED" "❌ Failed to start containers."
        exit 1
    fi
}

# Function to show container status
show_status() {
    print_message "$YELLOW" "📊 Container Status:"
    
    # Try docker compose (v2) first, then fall back to docker-compose (v1)
    if docker compose version &> /dev/null; then
        COMPOSE_CMD="docker compose"
    else
        COMPOSE_CMD="docker-compose"
    fi
    
    $COMPOSE_CMD -f "$COMPOSE_FILE" ps
    
    echo ""
    print_message "$GREEN" "🌐 Service URLs:"
    echo "  - Web UI: http://localhost:8080"
    echo "  - Device Management: http://localhost:8080/devices.html"
    echo "  - Prometheus Metrics: http://localhost:9108/metrics"
    echo "  - Prometheus (if enabled): http://localhost:9090"
    echo "  - Grafana (if enabled): http://localhost:3000"
}

# Function to show logs
show_logs() {
    print_message "$YELLOW" "📝 Recent logs (last 20 lines):"
    
    # Try docker compose (v2) first, then fall back to docker-compose (v1)
    if docker compose version &> /dev/null; then
        COMPOSE_CMD="docker compose"
    else
        COMPOSE_CMD="docker-compose"
    fi
    
    $COMPOSE_CMD -f "$COMPOSE_FILE" logs --tail=20
}

# Function to perform health checks
health_check() {
    print_message "$YELLOW" "🏥 Performing health checks..."
    
    # Wait a bit for services to start
    sleep 5
    
    # Check API health
    if curl -s -o /dev/null -w "%{http_code}" http://localhost:8080/api/status | grep -q "200"; then
        print_message "$GREEN" "  ✅ API is healthy"
    else
        print_message "$YELLOW" "  ⚠️  API is not responding (might still be starting)"
    fi
    
    # Check Prometheus metrics
    if curl -s -o /dev/null -w "%{http_code}" http://localhost:9108/metrics | grep -q "200"; then
        print_message "$GREEN" "  ✅ Prometheus exporter is healthy"
    else
        print_message "$YELLOW" "  ⚠️  Prometheus exporter is not responding (might still be starting)"
    fi
}

# Main script execution
main() {
    print_message "$GREEN" "========================================"
    print_message "$GREEN" "  Route Monitor Deployment Script"
    print_message "$GREEN" "========================================"
    echo ""
    
    # Parse command line arguments
    case "${1:-deploy}" in
        deploy)
            check_prerequisites
            pull_images
            stop_containers
            start_containers
            health_check
            show_status
            ;;
        pull)
            pull_images
            ;;
        stop)
            stop_containers
            ;;
        start)
            start_containers
            show_status
            ;;
        restart)
            stop_containers
            start_containers
            show_status
            ;;
        status)
            show_status
            ;;
        logs)
            show_logs
            ;;
        update)
            check_prerequisites
            pull_images
            print_message "$YELLOW" "🔄 Recreating containers with new images..."
            
            # Try docker compose (v2) first, then fall back to docker-compose (v1)
            if docker compose version &> /dev/null; then
                COMPOSE_CMD="docker compose"
            else
                COMPOSE_CMD="docker-compose"
            fi
            
            $COMPOSE_CMD -f "$COMPOSE_FILE" up -d --force-recreate
            health_check
            show_status
            ;;
        help|--help|-h)
            echo "Usage: $0 [command]"
            echo ""
            echo "Commands:"
            echo "  deploy   - Pull images, stop old containers, and start new ones (default)"
            echo "  pull     - Pull latest images from GHCR"
            echo "  stop     - Stop all containers"
            echo "  start    - Start all containers"
            echo "  restart  - Restart all containers"
            echo "  status   - Show container status"
            echo "  logs     - Show recent logs"
            echo "  update   - Pull latest images and recreate containers"
            echo "  help     - Show this help message"
            ;;
        *)
            print_message "$RED" "Unknown command: $1"
            echo "Run '$0 help' for usage information."
            exit 1
            ;;
    esac
    
    echo ""
    print_message "$GREEN" "✨ Deployment complete!"
}

# Run main function with all arguments
main "$@"