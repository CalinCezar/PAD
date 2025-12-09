from flask import Flask, request, jsonify
from datetime import datetime
from threading import Lock
import logging

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# In-memory storage for employee data (thread-safe)
employees = {}
updates_log = []
data_lock = Lock()

# GET /employee - Get employee by ID
@app.route('/employee', methods=['GET'])
def get_employee():
    emp_id = request.args.get('id')

    if not emp_id:
        return jsonify({'error': 'Employee ID is required'}), 400

    with data_lock:
        employee = employees.get(emp_id)

    if employee:
        return jsonify(employee), 200
    else:
        return jsonify({'error': 'Employee not found'}), 404

# GET /employees - Get all employees
@app.route('/employees', methods=['GET'])
def get_employees():
    with data_lock:
        all_employees = list(employees.values())

    return jsonify({
        'employees': all_employees,
        'count': len(all_employees)
    }), 200

# PUT /employee - Add or update employee
@app.route('/employee', methods=['PUT'])
def put_employee():
    data = request.get_json()

    if not data or 'id' not in data:
        return jsonify({'error': 'Invalid employee data'}), 400

    emp_id = data['id']
    timestamp = datetime.now().isoformat()

    data['updated_at'] = timestamp
    data['source'] = 'json_node'

    with data_lock:
        is_new = emp_id not in employees
        employees[emp_id] = data

        # Log the update
        updates_log.append({
            'employee_id': emp_id,
            'timestamp': timestamp,
            'action': 'create' if is_new else 'update',
            'data': data
        })

    logger.info(f"Employee {emp_id} {'created' if is_new else 'updated'}")

    return jsonify({
        'message': f"Employee {'created' if is_new else 'updated'} successfully",
        'id': emp_id,
        'timestamp': timestamp
    }), 201

# POST /employee - Update employee from Data Warehouse (PUSH method)
@app.route('/employee', methods=['POST'])
def post_employee():
    data = request.get_json()

    if not data or 'id' not in data:
        return jsonify({'error': 'Invalid employee data'}), 400

    emp_id = data['id']
    timestamp = datetime.now().isoformat()

    with data_lock:
        if emp_id not in employees:
            return jsonify({'error': 'Employee not found'}), 404

        # Update only provided fields
        for key, value in data.items():
            if key != 'id':
                employees[emp_id][key] = value

        employees[emp_id]['updated_at'] = timestamp
        employees[emp_id]['synced_from_dw'] = True

        # Log the update
        updates_log.append({
            'employee_id': emp_id,
            'timestamp': timestamp,
            'action': 'sync_from_dw',
            'data': employees[emp_id]
        })

    logger.info(f"Employee {emp_id} synced from Data Warehouse")

    return jsonify({
        'message': 'Employee synced successfully',
        'id': emp_id,
        'timestamp': timestamp
    }), 200

# DELETE /employee - Delete employee
@app.route('/employee', methods=['DELETE'])
def delete_employee():
    emp_id = request.args.get('id')

    if not emp_id:
        return jsonify({'error': 'Employee ID is required'}), 400

    with data_lock:
        if emp_id in employees:
            del employees[emp_id]
            timestamp = datetime.now().isoformat()

            updates_log.append({
                'employee_id': emp_id,
                'timestamp': timestamp,
                'action': 'delete'
            })

            logger.info(f"Employee {emp_id} deleted")
            return jsonify({
                'message': 'Employee deleted successfully',
                'id': emp_id
            }), 200
        else:
            return jsonify({'error': 'Employee not found'}), 404

# GET /updates - Return updates since timestamp (PULL method)
@app.route('/updates', methods=['GET'])
def get_updates():
    since = request.args.get('since', '')

    with data_lock:
        if since:
            # Filter updates after the given timestamp
            filtered_updates = [
                update for update in updates_log
                if update['timestamp'] > since
            ]
        else:
            # Return all updates
            filtered_updates = updates_log.copy()

    return jsonify({
        'updates': filtered_updates,
        'count': len(filtered_updates)
    }), 200

# Health check endpoint
@app.route('/health', methods=['GET'])
def health():
    with data_lock:
        employee_count = len(employees)

    return jsonify({
        'status': 'healthy',
        'service': 'json-node',
        'employee_count': employee_count,
        'timestamp': datetime.now().isoformat()
    }), 200

# Hello endpoint
@app.route('/hello', methods=['GET'])
def health():
    with data_lock:
        employee_count = len(employees)

    return jsonify({'message': 'Hello from JSON Node!'}), 200

# Initialize with some sample data
def init_sample_data():
    sample_employees = [
        {
            'id': '1',
            'name': 'John Doe',
            'position': 'Software Engineer',
            'department': 'Engineering',
            'salary': 75000,
            'email': 'john.doe@company.com'
        },
        {
            'id': '2',
            'name': 'Jane Smith',
            'position': 'Product Manager',
            'department': 'Product',
            'salary': 85000,
            'email': 'jane.smith@company.com'
        },
        {
            'id': '3',
            'name': 'Bob Johnson',
            'position': 'DevOps Engineer',
            'department': 'Operations',
            'salary': 80000,
            'email': 'bob.johnson@company.com'
        }
    ]

    timestamp = datetime.now().isoformat()

    with data_lock:
        for emp in sample_employees:
            emp['updated_at'] = timestamp
            emp['source'] = 'json_node'
            employees[emp['id']] = emp

            updates_log.append({
                'employee_id': emp['id'],
                'timestamp': timestamp,
                'action': 'create',
                'data': emp
            })

    logger.info(f"Initialized with {len(sample_employees)} sample employees")

if __name__ == '__main__':
    init_sample_data()
    app.run(host='0.0.0.0', port=5001, threaded=True, debug=True)
