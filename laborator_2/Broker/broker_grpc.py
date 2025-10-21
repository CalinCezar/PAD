import grpc
from concurrent import futures
import sqlite3
import json
import xml.etree.ElementTree as ET
import os
import time
import queue
import threading
import argparse
import socket
import psutil
from datetime import datetime
from typing import Optional, Callable, Dict, Any, List
import logging

# Import generated gRPC code
import broker_pb2
import broker_pb2_grpc
from google.protobuf.timestamp_pb2 import Timestamp
from google.protobuf.empty_pb2 import Empty

# Import our RAFT implementation
from raft_node_grpc import RaftNodeGRPC, LogEntry

# Parse command line arguments
def parse_args():
    parser = argparse.ArgumentParser(description='gRPC Message Broker with RAFT consensus')
    parser.add_argument('--node-id', type=int, help='Node ID for this broker instance (auto-assigned if not specified)')
    parser.add_argument('--grpc-port', type=int, help='gRPC server port (auto-assigned if not specified)')
    parser.add_argument('--http-port', type=int, help='HTTP bridge port (auto-assigned if not specified)')
    parser.add_argument('--peers', type=str, help='Comma-separated list of peer addresses (auto-discovered if not specified)')
    parser.add_argument('--cluster-size', type=int, default=3, help='Expected cluster size for auto-configuration')
    parser.add_argument('--single-node', action='store_true', help='Run as single-node cluster')
    return parser.parse_args()

def auto_configure_cluster():
    """Auto-configure node settings based on running instances"""
    import psutil
    import socket
    
    base_grpc_port = 50051
    base_http_port = 8080
    max_cluster_size = args.cluster_size
    
    # Find running broker instances by checking listening ports
    running_brokers = []
    for port in range(base_grpc_port, base_grpc_port + max_cluster_size):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                result = s.connect_ex(('127.0.0.1', port))
                if result == 0:  # Port is in use
                    running_brokers.append(port)
        except Exception:
            pass
    
    print(f"[AUTO-CONFIG] Found {len(running_brokers)} running broker instances: {running_brokers}")
    
    # Auto-assign node ID and ports
    if args.node_id is None:
        # Find next available node ID
        used_node_ids = []
        for port in running_brokers:
            node_id = port - base_grpc_port
            used_node_ids.append(node_id)
        
        # Assign next available node ID
        for node_id in range(max_cluster_size):
            if node_id not in used_node_ids:
                args.node_id = node_id
                break
        else:
            args.node_id = len(running_brokers)
        
        print(f"[AUTO-CONFIG] Auto-assigned node ID: {args.node_id}")
    
    if args.grpc_port is None:
        args.grpc_port = base_grpc_port + args.node_id
        
        # Check if port is already in use
        while args.grpc_port in running_brokers:
            args.grpc_port += 1
        
        print(f"[AUTO-CONFIG] Auto-assigned gRPC port: {args.grpc_port}")
    
    if args.http_port is None:
        args.http_port = base_http_port + args.node_id
        print(f"[AUTO-CONFIG] Auto-assigned HTTP port: {args.http_port}")
    
    # Auto-discover peers if not specified and not single-node
    if args.peers is None and not args.single_node:
        peers = []
        
        # Add running brokers as peers
        for port in running_brokers:
            if port != args.grpc_port:
                peers.append(f"127.0.0.1:{port}")
        
        # Add expected future nodes if cluster is not complete
        if len(running_brokers) < max_cluster_size - 1:  # -1 because current instance not counted yet
            for node_id in range(max_cluster_size):
                expected_port = base_grpc_port + node_id
                if expected_port != args.grpc_port and expected_port not in running_brokers:
                    peers.append(f"127.0.0.1:{expected_port}")
                    if len(peers) + len(running_brokers) >= max_cluster_size - 1:
                        break  # Don't add more peers than needed
        
        args.peers = ','.join(peers) if peers else None
        
        if args.peers:
            print(f"[AUTO-CONFIG] Auto-discovered peers: {args.peers}")
        else:
            print(f"[AUTO-CONFIG] No peers found, running as single-node cluster")

def check_port_available(port):
    """Check if a port is available"""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(('127.0.0.1', port))
            return True
    except OSError:
        return False

# Parse arguments and auto-configure
args = parse_args()

# Auto-configure if needed
if args.node_id is None or args.grpc_port is None or (args.peers is None and not args.single_node):
    auto_configure_cluster()

BROKER_NODE_ID = args.node_id or 0
BROKER_PORT = args.grpc_port or 50051
HTTP_PORT = args.http_port or 8080
PEERS = args.peers.split(',') if args.peers else None

print(f"[CONFIG] Node ID: {BROKER_NODE_ID}, gRPC Port: {BROKER_PORT}, HTTP Port: {HTTP_PORT}")
if PEERS:
    print(f"[CONFIG] Peers: {PEERS}")
else:
    print(f"[CONFIG] Running as single-node cluster")

HOST = "127.0.0.1"

# Subscriber management
subscribers = {}  # {subscriber_id: {"topics": set(), "stream": grpc_stream, "last_heartbeat": timestamp}}

# Heartbeat configuration
HEARTBEAT_TIMEOUT = 90  # seconds
MAX_MISSED_HEARTBEATS = 3

# Statistics
broker_stats = {
    "start_time": datetime.now(),
    "total_messages": 0,
}

class DatabaseWriter:
    """Thread-safe database writer using queue to serialize writes"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.write_queue = queue.Queue()
        self.running = True
        
        # Single writer thread to avoid database locks
        self.writer_thread = threading.Thread(target=self._writer_loop, daemon=True)
        self.writer_thread.start()
        
        print(f"[DatabaseWriter] Started with db: {db_path}")
    
    def _writer_loop(self):
        """Single thread processes all writes sequentially"""
        conn = None
        try:
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            conn.execute("PRAGMA journal_mode=WAL")  # Enable WAL mode for better concurrency
            cur = conn.cursor()
            
            while self.running:
                try:
                    # Get write request from queue (blocking with timeout)
                    write_request = self.write_queue.get(timeout=1.0)
                    
                    if write_request is None:  # Shutdown signal
                        break
                    
                    # Execute write operation
                    query = write_request['query']
                    params = write_request.get('params', ())
                    callback = write_request.get('callback')
                    
                    cur.execute(query, params)
                    conn.commit()
                    
                    # Signal success to callback
                    if callback:
                        try:
                            callback(True, cur.lastrowid)
                        except:
                            pass  # Callback failed, but write succeeded
                    
                    # Mark task as done
                    self.write_queue.task_done()
                    
                except queue.Empty:
                    continue  # Timeout, check if still running
                except Exception as e:
                    print(f"[DatabaseWriter] Write error: {e}")
                    
                    # Signal failure to callback
                    if 'write_request' in locals() and write_request.get('callback'):
                        try:
                            write_request['callback'](False, None)
                        except:
                            pass
                    
                    # Mark task as done even on failure
                    try:
                        self.write_queue.task_done()
                    except:
                        pass
        
        except Exception as e:
            print(f"[DatabaseWriter] Connection error: {e}")
        finally:
            if conn:
                conn.close()
    
    def write_async(self, query: str, params: tuple = (), callback: Optional[Callable] = None):
        """Queue a write operation (non-blocking)"""
        write_request = {
            'query': query,
            'params': params,
            'callback': callback
        }
        self.write_queue.put(write_request)
    
    def write_sync(self, query: str, params: tuple = ()) -> tuple[bool, Any]:
        """Synchronous write with result (blocking)"""
        result_event = threading.Event()
        result_data = {'success': False, 'result': None}
        
        def callback(success: bool, result: Any):
            result_data['success'] = success
            result_data['result'] = result
            result_event.set()
        
        self.write_async(query, params, callback)
        result_event.wait(timeout=5.0)  # 5 second timeout
        
        return result_data['success'], result_data['result']
    
    def shutdown(self):
        """Shutdown the writer thread"""
        self.running = False
        self.write_queue.put(None)  # Signal shutdown
        
        try:
            self.writer_thread.join(timeout=2.0)
        except:
            pass

# Global instances
db_writer = None
raft_node = None
conn_db = None
cur = None

def escape_xml(text):
    """Escape XML special characters"""
    if text is None:
        return ""
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\"", "&quot;").replace("'", "&#x27;")

def datetime_to_timestamp(dt: datetime) -> Timestamp:
    """Convert datetime to protobuf Timestamp"""
    timestamp = Timestamp()
    timestamp.FromDatetime(dt)
    return timestamp

def timestamp_to_datetime(timestamp: Timestamp) -> datetime:
    """Convert protobuf Timestamp to datetime"""
    return timestamp.ToDatetime()

def convert_message_format(format_str: str) -> broker_pb2.MessageFormat:
    """Convert string format to protobuf enum"""
    format_map = {
        "RAW": broker_pb2.MessageFormat.RAW,
        "JSON": broker_pb2.MessageFormat.JSON,
        "XML": broker_pb2.MessageFormat.XML
    }
    return format_map.get(format_str.upper(), broker_pb2.MessageFormat.RAW)

def format_enum_to_string(format_enum: broker_pb2.MessageFormat) -> str:
    """Convert protobuf enum to string"""
    format_map = {
        broker_pb2.MessageFormat.RAW: "RAW",
        broker_pb2.MessageFormat.JSON: "JSON",
        broker_pb2.MessageFormat.XML: "XML"
    }
    return format_map.get(format_enum, "RAW")

class PublisherServiceImpl(broker_pb2_grpc.PublisherServiceServicer):
    """Implementation of Publisher gRPC service"""
    
    def PublishMessage(self, request, context):
        """Handle single message publishing"""
        try:
            # Extract message details
            topic = request.topic or "default"
            content = request.content
            format_str = format_enum_to_string(request.format)
            event_name = request.event_name or "PublisherMessage"
            
            # Validate and format message content
            if format_str == "JSON":
                try:
                    json.loads(content)  # Test if it's valid JSON
                    body = content
                except:
                    # Invalid JSON, create valid JSON wrapper
                    import time
                    body = json.dumps({
                        "Id": int(time.time() * 1000),
                        "EventName": event_name,
                        "Value": content,
                        "Topic": topic
                    })
            elif format_str == "XML":
                try:
                    ET.fromstring(content)  # Test if it's valid XML
                    body = content
                except:
                    # Invalid XML, create valid XML wrapper
                    import time
                    body = f"<Message><Id>{int(time.time() * 1000)}</Id><EventName>{event_name}</EventName><Value>{escape_xml(content)}</Value><Topic>{escape_xml(topic)}</Topic></Message>"
            else:
                body = content
            
            # Save message using RAFT consensus
            success = save_message(topic, format_str, body)
            
            # Forward to interested subscribers
            subscriber_count = forward_to_subscribers(topic, format_str, body)
            
            return broker_pb2.PublishResponse(
                success=success,
                message="Message published successfully" if success else "Failed to publish message",
                forwarded=subscriber_count > 0,
                subscriber_count=subscriber_count
            )
            
        except Exception as e:
            print(f"Error publishing message: {e}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return broker_pb2.PublishResponse(
                success=False,
                message=f"Error: {str(e)}",
                forwarded=False,
                subscriber_count=0
            )
    
    def PublishBatch(self, request_iterator, context):
        """Handle batch message publishing"""
        total_published = 0
        total_forwarded = 0
        
        try:
            for request in request_iterator:
                # Process each message in the batch
                topic = request.topic or "default"
                content = request.content
                format_str = format_enum_to_string(request.format)
                
                if save_message(topic, format_str, content):
                    total_published += 1
                    subscriber_count = forward_to_subscribers(topic, format_str, content)
                    if subscriber_count > 0:
                        total_forwarded += 1
            
            return broker_pb2.PublishResponse(
                success=True,
                message=f"Batch published: {total_published} messages",
                forwarded=total_forwarded > 0,
                subscriber_count=total_forwarded
            )
            
        except Exception as e:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return broker_pb2.PublishResponse(
                success=False,
                message=f"Batch error: {str(e)}",
                forwarded=False,
                subscriber_count=0
            )
    
    def GetPublisherHealth(self, request, context):
        """Return publisher health status"""
        return broker_pb2.HealthResponse(
            healthy=True,
            status="Publisher service operational",
            timestamp=datetime_to_timestamp(datetime.now())
        )

class SubscriberServiceImpl(broker_pb2_grpc.SubscriberServiceServicer):
    """Implementation of Subscriber gRPC service"""
    
    def Subscribe(self, request, context):
        """Handle topic subscription with real-time message streaming"""
        subscriber_id = request.subscriber_id or f"subscriber_{len(subscribers) + 1}"
        topics = set(request.topics) if request.topics else {"all"}
        
        print(f"New subscriber: {subscriber_id} for topics: {topics}")
        
        # Create message queue for this subscriber
        message_queue = queue.Queue()
        
        # Register subscriber
        subscribers[subscriber_id] = {
            "topics": topics,
            "queue": message_queue,
            "last_heartbeat": time.time(),
            "missed_beats": 0
        }
        
        try:
            # Send historical messages if requested
            if request.include_historical:
                for topic in topics:
                    if topic == "all":
                        cur.execute("SELECT topic, format, body, timestamp FROM queue ORDER BY timestamp DESC LIMIT 20")
                    else:
                        cur.execute("SELECT topic, format, body, timestamp FROM queue WHERE topic = ? ORDER BY timestamp DESC LIMIT 20", (topic,))
                    
                    for row in cur.fetchall():
                        msg = broker_pb2.Message(
                            id=int(time.time() * 1000),
                            topic=row[0],
                            format=convert_message_format(row[1]),
                            content=row[2],
                            timestamp=datetime_to_timestamp(datetime.fromisoformat(row[3])),
                            event_name="HistoricalMessage"
                        )
                        yield msg
            
            # Stream real-time messages
            while context.is_active():
                try:
                    # Wait for new messages with timeout
                    message = message_queue.get(timeout=1.0)
                    yield message
                    message_queue.task_done()
                except queue.Empty:
                    # Check if client is still connected
                    continue
                except Exception as e:
                    print(f"Error streaming to subscriber {subscriber_id}: {e}")
                    break
        
        finally:
            # Clean up subscriber
            if subscriber_id in subscribers:
                del subscribers[subscriber_id]
            print(f"Subscriber disconnected: {subscriber_id}")
    
    def SubscribeWithFilter(self, request, context):
        """Subscribe with additional filtering options"""
        # For now, delegate to regular Subscribe - can be extended with filtering logic
        return self.Subscribe(request, context)
    
    def Unsubscribe(self, request, context):
        """Handle unsubscription from topics"""
        subscriber_id = request.subscriber_id
        topics_to_remove = set(request.topics) if request.topics else set()
        
        if subscriber_id in subscribers:
            if topics_to_remove:
                # Remove specific topics
                subscribers[subscriber_id]["topics"] -= topics_to_remove
                message = f"Unsubscribed from topics: {topics_to_remove}"
            else:
                # Remove all topics (full unsubscribe)
                del subscribers[subscriber_id]
                message = "Fully unsubscribed"
            
            return broker_pb2.UnsubscribeResponse(success=True, message=message)
        else:
            return broker_pb2.UnsubscribeResponse(success=False, message="Subscriber not found")
    
    def Heartbeat(self, request, context):
        """Handle heartbeat from subscribers"""
        subscriber_id = request.subscriber_id
        
        if subscriber_id in subscribers:
            subscribers[subscriber_id]["last_heartbeat"] = time.time()
            subscribers[subscriber_id]["missed_beats"] = 0
        
        return broker_pb2.HeartbeatResponse(
            acknowledged=True,
            server_timestamp=datetime_to_timestamp(datetime.now())
        )
    
    def GetHistoricalMessages(self, request, context):
        """Retrieve historical messages for topics"""
        topics = request.topics if request.topics else ["all"]
        limit = request.limit if request.limit > 0 else 50
        
        for topic in topics:
            if topic == "all":
                cur.execute("SELECT topic, format, body, timestamp FROM queue ORDER BY timestamp DESC LIMIT ?", (limit,))
            else:
                cur.execute("SELECT topic, format, body, timestamp FROM queue WHERE topic = ? ORDER BY timestamp DESC LIMIT ?", (topic, limit))
            
            for row in cur.fetchall():
                msg = broker_pb2.Message(
                    id=int(time.time() * 1000),
                    topic=row[0],
                    format=convert_message_format(row[1]),
                    content=row[2],
                    timestamp=datetime_to_timestamp(datetime.fromisoformat(row[3])),
                    event_name="HistoricalMessage"
                )
                yield msg

class DashboardServiceImpl(broker_pb2_grpc.DashboardServiceServicer):
    """Implementation of Dashboard/Monitoring gRPC service"""
    
    def GetBrokerStatus(self, request, context):
        """Get broker status information"""
        # Count healthy subscribers
        current_time = time.time()
        healthy_subscribers = sum(1 for info in subscribers.values() 
                                if current_time - info["last_heartbeat"] <= HEARTBEAT_TIMEOUT)
        
        raft_status = raft_node.get_status() if raft_node else broker_pb2.RaftStatus(
            state=broker_pb2.NodeState.FOLLOWER
        )
        
        return broker_pb2.BrokerStatus(
            status="online",
            port=BROKER_PORT,
            subscribers=healthy_subscribers,
            current_connections=len(subscribers),
            raft_status=raft_status,
            uptime=datetime_to_timestamp(broker_stats["start_time"])
        )
    
    def GetSystemStats(self, request, context):
        """Get system statistics"""
        current_time = time.time()
        healthy_subscribers = sum(1 for info in subscribers.values() 
                                if current_time - info["last_heartbeat"] <= HEARTBEAT_TIMEOUT)
        
        # Count unique topics
        cur.execute("SELECT DISTINCT topic FROM queue")
        unique_topics = len(cur.fetchall())
        
        # Calculate messages per minute
        uptime_minutes = (datetime.now() - broker_stats["start_time"]).total_seconds() / 60
        messages_per_minute = broker_stats["total_messages"] / max(uptime_minutes, 1)
        
        return broker_pb2.SystemStats(
            total_messages=broker_stats["total_messages"],
            active_subscribers=healthy_subscribers,
            current_connections=len(subscribers),
            topics_count=unique_topics,
            messages_per_minute=messages_per_minute,
            start_time=datetime_to_timestamp(broker_stats["start_time"])
        )
    
    def GetRecentMessages(self, request, context):
        """Get recent messages with pagination"""
        limit = request.limit if request.limit > 0 else 20
        offset = request.offset if request.offset >= 0 else 0
        
        # Build query with optional filters
        query = "SELECT topic, format, body, timestamp FROM queue"
        params = []
        
        if request.topic_filter:
            query += " WHERE topic LIKE ?"
            params.append(f"%{request.topic_filter}%")
        
        if request.format_filter != broker_pb2.MessageFormat.RAW:
            format_str = format_enum_to_string(request.format_filter)
            if params:
                query += " AND format = ?"
            else:
                query += " WHERE format = ?"
            params.append(format_str)
        
        query += " ORDER BY timestamp DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        
        cur.execute(query, params)
        messages = []
        
        for row in cur.fetchall():
            msg = broker_pb2.Message(
                id=int(time.time() * 1000),
                topic=row[0],
                format=convert_message_format(row[1]),
                content=row[2],
                timestamp=datetime_to_timestamp(datetime.fromisoformat(row[3])),
                event_name="Message"
            )
            messages.append(msg)
        
        # Check if there are more messages
        cur.execute("SELECT COUNT(*) FROM queue")
        total_count = cur.fetchone()[0]
        has_more = (offset + limit) < total_count
        
        return broker_pb2.MessageQueryResponse(
            messages=messages,
            total_count=total_count,
            has_more=has_more
        )
    
    def GetTopics(self, request, context):
        """Get list of unique topics"""
        cur.execute("SELECT DISTINCT topic FROM queue ORDER BY topic")
        topics = [row[0] for row in cur.fetchall()]
        
        return broker_pb2.TopicsResponse(topics=topics)
    
    def GetSubscribers(self, request, context):
        """Get list of active subscribers"""
        current_time = time.time()
        active_subscribers = []
        
        for subscriber_id, info in subscribers.items():
            if current_time - info["last_heartbeat"] <= HEARTBEAT_TIMEOUT:
                subscriber_info = broker_pb2.SubscriberInfo(
                    id=subscriber_id,
                    topics=list(info["topics"]),
                    last_seen=datetime_to_timestamp(datetime.fromtimestamp(info["last_heartbeat"])),
                    role="subscriber",
                    is_active=True
                )
                active_subscribers.append(subscriber_info)
        
        return broker_pb2.SubscribersResponse(subscribers=active_subscribers)
    
    def StreamSystemEvents(self, request, context):
        """Stream real-time system events"""
        # This is a placeholder - in a full implementation, you'd have an event queue
        while context.is_active():
            time.sleep(5)  # Send periodic status updates
            
            event = broker_pb2.SystemEvent(
                type=broker_pb2.SystemEvent.EventType.NODE_STATUS_CHANGE,
                description=f"Broker status check - {len(subscribers)} active subscribers",
                timestamp=datetime_to_timestamp(datetime.now()),
                metadata={
                    "subscribers": str(len(subscribers)),
                    "total_messages": str(broker_stats["total_messages"])
                }
            )
            yield event

def save_message(topic: str, fmt: str, body: str) -> bool:
    """Save message using Raft consensus for distributed consistency"""
    timestamp = datetime.now().isoformat()
    
    # Create Raft log entry for the message
    command = {
        'type': 'message',
        'topic': topic,
        'format': fmt,
        'body': body,
        'timestamp': timestamp
    }
    
    # Try to append to Raft log (only works if this node is leader)
    if raft_node:
        success, message = raft_node.append_entry(command)
        if success:
            broker_stats["total_messages"] += 1
            print(f"Message saved via Raft consensus: {topic}")
            return True
        else:
            print(f"Raft append failed: {message}")
            # Fall back to direct database write if not leader
    
    # Fallback: Direct database write (for single-node or fallback scenarios)
    def on_write_complete(success, result):
        if success:
            broker_stats["total_messages"] += 1
            print(f"Message saved (fallback): {topic}")
        else:
            print(f"Failed to save message: {topic}")
    
    db_writer.write_async(
        "INSERT INTO queue(topic, format, body, timestamp) VALUES (?,?,?,?)", 
        (topic, fmt, body, timestamp),
        on_write_complete
    )
    return True

def forward_to_subscribers(topic: str, format_str: str, body: str) -> int:
    """Forward message to interested subscribers"""
    forwarded_count = 0
    
    # Create protobuf message
    msg = broker_pb2.Message(
        id=int(time.time() * 1000),
        topic=topic,
        format=convert_message_format(format_str),
        content=body,
        timestamp=datetime_to_timestamp(datetime.now()),
        event_name="RealtimeMessage"
    )
    
    # Send to interested subscribers
    for subscriber_id, info in list(subscribers.items()):
        try:
            if topic in info["topics"] or "all" in info["topics"]:
                info["queue"].put(msg)
                forwarded_count += 1
                
                # Update subscriber activity tracking
                info["last_heartbeat"] = time.time()
                info["missed_beats"] = 0
        except Exception as e:
            print(f"Error forwarding to subscriber {subscriber_id}: {e}")
            # Remove broken subscriber
            if subscriber_id in subscribers:
                del subscribers[subscriber_id]
    
    if forwarded_count > 0:
        print(f"Message forwarded to {forwarded_count} subscribers")
    else:
        print(f"No subscribers for topic '{topic}'")
    
    return forwarded_count

def initialize_database():
    """Initialize SQLite database with proper error handling and retry logic"""
    global db_writer, raft_node, conn_db, cur
    
    max_retries = 3
    retry_delay = 1  # seconds
    
    # Ensure we're in the correct directory
    broker_dir = os.path.dirname(os.path.abspath(__file__))
    db_path = os.path.join(broker_dir, f"messages_node_{BROKER_NODE_ID}.db")
    
    print(f"Initializing database at: {db_path}")
    
    for attempt in range(max_retries):
        try:
            # Ensure the directory exists and is writable
            os.makedirs(broker_dir, exist_ok=True)
            
            # Test write permissions
            test_file = os.path.join(broker_dir, ".test_write")
            try:
                with open(test_file, 'w') as f:
                    f.write("test")
                os.remove(test_file)
            except IOError as e:
                raise Exception(f"Directory not writable: {broker_dir}") from e
            
            # Connect to database for schema creation
            conn = sqlite3.connect(db_path, check_same_thread=False)
            cursor = conn.cursor()
            
            # Create table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS queue(
                    id INTEGER PRIMARY KEY AUTOINCREMENT, 
                    topic TEXT, 
                    format TEXT, 
                    body TEXT, 
                    timestamp TEXT
                )
            """)
            
            # Test read operation
            cursor.execute("SELECT COUNT(*) FROM queue")
            count = cursor.fetchone()[0]
            print(f"Database schema initialized. Current message count: {count}")
            
            conn.commit()
            conn.close()
            
            # Initialize thread-safe database writer
            db_writer = DatabaseWriter(db_path)
            
            # Initialize Raft node for distributed consensus
            cluster_nodes = discover_cluster_nodes()
            
            node_id = f"127.0.0.1:{BROKER_PORT}"
            raft_node = RaftNodeGRPC(node_id, cluster_nodes, db_writer)
            
            # Create a read-only connection for queries
            conn_db = sqlite3.connect(db_path, check_same_thread=False)
            cur = conn_db.cursor()
            
            print(f"Database writer and Raft node initialized (Node {BROKER_NODE_ID})")
            return True
            
        except Exception as e:
            print(f"Database initialization attempt {attempt + 1} failed: {e}")
            if attempt < max_retries - 1:
                print(f"Retrying in {retry_delay} seconds...")
                time.sleep(retry_delay)
                retry_delay *= 2  # Exponential backoff
            else:
                print("Failed to initialize database after all retries")
                raise

def discover_cluster_nodes():
    """Discover cluster nodes based on configuration"""
    cluster_nodes = []
    
    # Always include self
    self_address = ("127.0.0.1", BROKER_PORT)
    cluster_nodes.append(self_address)
    
    # Add peers if provided
    if PEERS:
        print(f"[Node {BROKER_NODE_ID}] Using provided peers: {PEERS}")
        for peer in PEERS:
            try:
                host, port = peer.strip().split(':')
                peer_address = (host, int(port))
                if peer_address not in cluster_nodes:
                    cluster_nodes.append(peer_address)
            except ValueError:
                print(f"[Node {BROKER_NODE_ID}] Invalid peer format: {peer}")
    else:
        print(f"[Node {BROKER_NODE_ID}] Running as single-node cluster")
    
    # Sort cluster nodes for consistency
    cluster_nodes.sort()
    
    print(f"[Node {BROKER_NODE_ID}] Final gRPC cluster configuration: {len(cluster_nodes)} nodes")
    for i, (host, port) in enumerate(cluster_nodes):
        print(f"  Node {i}: {host}:{port}")
    
    return cluster_nodes

def cleanup_dead_subscribers():
    """Background thread to clean up subscribers with expired heartbeats"""
    while True:
        try:
            current_time = time.time()
            dead_subscribers = []
            
            for subscriber_id, info in list(subscribers.items()):
                if current_time - info["last_heartbeat"] > HEARTBEAT_TIMEOUT:
                    info["missed_beats"] += 1
                    if info["missed_beats"] >= MAX_MISSED_HEARTBEATS:
                        dead_subscribers.append(subscriber_id)
                        print(f"Removing subscriber due to heartbeat timeout: {subscriber_id}")
            
            # Remove dead subscribers
            for subscriber_id in dead_subscribers:
                if subscriber_id in subscribers:
                    del subscribers[subscriber_id]
            
            time.sleep(30)  # Check every 30 seconds
        except Exception as e:
            print(f"Error in cleanup thread: {e}")
            time.sleep(30)

def serve():
    """Start the gRPC server"""
    # Initialize database and RAFT
    initialize_database()
    
    # Create gRPC server
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    
    # Add service implementations
    broker_pb2_grpc.add_PublisherServiceServicer_to_server(PublisherServiceImpl(), server)
    broker_pb2_grpc.add_SubscriberServiceServicer_to_server(SubscriberServiceImpl(), server)
    broker_pb2_grpc.add_DashboardServiceServicer_to_server(DashboardServiceImpl(), server)
    
    # Add RAFT service
    if raft_node:
        broker_pb2_grpc.add_RaftServiceServicer_to_server(raft_node, server)
    
    # Configure server address
    listen_addr = f'{HOST}:{BROKER_PORT}'
    server.add_insecure_port(listen_addr)
    
    # Start cleanup thread
    threading.Thread(target=cleanup_dead_subscribers, daemon=True).start()
    
    # Start server
    server.start()
    print(f"gRPC Broker server started on {listen_addr}")
    print("Features: RAFT consensus, Topic-based routing, Message persistence, Format validation")
    
    try:
        server.wait_for_termination()
    except KeyboardInterrupt:
        print("\nBroker shutting down...")
        
        # Cleanup
        if db_writer:
            db_writer.shutdown()
        if raft_node:
            raft_node.shutdown()
        if conn_db:
            conn_db.close()
        
        server.stop(0)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    serve()