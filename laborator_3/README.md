# Employee Data Warehouse - Distributed System

A comprehensive distributed system built with Python, featuring a Data Warehouse that aggregates employee data from multiple source nodes. This project demonstrates advanced architectural patterns including Circuit Breaker, Rate Limiting, Timeout handling, and concurrent request processing.

## Architecture Overview

```
┌─────────────┐
│   Client    │
│  (Postman)  │
└──────┬──────┘
       │ HTTP REST API
       ▼
┌─────────────────────────────────────────┐
│     Data Warehouse Service (DW)         │
│  - Flask HTTP Server (Port 5000)        │
│  - Rate Limiting (10 req/min)           │
│  - Timeout Handler (5-10s)              │
│  - Thread-safe operations               │
│  - Circuit Breaker for nodes            │
└────┬────────────────────────────────┬───┘
     │                                │
     │ Pull/Push Updates              │
     ▼                                ▼
┌─────────────┐              ┌─────────────┐
│ JSON Node   │              │  XML Node   │
│ (Port 5001) │              │ (Port 5002) │
│ - JSON data │              │ - XML data  │
└─────────────┘              └─────────────┘

┌──────────────────────────────────────────┐
│         MongoDB (NoSQL)                  │
│  - Database: employee_warehouse          │
│  - Collection: employees                 │
│  - Port: 27017                           │
└──────────────────────────────────────────┘
```

## Features

### Core Technologies
- **Python 3.10** with Flask web framework
- **Docker** for containerization
- **Kubernetes** for orchestration
- **MongoDB** for NoSQL data storage
- **RESTful API** with all CRUD operations

### Design Patterns

#### 1. Circuit Breaker
- **Purpose**: Prevents cascading failures when calling external services
- **States**: CLOSED → OPEN → HALF_OPEN → CLOSED
- **Configuration**:
  - Failure threshold: 5 failures
  - Timeout: 60 seconds
- **Location**: [data_warehouse/app.py:16](data_warehouse/app.py#L16)

#### 2. Rate Limiting
- **Purpose**: Prevents abuse and ensures fair resource usage
- **Implementation**: Per-client IP address tracking
- **Limit**: 10 requests per 60 seconds
- **Response**: HTTP 429 (Too Many Requests)
- **Location**: [data_warehouse/app.py:49](data_warehouse/app.py#L49)

#### 3. Timeout Handling
- **Purpose**: Prevents requests from hanging indefinitely
- **Implementation**: Thread-based with daemon threads
- **Timeout**: 5-10 seconds per endpoint
- **Response**: HTTP 504 (Gateway Timeout)
- **Location**: [data_warehouse/app.py:73](data_warehouse/app.py#L73)

#### 4. Thread-Per-Request
- **Purpose**: Handle concurrent requests efficiently
- **Implementation**: Flask threaded mode with locks
- **Thread Safety**:
  - `data_lock` for MongoDB operations
  - `rate_limit_lock` for rate limiting
  - Circuit breaker internal locks

## Project Structure

```
laborator_3/
├── data_warehouse/
│   ├── app.py              # Main Data Warehouse service
│   └── Dockerfile          # DW Docker image
├── json_node/
│   ├── app.py              # JSON employee data node
│   └── Dockerfile          # JSON node Docker image
├── xml_node/
│   ├── app.py              # XML employee data node
│   └── Dockerfile          # XML node Docker image
├── kubernetes/
│   ├── mongodb-pvc.yaml            # MongoDB persistent storage
│   ├── mongodb-deployment.yaml     # MongoDB deployment
│   ├── mongodb-service.yaml        # MongoDB service
│   ├── jsonnode-deployment.yaml    # JSON node deployment
│   ├── jsonnode-service.yaml       # JSON node service
│   ├── xmlnode-deployment.yaml     # XML node deployment
│   ├── xmlnode-service.yaml        # XML node service
│   ├── datawarehouse-deployment.yaml  # DW deployment
│   └── datawarehouse-service.yaml     # DW service
├── scripts/
│   ├── seed_data.py        # Seed sample employee data
│   ├── test_endpoints.py   # Test all API endpoints
│   ├── start_docker.sh     # Start Docker services
│   ├── stop_docker.sh      # Stop Docker services
│   ├── start_k8s.sh        # Deploy to Kubernetes
│   └── stop_k8s.sh         # Remove from Kubernetes
├── postman/
│   └── Employee_DataWarehouse.postman_collection.json
├── docker-compose.yml      # Docker Compose configuration
├── requirements.txt        # Python dependencies
└── README.md              # This file
```

## Prerequisites

- **Docker** (version 20.10+)
- **Docker Compose** (version 2.0+)
- **Python 3.10+** (for running scripts)
- **Kubernetes** (optional - Minikube or similar)
- **kubectl** (optional - for Kubernetes deployment)
- **Postman** (optional - for API testing)

## Quick Start with Docker

### 1. Start All Services

On Linux/Mac:
```bash
chmod +x scripts/start_docker.sh
./scripts/start_docker.sh
```

On Windows (Git Bash):
```bash
bash scripts/start_docker.sh
```

Or manually:
```bash
docker-compose up -d --build
```

### 2. Wait for Services to be Ready

The script automatically waits for all services to be healthy. You can verify manually:

```bash
# Check all containers are running
docker-compose ps

# Check logs
docker-compose logs -f
```

### 3. Seed Sample Data

```bash
python scripts/seed_data.py
```

This will:
- Add 6 additional employees to the nodes
- Sync all data to the Data Warehouse
- Verify all services are accessible

### 4. Test the API

```bash
python scripts/test_endpoints.py
```

This runs comprehensive tests on all endpoints including:
- CRUD operations
- Pagination
- Rate limiting
- Circuit breaker status
- Update synchronization

### 5. Stop Services

```bash
docker-compose down

# To also remove data volumes:
docker-compose down -v
```

## API Endpoints

### Data Warehouse (Port 5000)

#### GET /employees
Get all employees with pagination.

**Query Parameters:**
- `offset` (optional): Skip N employees (default: 0)
- `limit` (optional): Return max N employees (default: 10)

**Example:**
```bash
curl "http://localhost:5000/employees?offset=0&limit=5"
```

**Response:**
```json
{
  "employees": [...],
  "offset": 0,
  "limit": 5,
  "total": 12
}
```

#### GET /employee
Get a specific employee by ID.

**Query Parameters:**
- `id` (required): Employee ID

**Example:**
```bash
curl "http://localhost:5000/employee?id=1"
```

**Response:**
```json
{
  "id": "1",
  "name": "John Doe",
  "position": "Software Engineer",
  "department": "Engineering",
  "salary": 75000,
  "email": "john.doe@company.com",
  "updated_at": "2025-12-07T10:30:00",
  "source": "json_node"
}
```

#### PUT /employee
Create or update an employee (upsert).

**Body (JSON):**
```json
{
  "id": "99",
  "name": "New Employee",
  "position": "Developer",
  "department": "Engineering",
  "salary": 70000,
  "email": "new.employee@company.com"
}
```

**Example:**
```bash
curl -X PUT http://localhost:5000/employee \
  -H "Content-Type: application/json" \
  -d '{"id":"99","name":"New Employee","position":"Developer"}'
```

**Response:**
```json
{
  "message": "Employee updated successfully",
  "id": "99",
  "matched": 0,
  "modified": 0
}
```

#### POST /employee
Modify an existing employee (partial update).

**Body (JSON):**
```json
{
  "id": "1",
  "salary": 80000,
  "position": "Senior Software Engineer"
}
```

**Example:**
```bash
curl -X POST http://localhost:5000/employee \
  -H "Content-Type: application/json" \
  -d '{"id":"1","salary":80000}'
```

**Response:**
```json
{
  "message": "Employee modified successfully",
  "id": "1",
  "modified": 1
}
```

#### DELETE /employee
Delete an employee by ID.

**Query Parameters:**
- `id` (required): Employee ID

**Example:**
```bash
curl -X DELETE "http://localhost:5000/employee?id=99"
```

**Response:**
```json
{
  "message": "Employee deleted successfully",
  "id": "99"
}
```

#### GET /update/employees
Pull updates from source nodes (PULL method).

**Query Parameters:**
- `since` (optional): ISO timestamp to get updates after

**Example:**
```bash
curl "http://localhost:5000/update/employees?since=2025-12-07T10:00:00"
```

#### GET /health
Health check endpoint.

**Example:**
```bash
curl http://localhost:5000/health
```

**Response:**
```json
{
  "status": "healthy",
  "service": "data-warehouse",
  "timestamp": "2025-12-07T12:00:00"
}
```

#### GET /circuit-breakers
Get circuit breaker status for all services.

**Example:**
```bash
curl http://localhost:5000/circuit-breakers
```

**Response:**
```json
{
  "json_node": {
    "state": "CLOSED",
    "failures": 0,
    "last_failure": null
  },
  "xml_node": {
    "state": "CLOSED",
    "failures": 0,
    "last_failure": null
  }
}
```

### JSON Node (Port 5001)

- `GET /employee?id=<id>` - Get employee by ID
- `GET /employees` - Get all employees
- `PUT /employee` - Add/update employee
- `POST /employee` - Sync update from DW
- `DELETE /employee?id=<id>` - Delete employee
- `GET /updates?since=<timestamp>` - Get updates log
- `GET /health` - Health check

### XML Node (Port 5002)

Same endpoints as JSON Node, but stores data in XML format internally.

## Kubernetes Deployment

### 1. Build and Deploy

```bash
chmod +x scripts/start_k8s.sh
./scripts/start_k8s.sh
```

This script:
- Builds all Docker images
- Loads images into Minikube (if using Minikube)
- Applies all Kubernetes configurations
- Waits for all pods to be ready

### 2. Verify Deployment

```bash
# Check all pods
kubectl get pods

# Check services
kubectl get services

# Check deployments
kubectl get deployments
```

### 3. Access the Data Warehouse

If using Minikube:
```bash
minikube service data-warehouse
```

This will open the service in your browser and show the URL.

### 4. View Logs

```bash
# Data Warehouse logs
kubectl logs -l app=data-warehouse

# JSON Node logs
kubectl logs -l app=json-node

# XML Node logs
kubectl logs -l app=xml-node

# MongoDB logs
kubectl logs -l app=mongodb
```

### 5. Scale Services

```bash
# Scale Data Warehouse to 5 replicas
kubectl scale deployment data-warehouse --replicas=5

# Scale JSON Node to 3 replicas
kubectl scale deployment json-node --replicas=3
```

### 6. Remove Deployment

```bash
chmod +x scripts/stop_k8s.sh
./scripts/stop_k8s.sh
```

## Testing with Postman

### 1. Import Collection

1. Open Postman
2. Click **Import**
3. Select `postman/Employee_DataWarehouse.postman_collection.json`
4. The collection will appear in your sidebar

### 2. Set Environment Variables

Create a new environment with:
- `base_url`: `http://localhost:5000`
- `json_node_url`: `http://localhost:5001`
- `xml_node_url`: `http://localhost:5002`

### 3. Run Tests

The collection includes tests for:
- All CRUD operations
- Pagination
- Rate limiting (rapid requests)
- Circuit breaker status
- Data synchronization
- Error handling

See [POSTMAN_GUIDE.md](POSTMAN_GUIDE.md) for detailed testing instructions.

## Design Pattern Examples

### Testing Circuit Breaker

1. Stop the JSON node:
```bash
docker stop employee-json-node
```

2. Make 6+ requests to trigger updates:
```bash
for i in {1..6}; do
  curl http://localhost:5000/update/employees
  sleep 1
done
```

3. Check circuit breaker status:
```bash
curl http://localhost:5000/circuit-breakers
```

Expected: `json_node` circuit should be in `OPEN` state.

4. Restart the JSON node:
```bash
docker start employee-json-node
```

### Testing Rate Limiting

Send 11 rapid requests:
```bash
for i in {1..11}; do
  curl http://localhost:5000/health
done
```

Expected: The 11th request should return HTTP 429 with rate limit error.

### Testing Timeout

The timeout is automatically applied to all endpoints. If a request takes longer than the configured timeout (5-10 seconds), it will return HTTP 504.

### Testing Concurrent Requests

Use Apache Bench or similar tool:
```bash
# Install Apache Bench (if not installed)
# Ubuntu: sudo apt-get install apache2-utils
# Mac: brew install httpd

# Send 100 requests with 10 concurrent
ab -n 100 -c 10 http://localhost:5000/employees
```

All requests should be handled correctly without data corruption.

## Troubleshooting

### Services won't start

1. Check Docker is running:
```bash
docker info
```

2. Check port availability:
```bash
# Windows
netstat -ano | findstr :5000

# Linux/Mac
lsof -i :5000
```

3. View logs:
```bash
docker-compose logs -f
```

### MongoDB connection errors

1. Ensure MongoDB container is running:
```bash
docker ps | grep mongodb
```

2. Check MongoDB logs:
```bash
docker-compose logs mongodb
```

3. Verify network connectivity:
```bash
docker network inspect laborator_3_employee-network
```

### Circuit breaker stuck in OPEN state

Wait for the timeout period (60 seconds by default), then the circuit will transition to HALF_OPEN and retry.

Or restart the Data Warehouse service:
```bash
docker-compose restart data-warehouse
```

## Development

### Running Services Locally (without Docker)

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Start MongoDB:
```bash
# Using Docker
docker run -d -p 27017:27017 mongo:7.0

# Or use a local MongoDB installation
```

3. Start services in separate terminals:
```bash
# Terminal 1 - JSON Node
python json_node/app.py

# Terminal 2 - XML Node
python xml_node/app.py

# Terminal 3 - Data Warehouse
python data_warehouse/app.py
```

### Modifying Configuration

**Rate Limiting:**
Edit `data_warehouse/app.py`:
```python
RATE_LIMIT = 10  # requests per minute
RATE_WINDOW = 60  # seconds
```

**Circuit Breaker:**
Edit `data_warehouse/app.py`:
```python
CircuitBreaker(failure_threshold=5, timeout=60)
```

**Timeout:**
Edit decorator in `data_warehouse/app.py`:
```python
@timeout_handler(timeout_seconds=10)
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## License

This project is part of the PAD (Programarea Aplicațiilor Distribuite) laboratory work.

## Contact

For questions or issues, please open an issue on GitHub or contact the course instructor.

---

**Built with ❤️ for PAD Laboratory 3**
