import socket, threading, sqlite3
import json
import xml.etree.ElementTree as ET
import os
import time
import queue
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse
from typing import Optional, Callable, Dict, Any
from raft_node import RaftNode, LogEntry

# Read configuration from environment variables
BROKER_NODE_ID = int(os.environ.get('BROKER_NODE_ID', '0'))
BROKER_PORT = int(os.environ.get('BROKER_PORT', '5000'))
HTTP_PORT = int(os.environ.get('HTTP_PORT', '8080'))

HOST, PORT = "127.0.0.1", BROKER_PORT
subscribers = {}  # Changed to dict: {connection: {"topics": set(), "formats": set(), "last_heartbeat": timestamp, "missed_beats": int}}

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

# Global database writer instance
db_writer = None
raft_node = None

def escape_xml(text):
    """Escape XML special characters"""
    if text is None:
        return ""
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\"", "&quot;").replace("'", "&#x27;")

class BrokerHTTPHandler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
    
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        
        parsed_path = urlparse(self.path)
        
        if parsed_path.path == '/status':
            # Count healthy subscribers (based on heartbeat)
            import time
            current_time = time.time()
            
            healthy_subscribers = 0
            for conn, info in list(subscribers.items()):
                if current_time - info["last_heartbeat"] <= HEARTBEAT_TIMEOUT:
                    healthy_subscribers += 1
            
            status = {
                "status": "online", 
                "port": PORT, 
                "subscribers": healthy_subscribers,
                "current_connections": len(subscribers),
                "raft_status": raft_node.get_status() if raft_node else {"state": "disabled"}
            }
            self.wfile.write(json.dumps(status).encode())
        elif parsed_path.path == '/raft':
            # Raft-specific status endpoint
            if raft_node:
                raft_status = raft_node.get_status()
                self.wfile.write(json.dumps(raft_status).encode())
            else:
                self.send_response(503)
                self.end_headers()
                self.wfile.write(json.dumps({"error": "Raft not initialized"}).encode())
        elif parsed_path.path == '/stats':
            # Count healthy subscribers (based on heartbeat)
            import time
            current_time = time.time()
            
            healthy_subscribers = 0
            for conn, info in list(subscribers.items()):
                if current_time - info["last_heartbeat"] <= HEARTBEAT_TIMEOUT:
                    healthy_subscribers += 1
            
            # Count unique topics from database
            cur.execute("SELECT DISTINCT topic FROM queue")
            unique_topics = len(cur.fetchall())
                
            stats = {
                "total_messages": broker_stats["total_messages"], 
                "active_subscribers": healthy_subscribers,
                "current_connections": len(subscribers),
                "topics_count": unique_topics
            }
            self.wfile.write(json.dumps(stats).encode())
        elif parsed_path.path == '/messages':
            cur.execute("SELECT topic, format, body, timestamp FROM queue ORDER BY timestamp DESC LIMIT 20")
            messages = [{"topic": r[0], "format": r[1], "content": r[2], "timestamp": r[3]} for r in cur.fetchall()]
            self.wfile.write(json.dumps({"messages": messages}).encode())
        elif parsed_path.path == '/topics':
            # Return list of unique topics from database
            cur.execute("SELECT DISTINCT topic FROM queue ORDER BY topic")
            topics = [row[0] for row in cur.fetchall()]
            self.wfile.write(json.dumps({"topics": topics}).encode())
        elif parsed_path.path == '/subscribers':
            # Return list of active subscribers with their topics
            import time
            current_time = time.time()
            
            active_subscribers = []
            for conn, info in list(subscribers.items()):
                if current_time - info["last_heartbeat"] <= HEARTBEAT_TIMEOUT:
                    subscriber_data = {
                        "id": f"subscriber_{len(active_subscribers) + 1}",
                        "topics": list(info["topics"]),
                        "last_seen": info["last_heartbeat"],
                        "role": info.get("role", "subscriber")
                    }
                    active_subscribers.append(subscriber_data)
            
            self.wfile.write(json.dumps({"subscribers": active_subscribers}).encode())
        else:
            self.wfile.write(json.dumps({"error": "Not found"}).encode())
    
    def do_POST(self):
        if self.path == '/publish':
            try:
                content_length = int(self.headers['Content-Length'])
                post_data = self.rfile.read(content_length)
                message = json.loads(post_data.decode())
                
                topic = message.get("topic", "default")
                content = message.get("content", "")
                fmt = message.get("format", "RAW").upper()
                
                # Validate and format message content
                if fmt == "JSON":
                    try:
                        json.loads(content)  # Test if it's valid JSON
                        body = content
                    except:
                        # Invalid JSON, create valid JSON wrapper
                        import time
                        body = json.dumps({
                            "Id": int(time.time() * 1000),
                            "EventName": "PublisherMessage",
                            "Value": content,
                            "Topic": topic
                        })
                elif fmt == "XML":
                    try:
                        ET.fromstring(content)  # Test if it's valid XML
                        body = content
                    except:
                        # Invalid XML, create valid XML wrapper (same format as Java Publisher)
                        import time
                        body = f"<Message><Id>{int(time.time() * 1000)}</Id><EventName>PublisherMessage</EventName><Value>{escape_xml(content)}</Value><Topic>{escape_xml(topic)}</Topic></Message>"
                else:
                    body = content
                
                # Store message in database
                timestamp = datetime.now().isoformat()
                cur.execute("INSERT INTO queue (topic, format, body, timestamp) VALUES (?, ?, ?, ?)",
                           (topic, fmt, body, timestamp))
                conn_db.commit()
                broker_stats["total_messages"] += 1
                
                # Forward to interested subscribers
                message_sent = False
                import time
                for sub, sub_info in list(subscribers.items()):
                    try:
                        if topic in sub_info["topics"] or "all" in sub_info["topics"]:
                            msg = f"FORMAT:{fmt}|{body}\n"
                            sub.sendall(msg.encode("utf-8"))
                            message_sent = True
                            
                            # Update subscriber activity tracking
                            sub_info["last_heartbeat"] = time.time()
                            sub_info["missed_beats"] = 0
                    except:
                        # Remove broken connections
                        if sub in subscribers:
                            del subscribers[sub]
                        try:
                            sub.close()
                        except:
                            pass
                
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(json.dumps({"success": True, "forwarded": message_sent}).encode())
                
            except Exception as e:
                self.send_response(500)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode())
        else:
            self.send_response(404)
            self.end_headers()

def initialize_database():
    """Initialize SQLite database with proper error handling and retry logic"""
    global db_writer, raft_node
    
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
            # Dynamic cluster discovery - with retry and coordination
            cluster_nodes = []
            
            # Scan common port range for active brokers
            base_port = 5000
            max_nodes = int(os.environ.get('MAX_CLUSTER_SIZE', '10'))  # Default: scan up to 10 nodes
            
            print(f"[Node {BROKER_NODE_ID}] Discovering cluster nodes...")
            
            # Multiple discovery attempts to handle timing issues
            for attempt in range(3):
                cluster_nodes = []
                for node_id in range(max_nodes):
                    port = base_port + node_id
                    try:
                        # Try to connect to potential node
                        test_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                        test_sock.settimeout(0.2)  # Slightly longer timeout
                        result = test_sock.connect_ex(('127.0.0.1', port))
                        test_sock.close()
                        
                        if result == 0:  # Connection successful
                            cluster_nodes.append(("127.0.0.1", port))
                            print(f"  ✅ Found node at 127.0.0.1:{port}")
                    except:
                        pass
                
                # If we found nodes or this is the last attempt, break
                if cluster_nodes or attempt == 2:
                    break
                    
                print(f"  🔄 Discovery attempt {attempt + 1}/3, found {len(cluster_nodes)} nodes, retrying...")
                time.sleep(1)  # Wait before retry
            
            # Always ensure this node is in the cluster list
            this_node = ("127.0.0.1", PORT)
            if this_node not in cluster_nodes:
                cluster_nodes.append(this_node)
                print(f"  ✅ Added self: 127.0.0.1:{PORT}")
            
            # Sort cluster nodes for consistency
            cluster_nodes.sort()
            
            print(f"[Node {BROKER_NODE_ID}] Final cluster configuration: {len(cluster_nodes)} nodes")
            for i, (host, port) in enumerate(cluster_nodes):
                print(f"  Node {i}: {host}:{port}")
            
            node_id = f"127.0.0.1:{PORT}"
            raft_node = RaftNode(node_id, cluster_nodes, db_writer)
            
            print(f"✅ Database writer and Raft node initialized (Node {BROKER_NODE_ID})")
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

# Initialize database and systems
initialize_database()

# Create a read-only connection for queries
conn_db = sqlite3.connect(os.path.join(os.path.dirname(os.path.abspath(__file__)), f"messages_node_{BROKER_NODE_ID}.db"), check_same_thread=False)
cur = conn_db.cursor()

def parse_message_content(format_type, body):
    """Parse message content and extract topic information"""
    topic = "default"
    
    try:
        if format_type.upper() == "JSON":
            data = json.loads(body)
            topic = data.get("Topic", "default")
        elif format_type.upper() == "XML":
            root = ET.fromstring(body)
            topic_elem = root.find("Topic")
            if topic_elem is not None:
                topic = topic_elem.text or "default"
    except:
        # If parsing fails, use default topic
        pass
    
    return topic

def save_message(topic, fmt, body):
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
            print(f"✅ Message saved via Raft consensus: {topic}")
            return True
        else:
            print(f"⚠️  Raft append failed: {message}")
            # Fall back to direct database write if not leader
    
    # Fallback: Direct database write (for single-node or fallback scenarios)
    def on_write_complete(success, result):
        if success:
            broker_stats["total_messages"] += 1
            print(f"✅ Message saved (fallback): {topic}")
        else:
            print(f"❌ Failed to save message: {topic}")
    
    db_writer.write_async(
        "INSERT INTO queue(topic, format, body, timestamp) VALUES (?,?,?,?)", 
        (topic, fmt, body, timestamp),
        on_write_complete
    )
    return True

def validate_message_format(format_type, body):
    """Validate message format and return True if valid"""
    try:
        if format_type.upper() == "JSON":
            json.loads(body)
            return True
        elif format_type.upper() == "XML":
            ET.fromstring(body)
            return True
        else:
            # RAW format is always valid
            return True
    except:
        return False

def handle_publisher(conn):
    print("Publisher connected")
    while True:
        try:
            data = conn.recv(4096)
            if not data: break
            raw = data.decode("utf-8")
            
            # FORMAT:TYPE|BODY
            try:
                fmt, body = raw.split("|", 1)
                fmt = fmt.replace("FORMAT:", "")
            except:
                fmt, body = "RAW", raw
            
            # Validate message format
            if not validate_message_format(fmt, body):
                print(f"Invalid {fmt} format received, treating as RAW")
                fmt, body = "RAW", raw
            
            # Extract topic from message content
            topic = parse_message_content(fmt, body)
            
            # Save to database
            save_message(topic, fmt, body)
            print(f"Received message: Topic='{topic}', Format='{fmt}'")
            
            # Forward to interested subscribers
            message_sent = False
            for sub, sub_info in list(subscribers.items()):
                try:
                    # Check if subscriber is interested in this topic
                    if topic in sub_info["topics"] or "all" in sub_info["topics"]:
                        msg = f"FORMAT:{fmt}|{body}\n"
                        sub.sendall(msg.encode("utf-8"))
                        message_sent = True
                except:
                    # Remove broken connections
                    if sub in subscribers:
                        del subscribers[sub]
                    try:
                        sub.close()
                    except:
                        pass
            
            if message_sent:
                print(f"Message forwarded to {sum(1 for s, info in subscribers.items() if topic in info['topics'] or 'all' in info['topics'])} subscribers")
            else:
                print(f"No subscribers for topic '{topic}'")
                
        except Exception as e:
            print(f"Error handling publisher: {e}")
            break
    
    conn.close()
    print("Publisher disconnected")

def handle_subscriber(conn):
    print("Subscriber connected")
    # Initialize subscriber info with heartbeat tracking
    import time
    subscribers[conn] = {
        "topics": set(), 
        "formats": set(),
        "last_heartbeat": time.time(),
        "missed_beats": 0
    }
    
    try:
        # Handle subscription requests
        while True:
            try:
                data = conn.recv(1024)
                if not data:
                    break
                
                message = data.decode("utf-8").strip()
                print(f"Received from subscriber: '{message}'")  # Debug log
                
                # Update heartbeat on any activity
                subscribers[conn]["last_heartbeat"] = time.time()
                subscribers[conn]["missed_beats"] = 0
                
                if message == "PING":
                    # Respond to heartbeat ping
                    conn.sendall(b"PONG\n")
                    print("Sent PONG response to subscriber")
                elif message.startswith("SUBSCRIBE:"):
                    topic = message.replace("SUBSCRIBE:", "").strip()
                    subscribers[conn]["topics"].add(topic)
                    print(f"Subscriber subscribed to topic: '{topic}'")
                    
                    # Send historical messages for this topic
                    for row in cur.execute("SELECT topic, format, body FROM queue WHERE topic = ? OR ? = 'all'", (topic, topic)):
                        if row[0] == topic or topic == "all":
                            msg = f"FORMAT:{row[1]}|{row[2]}\n"
                            conn.sendall(msg.encode("utf-8"))
                    
                elif message.startswith("UNSUBSCRIBE:"):
                    topic = message.replace("UNSUBSCRIBE:", "").strip()
                    subscribers[conn]["topics"].discard(topic)
                    print(f"Subscriber unsubscribed from topic: '{topic}'")
                else:
                    # If it's not a subscription command, just keep the connection alive
                    # This allows the subscriber to receive messages
                    pass
                
            except socket.timeout:
                continue
            except Exception as e:
                print(f"Error handling subscriber command: {e}")
                break
                
    except Exception as e:
        print(f"Error in subscriber handler: {e}")
    finally:
        # Clean up
        if conn in subscribers:
            del subscribers[conn]
        try:
            conn.close()
        except:
            pass
        print("Subscriber disconnected")

def broker():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((HOST, PORT))
        s.listen()
        print(f"Enhanced Broker running on {HOST}:{PORT}")
        print("Supports: JSON, XML, and RAW message formats")
        print("Features: Topic-based routing, Message persistence, Format validation")
        
        # Start heartbeat cleanup thread
        def cleanup_dead_subscribers():
            """Background thread to clean up subscribers with expired heartbeats"""
            import time
            while True:
                try:
                    current_time = time.time()
                    dead_subscribers = []
                    
                    for conn, info in list(subscribers.items()):
                        if current_time - info["last_heartbeat"] > HEARTBEAT_TIMEOUT:
                            info["missed_beats"] += 1
                            if info["missed_beats"] >= MAX_MISSED_HEARTBEATS:
                                dead_subscribers.append(conn)
                                print(f"Removing subscriber due to heartbeat timeout: {conn.getpeername()}")
                    
                    # Remove dead subscribers
                    for conn in dead_subscribers:
                        if conn in subscribers:
                            del subscribers[conn]
                        try:
                            conn.close()
                        except:
                            pass
                    
                    time.sleep(5)  # Check every 30 seconds
                except Exception as e:
                    print(f"Error in cleanup thread: {e}")
                    time.sleep(5)
        
        def cleanup_dead_nodes():
            """Background thread to clean up dead node files"""
            while True:
                try:
                    # Only run cleanup on the current leader to avoid conflicts
                    if raft_node and raft_node.state.value == "LEADER":
                        # Look for stale PID files in parent directory
                        import glob
                        parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                        pid_pattern = os.path.join(parent_dir, "broker_node_*.pid")
                        
                        for pid_file in glob.glob(pid_pattern):
                            try:
                                with open(pid_file, 'r') as f:
                                    pid = int(f.read().strip())
                                
                                # Check if process exists
                                try:
                                    os.kill(pid, 0)  # Signal 0 checks if process exists
                                except OSError:
                                    # Process doesn't exist, clean up
                                    print(f"[Leader Cleanup] Dead process detected, removing {pid_file}")
                                    os.remove(pid_file)
                                    
                                    # Also remove corresponding log file
                                    log_file = pid_file.replace('.pid', '.log')
                                    if os.path.exists(log_file):
                                        os.remove(log_file)
                                        print(f"[Leader Cleanup] Removed {log_file}")
                                        
                            except (ValueError, FileNotFoundError):
                                # Invalid PID file, remove it
                                try:
                                    os.remove(pid_file)
                                    print(f"[Leader Cleanup] Removed invalid PID file: {pid_file}")
                                except:
                                    pass
                    
                    time.sleep(60)  # Check every minute
                except Exception as e:
                    print(f"Error in dead node cleanup: {e}")
                    time.sleep(60)
        
        # Start cleanup threads
        threading.Thread(target=cleanup_dead_subscribers, daemon=True).start()
        threading.Thread(target=cleanup_dead_nodes, daemon=True).start()
        
        while True:
            try:
                conn, addr = s.accept()
                print(f"New connection from {addr}")
                
                # Set socket timeout for role detection
                conn.settimeout(10.0)
                role = conn.recv(7).decode("utf-8")
                conn.settimeout(None)  # Remove timeout after role detection
                
                if role == "PUBLISH":
                    threading.Thread(target=handle_publisher, args=(conn,), daemon=True).start()
                elif role == "SUBSCRI":
                    threading.Thread(target=handle_subscriber, args=(conn,), daemon=True).start()
                else:
                    print(f"Unknown role: {role}")
                    conn.close()
            except Exception as e:
                print(f"Error accepting connection: {e}")

def start_raft_rpc_server():
    """Start Raft RPC server for inter-node communication"""
    raft_port = PORT + 1000  # Use port+1000 for Raft RPC
    
    def handle_raft_rpc(conn, addr):
        try:
            data = conn.recv(1024).decode().strip()
            if not data:
                return
            
            rpc_request = json.loads(data)
            method = rpc_request.get('method')
            request_data = rpc_request.get('request')
            
            if method == 'vote_request':
                from raft_node import VoteRequest
                vote_request = VoteRequest(**request_data)
                response = raft_node.handle_vote_request(vote_request)
                response_data = response.__dict__
            
            elif method == 'append_entries':
                from raft_node import AppendEntriesRequest
                append_request = AppendEntriesRequest(**request_data)
                response = raft_node.handle_append_entries(append_request)
                response_data = response.__dict__
            
            else:
                response_data = {"error": f"Unknown method: {method}"}
            
            conn.send(json.dumps(response_data).encode() + b'\n')
            
        except Exception as e:
            print(f"Raft RPC error: {e}")
            error_response = {"error": str(e)}
            try:
                conn.send(json.dumps(error_response).encode() + b'\n')
            except:
                pass
        finally:
            conn.close()
    
    def raft_rpc_server():
        raft_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        raft_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        raft_sock.bind(('127.0.0.1', raft_port))
        raft_sock.listen(5)
        print(f"Raft RPC server listening on port {raft_port}")
        
        while True:
            try:
                conn, addr = raft_sock.accept()
                threading.Thread(target=handle_raft_rpc, args=(conn, addr), daemon=True).start()
            except Exception as e:
                print(f"Raft RPC server error: {e}")
                break
    
    # Start Raft RPC server in separate thread
    raft_thread = threading.Thread(target=raft_rpc_server, daemon=True)
    raft_thread.start()
    return raft_thread

if __name__ == "__main__":
    try:
        # Start Raft RPC server
        raft_rpc_thread = start_raft_rpc_server()
        
        # Start HTTP server in a separate thread
        http_server = HTTPServer(('127.0.0.1', HTTP_PORT), BrokerHTTPHandler)
        http_thread = threading.Thread(target=http_server.serve_forever, daemon=True)
        http_thread.start()
        print(f"HTTP API server running on http://127.0.0.1:{HTTP_PORT}")
        
        # Start main TCP broker
        broker()
    except KeyboardInterrupt:
        print("\nBroker shutting down...")
        
        # Cleanup
        if db_writer:
            db_writer.shutdown()
        if raft_node:
            raft_node.shutdown()
        
        conn_db.close()
