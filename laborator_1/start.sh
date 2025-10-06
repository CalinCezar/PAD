#!/bin/bash

# Distributed Message Broker System Startup Script
echo "🚀 Starting Distributed Message Broker System..."
echo "🎯 Features: Raft Consensus, SQL Write Queue, Multi-Node Clustering"

# Create logs directory
mkdir -p logs

# Check if cluster mode is requested
CLUSTER_MODE=${1:-"single"}

if [ "$CLUSTER_MODE" = "cluster" ]; then
    echo "🌐 Starting 3-Node Raft Cluster..."
    
    # Get the directory where this script is located
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    PROJECT_ROOT="$SCRIPT_DIR"
    
    # Kill any existing processes
    pkill -f "python.*broker" 2>/dev/null || true
    sleep 2

    # Remove old files
    rm -f "${PROJECT_ROOT}"/broker_node_*.py "${PROJECT_ROOT}"/broker_node_*.log "${PROJECT_ROOT}"/broker_node_*.pid "${PROJECT_ROOT}"/messages_node_*.db

    # Start Node 0 (Port 5000)
    echo "Starting Node 0 (TCP:5000, HTTP:8080)..."
    cd "${PROJECT_ROOT}/Broker"
    BROKER_NODE_ID=0 BROKER_PORT=5000 HTTP_PORT=8080 python3 broker.py > "${PROJECT_ROOT}/broker_node_0.log" 2>&1 &
    echo $! > "${PROJECT_ROOT}/broker_node_0.pid"
    sleep 3

    # Start Node 1 (Port 5001) 
    echo "Starting Node 1 (TCP:5001, HTTP:8081)..."
    cd "${PROJECT_ROOT}/Broker"
    BROKER_NODE_ID=1 BROKER_PORT=5001 HTTP_PORT=8081 python3 broker.py > "${PROJECT_ROOT}/broker_node_1.log" 2>&1 &
    echo $! > "${PROJECT_ROOT}/broker_node_1.pid"
    sleep 3

    # Start Node 2 (Port 5002)
    echo "Starting Node 2 (TCP:5002, HTTP:8082)..."
    cd "${PROJECT_ROOT}/Broker"
    BROKER_NODE_ID=2 BROKER_PORT=5002 HTTP_PORT=8082 python3 broker.py > "${PROJECT_ROOT}/broker_node_2.log" 2>&1 &
    echo $! > "${PROJECT_ROOT}/broker_node_2.pid"
    sleep 3

    echo "✅ Cluster nodes started!"
    echo ""
    echo "Node Status:"
    echo "============"
    echo "Node 0 - TCP:5000, HTTP:8080 (PID: $(cat ${PROJECT_ROOT}/broker_node_0.pid))"
    echo "Node 1 - TCP:5001, HTTP:8081 (PID: $(cat ${PROJECT_ROOT}/broker_node_1.pid))"  
    echo "Node 2 - TCP:5002, HTTP:8082 (PID: $(cat ${PROJECT_ROOT}/broker_node_2.pid))"
    
    # Return to project root for dashboard setup
    cd "${PROJECT_ROOT}"
    
    # Wait for cluster to stabilize
    echo "⏳ Waiting for cluster to stabilize..."
    sleep 10
    
    echo "✅ Cluster started! Available endpoints:"
    echo "📊 Node 0 - TCP:5000, HTTP:8080, Raft-RPC:6000"
    echo "📊 Node 1 - TCP:5001, HTTP:8081, Raft-RPC:6001" 
    echo "📊 Node 2 - TCP:5002, HTTP:8082, Raft-RPC:6002"
    echo ""
    echo "🔍 Check cluster status: ./cluster_status.sh"
    echo "🛑 Stop cluster: ./stop.sh"
    
    # Start Dashboard pointing to cluster
    echo "🌐 Starting Dashboard (HTTP:3000) with cluster support..."
    cd Dashboard
    
    # Update dashboard to know about cluster endpoints
    cat > cluster_config.js << EOF
// Cluster Configuration for Dashboard
const CLUSTER_ENDPOINTS = [
    { tcp: 'localhost:5000', http: 'http://localhost:8080', name: 'Node 0' },
    { tcp: 'localhost:5001', http: 'http://localhost:8081', name: 'Node 1' },
    { tcp: 'localhost:5002', http: 'http://localhost:8082', name: 'Node 2' }
];

// Try to find the current leader
async function findLeader() {
    for (const endpoint of CLUSTER_ENDPOINTS) {
        try {
            const response = await fetch(endpoint.http + '/raft');
            const status = await response.json();
            if (status.state === 'LEADER') {
                return endpoint;
            }
        } catch (e) {
            console.log('Node', endpoint.name, 'unreachable');
        }
    }
    return CLUSTER_ENDPOINTS[0]; // Fallback to first node
}
EOF
    
    python3 -m http.server 3000 > ../logs/dashboard.log 2>&1 &
    DASHBOARD_PID=$!
    cd ..
    
    echo $DASHBOARD_PID > logs/dashboard.pid
    
else
    echo "📡 Starting Single-Node Broker with Raft (TCP:5000, HTTP:8080)..."
    cd Broker
    python3 broker.py > ../logs/broker.log 2>&1 &
    BROKER_PID=$!
    cd ..

    # Wait for broker to start
    sleep 3

    # Start Dashboard (Simple HTTP server)
    echo "🌐 Starting Dashboard (HTTP:3000)..."
    cd Dashboard
    python3 -m http.server 3000 > ../logs/dashboard.log 2>&1 &
    DASHBOARD_PID=$!
    cd ..

    echo "✅ Single-node system started!"
    echo ""
    echo "📊 Dashboard:    http://localhost:3000"
    echo "🔌 Broker API:   http://localhost:8080"
    echo "🔗 Broker TCP:   localhost:5000"
    echo "� Raft Status:  http://localhost:8080/raft"
    
    # Save PIDs for easy shutdown
    echo $BROKER_PID > logs/broker.pid
    echo $DASHBOARD_PID > logs/dashboard.pid
fi

echo ""
echo "📄 Logs available in ./logs/"
echo "🎮 Usage Examples:"
echo "   Single node:  ./start.sh"
echo "   Cluster mode: ./start.sh cluster"
echo ""
echo "Press Ctrl+C to stop all services..."
wait