# Postman Testing Guide

This guide provides detailed instructions for testing the Employee Data Warehouse system using Postman.

## Setup

### 1. Import the Collection

1. Open Postman
2. Click **Import** button (top left)
3. Select **File** tab
4. Choose `postman/Employee_DataWarehouse.postman_collection.json`
5. Click **Import**

### 2. Create Environment

1. Click **Environments** in the left sidebar
2. Click **+** to create a new environment
3. Name it "Employee DW Local"
4. Add the following variables:

| Variable | Initial Value | Current Value |
|----------|--------------|---------------|
| base_url | http://localhost:5000 | http://localhost:5000 |
| json_node_url | http://localhost:5001 | http://localhost:5001 |
| xml_node_url | http://localhost:5002 | http://localhost:5002 |
| employee_id | 1 | 1 |

5. Click **Save**
6. Select the environment from the dropdown in the top-right

## Test Scenarios

### Scenario 1: Health Checks

**Purpose:** Verify all services are running

**Steps:**
1. Open "Health Checks" folder
2. Run "DW Health Check"
   - Expected: Status 200, `"status": "healthy"`
3. Run "JSON Node Health"
   - Expected: Status 200, `"status": "healthy"`
4. Run "XML Node Health"
   - Expected: Status 200, `"status": "healthy"`

### Scenario 2: Get All Employees

**Purpose:** Retrieve all employees from the Data Warehouse

**Steps:**
1. Run "Get All Employees"
   - Expected: Status 200
   - Response contains `employees` array
   - Total count shown

2. Run "Get Employees - Paginated (Limit 3)"
   - Expected: Status 200
   - Exactly 3 employees returned
   - `offset: 0`, `limit: 3`

3. Run "Get Employees - Paginated (Offset 3, Limit 3)"
   - Expected: Status 200
   - Next 3 employees (IDs 4, 5, 6)
   - `offset: 3`, `limit: 3`

### Scenario 3: Get Employee by ID

**Purpose:** Retrieve a specific employee

**Steps:**
1. Run "Get Employee by ID (1)"
   - Expected: Status 200
   - Employee ID is "1"
   - Contains name, position, department, etc.

2. Run "Get Employee by ID (Non-existent)"
   - Expected: Status 404
   - Error message: "Employee not found"

3. Run "Get Employee by ID (Missing ID)"
   - Expected: Status 400
   - Error message: "Employee ID is required"

### Scenario 4: Create New Employee (PUT)

**Purpose:** Add a new employee to the system

**Steps:**
1. Run "Create New Employee"
   - Request body:
     ```json
     {
       "id": "100",
       "name": "Test Employee",
       "position": "Test Position",
       "department": "Testing",
       "salary": 60000,
       "email": "test@company.com"
     }
     ```
   - Expected: Status 201
   - Message: "Employee updated successfully"

2. Verify creation with "Get Employee by ID (100)"
   - Expected: Status 200
   - Employee data matches what was sent

### Scenario 5: Update Employee (POST)

**Purpose:** Modify an existing employee

**Steps:**
1. Run "Update Employee Salary"
   - Request body:
     ```json
     {
       "id": "1",
       "salary": 85000
     }
     ```
   - Expected: Status 200
   - Message: "Employee modified successfully"
   - `modified: 1`

2. Verify update with "Get Employee by ID (1)"
   - Expected: Salary is now 85000

3. Run "Update Non-existent Employee"
   - Expected: Status 404
   - Error: "Employee not found"

### Scenario 6: Delete Employee

**Purpose:** Remove an employee from the system

**Steps:**
1. Create a test employee first (ID: 999)
2. Run "Delete Employee"
   - URL: `{{base_url}}/employee?id=999`
   - Expected: Status 200
   - Message: "Employee deleted successfully"

3. Verify deletion with "Get Employee by ID (999)"
   - Expected: Status 404

4. Try deleting again
   - Expected: Status 404
   - Error: "Employee not found"

### Scenario 7: Rate Limiting

**Purpose:** Test rate limiting protection (10 req/min)

**Steps:**
1. Open "Get All Employees" request
2. Click **Send** button rapidly 11 times
3. On the 11th request (or close to it):
   - Expected: Status 429 (Too Many Requests)
   - Response:
     ```json
     {
       "error": "Rate limit exceeded",
       "limit": 10,
       "window": 60
     }
     ```

**Alternative Method:**
1. Use Postman Runner:
   - Select "Rate Limit Test" folder
   - Click **Run**
   - Set Iterations to 11
   - Set Delay to 0ms
   - Click **Run Employee DW Local**

2. Check results:
   - First 10 requests: Status 200
   - 11th request onwards: Status 429

**Note:** Wait 60 seconds before continuing to reset the rate limit.

### Scenario 8: Circuit Breaker

**Purpose:** Test circuit breaker pattern

**Steps:**
1. Check initial state:
   - Run "Get Circuit Breaker Status"
   - Expected: All services in "CLOSED" state, 0 failures

2. Simulate a node failure:
   ```bash
   # In terminal
   docker stop employee-json-node
   ```

3. Trigger circuit breaker:
   - Run "Get Updates from Nodes" 6 times
   - Circuit breaker opens after 5 failures

4. Check status again:
   - Run "Get Circuit Breaker Status"
   - Expected: `json_node` in "OPEN" state
   - `failures: 5` or more

5. Restore service:
   ```bash
   # In terminal
   docker start employee-json-node
   ```

6. Wait 60 seconds (circuit breaker timeout)

7. Check status:
   - Circuit should transition to "HALF_OPEN", then "CLOSED"

### Scenario 9: Data Synchronization

**Purpose:** Test PULL and PUSH methods

**Steps:**

#### PULL Method (Warehouse pulls from nodes)

1. Add employee to JSON Node directly:
   - Request: `PUT {{json_node_url}}/employee`
   - Body:
     ```json
     {
       "id": "200",
       "name": "JSON Test",
       "position": "Developer",
       "salary": 70000
     }
     ```
   - Expected: Status 201

2. Pull updates to Data Warehouse:
   - Run "Get Updates from Nodes"
   - Expected: See update for employee 200

3. Verify in Data Warehouse:
   - Run "Get Employee by ID (200)" on Data Warehouse
   - Employee might not be in DW yet (depends on pull timing)

#### PUSH Method (Warehouse pushes to nodes)

1. Modify employee in Data Warehouse:
   - Run "Update Employee Salary" (ID: 1)
   - Body: `{"id": "1", "salary": 90000}`

2. Check if update was pushed to JSON Node:
   - Request: `GET {{json_node_url}}/employee?id=1`
   - Expected: Salary updated to 90000

### Scenario 10: Concurrent Requests

**Purpose:** Test thread-safe concurrent processing

**Steps:**
1. Use Postman Runner with Collection Runner:
   - Select "Employee DW Local" collection
   - Set Iterations: 10
   - Set Delay: 0ms (concurrent)
   - Enable "Run collection without waiting for responses"

2. Run the collection

3. Verify results:
   - All requests should complete successfully
   - No data corruption
   - Thread-safe operations confirmed

### Scenario 11: Timeout Testing

**Purpose:** Verify timeout handling

**Note:** This is difficult to test without modifying the code. The timeout is set to 5-10 seconds per endpoint.

**Manual Test:**
1. Modify one of the node services to add a delay:
   ```python
   import time
   time.sleep(11)  # Sleep longer than timeout
   ```

2. Make request to Data Warehouse
   - Expected: Status 504 (Gateway Timeout)
   - Response: `{"error": "Request timeout"}`

## Advanced Testing

### Using Runner for Automation

1. Click **Runner** button (bottom-right)
2. Select "Employee DW Local" collection
3. Select environment
4. Configure:
   - Iterations: 1
   - Delay: 500ms
   - Data File: (optional - CSV with test data)
5. Click **Run Employee DW Local**
6. View results and test passes/failures

### Writing Tests

Each request can have tests. Example:

```javascript
// Test status code
pm.test("Status code is 200", function () {
    pm.response.to.have.status(200);
});

// Test response body
pm.test("Response has employees array", function () {
    var jsonData = pm.response.json();
    pm.expect(jsonData).to.have.property('employees');
    pm.expect(jsonData.employees).to.be.an('array');
});

// Test response time
pm.test("Response time is less than 200ms", function () {
    pm.expect(pm.response.responseTime).to.be.below(200);
});

// Save variable for next request
pm.test("Save employee ID", function () {
    var jsonData = pm.response.json();
    pm.environment.set("employee_id", jsonData.id);
});
```

### Monitor Setup

Create a monitor to run tests periodically:

1. Click **Monitors** in left sidebar
2. Click **+** to create monitor
3. Select collection
4. Configure:
   - Name: "Employee DW Health Monitor"
   - Environment: Employee DW Local
   - Frequency: Every 5 minutes
5. Click **Create Monitor**

## Troubleshooting

### Connection Refused

**Symptom:** "Error: connect ECONNREFUSED 127.0.0.1:5000"

**Solution:**
1. Verify services are running:
   ```bash
   docker-compose ps
   ```
2. Check service health:
   ```bash
   curl http://localhost:5000/health
   ```

### Rate Limit Not Working

**Symptom:** Can send more than 10 requests without getting 429

**Solution:**
1. Ensure requests are from same IP
2. Wait 60 seconds to reset
3. Send requests rapidly (< 6 seconds between batches)

### Circuit Breaker Not Opening

**Symptom:** Circuit breaker stays CLOSED despite failures

**Solution:**
1. Ensure node is actually stopped
2. Make at least 5 failed requests
3. Check circuit breaker configuration in code

### Timeout Not Triggering

**Symptom:** Requests never return 504

**Solution:**
1. Normal requests complete too quickly
2. Need to artificially add delay to test
3. Check timeout configuration (default 5-10s)

## Best Practices

1. **Run health checks first** to ensure all services are up
2. **Wait between rate limit tests** (60 seconds)
3. **Clean up test data** after creating test employees
4. **Use environments** for different deployment targets (local, staging, prod)
5. **Save responses** for debugging
6. **Use variables** for dynamic values like employee IDs
7. **Write assertions** in test scripts
8. **Group related requests** in folders
9. **Document expected behavior** in request descriptions
10. **Version control** your collection

## Complete Test Sequence

For a full system test, run in this order:

1. Health Checks (all 3 services)
2. Get All Employees
3. Get Employee by ID
4. Create New Employee
5. Update Employee
6. Get Updates from Nodes
7. Circuit Breaker Status
8. Delete Employee
9. Rate Limit Test (last, as it may block requests)

Total time: ~5-10 minutes (including wait times)

---

**Happy Testing!** 🚀
