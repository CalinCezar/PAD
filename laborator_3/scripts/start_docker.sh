#!/bin/bash

echo "=========================================="
echo "  Starting Employee Data Warehouse System"
echo "=========================================="

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo "✗ Docker is not running. Please start Docker first."
    exit 1
fi

echo "✓ Docker is running"

# Check if docker-compose is available
if ! command -v docker-compose &> /dev/null; then
    echo "✗ docker-compose not found. Please install docker-compose."
    exit 1
fi

echo "✓ docker-compose is available"

# Stop any existing containers
echo ""
echo "Stopping any existing containers..."
docker-compose down

# Build and start services
echo ""
echo "Building and starting services..."
docker-compose up -d --build

# Wait for services to be healthy
echo ""
echo "Waiting for services to be healthy..."
sleep 10

# Check service health
echo ""
echo "Checking service health..."

check_service() {
    local service=$1
    local port=$2
    local max_attempts=30
    local attempt=1

    while [ $attempt -le $max_attempts ]; do
        if curl -s http://localhost:$port/health > /dev/null 2>&1; then
            echo "✓ $service is healthy"
            return 0
        fi
        echo "  Waiting for $service... (attempt $attempt/$max_attempts)"
        sleep 2
        attempt=$((attempt + 1))
    done

    echo "✗ $service failed to start"
    return 1
}

check_service "JSON Node" 5001
check_service "XML Node" 5002
check_service "Data Warehouse" 5000

echo ""
echo "=========================================="
echo "  System Started Successfully!"
echo "=========================================="
echo ""
echo "Services available at:"
echo "  - Data Warehouse: http://localhost:5000"
echo "  - JSON Node:      http://localhost:5001"
echo "  - XML Node:       http://localhost:5002"
echo "  - MongoDB:        localhost:27017"
echo ""
echo "Next steps:"
echo "  1. Seed data: python scripts/seed_data.py"
echo "  2. Test endpoints: python scripts/test_endpoints.py"
echo "  3. View logs: docker-compose logs -f"
echo "  4. Stop system: docker-compose down"
echo ""
