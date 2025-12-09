from flask import Flask, request, jsonify
from pymongo import MongoClient
from threading import Lock, Thread
from datetime import datetime, timedelta
import time
import requests
from functools import wraps
from collections import defaultdict
import logging
import os

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# MongoDB Configuration
MONGO_URI = os.environ.get('MONGO_URI', 'mongodb://mongodb:27017/')
client = MongoClient(MONGO_URI)
db = client.employee_warehouse
employees_collection = db.employees

# Thread-safe collection with locks
data_lock = Lock()

# Rate Limiting Configuration
RATE_LIMIT = 10  # requests per minute
RATE_WINDOW = 60  # seconds
rate_limit_data = defaultdict(list)
rate_limit_lock = Lock()

# Circuit Breaker Configuration
class CircuitBreaker:
    def __init__(self, failure_threshold=5, timeout=60):
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.failures = 0
        self.last_failure_time = None
        self.state = 'CLOSED'  # CLOSED, OPEN, HALF_OPEN
        self.lock = Lock()

    def call(self, func, *args, **kwargs):
        with self.lock:
            if self.state == 'OPEN':
                if datetime.now() - self.last_failure_time > timedelta(seconds=self.timeout):
                    self.state = 'HALF_OPEN'
                    logger.info("Circuit breaker: HALF_OPEN")
                else:
                    raise Exception("Circuit breaker is OPEN")

        try:
            result = func(*args, **kwargs)
            with self.lock:
                if self.state == 'HALF_OPEN':
                    self.state = 'CLOSED'
                    self.failures = 0
                    logger.info("Circuit breaker: CLOSED")
            return result
        except Exception as e:
            with self.lock:
                self.failures += 1
                self.last_failure_time = datetime.now()
                if self.failures >= self.failure_threshold:
                    self.state = 'OPEN'
                    logger.error(f"Circuit breaker: OPEN - {self.failures} failures")
            raise e

circuit_breakers = {}

def get_circuit_breaker(service_name):
    if service_name not in circuit_breakers:
        circuit_breakers[service_name] = CircuitBreaker()
    return circuit_breakers[service_name]

# Rate Limiting Decorator
def rate_limit(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        client_ip = request.remote_addr
        current_time = time.time()

        with rate_limit_lock:
            # Clean old entries
            rate_limit_data[client_ip] = [
                req_time for req_time in rate_limit_data[client_ip]
                if current_time - req_time < RATE_WINDOW
            ]

            if len(rate_limit_data[client_ip]) >= RATE_LIMIT:
                return jsonify({
                    'error': 'Rate limit exceeded',
                    'limit': RATE_LIMIT,
                    'window': RATE_WINDOW
                }), 429

            rate_limit_data[client_ip].append(current_time)

        return f(*args, **kwargs)
    return decorated_function

# Timeout Decorator
# Note: Flask has built-in timeout through server configuration
# This is a simplified version that sets timeouts on external calls
def timeout_handler(timeout_seconds=5):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Simply execute the function normally
            # Timeouts are handled at the HTTP client level (requests library)
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# GET /employees - Get all employees with pagination
@app.route('/employees', methods=['GET'])
@rate_limit
@timeout_handler(timeout_seconds=10)
def get_employees():
    offset = int(request.args.get('offset', 0))
    limit = int(request.args.get('limit', 10))

    with data_lock:
        employees = list(employees_collection.find().skip(offset).limit(limit))
        for emp in employees:
            emp['_id'] = str(emp['_id'])

    return jsonify({
        'employees': employees,
        'offset': offset,
        'limit': limit,
        'total': employees_collection.count_documents({})
    }), 200

# GET /employee - Get employee by ID
@app.route('/employee', methods=['GET'])
@rate_limit
@timeout_handler(timeout_seconds=10)
def get_employee():
    emp_id = request.args.get('id')

    if not emp_id:
        return jsonify({'error': 'Employee ID is required'}), 400

    with data_lock:
        employee = employees_collection.find_one({'id': emp_id})

    if employee:
        employee['_id'] = str(employee['_id'])
        return jsonify(employee), 200
    else:
        return jsonify({'error': 'Employee not found'}), 404

# PUT /employee - Add or update employee from storage nodes
@app.route('/employee', methods=['PUT'])
@rate_limit
@timeout_handler(timeout_seconds=10)
def put_employee():
    data = request.get_json()

    if not data or 'id' not in data:
        return jsonify({'error': 'Invalid employee data'}), 400

    data['updated_at'] = datetime.now().isoformat()

    with data_lock:
        result = employees_collection.update_one(
            {'id': data['id']},
            {'$set': data},
            upsert=True
        )

    return jsonify({
        'message': 'Employee updated successfully',
        'id': data['id'],
        'matched': result.matched_count,
        'modified': result.modified_count
    }), 201

# POST /employee - Modify employee data
@app.route('/employee', methods=['POST'])
@rate_limit
@timeout_handler(timeout_seconds=10)
def post_employee():
    data = request.get_json()

    if not data or 'id' not in data:
        return jsonify({'error': 'Invalid employee data'}), 400

    emp_id = data['id']

    with data_lock:
        existing = employees_collection.find_one({'id': emp_id})

        if not existing:
            return jsonify({'error': 'Employee not found'}), 404

        # Update only provided fields
        update_data = {k: v for k, v in data.items() if k != 'id'}
        update_data['updated_at'] = datetime.now().isoformat()

        result = employees_collection.update_one(
            {'id': emp_id},
            {'$set': update_data}
        )

    # Push updates to source nodes (optional PUSH method)
    push_to_source_nodes(emp_id, data)

    return jsonify({
        'message': 'Employee modified successfully',
        'id': emp_id,
        'modified': result.modified_count
    }), 200

# DELETE /employee - Delete employee
@app.route('/employee', methods=['DELETE'])
@rate_limit
@timeout_handler(timeout_seconds=10)
def delete_employee():
    emp_id = request.args.get('id')

    if not emp_id:
        return jsonify({'error': 'Employee ID is required'}), 400

    with data_lock:
        result = employees_collection.delete_one({'id': emp_id})

    if result.deleted_count > 0:
        return jsonify({
            'message': 'Employee deleted successfully',
            'id': emp_id
        }), 200
    else:
        return jsonify({'error': 'Employee not found'}), 404

# GET /update/employees - Pull updates from source nodes
@app.route('/update/employees', methods=['GET'])
@rate_limit
def get_updates():
    since = request.args.get('since', '')

    updates = []

    # Pull from JSON node
    try:
        cb = get_circuit_breaker('json_node')
        json_updates = cb.call(
            requests.get,
            'http://json-node:5001/updates',
            params={'since': since},
            timeout=5
        )
        if json_updates.status_code == 200:
            updates.extend(json_updates.json().get('updates', []))
    except Exception as e:
        logger.error(f"Failed to get updates from JSON node: {e}")

    # Pull from XML node
    try:
        cb = get_circuit_breaker('xml_node')
        xml_updates = cb.call(
            requests.get,
            'http://xml-node:5002/updates',
            params={'since': since},
            timeout=5
        )
        if xml_updates.status_code == 200:
            updates.extend(xml_updates.json().get('updates', []))
    except Exception as e:
        logger.error(f"Failed to get updates from XML node: {e}")

    return jsonify({'updates': updates}), 200

# PUSH method - Push updates to source nodes
def push_to_source_nodes(emp_id, data):
    def push_to_node(url, data):
        try:
            cb = get_circuit_breaker(url)
            response = cb.call(
                requests.post,
                url,
                json=data,
                timeout=5
            )
            logger.info(f"Pushed update to {url}: {response.status_code}")
        except Exception as e:
            logger.error(f"Failed to push to {url}: {e}")

    # Push to nodes in separate threads
    Thread(target=push_to_node, args=('http://json-node:5001/employee', data)).start()
    Thread(target=push_to_node, args=('http://xml-node:5002/employee', data)).start()

# Hello endpoint
@app.route('/hello', methods=['GET'])
def hello():
    return jsonify({
        'message': 'Hello from JSON Node!'
    }), 200

# Health check endpoint
@app.route('/health', methods=['GET'])
def health():
    return jsonify({
        'status': 'healthy',
        'service': 'data-warehouse',
        'timestamp': datetime.now().isoformat()
    }), 200

# Circuit breaker status
@app.route('/circuit-breakers', methods=['GET'])
def circuit_breaker_status():
    status = {}
    for name, cb in circuit_breakers.items():
        status[name] = {
            'state': cb.state,
            'failures': cb.failures,
            'last_failure': cb.last_failure_time.isoformat() if cb.last_failure_time else None
        }
    return jsonify(status), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, threaded=True, debug=True)
