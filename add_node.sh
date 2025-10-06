#!/bin/bash

# Add New Node to Existing Cluster - Dynamic Discovery
echo "➕ Adding New Node to Raft Cluster"
echo "=================================="

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR"

# Auto-discover next available node ID
NEXT_NODE_ID=0
while lsof -i :$((5000 + NEXT_NODE_ID)) > /dev/null 2>&1; do
    NEXT_NODE_ID=$((NEXT_NODE_ID + 1))
    if [ $NEXT_NODE_ID -gt 20 ]; then
        echo "❌ Error: Too many nodes (max 20)"
        exit 1
    fi
done

TCP_PORT=$((5000 + NEXT_NODE_ID))
HTTP_PORT=$((8080 + NEXT_NODE_ID))

echo "Auto-detected next available Node ID: ${NEXT_NODE_ID}"
echo "  - TCP Port: ${TCP_PORT}"
echo "  - HTTP Port: ${HTTP_PORT}"
echo "  - Raft RPC Port: $((TCP_PORT + 1000))"
echo "  - Database: messages_node_${NEXT_NODE_ID}.db"
echo ""

# Check if any cluster nodes exist
CLUSTER_EXISTS=false
for port in {5000..5020}; do
    if lsof -i :$port > /dev/null 2>&1; then
        CLUSTER_EXISTS=true
        break
    fi
done

if [ "$CLUSTER_EXISTS" = false ]; then
    echo "❌ Error: No cluster detected. Start cluster first with:"
    echo "   ./start.sh cluster"
    echo "   or start first node with: ./start.sh"
    exit 1
fi

echo "✅ Existing cluster detected"

# Start the new node
echo "🚀 Starting Node ${NEXT_NODE_ID}..."
cd "${PROJECT_ROOT}/Broker"

MAX_CLUSTER_SIZE=20 BROKER_NODE_ID=$NEXT_NODE_ID BROKER_PORT=$TCP_PORT HTTP_PORT=$HTTP_PORT python3 broker.py > "${PROJECT_ROOT}/broker_node_${NEXT_NODE_ID}.log" 2>&1 &

NEW_PID=$!
echo $NEW_PID > "${PROJECT_ROOT}/broker_node_${NEXT_NODE_ID}.pid"

echo "✅ Node ${NEXT_NODE_ID} started with PID: ${NEW_PID}"
echo ""

# Wait for node to initialize and discover cluster
echo "⏳ Waiting for node to discover cluster and initialize..."
sleep 8

# Check if node is responding
if curl -s --connect-timeout 2 http://127.0.0.1:$HTTP_PORT/raft > /dev/null 2>&1; then
    status=$(curl -s http://127.0.0.1:$HTTP_PORT/raft | python3 -c "import sys, json; data=json.load(sys.stdin); print(f\"{data['state']} (term {data['current_term']}, cluster_size: {data.get('cluster_size', 'unknown')})\")" 2>/dev/null)
    echo "✅ Node ${NEXT_NODE_ID} is ONLINE - $status"
else
    echo "❌ Node ${NEXT_NODE_ID} failed to start properly"
    echo "Check log: tail -f broker_node_${NEXT_NODE_ID}.log"
    exit 1
fi

echo ""
echo "🎯 Node added to cluster!"
echo "🔍 Check cluster status: ./cluster_status.sh"
echo "🛑 Stop this node: kill \$(cat broker_node_${NEXT_NODE_ID}.pid)"
echo "📊 View logs: tail -f broker_node_${NEXT_NODE_ID}.log"