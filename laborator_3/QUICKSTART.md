# Quick Start Guide

This guide will help you get the Employee Data Warehouse system up and running in under 5 minutes.

## Prerequisites Check

Before starting, ensure you have:
- ✅ Docker Desktop installed and running
- ✅ Python 3.10+ installed
- ✅ Git Bash (Windows) or Terminal (Mac/Linux)

### Quick Verification

```bash
# Check Docker
docker --version
docker-compose --version

# Check Python
python --version
```

## Option 1: Docker Compose (Recommended)

### Step 1: Start the System

**On Windows (PowerShell):**
```powershell
docker-compose up -d --build
```

**On Linux/Mac:**
```bash
docker-compose up -d --build
```

### Step 2: Wait for Services

Wait about 30 seconds for all services to start, then verify:

```bash
# Check all containers are running
docker-compose ps

# Should see 4 services: mongodb, json-node, xml-node, data-warehouse
```

### Step 3: Seed Data (Optional)

```bash
# Install Python dependencies first
pip install requests

# Run seed script
python scripts/seed_data.py
```

### Step 4: Test the API

**Quick Health Check:**
```bash
curl http://localhost:5000/health
```

**Get All Employees:**
```bash
curl http://localhost:5000/employees
```

**Full Test Suite:**
```bash
python scripts/test_endpoints.py
```

## Option 2: Using Shell Scripts

### On Linux/Mac/Git Bash:

```bash
# Make scripts executable
chmod +x scripts/*.sh

# Start all services
./scripts/start_docker.sh

# This will:
# 1. Check Docker is running
# 2. Build and start all services
# 3. Wait for health checks
# 4. Show service URLs
```

### Stop Services:

```bash
./scripts/stop_docker.sh
```

## Verify Everything Works

### 1. Check Service Health

```bash
# Data Warehouse
curl http://localhost:5000/health

# JSON Node
curl http://localhost:5001/health

# XML Node
curl http://localhost:5002/health
```

Expected response: `{"status": "healthy", ...}`

### 2. Get Sample Data

The nodes initialize with sample data automatically:
- JSON Node: Employees 1, 2, 3
- XML Node: Employees 4, 5, 6

```bash
# Get all employees from Data Warehouse
curl http://localhost:5000/employees
```

### 3. Test CRUD Operations

**Create Employee:**
```bash
curl -X PUT http://localhost:5000/employee \
  -H "Content-Type: application/json" \
  -d '{"id":"99","name":"Test User","position":"Developer","salary":70000}'
```

**Get Employee:**
```bash
curl "http://localhost:5000/employee?id=99"
```

**Update Employee:**
```bash
curl -X POST http://localhost:5000/employee \
  -H "Content-Type: application/json" \
  -d '{"id":"99","salary":80000}'
```

**Delete Employee:**
```bash
curl -X DELETE "http://localhost:5000/employee?id=99"
```

## Testing with Postman

### 1. Import Collection

1. Open Postman
2. Click **Import**
3. Select `postman/Employee_DataWarehouse.postman_collection.json`
4. Collection appears in sidebar

### 2. Quick Test

1. Open "Health Checks" folder
2. Click "DW Health Check"
3. Click **Send**
4. Expected: Status 200, response with `"status": "healthy"`

### 3. Run All Tests

See [POSTMAN_GUIDE.md](POSTMAN_GUIDE.md) for comprehensive testing guide.

## Common Issues & Solutions

### Issue: "Cannot connect to Docker daemon"

**Solution:**
```bash
# Start Docker Desktop
# Windows: Open Docker Desktop application
# Mac: Open Docker.app
# Linux: sudo systemctl start docker
```

### Issue: "Port already in use"

**Solution:**
```bash
# Check what's using the port
# Windows:
netstat -ano | findstr :5000

# Linux/Mac:
lsof -i :5000

# Stop existing services
docker-compose down
```

### Issue: "Services not healthy"

**Solution:**
```bash
# View logs to see what's wrong
docker-compose logs -f

# Restart specific service
docker-compose restart data-warehouse

# Rebuild everything
docker-compose down
docker-compose up -d --build
```

### Issue: "Python script errors"

**Solution:**
```bash
# Install dependencies
pip install -r requirements.txt

# Or install individually
pip install Flask pymongo requests
```

## Next Steps

### 1. Explore the API

See [README.md](README.md) for complete API documentation.

### 2. Test Design Patterns

**Rate Limiting:**
```bash
# Send 11 rapid requests
for i in {1..11}; do curl http://localhost:5000/health; done
```

**Circuit Breaker:**
```bash
# Stop a node
docker stop employee-json-node

# Make requests to trigger circuit breaker
for i in {1..6}; do curl http://localhost:5000/update/employees; done

# Check circuit breaker status
curl http://localhost:5000/circuit-breakers

# Restart node
docker start employee-json-node
```

### 3. View Logs

```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f data-warehouse

# Last 50 lines
docker-compose logs --tail=50 data-warehouse
```

### 4. Monitor Resources

```bash
# Container stats
docker stats

# Shows CPU, memory, network usage for all containers
```

## Kubernetes Deployment (Advanced)

If you want to deploy to Kubernetes:

```bash
# Ensure Minikube is running
minikube start

# Deploy
./scripts/start_k8s.sh

# Access service
minikube service data-warehouse

# Remove deployment
./scripts/stop_k8s.sh
```

See [README.md](README.md) for detailed Kubernetes instructions.

## Architecture Overview

```
Client (Postman/curl)
    ↓ HTTP
Data Warehouse :5000
    ↓ Circuit Breaker Protected
JSON Node :5001  |  XML Node :5002
    ↓
MongoDB :27017
```

**Key Features:**
- ✅ Rate Limiting (10 req/min)
- ✅ Circuit Breaker (5 failures → OPEN)
- ✅ Timeout (5-10s per request)
- ✅ Thread-safe concurrent processing
- ✅ NoSQL (MongoDB)
- ✅ Docker & Kubernetes ready

## Development Workflow

### 1. Make Changes

Edit files in `data_warehouse/`, `json_node/`, or `xml_node/`

### 2. Rebuild

```bash
# Rebuild and restart affected service
docker-compose up -d --build data-warehouse

# Or rebuild everything
docker-compose up -d --build
```

### 3. Test

```bash
python scripts/test_endpoints.py
```

### 4. View Logs

```bash
docker-compose logs -f data-warehouse
```

## Cleanup

### Remove All Containers and Data

```bash
# Stop and remove containers
docker-compose down

# Also remove volumes (MongoDB data)
docker-compose down -v

# Remove images (to save space)
docker rmi employee-data-warehouse:latest
docker rmi employee-json-node:latest
docker rmi employee-xml-node:latest
```

## Getting Help

- **Full Documentation:** See [README.md](README.md)
- **API Reference:** See [README.md#api-endpoints](README.md#api-endpoints)
- **Postman Testing:** See [POSTMAN_GUIDE.md](POSTMAN_GUIDE.md)
- **Troubleshooting:** See [README.md#troubleshooting](README.md#troubleshooting)

## Summary

You now have a fully functional distributed data warehouse system with:

1. ✅ 3 microservices running in Docker
2. ✅ MongoDB for persistent storage
3. ✅ Circuit Breaker, Rate Limiting, and Timeout patterns
4. ✅ RESTful API with full CRUD operations
5. ✅ Sample data for testing
6. ✅ Postman collection for API testing

**Next:** Start testing with Postman or explore the API endpoints!

---

**Happy Coding!** 🚀
