#!/bin/bash

# Stop Message Broker System - Unified script for single node and cluster
echo "🛑 Stopping Message Broker System..."

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR"

# Check what's running and stop accordingly

# 1. Check for cluster nodes (broker_node_*.pid files)
CLUSTER_NODES=()
for pid_file in "${PROJECT_ROOT}"/broker_node_*.pid; do
    if [ -f "$pid_file" ]; then
        # Extract node ID from filename
        node_id=$(basename "$pid_file" .pid | sed 's/broker_node_//')
        CLUSTER_NODES+=($node_id)
    fi
done

# 2. Check for single-node broker
SINGLE_NODE_RUNNING=false
if [ -f "${PROJECT_ROOT}/logs/broker.pid" ]; then
    SINGLE_NODE_RUNNING=true
fi

# 3. Check for dashboard
DASHBOARD_RUNNING=false
if [ -f "${PROJECT_ROOT}/logs/dashboard.pid" ]; then
    DASHBOARD_RUNNING=true
fi

# Stop cluster nodes if any exist
if [ ${#CLUSTER_NODES[@]} -gt 0 ]; then
    echo "🌐 Detected cluster mode with ${#CLUSTER_NODES[@]} node(s): ${CLUSTER_NODES[*]}"
    echo ""
    
    # Stop all detected cluster nodes
    for node_id in "${CLUSTER_NODES[@]}"; do
        echo "Stopping Cluster Node ${node_id}..."
        
        pid_file="${PROJECT_ROOT}/broker_node_${node_id}.pid"
        if [ -f "$pid_file" ]; then
            pid=$(cat "$pid_file")
            if ps -p $pid > /dev/null 2>&1; then
                kill $pid
                echo "  - Sent SIGTERM to PID $pid"
                
                # Wait for graceful shutdown
                sleep 1
                
                # Force kill if still running
                if ps -p $pid > /dev/null 2>&1; then
                    kill -9 $pid
                    echo "  - Force killed PID $pid"
                fi
            else
                echo "  - Process already stopped"
            fi
            
            # Remove PID file
            rm -f "$pid_file"
        fi
    done
    
    # Clean up cluster-related files
    echo ""
    echo "🧹 Cleaning up cluster files..."
    rm -f "${PROJECT_ROOT}"/broker_node_*.py
    rm -f "${PROJECT_ROOT}"/broker_node_*.log
    rm -f "${PROJECT_ROOT}"/messages_node_*.db
    rm -f "${PROJECT_ROOT}"/.test_write_*
fi

# Stop single-node broker if running
if [ "$SINGLE_NODE_RUNNING" = true ]; then
    echo "📡 Stopping single-node broker..."
    
    if [ -f "${PROJECT_ROOT}/logs/broker.pid" ]; then
        BROKER_PID=$(cat "${PROJECT_ROOT}/logs/broker.pid")
        if ps -p $BROKER_PID > /dev/null 2>&1; then
            kill $BROKER_PID
            echo "  - Stopped broker (PID: $BROKER_PID)"
        fi
        rm -f "${PROJECT_ROOT}/logs/broker.pid"
    fi
fi

# Stop dashboard if running
if [ "$DASHBOARD_RUNNING" = true ]; then
    echo "🌐 Stopping dashboard..."
    
    if [ -f "${PROJECT_ROOT}/logs/dashboard.pid" ]; then
        DASHBOARD_PID=$(cat "${PROJECT_ROOT}/logs/dashboard.pid")
        if ps -p $DASHBOARD_PID > /dev/null 2>&1; then
            kill $DASHBOARD_PID
            echo "  - Stopped dashboard (PID: $DASHBOARD_PID)"
        fi
        rm -f "${PROJECT_ROOT}/logs/dashboard.pid"
    fi
fi

# Final cleanup: Kill any remaining processes
echo ""
echo "🧹 Final cleanup - killing any remaining processes..."
pkill -f "python.*broker" 2>/dev/null && echo "  - Killed remaining broker processes" || echo "  - No remaining broker processes"
pkill -f "http.server 3000" 2>/dev/null && echo "  - Killed remaining dashboard processes" || echo "  - No remaining dashboard processes"

# Auto-cleanup: Remove any remaining stale PID files
for pid_file in "${PROJECT_ROOT}"/broker_node_*.pid "${PROJECT_ROOT}/logs/broker.pid" "${PROJECT_ROOT}/logs/dashboard.pid"; do
    if [ -f "$pid_file" ]; then
        pid=$(cat "$pid_file" 2>/dev/null)
        if [ -n "$pid" ] && ! ps -p "$pid" > /dev/null 2>&1; then
            echo "🗑️  Removing stale PID file: $(basename "$pid_file") (process $pid dead)"
            rm -f "$pid_file"
        fi
    fi
done

echo ""
echo "✅ Message Broker System stopped successfully!"
echo "💡 Note: Database files are preserved for data persistence."
echo "🚀 To start again: ./start.sh [cluster]"