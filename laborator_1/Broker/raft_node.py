import time
import random
import threading
import json
import socket
import logging
from enum import Enum
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple

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

@dataclass
class VoteRequest:
    term: int
    candidate_id: str
    last_log_index: int
    last_log_term: int

@dataclass
class VoteResponse:
    term: int
    vote_granted: bool

@dataclass
class AppendEntriesRequest:
    term: int
    leader_id: str
    prev_log_index: int
    prev_log_term: int
    entries: List[LogEntry]
    leader_commit: int

@dataclass
class AppendEntriesResponse:
    term: int
    success: bool

class RaftNode:
    def __init__(self, node_id: str, cluster_nodes: List[Tuple[str, int]], db_writer):
        # Node identification
        self.node_id = node_id
        self.cluster_nodes = cluster_nodes
        self.db_writer = db_writer
        
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
        
        # Network
        self.rpc_server = None
        
        # Start election timer
        self.election_timer_thread.start()
        
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(f"Raft-{node_id}")
    
    def _reset_election_timeout(self) -> float:
        """Random election timeout between 2-4 seconds (much longer than heartbeat)"""
        return random.uniform(2.0, 4.0)
    
    def _election_timer(self):
        """Monitor election timeout and trigger elections"""
        while self.running:
            time.sleep(0.01)  # Check every 10ms
            
            if self.state != NodeState.LEADER:
                elapsed = time.time() - self.last_heartbeat
                if elapsed > self.election_timeout:
                    self._start_election()
    
    def _start_election(self):
        """Start a new election"""
        self.logger.info(f"Starting election for term {self.current_term + 1}")
        
        # Become candidate
        self.state = NodeState.CANDIDATE
        self.current_term += 1
        self.voted_for = self.node_id
        self.last_heartbeat = time.time()
        self.election_timeout = self._reset_election_timeout()
        
        # Vote for self
        votes_received = 1
        
        # Request votes from other nodes
        vote_threads = []
        vote_results = []
        
        for node_host, node_port in self.cluster_nodes:
            if f"{node_host}:{node_port}" != self.node_id:
                thread = threading.Thread(
                    target=self._request_vote_from_node,
                    args=(node_host, node_port, vote_results)
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
        
        # Check if won election
        majority = len(self.cluster_nodes) // 2 + 1
        if votes_received >= majority and self.state == NodeState.CANDIDATE:
            self._become_leader()
        else:
            self.state = NodeState.FOLLOWER
    
    def _request_vote_from_node(self, host: str, port: int, results: list):
        """Request vote from a specific node"""
        try:
            last_log_index = len(self.log) - 1 if self.log else -1
            last_log_term = self.log[-1].term if self.log else 0
            
            vote_request = VoteRequest(
                term=self.current_term,
                candidate_id=self.node_id,
                last_log_index=last_log_index,
                last_log_term=last_log_term
            )
            
            response = self._send_rpc(host, port, "vote_request", vote_request)
            if response:
                results.append(response)
                
        except Exception as e:
            self.logger.error(f"Error requesting vote from {host}:{port}: {e}")
    
    def _become_leader(self):
        """Become leader and start sending heartbeats"""
        self.logger.info(f"Became leader for term {self.current_term}")
        self.state = NodeState.LEADER
        
        # Initialize leader state
        self.next_index = {}
        self.match_index = {}
        for node_host, node_port in self.cluster_nodes:
            node_id = f"{node_host}:{node_port}"
            if node_id != self.node_id:
                self.next_index[node_id] = len(self.log)
                self.match_index[node_id] = -1
        
        # Start heartbeat thread
        if self.heartbeat_thread and self.heartbeat_thread.is_alive():
            self.heartbeat_thread.join(timeout=0.1)
        
        self.heartbeat_thread = threading.Thread(target=self._send_heartbeats, daemon=True)
        self.heartbeat_thread.start()
    
    def _send_heartbeats(self):
        """Send periodic heartbeats to all followers"""
        while self.running and self.state == NodeState.LEADER:
            for node_host, node_port in self.cluster_nodes:
                node_id = f"{node_host}:{node_port}"
                if node_id != self.node_id:
                    threading.Thread(
                        target=self._send_append_entries,
                        args=(node_host, node_port, [])  # Empty entries = heartbeat
                    ).start()
            
            time.sleep(self.heartbeat_interval)
    
    def _send_append_entries(self, host: str, port: int, entries: List[LogEntry]):
        """Send append entries RPC to a specific node"""
        try:
            node_id = f"{host}:{port}"
            prev_log_index = self.next_index[node_id] - 1
            prev_log_term = 0
            
            if prev_log_index >= 0 and prev_log_index < len(self.log):
                prev_log_term = self.log[prev_log_index].term
            
            append_request = AppendEntriesRequest(
                term=self.current_term,
                leader_id=self.node_id,
                prev_log_index=prev_log_index,
                prev_log_term=prev_log_term,
                entries=entries,
                leader_commit=self.commit_index
            )
            
            response = self._send_rpc(host, port, "append_entries", append_request)
            
            if response:
                self._handle_append_entries_response(node_id, response)
                
        except Exception as e:
            self.logger.error(f"Error sending append entries to {host}:{port}: {e}")
    
    def _handle_append_entries_response(self, node_id: str, response: AppendEntriesResponse):
        """Handle response from append entries RPC"""
        if response.term > self.current_term:
            self.current_term = response.term
            self.voted_for = None
            self.state = NodeState.FOLLOWER
            return
        
        if self.state == NodeState.LEADER and response.term == self.current_term:
            if response.success:
                # Update next_index and match_index
                self.match_index[node_id] = self.next_index[node_id]
                self.next_index[node_id] += 1
            else:
                # Decrement next_index and retry
                if self.next_index[node_id] > 0:
                    self.next_index[node_id] -= 1
    
    def append_entry(self, command: dict) -> Tuple[bool, str]:
        """Append a new entry to the log (only leader)"""
        if self.state != NodeState.LEADER:
            return False, f"Not leader. Current state: {self.state.value}"
        
        # Create log entry
        entry = LogEntry(
            term=self.current_term,
            index=len(self.log),
            command=command,
            timestamp=time.time()
        )
        
        # Append to log
        self.log.append(entry)
        self.logger.info(f"Appended entry {entry.index} to log: {command}")
        
        # Start replication to followers
        self._replicate_entry(entry)
        
        return True, "Entry appended"
    
    def _replicate_entry(self, entry: LogEntry):
        """Replicate entry to all followers"""
        replication_threads = []
        
        for node_host, node_port in self.cluster_nodes:
            node_id = f"{node_host}:{node_port}"
            if node_id != self.node_id:
                thread = threading.Thread(
                    target=self._send_append_entries,
                    args=(node_host, node_port, [entry])
                )
                replication_threads.append(thread)
                thread.start()
        
        # Wait for replication (with timeout)
        for thread in replication_threads:
            thread.join(timeout=0.1)
    
    def _send_rpc(self, host: str, port: int, method: str, request) -> Optional[object]:
        """Send RPC to another node"""
        try:
            # Create socket connection
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(0.1)  # 100ms timeout
            sock.connect((host, port + 1000))  # Use port+1000 for Raft RPC
            
            # Send request
            rpc_data = {
                "method": method,
                "request": self._serialize_request(request)
            }
            
            sock.send(json.dumps(rpc_data).encode() + b'\n')
            
            # Receive response
            response_data = sock.recv(1024).decode().strip()
            response = json.loads(response_data)
            
            sock.close()
            
            return self._deserialize_response(method, response)
            
        except Exception as e:
            self.logger.debug(f"RPC error to {host}:{port}: {e}")
            return None
    
    def _serialize_request(self, request) -> dict:
        """Serialize request object to dict"""
        if hasattr(request, '__dict__'):
            result = {}
            for key, value in request.__dict__.items():
                if isinstance(value, list) and value and hasattr(value[0], '__dict__'):
                    result[key] = [item.__dict__ for item in value]
                else:
                    result[key] = value
            return result
        return request
    
    def _deserialize_response(self, method: str, response: dict):
        """Deserialize response dict to object"""
        if method == "vote_request":
            return VoteResponse(**response)
        elif method == "append_entries":
            return AppendEntriesResponse(**response)
        return response
    
    def handle_vote_request(self, request: VoteRequest) -> VoteResponse:
        """Handle incoming vote request"""
        vote_granted = False
        
        # Update term if necessary
        if request.term > self.current_term:
            self.current_term = request.term
            self.voted_for = None
            self.state = NodeState.FOLLOWER
        
        # Grant vote if conditions are met
        if (request.term == self.current_term and 
            (self.voted_for is None or self.voted_for == request.candidate_id)):
            
            # Check if candidate's log is at least as up-to-date
            last_log_index = len(self.log) - 1 if self.log else -1
            last_log_term = self.log[-1].term if self.log else 0
            
            if (request.last_log_term > last_log_term or
                (request.last_log_term == last_log_term and request.last_log_index >= last_log_index)):
                
                vote_granted = True
                self.voted_for = request.candidate_id
                self.last_heartbeat = time.time()  # Reset election timeout
        
        return VoteResponse(term=self.current_term, vote_granted=vote_granted)
    
    def handle_append_entries(self, request: AppendEntriesRequest) -> AppendEntriesResponse:
        """Handle incoming append entries request"""
        success = False
        
        # Update term if necessary
        if request.term > self.current_term:
            self.current_term = request.term
            self.voted_for = None
            self.state = NodeState.FOLLOWER
        
        if request.term == self.current_term:
            self.state = NodeState.FOLLOWER
            self.last_heartbeat = time.time()  # Reset election timeout
            
            # Check if log contains entry at prev_log_index with matching term
            if (request.prev_log_index == -1 or
                (request.prev_log_index < len(self.log) and
                 self.log[request.prev_log_index].term == request.prev_log_term)):
                
                success = True
                
                # Append new entries
                if request.entries:
                    # Remove conflicting entries
                    self.log = self.log[:request.prev_log_index + 1]
                    
                    # Append new entries
                    for entry_dict in request.entries:
                        if isinstance(entry_dict, dict):
                            entry = LogEntry(**entry_dict)
                        else:
                            entry = entry_dict
                        self.log.append(entry)
                        
                        # Apply committed entries to state machine (database)
                        if entry.index <= request.leader_commit:
                            self._apply_to_state_machine(entry)
                
                # Update commit index
                if request.leader_commit > self.commit_index:
                    self.commit_index = min(request.leader_commit, len(self.log) - 1)
        
        return AppendEntriesResponse(term=self.current_term, success=success)
    
    def _apply_to_state_machine(self, entry: LogEntry):
        """Apply committed log entry to state machine (database)"""
        try:
            command = entry.command
            if command.get('type') == 'message':
                # Apply message to database
                self.db_writer.write_async(
                    "INSERT INTO queue (topic, format, body, timestamp) VALUES (?, ?, ?, ?)",
                    (command['topic'], command['format'], command['body'], command['timestamp'])
                )
                self.logger.info(f"Applied entry {entry.index} to state machine")
                
        except Exception as e:
            self.logger.error(f"Error applying entry to state machine: {e}")
    
    def get_status(self) -> dict:
        """Get current Raft status"""
        return {
            "node_id": self.node_id,
            "state": self.state.value,
            "current_term": self.current_term,
            "log_length": len(self.log),
            "commit_index": self.commit_index,
            "last_applied": self.last_applied,
            "cluster_size": len(self.cluster_nodes)
        }
    
    def shutdown(self):
        """Shutdown the Raft node"""
        self.running = False
        if self.heartbeat_thread:
            self.heartbeat_thread.join(timeout=1)