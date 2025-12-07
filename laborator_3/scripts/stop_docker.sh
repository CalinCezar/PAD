#!/bin/bash

echo "=========================================="
echo "  Stopping Employee Data Warehouse System"
echo "=========================================="

# Stop all containers
echo "Stopping all containers..."
docker-compose down

# Optional: Remove volumes (uncomment to also delete MongoDB data)
# docker-compose down -v

echo ""
echo "✓ All services stopped"
echo ""
echo "To remove all data including MongoDB volumes:"
echo "  docker-compose down -v"
echo ""
