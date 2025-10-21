#!/usr/bin/env python3
"""
HTTP-to-gRPC Bridge for Dashboard
Provides REST API endpoints that forward requests to gRPC services
"""

import grpc
import json
import asyncio
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from typing import Optional
import threading
import os

# Import generated gRPC code
import broker_pb2
import broker_pb2_grpc
from google.protobuf.timestamp_pb2 import Timestamp
from google.protobuf.empty_pb2 import Empty

# Configuration
BRIDGE_PORT = int(os.environ.get('BRIDGE_PORT', '8080'))
GRPC_BROKER_HOST = os.environ.get('GRPC_BROKER_HOST', '127.0.0.1')
GRPC_BROKER_PORT = int(os.environ.get('GRPC_BROKER_PORT', '50051'))

class GRPCBridgeHandler(BaseHTTPRequestHandler):
    """HTTP request handler that bridges to gRPC services"""
    
    def __init__(self, *args, **kwargs):
        self.grpc_channel = None
        self.publisher_stub = None
        self.dashboard_stub = None
        super().__init__(*args, **kwargs)
    
    def _get_grpc_stubs(self):
        """Get or create gRPC stubs"""
        if not self.grpc_channel or self.grpc_channel._channel.check_connectivity_state(True) != grpc.ChannelConnectivity.READY:
            if self.grpc_channel:
                self.grpc_channel.close()
            
            grpc_address = f"{GRPC_BROKER_HOST}:{GRPC_BROKER_PORT}"
            self.grpc_channel = grpc.insecure_channel(grpc_address)
            self.publisher_stub = broker_pb2_grpc.PublisherServiceStub(self.grpc_channel)
            self.dashboard_stub = broker_pb2_grpc.DashboardServiceStub(self.grpc_channel)
        
        return self.publisher_stub, self.dashboard_stub
    
    def _set_cors_headers(self):
        """Set CORS headers for browser compatibility"""
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Accept')
        self.send_header('Content-Type', 'application/json')
    
    def _send_json_response(self, data, status_code=200):
        """Send JSON response"""
        response = json.dumps(data, default=str)
        self.send_response(status_code)
        self._set_cors_headers()
        self.end_headers()
        self.wfile.write(response.encode('utf-8'))
    
    def _send_error_response(self, message, status_code=500):
        """Send error response"""
        error_data = {"error": message, "timestamp": datetime.now().isoformat()}
        self._send_json_response(error_data, status_code)
    
    def _timestamp_to_dict(self, timestamp: Timestamp) -> dict:
        """Convert protobuf Timestamp to dict"""
        if not timestamp or not timestamp.seconds:
            return {"seconds": 0, "nanos": 0}
        return {
            "seconds": timestamp.seconds,
            "nanos": timestamp.nanos
        }
    
    def _message_to_dict(self, message: broker_pb2.Message) -> dict:
        """Convert protobuf Message to dict"""
        return {
            "id": message.id,
            "topic": message.topic,
            "format": message.format,  # This will be the enum value (0, 1, 2)
            "content": message.content,
            "timestamp": self._timestamp_to_dict(message.timestamp),
            "eventName": message.event_name
        }
    
    def do_OPTIONS(self):
        """Handle CORS preflight requests"""
        self.send_response(200)
        self._set_cors_headers()
        self.end_headers()
    
    def do_GET(self):
        """Handle GET requests"""
        parsed_path = urlparse(self.path)
        path = parsed_path.path
        query_params = parse_qs(parsed_path.query)
        
        try:
            publisher_stub, dashboard_stub = self._get_grpc_stubs()
            
            if path == '/grpc/status':
                self._handle_get_status(dashboard_stub)
            elif path == '/grpc/stats':
                self._handle_get_stats(dashboard_stub)
            elif path == '/grpc/messages':
                self._handle_get_messages(dashboard_stub, query_params)
            elif path == '/grpc/topics':
                self._handle_get_topics(dashboard_stub)
            elif path == '/grpc/subscribers':
                self._handle_get_subscribers(dashboard_stub)
            elif path == '/health':
                self._send_json_response({"status": "healthy", "service": "grpc-bridge"})
            else:
                self._send_error_response("Endpoint not found", 404)
                
        except grpc.RpcError as e:
            self._send_error_response(f"gRPC error: {e.details()}", 502)
        except Exception as e:
            self._send_error_response(f"Internal error: {str(e)}", 500)
    
    def do_POST(self):
        """Handle POST requests"""
        parsed_path = urlparse(self.path)
        path = parsed_path.path
        
        try:
            # Read request body
            content_length = int(self.headers.get('Content-Length', 0))
            if content_length > 0:
                body = self.rfile.read(content_length)
                request_data = json.loads(body.decode('utf-8'))
            else:
                request_data = {}
            
            publisher_stub, dashboard_stub = self._get_grpc_stubs()
            
            if path == '/grpc/publish':
                self._handle_publish_message(publisher_stub, request_data)
            else:
                self._send_error_response("Endpoint not found", 404)
                
        except json.JSONDecodeError:
            self._send_error_response("Invalid JSON in request body", 400)
        except grpc.RpcError as e:
            self._send_error_response(f"gRPC error: {e.details()}", 502)
        except Exception as e:
            self._send_error_response(f"Internal error: {str(e)}", 500)
    
    def _handle_get_status(self, dashboard_stub):
        """Handle /grpc/status"""
        try:
            status = dashboard_stub.GetBrokerStatus(Empty())
            
            response = {
                "status": status.status,
                "port": status.port,
                "subscribers": status.subscribers,
                "currentConnections": status.current_connections,
                "uptime": self._timestamp_to_dict(status.uptime),
                "raftStatus": {
                    "state": status.raft_status.state,
                    "currentTerm": status.raft_status.current_term,
                    "votedFor": status.raft_status.voted_for,
                    "commitIndex": status.raft_status.commit_index,
                    "lastApplied": status.raft_status.last_applied,
                    "leaderId": status.raft_status.leader_id,
                    "clusterNodes": list(status.raft_status.cluster_nodes),
                    "lastHeartbeat": self._timestamp_to_dict(status.raft_status.last_heartbeat)
                }
            }
            
            self._send_json_response(response)
            
        except grpc.RpcError as e:
            if e.code() == grpc.StatusCode.UNAVAILABLE:
                self._send_json_response({"status": "offline", "error": "Broker unavailable"})
            else:
                raise
    
    def _handle_get_stats(self, dashboard_stub):
        """Handle /grpc/stats"""
        stats = dashboard_stub.GetSystemStats(Empty())
        
        response = {
            "totalMessages": stats.total_messages,
            "activeSubscribers": stats.active_subscribers,
            "currentConnections": stats.current_connections,
            "topicsCount": stats.topics_count,
            "messagesPerMinute": stats.messages_per_minute,
            "startTime": self._timestamp_to_dict(stats.start_time)
        }
        
        self._send_json_response(response)
    
    def _handle_get_messages(self, dashboard_stub, query_params):
        """Handle /grpc/messages"""
        # Parse query parameters
        limit = int(query_params.get('limit', [20])[0])
        offset = int(query_params.get('offset', [0])[0])
        topic_filter = query_params.get('topic_filter', [''])[0]
        format_filter = query_params.get('format_filter', ['RAW'])[0]
        
        # Convert format filter to enum
        format_map = {'RAW': 0, 'JSON': 1, 'XML': 2}
        format_enum = format_map.get(format_filter.upper(), 0)
        
        request = broker_pb2.MessageQueryRequest(
            limit=limit,
            offset=offset,
            topic_filter=topic_filter,
            format_filter=format_enum
        )
        
        result = dashboard_stub.GetRecentMessages(request)
        
        response = {
            "messages": [self._message_to_dict(msg) for msg in result.messages],
            "totalCount": result.total_count,
            "hasMore": result.has_more
        }
        
        self._send_json_response(response)
    
    def _handle_get_topics(self, dashboard_stub):
        """Handle /grpc/topics"""
        topics_response = dashboard_stub.GetTopics(Empty())
        
        response = {
            "topics": list(topics_response.topics)
        }
        
        self._send_json_response(response)
    
    def _handle_get_subscribers(self, dashboard_stub):
        """Handle /grpc/subscribers"""
        subscribers_response = dashboard_stub.GetSubscribers(Empty())
        
        subscribers = []
        for sub in subscribers_response.subscribers:
            subscribers.append({
                "id": sub.id,
                "topics": list(sub.topics),
                "lastSeen": self._timestamp_to_dict(sub.last_seen),
                "role": sub.role,
                "isActive": sub.is_active
            })
        
        response = {
            "subscribers": subscribers
        }
        
        self._send_json_response(response)
    
    def _handle_publish_message(self, publisher_stub, request_data):
        """Handle /grpc/publish"""
        # Validate required fields
        if 'topic' not in request_data or 'content' not in request_data:
            self._send_error_response("Missing required fields: topic, content", 400)
            return
        
        # Create publish request
        request = broker_pb2.PublishRequest(
            topic=request_data['topic'],
            content=request_data['content'],
            format=request_data.get('format', 0),  # Default to RAW (0)
            event_name=request_data.get('eventName', 'HTTPBridge')
        )
        
        # Make gRPC call
        response = publisher_stub.PublishMessage(request)
        
        # Convert response
        result = {
            "success": response.success,
            "message": response.message,
            "forwarded": response.forwarded,
            "subscriberCount": response.subscriber_count
        }
        
        self._send_json_response(result)
    
    def log_message(self, format, *args):
        """Override to provide custom logging"""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        print(f"[{timestamp}] {format % args}")

def run_bridge_server():
    """Run the HTTP-to-gRPC bridge server"""
    server_address = ('', BRIDGE_PORT)
    httpd = HTTPServer(server_address, GRPCBridgeHandler)
    
    print(f" HTTP-to-gRPC Bridge running on port {BRIDGE_PORT}")
    print(f" Forwarding to gRPC broker at {GRPC_BROKER_HOST}:{GRPC_BROKER_PORT}")
    print(" Available endpoints:")
    print("   GET  /grpc/status      - Broker status")
    print("   GET  /grpc/stats       - System statistics")
    print("   GET  /grpc/messages    - Recent messages")
    print("   GET  /grpc/topics      - Available topics")
    print("   GET  /grpc/subscribers - Active subscribers")
    print("   POST /grpc/publish     - Publish message")
    print("   GET  /health           - Bridge health check")
    
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n Shutting down bridge server...")
        httpd.shutdown()

if __name__ == "__main__":
    run_bridge_server()