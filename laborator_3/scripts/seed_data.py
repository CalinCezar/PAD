import requests
import time
import json

# Configuration
DATA_WAREHOUSE_URL = "http://localhost:5000"
JSON_NODE_URL = "http://localhost:5001"
XML_NODE_URL = "http://localhost:5002"

# Additional employees to seed
additional_employees = [
    {
        'id': '7',
        'name': 'Eve Martinez',
        'position': 'Frontend Developer',
        'department': 'Engineering',
        'salary': 72000,
        'email': 'eve.martinez@company.com'
    },
    {
        'id': '8',
        'name': 'Frank Miller',
        'position': 'Backend Developer',
        'department': 'Engineering',
        'salary': 78000,
        'email': 'frank.miller@company.com'
    },
    {
        'id': '9',
        'name': 'Grace Lee',
        'position': 'QA Engineer',
        'department': 'Quality',
        'salary': 68000,
        'email': 'grace.lee@company.com'
    },
    {
        'id': '10',
        'name': 'Henry Davis',
        'position': 'DevOps Lead',
        'department': 'Operations',
        'salary': 92000,
        'email': 'henry.davis@company.com'
    },
    {
        'id': '11',
        'name': 'Iris Taylor',
        'position': 'Business Analyst',
        'department': 'Business',
        'salary': 65000,
        'email': 'iris.taylor@company.com'
    },
    {
        'id': '12',
        'name': 'Jack Anderson',
        'position': 'ML Engineer',
        'department': 'Analytics',
        'salary': 95000,
        'email': 'jack.anderson@company.com'
    }
]

def check_service_health(url, service_name):
    """Check if a service is healthy"""
    try:
        response = requests.get(f"{url}/health", timeout=5)
        if response.status_code == 200:
            print(f"✓ {service_name} is healthy")
            return True
        else:
            print(f"✗ {service_name} returned status {response.status_code}")
            return False
    except Exception as e:
        print(f"✗ {service_name} is not accessible: {e}")
        return False

def seed_to_json_node(employees):
    """Seed employees to JSON node"""
    print("\n--- Seeding data to JSON Node ---")
    for emp in employees[:3]:  # First 3 employees
        try:
            response = requests.put(
                f"{JSON_NODE_URL}/employee",
                json=emp,
                timeout=5
            )
            if response.status_code == 201:
                print(f"✓ Added employee {emp['id']} ({emp['name']}) to JSON node")
            else:
                print(f"✗ Failed to add employee {emp['id']}: {response.text}")
        except Exception as e:
            print(f"✗ Error adding employee {emp['id']}: {e}")

def seed_to_xml_node(employees):
    """Seed employees to XML node"""
    print("\n--- Seeding data to XML Node ---")
    for emp in employees[3:]:  # Last 3 employees
        try:
            response = requests.put(
                f"{XML_NODE_URL}/employee",
                json=emp,
                timeout=5
            )
            if response.status_code == 201:
                print(f"✓ Added employee {emp['id']} ({emp['name']}) to XML node")
            else:
                print(f"✗ Failed to add employee {emp['id']}: {response.text}")
        except Exception as e:
            print(f"✗ Error adding employee {emp['id']}: {e}")

def sync_to_data_warehouse():
    """Sync all data to data warehouse"""
    print("\n--- Syncing data to Data Warehouse ---")

    # Get employees from JSON node
    try:
        response = requests.get(f"{JSON_NODE_URL}/employees", timeout=5)
        if response.status_code == 200:
            json_employees = response.json().get('employees', [])
            print(f"Found {len(json_employees)} employees from JSON node")

            for emp in json_employees:
                try:
                    sync_response = requests.put(
                        f"{DATA_WAREHOUSE_URL}/employee",
                        json=emp,
                        timeout=5
                    )
                    if sync_response.status_code == 201:
                        print(f"✓ Synced employee {emp['id']} from JSON node to DW")
                except Exception as e:
                    print(f"✗ Failed to sync employee {emp['id']}: {e}")
    except Exception as e:
        print(f"✗ Failed to get employees from JSON node: {e}")

    # Get employees from XML node
    try:
        response = requests.get(f"{XML_NODE_URL}/employees", timeout=5)
        if response.status_code == 200:
            xml_employees = response.json().get('employees', [])
            print(f"Found {len(xml_employees)} employees from XML node")

            for emp in xml_employees:
                try:
                    sync_response = requests.put(
                        f"{DATA_WAREHOUSE_URL}/employee",
                        json=emp,
                        timeout=5
                    )
                    if sync_response.status_code == 201:
                        print(f"✓ Synced employee {emp['id']} from XML node to DW")
                except Exception as e:
                    print(f"✗ Failed to sync employee {emp['id']}: {e}")
    except Exception as e:
        print(f"✗ Failed to get employees from XML node: {e}")

def main():
    print("=" * 60)
    print("Employee Data Warehouse - Seed Data Script")
    print("=" * 60)

    # Check service health
    print("\n--- Checking Service Health ---")
    dw_healthy = check_service_health(DATA_WAREHOUSE_URL, "Data Warehouse")
    json_healthy = check_service_health(JSON_NODE_URL, "JSON Node")
    xml_healthy = check_service_health(XML_NODE_URL, "XML Node")

    if not (dw_healthy and json_healthy and xml_healthy):
        print("\n✗ Not all services are healthy. Please start all services first.")
        print("  Run: docker-compose up -d")
        return

    print("\n✓ All services are healthy")

    # Seed data
    seed_to_json_node(additional_employees)
    seed_to_xml_node(additional_employees)

    # Wait a bit for nodes to process
    print("\nWaiting 2 seconds before syncing to Data Warehouse...")
    time.sleep(2)

    # Sync to data warehouse
    sync_to_data_warehouse()

    print("\n" + "=" * 60)
    print("Seed data completed successfully!")
    print("=" * 60)
    print(f"\nData Warehouse now has all employee data from both nodes.")
    print(f"Test with: curl http://localhost:5000/employees")

if __name__ == "__main__":
    main()
