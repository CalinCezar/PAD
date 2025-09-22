import socket, threading, sqlite3
import json
import xml.etree.ElementTree as ET
import os
import time
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

HOST, PORT = "127.0.0.1", 5000
subscribers = {}  # Changed to dict: {connection: {"topics": set(), "formats": set(), "last_heartbeat": timestamp, "missed_beats": int}}

# Heartbeat configuration
HEARTBEAT_TIMEOUT = 90  # seconds
MAX_MISSED_HEARTBEATS = 3

# HTTP API configuration
HTTP_PORT = 8080

# Statistics
broker_stats = {
    "start_time": datetime.now(),
    "total_messages": 0,
}

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
                "current_connections": len(subscribers)
            }
            self.wfile.write(json.dumps(status).encode())
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
    max_retries = 3
    retry_delay = 1  # seconds
    
    # Ensure we're in the correct directory
    broker_dir = os.path.dirname(os.path.abspath(__file__))
    db_path = os.path.join(broker_dir, "messages.db")
    
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
            
            # Connect to database
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
            
            # Test write operation
            cursor.execute("SELECT COUNT(*) FROM queue")
            count = cursor.fetchone()[0]
            print(f"Database initialized successfully. Current message count: {count}")
            
            conn.commit()
            return conn, cursor
            
        except Exception as e:
            print(f"Database initialization attempt {attempt + 1} failed: {e}")
            if attempt < max_retries - 1:
                print(f"Retrying in {retry_delay} seconds...")
                time.sleep(retry_delay)
                retry_delay *= 2  # Exponential backoff
            else:
                print("Failed to initialize database after all retries")
                raise

# Initialize database connection
conn_db, cur = initialize_database()

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
    timestamp = datetime.now().isoformat()
    cur.execute("INSERT INTO queue(topic, format, body, timestamp) VALUES (?,?,?,?)", 
                (topic, fmt, body, timestamp))
    conn_db.commit()
    broker_stats["total_messages"] += 1  # Update stats counter

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
                    
                    time.sleep(30)  # Check every 30 seconds
                except Exception as e:
                    print(f"Error in cleanup thread: {e}")
                    time.sleep(30)
        
        # Start cleanup thread
        threading.Thread(target=cleanup_dead_subscribers, daemon=True).start()
        
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

if __name__ == "__main__":
    try:
        # Start HTTP server in a separate thread
        http_server = HTTPServer(('127.0.0.1', HTTP_PORT), BrokerHTTPHandler)
        http_thread = threading.Thread(target=http_server.serve_forever, daemon=True)
        http_thread.start()
        print(f"HTTP API server running on http://127.0.0.1:{HTTP_PORT}")
        
        # Start main TCP broker
        broker()
    except KeyboardInterrupt:
        print("\nBroker shutting down...")
        conn_db.close()
