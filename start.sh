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
    
    # Start the cluster using our simple cluster script (no file generation)
    ./start_cluster_simple.sh
    
    # Wait for cluster to stabilize
    echo "⏳ Waiting for cluster to stabilize..."
    sleep 10
    
    echo "✅ Cluster started! Available endpoints:"
    echo "📊 Node 0 - TCP:5000, HTTP:8080, Raft-RPC:6000"
    echo "📊 Node 1 - TCP:5001, HTTP:8081, Raft-RPC:6001" 
    echo "📊 Node 2 - TCP:5002, HTTP:8082, Raft-RPC:6002"
    echo ""
    echo "🔍 Check cluster status: ./cluster_status.sh"
    echo "🛑 Stop cluster: ./stop_cluster.sh"
    
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