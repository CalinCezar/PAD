#!/bin/bash

# Stop Message Broker System
echo "🛑 Stopping Message Broker System..."

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

echo "✅ System stopped."