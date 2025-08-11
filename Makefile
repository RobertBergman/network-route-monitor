.PHONY: help build up down logs clean test dev prod

help: ## Show this help message
	@echo "Route Monitor Docker Commands:"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-15s\033[0m %s\n", $$1, $$2}'

build: ## Build Docker images
	docker-compose build

up: ## Start all services (development)
	docker-compose up -d

down: ## Stop all services
	docker-compose down

logs: ## Show logs from all services
	docker-compose logs -f

clean: ## Stop services and remove volumes (WARNING: removes data)
	docker-compose down -v

test: ## Run tests in container
	docker-compose run --rm poller python -m pytest tests/

dev: ## Start development environment
	docker-compose up -d poller api
	@echo "API available at: http://localhost:5000"
	@echo "Web UI available at: http://localhost:5000"

prod: ## Start production environment with all services
	docker-compose -f docker-compose.prod.yml up -d
	@echo "Web UI available at: http://localhost"
	@echo "API available at: http://localhost/api/"
	@echo "Prometheus available at: http://localhost:9090"
	@echo "Grafana available at: http://localhost:3000"

prod-down: ## Stop production environment
	docker-compose -f docker-compose.prod.yml down

prod-logs: ## Show production logs
	docker-compose -f docker-compose.prod.yml logs -f

restart-poller: ## Restart just the poller service
	docker-compose restart poller

shell-poller: ## Open shell in poller container
	docker-compose exec poller /bin/bash

shell-api: ## Open shell in API container
	docker-compose exec api /bin/bash

status: ## Show status of all services
	docker-compose ps

backup: ## Backup route snapshots
	tar -czf route_snaps_backup_$$(date +%Y%m%d_%H%M%S).tar.gz route_snaps/

restore: ## Restore route snapshots from latest backup
	@echo "Available backups:"
	@ls -1 route_snaps_backup_*.tar.gz 2>/dev/null || echo "No backups found"
	@echo ""
	@echo "To restore, run: tar -xzf route_snaps_backup_TIMESTAMP.tar.gz"