import socket, threading, sqlite3
import json
import xml.etree.ElementTree as ET
from datetime import datetime

HOST, PORT = "127.0.0.1", 5000
subscribers = {}  # Changed to dict: {connection: {"topics": set(), "formats": set()}}

# DB pentru persistență
conn_db = sqlite3.connect("messages.db", check_same_thread=False)
cur = conn_db.cursor()
cur.execute("CREATE TABLE IF NOT EXISTS queue(id INTEGER PRIMARY KEY AUTOINCREMENT, topic TEXT, format TEXT, body TEXT, timestamp TEXT)")
conn_db.commit()

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
    # Initialize subscriber info
    subscribers[conn] = {"topics": set(), "formats": set()}
    
    try:
        # Handle subscription requests
        while True:
            try:
                data = conn.recv(1024)
                if not data:
                    break
                
                message = data.decode("utf-8").strip()
                print(f"Received from subscriber: '{message}'")  # Debug log
                
                if message.startswith("SUBSCRIBE:"):
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
        broker()
    except KeyboardInterrupt:
        print("\nBroker shutting down...")
        conn_db.close()
