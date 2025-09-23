#!/bin/bash

# Stop Cluster Script
# Gracefully stop all Raft nodes

echo "🛑 Stopping Raft Cluster"
echo "========================"

CLUSTER_SIZE=3

# Stop all nodes
for i in $(seq 0 $((CLUSTER_SIZE - 1))); do
    echo "Stopping Node ${i}..."
    
    if [ -f "broker_node_${i}.pid" ]; then
        pid=$(cat broker_node_${i}.pid)
        if ps -p $pid > /dev/null 2>&1; then
            kill $pid
            echo "  - Sent SIGTERM to PID $pid"
            
            # Wait for graceful shutdown
            sleep 2
            
            # Force kill if still running
            if ps -p $pid > /dev/null 2>&1; then
                kill -9 $pid
                echo "  - Force killed PID $pid"
            fi
        else
            echo "  - Process already stopped"
        fi
        
        # Remove PID file
        rm -f broker_node_${i}.pid
    else
        echo "  - No PID file found"
    fi
done

# Clean up temporary files
echo ""
echo "🧹 Cleaning up..."
rm -f broker_node_*.py
rm -f broker_node_*.log
rm -f messages_node_*.db
rm -f .test_write_*

# Auto-cleanup: Remove stale PID files of dead processes
for pid_file in broker_node_*.pid; do
    if [ -f "$pid_file" ]; then
        pid=$(cat "$pid_file" 2>/dev/null)
        if [ -n "$pid" ] && ! ps -p "$pid" > /dev/null 2>&1; then
            echo "🗑️  Removing stale PID file: $pid_file (process $pid dead)"
            rm -f "$pid_file"
        fi
    fi
done

echo "✅ Cluster stopped and cleaned up successfully!"
echo ""
echo "Note: Original broker.py and single-node database (messages.db) are preserved."