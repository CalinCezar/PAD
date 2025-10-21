import time
import random
import threading
import json
import grpc
import logging
import datetime
from enum import Enum
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple
from concurrent import futures

# Import generated gRPC code
import broker_pb2
import broker_pb2_grpc
from google.protobuf.timestamp_pb2 import Timestamp
from google.protobuf.empty_pb2 import Empty

class NodeState(Enum):
    FOLLOWER = "FOLLOWER"
    CANDIDATE = "CANDIDATE"
    LEADER = "LEADER"

@dataclass
class LogEntry:
    term: int
    index: int
    command: dict
    timestamp: float

def datetime_to_timestamp(dt) -> Timestamp:
    """Convert datetime to protobuf Timestamp"""
    timestamp = Timestamp()
    timestamp.FromDatetime(dt)
    return timestamp

def current_time_to_timestamp() -> Timestamp:
    """Convert current time to protobuf Timestamp"""
    return datetime_to_timestamp(datetime.datetime.utcnow())

def convert_node_state(state: NodeState) -> broker_pb2.NodeState:
    """Convert internal node state to protobuf enum"""
    state_map = {
        NodeState.FOLLOWER: broker_pb2.NodeState.FOLLOWER,
        NodeState.CANDIDATE: broker_pb2.NodeState.CANDIDATE,
        NodeState.LEADER: broker_pb2.NodeState.LEADER
    }
    return state_map.get(state, broker_pb2.NodeState.FOLLOWER)

class RaftNodeGRPC(broker_pb2_grpc.RaftServiceServicer):
    def __init__(self, node_id: str, cluster_nodes: List[Tuple[str, int]], db_writer):
        # Initialize logging first
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(f"Raft-{node_id}")
        
        # Node identification
        self.node_id = node_id
        self.cluster_nodes = cluster_nodes
        self.db_writer = db_writer
        
        # Determine cluster mode
        self.is_single_node = len(cluster_nodes) == 1
        
        # Persistent state (should be saved to disk in production)
        self.current_term = 0
        self.voted_for = None
        self.log: List[LogEntry] = []
        
        # Volatile state
        self.commit_index = 0
        self.last_applied = 0
        self.state = NodeState.FOLLOWER
        
        # Leader state (reinitialized after election)
        self.next_index: Dict[str, int] = {}
        self.match_index: Dict[str, int] = {}
        
        # Timing
        self.election_timeout = self._reset_election_timeout()
        self.last_heartbeat = time.time()
        self.heartbeat_interval = 0.1  # 100ms - faster heartbeats
        
        # Threading
        self.running = True
        self.election_timer_thread = threading.Thread(target=self._election_timer, daemon=True)
        self.heartbeat_thread = None
        
        # gRPC channels for communicating with other nodes
        self.node_channels = {}
        self.node_stubs = {}
        self.available_nodes = set()  # Track which nodes are actually available
        
        # Initialize gRPC connections to other nodes
        self._initialize_grpc_connections()
        
        # For single-node clusters, immediately become leader
        if self.is_single_node:
            self.logger.info("Single-node cluster detected, becoming leader immediately")
            self._become_leader()
        else:
            # Start election timer for multi-node clusters
            self.election_timer_thread.start()
            
            # Start periodic peer discovery
            self.discovery_thread = threading.Thread(target=self._periodic_peer_discovery, daemon=True)
            self.discovery_thread.start()
    
    def _initialize_grpc_connections(self):
        """Initialize gRPC channels to other cluster nodes"""
        for node_host, node_port in self.cluster_nodes:
            node_addr = f"{node_host}:{node_port}"
            if node_addr != self.node_id:
                self._try_connect_to_node(node_addr)
    
    def _try_connect_to_node(self, node_addr: str):
        """Try to connect to a single node"""
        try:
            channel = grpc.insecure_channel(node_addr)
            stub = broker_pb2_grpc.RaftServiceStub(channel)
            
            # Test connection with a quick health check
            try:
                stub.GetRaftStatus(Empty(), timeout=0.1)
                self.node_channels[node_addr] = channel
                self.node_stubs[node_addr] = stub
                self.available_nodes.add(node_addr)
                self.logger.info(f"Connected to node {node_addr}")
            except grpc.RpcError:
                # Node not available yet, keep channel for later retry
                self.node_channels[node_addr] = channel
                self.node_stubs[node_addr] = stub
                self.logger.debug(f"Node {node_addr} not ready yet, will retry")
                
        except Exception as e:
            self.logger.debug(f"Failed to connect to node {node_addr}: {e}")
    
    def _periodic_peer_discovery(self):
        """Periodically try to discover and connect to peers"""
        while self.running:
            for node_host, node_port in self.cluster_nodes:
                node_addr = f"{node_host}:{node_port}"
                if node_addr != self.node_id and node_addr not in self.available_nodes:
                    try:
                        if node_addr in self.node_stubs:
                            # Try to ping existing connection
                            stub = self.node_stubs[node_addr]
                            stub.GetRaftStatus(Empty(), timeout=0.1)
                            self.available_nodes.add(node_addr)
                            self.logger.info(f"Node {node_addr} is now available")
                        else:
                            self._try_connect_to_node(node_addr)
                    except grpc.RpcError:
                        # Node still not available
                        pass
                    except Exception as e:
                        self.logger.debug(f"Error checking node {node_addr}: {e}")
            
            time.sleep(1.0)  # Check every second
    
    def _reset_election_timeout(self) -> float:
        """Random election timeout between 2-4 seconds (much longer than heartbeat)"""
        return random.uniform(2.0, 4.0)
    
    def _election_timer(self):
        """Monitor election timeout and trigger elections"""
        while self.running:
            time.sleep(0.01)  # Check every 10ms
            
            # Skip elections for single-node clusters (already leader)
            if self.is_single_node:
                continue
                
            if self.state != NodeState.LEADER:
                elapsed = time.time() - self.last_heartbeat
                if elapsed > self.election_timeout:
                    self._start_election()
    
    def _start_election(self):
        """Start a new election"""
        # Skip elections if we don't have enough available nodes
        available_count = len(self.available_nodes) + 1  # +1 for self
        if available_count < 2:
            self.logger.debug(f"Only {available_count} nodes available, skipping election")
            self.last_heartbeat = time.time()  # Reset timeout
            return
            
        self.logger.info(f"Starting election for term {self.current_term + 1}")
        
        # Become candidate
        self.state = NodeState.CANDIDATE
        self.current_term += 1
        self.voted_for = self.node_id
        self.last_heartbeat = time.time()
        self.election_timeout = self._reset_election_timeout()
        
        # Vote for self
        votes_received = 1
        
        # Request votes from other nodes (only available ones)
        vote_threads = []
        vote_results = []
        
        for node_addr in self.available_nodes:
            if node_addr in self.node_stubs:
                thread = threading.Thread(
                    target=self._request_vote_from_node,
                    args=(node_addr, self.node_stubs[node_addr], vote_results)
                )
                vote_threads.append(thread)
                thread.start()
        
        # Wait for votes (with timeout)
        for thread in vote_threads:
            thread.join(timeout=0.1)  # 100ms timeout per vote
        
        # Count votes
        for result in vote_results:
            if result and result.vote_granted and result.term == self.current_term:
                votes_received += 1
        
        # Check if won election - use available nodes for majority calculation
        total_nodes = available_count
        majority = total_nodes // 2 + 1
        
        self.logger.debug(f"Election results: {votes_received}/{total_nodes} votes, need {majority}")
        
        if votes_received >= majority and self.state == NodeState.CANDIDATE:
            self._become_leader()
        else:
            self.state = NodeState.FOLLOWER
    
    def _request_vote_from_node(self, node_addr: str, stub, results: list):
        """Request vote from a specific node using gRPC"""
        try:
            last_log_index = len(self.log) - 1 if self.log else -1
            last_log_term = self.log[-1].term if self.log else 0
            
            vote_request = broker_pb2.VoteRequest(
                term=self.current_term,
                candidate_id=self.node_id,
                last_log_index=last_log_index,
                last_log_term=last_log_term
            )
            
            # Make gRPC call with timeout
            response = stub.RequestVote(vote_request, timeout=0.1)
            results.append(response)
                
        except grpc.RpcError as e:
            self.logger.debug(f"gRPC error requesting vote from {node_addr}: {e}")
        except Exception as e:
            self.logger.error(f"Error requesting vote from {node_addr}: {e}")
    
    def _become_leader(self):
        """Become leader and start sending heartbeats"""
        self.logger.info(f"Became leader for term {self.current_term}")
        self.state = NodeState.LEADER
        
        # Initialize leader state
        self.next_index = {}
        self.match_index = {}
        for node_host, node_port in self.cluster_nodes:
            node_addr = f"{node_host}:{node_port}"
            if node_addr != self.node_id:
                self.next_index[node_addr] = len(self.log)
                self.match_index[node_addr] = -1
        
        # Start heartbeat thread (only for multi-node clusters)
        if not self.is_single_node:
            if self.heartbeat_thread and self.heartbeat_thread.is_alive():
                self.heartbeat_thread.join(timeout=0.1)
            
            self.heartbeat_thread = threading.Thread(target=self._send_heartbeats, daemon=True)
            self.heartbeat_thread.start()
    
    def _send_heartbeats(self):
        """Send periodic heartbeats to all followers"""
        while self.running and self.state == NodeState.LEADER:
            # Only send to available nodes
            for node_addr in self.available_nodes:
                if node_addr in self.node_stubs:
                    threading.Thread(
                        target=self._send_append_entries,
                        args=(node_addr, self.node_stubs[node_addr], [])  # Empty entries = heartbeat
                    ).start()
            
            time.sleep(self.heartbeat_interval)
    
    def _send_append_entries(self, node_addr: str, stub, entries: List[LogEntry]):
        """Send append entries RPC to a specific node"""
        try:
            prev_log_index = self.next_index.get(node_addr, 0) - 1
            prev_log_term = 0
            
            if prev_log_index >= 0 and prev_log_index < len(self.log):
                prev_log_term = self.log[prev_log_index].term
            
            # Convert internal log entries to protobuf format
            pb_entries = []
            for entry in entries:
                pb_entry = broker_pb2.LogEntry(
                    term=entry.term,
                    index=entry.index,
                    command_type=entry.command.get('type', ''),
                    command_data=json.dumps(entry.command),
                    timestamp=current_time_to_timestamp()
                )
                pb_entries.append(pb_entry)
            
            append_request = broker_pb2.AppendEntriesRequest(
                term=self.current_term,
                leader_id=self.node_id,
                prev_log_index=prev_log_index,
                prev_log_term=prev_log_term,
                entries=pb_entries,
                leader_commit=self.commit_index
            )
            
            # Make gRPC call with timeout
            response = stub.AppendEntries(append_request, timeout=0.1)
            
            # Mark node as available if call succeeded
            self.available_nodes.add(node_addr)
            
            # Handle response
            if response.term > self.current_term:
                self.current_term = response.term
                self.state = NodeState.FOLLOWER
                self.voted_for = None
            elif self.state == NodeState.LEADER:
                if response.success:
                    # Update next_index and match_index for successful replication
                    self.match_index[node_addr] = prev_log_index + len(entries)
                    self.next_index[node_addr] = self.match_index[node_addr] + 1
                else:
                    # Decrement next_index on failure
                    if node_addr in self.next_index:
                        self.next_index[node_addr] = max(0, self.next_index[node_addr] - 1)
            
        except grpc.RpcError as e:
            # Remove from available nodes if call failed
            self.available_nodes.discard(node_addr)
            self.logger.debug(f"gRPC error sending append entries to {node_addr}: {e}")
        except Exception as e:
            self.available_nodes.discard(node_addr)
            self.logger.error(f"Error sending append entries to {node_addr}: {e}")
    
    def append_entry(self, command: dict) -> tuple[bool, str]:
        """Append a new entry to the log (only for leaders)"""
        if self.state != NodeState.LEADER:
            return False, "Not the leader"
        
        # Create new log entry
        new_entry = LogEntry(
            term=self.current_term,
            index=len(self.log),
            command=command,
            timestamp=time.time()
        )
        
        # Add to local log
        self.log.append(new_entry)
        
        # Replicate to followers (simplified - in production, wait for majority)
        for node_addr, stub in self.node_stubs.items():
            threading.Thread(
                target=self._send_append_entries,
                args=(node_addr, stub, [new_entry])
            ).start()
        
        # For now, immediately commit (in production, wait for majority acknowledgment)
        self.commit_index = len(self.log) - 1
        self._apply_committed_entries()
        
        return True, "Entry appended successfully"
    
    def _apply_committed_entries(self):
        """Apply committed entries to the state machine (database)"""
        while self.last_applied < self.commit_index:
            self.last_applied += 1
            if self.last_applied < len(self.log):
                entry = self.log[self.last_applied]
                
                # Apply the command to the database
                if entry.command.get('type') == 'message':
                    cmd = entry.command
                    self.db_writer.write_async(
                        "INSERT INTO queue(topic, format, body, timestamp) VALUES (?,?,?,?)",
                        (cmd['topic'], cmd['format'], cmd['body'], cmd['timestamp'])
                    )
    
    def get_status(self) -> broker_pb2.RaftStatus:
        """Get current RAFT status"""
        cluster_node_addrs = [f"{host}:{port}" for host, port in self.cluster_nodes]
        
        return broker_pb2.RaftStatus(
            state=convert_node_state(self.state),
            current_term=self.current_term,
            voted_for=self.voted_for or "",
            commit_index=self.commit_index,
            last_applied=self.last_applied,
            leader_id=self.node_id if self.state == NodeState.LEADER else "",
            cluster_nodes=cluster_node_addrs,
            last_heartbeat=current_time_to_timestamp()
        )
    
    def shutdown(self):
        """Shutdown the RAFT node"""
        self.running = False
        
        # Close gRPC channels
        for channel in self.node_channels.values():
            try:
                channel.close()
            except:
                pass
        
        # Wait for threads to finish
        try:
            if self.election_timer_thread.is_alive():
                self.election_timer_thread.join(timeout=1.0)
            if self.heartbeat_thread and self.heartbeat_thread.is_alive():
                self.heartbeat_thread.join(timeout=1.0)
        except:
            pass
    
    # gRPC Service Methods
    def RequestVote(self, request, context):
        """Handle vote request from candidate"""
        try:
            # If candidate's term is higher, update our term and become follower
            if request.term > self.current_term:
                self.current_term = request.term
                self.voted_for = None
                self.state = NodeState.FOLLOWER
            
            vote_granted = False
            
            # Grant vote if:
            # 1. We haven't voted in this term, or we already voted for this candidate
            # 2. Candidate's log is at least as up-to-date as ours
            if (request.term == self.current_term and 
                (self.voted_for is None or self.voted_for == request.candidate_id)):
                
                # Check if candidate's log is up-to-date
                last_log_index = len(self.log) - 1 if self.log else -1
                last_log_term = self.log[-1].term if self.log else 0
                
                if (request.last_log_term > last_log_term or 
                    (request.last_log_term == last_log_term and request.last_log_index >= last_log_index)):
                    
                    vote_granted = True
                    self.voted_for = request.candidate_id
                    self.last_heartbeat = time.time()  # Reset election timeout
            
            return broker_pb2.VoteResponse(
                term=self.current_term,
                vote_granted=vote_granted
            )
            
        except Exception as e:
            self.logger.error(f"Error handling vote request: {e}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return broker_pb2.VoteResponse(term=self.current_term, vote_granted=False)
    
    def AppendEntries(self, request, context):
        """Handle append entries request from leader"""
        try:
            # If leader's term is higher, update our term and become follower
            if request.term > self.current_term:
                self.current_term = request.term
                self.voted_for = None
                self.state = NodeState.FOLLOWER
            
            # Reset election timeout since we heard from leader
            if request.term == self.current_term:
                self.last_heartbeat = time.time()
                self.state = NodeState.FOLLOWER
            
            success = False
            
            # Reply false if term < currentTerm
            if request.term >= self.current_term:
                # Check if previous log entry matches
                if (request.prev_log_index == -1 or 
                    (request.prev_log_index < len(self.log) and 
                     self.log[request.prev_log_index].term == request.prev_log_term)):
                    
                    success = True
                    
                    # If entries are provided, append them
                    if request.entries:
                        # Convert protobuf entries to internal format
                        new_entries = []
                        for pb_entry in request.entries:
                            command = json.loads(pb_entry.command_data) if pb_entry.command_data else {}
                            entry = LogEntry(
                                term=pb_entry.term,
                                index=pb_entry.index,
                                command=command,
                                timestamp=time.time()
                            )
                            new_entries.append(entry)
                        
                        # Append new entries
                        start_index = request.prev_log_index + 1
                        self.log = self.log[:start_index] + new_entries
                    
                    # Update commit index
                    if request.leader_commit > self.commit_index:
                        self.commit_index = min(request.leader_commit, len(self.log) - 1)
                        self._apply_committed_entries()
            
            return broker_pb2.AppendEntriesResponse(
                term=self.current_term,
                success=success
            )
            
        except Exception as e:
            self.logger.error(f"Error handling append entries: {e}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return broker_pb2.AppendEntriesResponse(term=self.current_term, success=False)
    
    def GetRaftStatus(self, request, context):
        """Get current RAFT status via gRPC"""
        return self.get_status()
    
    def InstallSnapshot(self, request, context):
        """Handle snapshot installation (placeholder)"""
        # This is a simplified implementation
        # In production, you'd handle snapshot installation properly
        return broker_pb2.InstallSnapshotResponse(term=self.current_term)