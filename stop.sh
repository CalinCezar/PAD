#!/bin/bash

# Stop Message Broker System - Auto-detect mode
echo "🛑 Stopping Message Broker System..."

# Check if cluster mode is running (look for cluster PID files)
if [ -f "broker_node_0.pid" ] || [ -f "broker_node_1.pid" ] || [ -f "broker_node_2.pid" ]; then
    echo "🌐 Detected cluster mode - delegating to cluster stop script..."
    ./stop_cluster.sh
    exit 0
fi

# Single-node mode cleanup
echo "📡 Stopping single-node mode..."

# Read PIDs if they exist
if [ -f logs/broker.pid ]; then
    BROKER_PID=$(cat logs/broker.pid)
    echo "Stopping Broker (PID: $BROKER_PID)..."
    kill $BROKER_PID 2>/dev/null
    rm logs/broker.pid
fi

if [ -f logs/dashboard.pid ]; then
    DASHBOARD_PID=$(cat logs/dashboard.pid)
    echo "Stopping Dashboard (PID: $DASHBOARD_PID)..."
    kill $DASHBOARD_PID 2>/dev/null
    rm logs/dashboard.pid
fi

# Kill any remaining processes
pkill -f "broker.py"
pkill -f "http.server 3000"

echo "✅ Single-node system stopped."