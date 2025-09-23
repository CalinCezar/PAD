#!/bin/bash

# Dead Node Cleanup Script
# Automatically detects and cleans up dead broker nodes

echo "🧹 Dead Node Cleanup"
echo "===================="

cleaned_count=0
total_checked=0

# Check for PID files and validate processes
for pid_file in broker_node_*.pid; do
    # Skip if no PID files exist
    if [ ! -f "$pid_file" ]; then
        continue
    fi
    
    total_checked=$((total_checked + 1))
    
    # Extract node ID from filename
    node_id=$(echo "$pid_file" | sed 's/broker_node_\([0-9]*\)\.pid/\1/')
    pid=$(cat "$pid_file")
    
    echo "Checking Node ${node_id} (PID: ${pid})..."
    
    # Check if process is running
    if ps -p "$pid" > /dev/null 2>&1; then
        echo "  ✅ Process alive"
    else
        echo "  💀 Process dead - cleaning up..."
        
        # Remove PID file
        rm -f "$pid_file"
        echo "    🗑️  Removed $pid_file"
        
        # Remove log file
        log_file="broker_node_${node_id}.log"
        if [ -f "$log_file" ]; then
            rm -f "$log_file"
            echo "    🗑️  Removed $log_file"
        fi
        
        # Remove database file (optional - comment out to preserve data)
        db_file="Broker/messages_node_${node_id}.db"
        if [ -f "$db_file" ]; then
            echo "    ⚠️  Database file exists: $db_file"
            echo "    💾 Keeping database (contains message history)"
            # Uncomment next line to also remove database:
            # rm -f "$db_file" && echo "    🗑️  Removed $db_file"
        fi
        
        cleaned_count=$((cleaned_count + 1))
        echo "  ✅ Node ${node_id} cleanup complete"
    fi
    echo ""
done

# Summary
if [ $total_checked -eq 0 ]; then
    echo "ℹ️  No broker nodes found"
elif [ $cleaned_count -eq 0 ]; then
    echo "✅ All $total_checked node(s) are running - no cleanup needed"
else
    echo "🧹 Cleanup complete: $cleaned_count dead node(s) cleaned up"
    echo "💾 Database files preserved (contain message history)"
fi

# Also clean up any orphaned log files without PID files
orphaned_logs=$(find . -name "broker_node_*.log" -type f)
if [ -n "$orphaned_logs" ]; then
    echo ""
    echo "🔍 Checking for orphaned log files..."
    for log_file in $orphaned_logs; do
        node_id=$(echo "$log_file" | sed 's/.*broker_node_\([0-9]*\)\.log/\1/')
        pid_file="broker_node_${node_id}.pid"
        
        if [ ! -f "$pid_file" ]; then
            echo "🗑️  Removing orphaned log: $log_file"
            rm -f "$log_file"
        fi
    done
fi

echo ""
echo "🎯 Cleanup finished!"