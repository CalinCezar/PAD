#!/bin/bash

# Message Broker System Startup Script
echo "🚀 Starting Message Broker System..."

# Create logs directory
mkdir -p logs

# Start Broker with API
echo "📡 Starting Python Broker (TCP:5000, HTTP:8080)..."
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

echo "✅ System started successfully!"
echo ""
echo "📊 Dashboard:    http://localhost:3000"
echo "🔌 Broker API:   http://localhost:8080"
echo "🔗 Broker TCP:   localhost:5000"
echo ""
echo "📝 To stop the system:"
echo "   kill $BROKER_PID $DASHBOARD_PID"
echo ""
echo "📄 Logs available in ./logs/"

# Save PIDs for easy shutdown
echo $BROKER_PID > logs/broker.pid
echo $DASHBOARD_PID > logs/dashboard.pid

echo "Press Ctrl+C to stop all services..."
wait