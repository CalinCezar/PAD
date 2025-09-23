#!/bin/bash

# Cluster Status Script
# Check the status of all Raft nodes (auto-detect cluster size)

echo "🔍 Raft Cluster Status"
echo "======================"

# Auto-detect cluster size by checking for PID files
CLUSTER_SIZE=0
for i in {0..9}; do  # Check up to 10 nodes
    if [ -f "broker_node_${i}.pid" ] || lsof -i :$((8080 + i)) > /dev/null 2>&1; then
        CLUSTER_SIZE=$((i + 1))
    fi
done

if [ $CLUSTER_SIZE -eq 0 ]; then
    echo "❌ No cluster nodes detected"
    echo "Start cluster with: ./start.sh cluster"
    exit 1
fi

echo "Detected ${CLUSTER_SIZE} node(s)"
echo ""

HTTP_BASE_PORT=8080

for i in $(seq 0 $((CLUSTER_SIZE - 1))); do
    http_port=$((HTTP_BASE_PORT + i))  # Removed 'local' - not needed in this context
    echo "Node ${i} (http://127.0.0.1:${http_port}):"
    echo "----------------------------------------"
    
    # Check if PID file exists
    pid_file="broker_node_${i}.pid"
    if [ -f "$pid_file" ]; then
        pid=$(cat "$pid_file")
        
        # Check if process is actually running
        if ! ps -p "$pid" > /dev/null 2>&1; then
            echo "💀 Process dead (PID $pid) - cleaning up files..."
            rm -f "$pid_file"
            rm -f "broker_node_${i}.log"
            echo "🧹 Cleaned up dead node files"
            echo ""
            continue
        fi
    fi
    
    # Check if node is running
    if curl -s --connect-timeout 2 http://127.0.0.1:${http_port}/status > /dev/null 2>&1; then
        echo "✅ Status: ONLINE"
        
        # Get Raft status
        raft_status=$(curl -s http://127.0.0.1:${http_port}/raft 2>/dev/null)
        if [ $? -eq 0 ]; then
            echo "📊 Raft Status:"
            echo "$raft_status" | python3 -m json.tool 2>/dev/null || echo "$raft_status"
        else
            echo "⚠️  Raft status unavailable"
        fi
        
        # Get general status
        general_status=$(curl -s http://127.0.0.1:${http_port}/status 2>/dev/null)
        if [ $? -eq 0 ]; then
            echo "🌐 General Status:"
            echo "$general_status" | python3 -m json.tool 2>/dev/null || echo "$general_status"
        fi
    else
        echo "❌ Status: OFFLINE"
        
        # Check if process file exists
        if [ -f "broker_node_${i}.pid" ]; then
            pid=$(cat broker_node_${i}.pid)
            if ps -p $pid > /dev/null 2>&1; then
                echo "🔄 Process running but not responding (PID: $pid)"
            else
                echo "💀 Process stopped (PID file exists but process dead)"
            fi
        else
            echo "📝 No PID file found"
        fi
    fi
    echo ""
done

echo "📈 Cluster Summary:"
echo "=================="

# Count online nodes
online_nodes=0
leader_count=0
follower_count=0
candidate_count=0

for i in $(seq 0 $((CLUSTER_SIZE - 1))); do
    http_port=$((HTTP_BASE_PORT + i))  # Removed 'local' - not in function
    if curl -s --connect-timeout 2 http://127.0.0.1:${http_port}/raft > /dev/null 2>&1; then
        online_nodes=$((online_nodes + 1))
        
        # Get node state
        state=$(curl -s http://127.0.0.1:${http_port}/raft 2>/dev/null | python3 -c "import sys, json; print(json.load(sys.stdin)['state'])" 2>/dev/null)
        
        case $state in
            "LEADER")
                leader_count=$((leader_count + 1))
                echo "👑 Leader: Node ${i}"
                ;;
            "FOLLOWER")
                follower_count=$((follower_count + 1))
                ;;
            "CANDIDATE")
                candidate_count=$((candidate_count + 1))
                echo "🗳️  Candidate: Node ${i}"
                ;;
        esac
    fi
done

echo "Online Nodes: ${online_nodes}/${CLUSTER_SIZE}"
echo "Leaders: ${leader_count}"
echo "Followers: ${follower_count}"
echo "Candidates: ${candidate_count}"

if [ $leader_count -eq 1 ]; then
    echo "✅ Cluster Status: HEALTHY (Single Leader)"
elif [ $leader_count -eq 0 ]; then
    echo "⚠️  Cluster Status: NO LEADER (Election in progress?)"
else
    echo "❌ Cluster Status: SPLIT BRAIN (Multiple Leaders)"
fi