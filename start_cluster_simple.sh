#!/bin/bash

# Simple Cluster Startup Script
echo "🚀 Starting 3-Node Raft Cluster"
echo "================================"

# Kill any existing processes
pkill -f "python.*broker" 2>/dev/null || true
sleep 2

# Remove old files
rm -f broker_node_*.py broker_node_*.log broker_node_*.pid messages_node_*.db

# Start Node 0 (Port 5000)
echo "Starting Node 0 (TCP:5000, HTTP:8080)..."
cd /home/calin/Projects/UTM/PAD/Broker
BROKER_NODE_ID=0 BROKER_PORT=5000 HTTP_PORT=8080 python3 broker.py > /home/calin/Projects/UTM/PAD/broker_node_0.log 2>&1 &
echo $! > /home/calin/Projects/UTM/PAD/broker_node_0.pid
sleep 3

# Start Node 1 (Port 5001) 
echo "Starting Node 1 (TCP:5001, HTTP:8081)..."
cd /home/calin/Projects/UTM/PAD/Broker
BROKER_NODE_ID=1 BROKER_PORT=5001 HTTP_PORT=8081 python3 broker.py > /home/calin/Projects/UTM/PAD/broker_node_1.log 2>&1 &
echo $! > /home/calin/Projects/UTM/PAD/broker_node_1.pid
sleep 3

# Start Node 2 (Port 5002)
echo "Starting Node 2 (TCP:5002, HTTP:8082)..."
cd /home/calin/Projects/UTM/PAD/Broker
BROKER_NODE_ID=2 BROKER_PORT=5002 HTTP_PORT=8082 python3 broker.py > /home/calin/Projects/UTM/PAD/broker_node_2.log 2>&1 &
echo $! > /home/calin/Projects/UTM/PAD/broker_node_2.pid
sleep 3

echo "✅ Cluster nodes started!"
echo ""
echo "Node Status:"
echo "============"
echo "Node 0 - TCP:5000, HTTP:8080 (PID: $(cat broker_node_0.pid))"
echo "Node 1 - TCP:5001, HTTP:8081 (PID: $(cat broker_node_1.pid))"  
echo "Node 2 - TCP:5002, HTTP:8082 (PID: $(cat broker_node_2.pid))"
echo ""
echo "Wait 10 seconds for cluster to stabilize..."
sleep 10

echo "🔍 Checking cluster status..."
for i in 0 1 2; do
    port=$((8080 + i))
    echo "Node $i:"
    if curl -s --connect-timeout 2 http://127.0.0.1:$port/raft > /dev/null 2>&1; then
        status=$(curl -s http://127.0.0.1:$port/raft | python3 -c "import sys, json; data=json.load(sys.stdin); print(f\"{data['state']} (term {data['current_term']})\")" 2>/dev/null)
        echo "  ✅ ONLINE - $status"
    else
        echo "  ❌ OFFLINE"
    fi
done

echo ""
echo "🎯 Cluster is ready!"
echo "Commands:"
echo "  Check status: ./cluster_status.sh"
echo "  Stop cluster: ./stop_cluster.sh"