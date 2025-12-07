from flask import Flask, request, jsonify
from datetime import datetime
from threading import Lock
import xml.etree.ElementTree as ET
import logging

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# In-memory storage for employee data (thread-safe)
employees = {}
updates_log = []
data_lock = Lock()

def employee_to_xml(employee_dict):
    """Convert employee dictionary to XML string"""
    root = ET.Element('employee')
    for key, value in employee_dict.items():
        child = ET.SubElement(root, key)
        child.text = str(value)
    return ET.tostring(root, encoding='unicode')

def xml_to_employee(xml_string):
    """Convert XML string to employee dictionary"""
    root = ET.fromstring(xml_string)
    employee = {}
    for child in root:
        employee[child.tag] = child.text
    return employee

# GET /employee - Get employee by ID
@app.route('/employee', methods=['GET'])
def get_employee():
    emp_id = request.args.get('id')

    if not emp_id:
        return jsonify({'error': 'Employee ID is required'}), 400

    with data_lock:
        employee = employees.get(emp_id)

    if employee:
        # Return as JSON for compatibility
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
        'count': len(all_employees),
        'format': 'xml'
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
    data['source'] = 'xml_node'
    data['format'] = 'xml'

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

    logger.info(f"Employee {emp_id} {'created' if is_new else 'updated'} (XML format)")

    return jsonify({
        'message': f"Employee {'created' if is_new else 'updated'} successfully",
        'id': emp_id,
        'timestamp': timestamp,
        'format': 'xml'
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

    logger.info(f"Employee {emp_id} synced from Data Warehouse (XML format)")

    return jsonify({
        'message': 'Employee synced successfully',
        'id': emp_id,
        'timestamp': timestamp,
        'format': 'xml'
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

            logger.info(f"Employee {emp_id} deleted (XML format)")
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
        'count': len(filtered_updates),
        'format': 'xml'
    }), 200

# Health check endpoint
@app.route('/health', methods=['GET'])
def health():
    with data_lock:
        employee_count = len(employees)

    return jsonify({
        'status': 'healthy',
        'service': 'xml-node',
        'employee_count': employee_count,
        'format': 'xml',
        'timestamp': datetime.now().isoformat()
    }), 200

# Initialize with some sample data
def init_sample_data():
    sample_employees = [
        {
            'id': '4',
            'name': 'Alice Williams',
            'position': 'Data Scientist',
            'department': 'Analytics',
            'salary': 90000,
            'email': 'alice.williams@company.com'
        },
        {
            'id': '5',
            'name': 'Charlie Brown',
            'position': 'UX Designer',
            'department': 'Design',
            'salary': 70000,
            'email': 'charlie.brown@company.com'
        },
        {
            'id': '6',
            'name': 'Diana Prince',
            'position': 'Security Engineer',
            'department': 'Security',
            'salary': 95000,
            'email': 'diana.prince@company.com'
        }
    ]

    timestamp = datetime.now().isoformat()

    with data_lock:
        for emp in sample_employees:
            emp['updated_at'] = timestamp
            emp['source'] = 'xml_node'
            emp['format'] = 'xml'
            employees[emp['id']] = emp

            updates_log.append({
                'employee_id': emp['id'],
                'timestamp': timestamp,
                'action': 'create',
                'data': emp
            })

    logger.info(f"Initialized with {len(sample_employees)} sample employees (XML format)")

if __name__ == '__main__':
    init_sample_data()
    app.run(host='0.0.0.0', port=5002, threaded=True, debug=True)
