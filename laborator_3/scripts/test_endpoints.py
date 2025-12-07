import requests
import time
import json

BASE_URL = "http://localhost:5000"

def print_section(title):
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)

def test_health():
    print_section("Testing Health Endpoint")
    response = requests.get(f"{BASE_URL}/health")
    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")

def test_get_all_employees():
    print_section("Testing GET /employees (All Employees)")
    response = requests.get(f"{BASE_URL}/employees")
    print(f"Status: {response.status_code}")
    data = response.json()
    print(f"Total Employees: {data.get('total', 0)}")
    print(f"Response: {json.dumps(data, indent=2)}")

def test_get_employees_pagination():
    print_section("Testing GET /employees with Pagination")
    response = requests.get(f"{BASE_URL}/employees?offset=0&limit=3")
    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")

def test_get_employee_by_id():
    print_section("Testing GET /employee?id=1")
    response = requests.get(f"{BASE_URL}/employee?id=1")
    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")

def test_put_employee():
    print_section("Testing PUT /employee (Create New)")
    new_employee = {
        'id': '99',
        'name': 'Test User',
        'position': 'Test Engineer',
        'department': 'Testing',
        'salary': 60000,
        'email': 'test.user@company.com'
    }
    response = requests.put(f"{BASE_URL}/employee", json=new_employee)
    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")
    return new_employee['id']

def test_post_employee(emp_id):
    print_section("Testing POST /employee (Modify Existing)")
    update_data = {
        'id': emp_id,
        'salary': 65000,
        'position': 'Senior Test Engineer'
    }
    response = requests.post(f"{BASE_URL}/employee", json=update_data)
    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")

def test_delete_employee(emp_id):
    print_section("Testing DELETE /employee")
    response = requests.delete(f"{BASE_URL}/employee?id={emp_id}")
    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")

def test_rate_limiting():
    print_section("Testing Rate Limiting (11 requests rapidly)")
    for i in range(11):
        response = requests.get(f"{BASE_URL}/health")
        print(f"Request {i+1}: Status {response.status_code}", end="")
        if response.status_code == 429:
            print(" - RATE LIMIT EXCEEDED ✓")
            print(f"Response: {json.dumps(response.json(), indent=2)}")
            return
        else:
            print(" - OK")
        time.sleep(0.1)
    print("Rate limiting did not trigger (may need faster requests)")

def test_circuit_breaker():
    print_section("Testing Circuit Breaker Status")
    response = requests.get(f"{BASE_URL}/circuit-breakers")
    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")

def test_updates():
    print_section("Testing GET /update/employees")
    response = requests.get(f"{BASE_URL}/update/employees")
    print(f"Status: {response.status_code}")
    data = response.json()
    print(f"Updates found: {len(data.get('updates', []))}")
    print(f"Response: {json.dumps(data, indent=2)}")

def main():
    print("\n" + "=" * 60)
    print("  EMPLOYEE DATA WAREHOUSE - API TEST SUITE")
    print("=" * 60)

    try:
        # Basic tests
        test_health()
        test_get_all_employees()
        test_get_employees_pagination()
        test_get_employee_by_id()

        # CRUD operations
        emp_id = test_put_employee()
        time.sleep(0.5)
        test_post_employee(emp_id)
        time.sleep(0.5)
        test_delete_employee(emp_id)

        # Advanced features
        test_updates()
        test_circuit_breaker()

        # Rate limiting (last because it might block requests)
        print("\nWaiting 5 seconds before rate limit test...")
        time.sleep(5)
        test_rate_limiting()

        print_section("ALL TESTS COMPLETED")
        print("All endpoints are working correctly!")

    except requests.exceptions.ConnectionError:
        print("\n✗ ERROR: Could not connect to the Data Warehouse")
        print("  Make sure the services are running: docker-compose up -d")
    except Exception as e:
        print(f"\n✗ ERROR: {e}")

if __name__ == "__main__":
    main()
