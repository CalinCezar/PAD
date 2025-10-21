package com.pad.publisher;

import broker.Broker.*;
import broker.DashboardServiceGrpc;
import broker.PublisherServiceGrpc;
import com.sun.net.httpserver.HttpServer;
import com.sun.net.httpserver.HttpHandler;
import com.sun.net.httpserver.HttpExchange;
import io.grpc.ManagedChannel;
import io.grpc.ManagedChannelBuilder;
import io.grpc.StatusRuntimeException;
import io.grpc.stub.StreamObserver;

import java.io.*;
import java.net.HttpURLConnection;
import java.net.InetSocketAddress;
import java.net.URL;
import java.time.Instant;
import java.util.*;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

class Message {
    private long id;
    private String eventName;
    private String value;
    private String topic;

    public Message() {
        this.id = Instant.now().toEpochMilli();
    }

    public Message(String eventName, String value, String topic) {
        this();
        this.eventName = eventName;
        this.value = value;
        this.topic = topic;
    }

    // Getters and setters
    public long getId() { return id; }
    public void setId(long id) { this.id = id; }

    public String getEventName() { return eventName; }
    public void setEventName(String eventName) { this.eventName = eventName; }

    public String getValue() { return value; }
    public void setValue(String value) { this.value = value; }

    public String getTopic() { return topic; }
    public void setTopic(String topic) { this.topic = topic; }

    // Simple JSON serialization (without external library)
    public String toJson() {
        return String.format(
            "{\"Id\":%d,\"EventName\":\"%s\",\"Value\":\"%s\",\"Topic\":\"%s\"}",
            id,
            escapeJson(eventName),
            escapeJson(value),
            escapeJson(topic)
        );
    }

    // Simple XML serialization (without external library)
    public String toXml() {
        return String.format(
            "<Message><Id>%d</Id><EventName>%s</EventName><Value>%s</Value><Topic>%s</Topic></Message>",
            id,
            escapeXml(eventName),
            escapeXml(value),
            escapeXml(topic)
        );
    }

    private String escapeJson(String text) {
        if (text == null) return "";
        return text.replace("\\", "\\\\")
                  .replace("\"", "\\\"")
                  .replace("\n", "\\n")
                  .replace("\r", "\\r")
                  .replace("\t", "\\t");
    }

    private String escapeXml(String text) {
        if (text == null) return "";
        return text.replace("&", "&amp;")
                  .replace("<", "&lt;")
                  .replace(">", "&gt;")
                  .replace("\"", "&quot;")
                  .replace("'", "&apos;");
    }
}

class ClusterNode {
    private String host;
    private int grpcPort;
    private int httpPort;
    private String name;
    private boolean isLeader;
    private boolean isAvailable;
    
    public ClusterNode(String host, int grpcPort, int httpPort, String name) {
        this.host = host;
        this.grpcPort = grpcPort;
        this.httpPort = httpPort;
        this.name = name;
        this.isLeader = false;
        this.isAvailable = true;
    }
    
    // Getters
    public String getHost() { return host; }
    public int getGrpcPort() { return grpcPort; }
    public int getHttpPort() { return httpPort; }
    public String getName() { return name; }
    public boolean isLeader() { return isLeader; }
    public boolean isAvailable() { return isAvailable; }
    
    // Setters
    public void setLeader(boolean leader) { this.isLeader = leader; }
    public void setAvailable(boolean available) { this.isAvailable = available; }
    
    public String getGrpcAddress() {
        return host + ":" + grpcPort;
    }
    
    public String getHttpUrl() {
        return "http://" + host + ":" + httpPort;
    }
    
    @Override
    public String toString() {
        return name + " (gRPC:" + getGrpcAddress() + ")" + 
               (isLeader ? " [LEADER]" : "") + 
               (isAvailable ? " [ONLINE]" : " [OFFLINE]");
    }
}

public class Publisher {
    private String host;
    private int port;
    private int webPort;
    private ManagedChannel channel;
    private PublisherServiceGrpc.PublisherServiceBlockingStub publisherStub;
    private DashboardServiceGrpc.DashboardServiceBlockingStub dashboardStub;
    
    private static List<String> publishHistory = Collections.synchronizedList(new ArrayList<>());
    private static boolean isConnected = false;
    
    // Cluster support
    private List<ClusterNode> clusterNodes;
    private ClusterNode currentNode;
    private boolean clusterMode;
    
    // Resilience configuration
    private static final int MAX_RETRY_ATTEMPTS = 5;
    private static final int INITIAL_RETRY_DELAY = 1000; // 1 second
    private static final int MAX_RETRY_DELAY = 30000; // 30 seconds
    private static final int CONNECTION_TIMEOUT = 30000; // 30 seconds

    // Add missing addToHistory method
    private static void addToHistory(String message) {
        publishHistory.add(message);
    }

    // Single-node constructor
    public Publisher(String host, int port, int webPort) {
        this.host = host;
        this.port = port;
        this.webPort = webPort;
        this.clusterMode = false;
        this.clusterNodes = new ArrayList<>();
    }

    // Add constructor without webPort for backward compatibility
    public Publisher(String host, int port) {
        this(host, port, 8080); // default webPort
    }
    
    // Cluster constructor
    public Publisher() {
        this.clusterMode = true;
        this.clusterNodes = new ArrayList<>();
        initializeCluster();
        this.webPort = 8080; // Default web port for single node fallback
    }
    
    private void initializeCluster() {
        // Add cluster nodes (gRPC ports: 50051, 50052, 50053)
        clusterNodes.add(new ClusterNode("127.0.0.1", 50051, 8080, "Node 0"));
        clusterNodes.add(new ClusterNode("127.0.0.1", 50052, 8081, "Node 1"));
        clusterNodes.add(new ClusterNode("127.0.0.1", 50053, 8082, "Node 2"));
        
        System.out.println("gRPC Cluster mode enabled with " + clusterNodes.size() + " nodes");
        updateClusterStatus();
    }
    
    private void updateClusterStatus() {
        System.out.println("Checking gRPC cluster status...");
        
        for (ClusterNode node : clusterNodes) {
            try {
                // Try to connect to gRPC service and check RAFT status
                ManagedChannel testChannel = ManagedChannelBuilder.forTarget(node.getGrpcAddress())
                        .usePlaintext()
                        .build();
                
                try {
                    DashboardServiceGrpc.DashboardServiceBlockingStub testStub = 
                        DashboardServiceGrpc.newBlockingStub(testChannel)
                            .withDeadlineAfter(2, TimeUnit.SECONDS);
                    
                    BrokerStatus status = testStub.getBrokerStatus(com.google.protobuf.Empty.getDefaultInstance());
                    
                    node.setAvailable(true);
                    boolean isLeader = status.getRaftStatus().getState() == NodeState.LEADER;
                    node.setLeader(isLeader);
                    
                    if (isLeader) {
                        System.out.println("Found gRPC leader: " + node.toString());
                    } else {
                        System.out.println("Available gRPC node: " + node.toString());
                    }
                } finally {
                    testChannel.shutdown();
                    try {
                        testChannel.awaitTermination(1, TimeUnit.SECONDS);
                    } catch (InterruptedException e) {
                        Thread.currentThread().interrupt();
                    }
                }
                
            } catch (Exception e) {
                node.setAvailable(false);
                node.setLeader(false);
                System.out.println("Unreachable gRPC node: " + node.toString() + " (" + e.getMessage() + ")");
            }
        }
    }

    private List<String> getTopicsFromBroker() {
        List<String> topics = new ArrayList<>();
        
        try {
            if (dashboardStub != null) {
                TopicsResponse response = dashboardStub
                        .withDeadlineAfter(5, TimeUnit.SECONDS)
                        .getTopics(com.google.protobuf.Empty.getDefaultInstance());                topics.addAll(response.getTopicsList());
                System.out.println("📚 Loaded topics from gRPC broker: " + topics);
            }
        } catch (StatusRuntimeException e) {
            System.err.println("Error accessing gRPC broker: " + e.getStatus());
            return getDefaultTopics();
        } catch (Exception e) {
            System.err.println("Error accessing gRPC broker: " + e.getMessage());
            return getDefaultTopics();
        }

        return topics.isEmpty() ? getDefaultTopics() : topics;
    }

    private List<String> getDefaultTopics() {
        return Arrays.asList("news", "alerts", "sports", "weather", "tech", "finance");
    }

    private ClusterNode findBestNode() {
        // Update cluster status first
        updateClusterStatus();
        
        // Prefer leader nodes
        for (ClusterNode node : clusterNodes) {
            if (node.isAvailable() && node.isLeader()) {
                System.out.println("Selecting gRPC leader node: " + node);
                return node;
            }
        }
        
        // Fallback to any available node
        for (ClusterNode node : clusterNodes) {
            if (node.isAvailable()) {
                System.out.println("[INFO] Selecting available gRPC node: " + node);
                return node;
            }
        }
        
        System.out.println("No available gRPC nodes found, trying first node as fallback");
        return clusterNodes.isEmpty() ? null : clusterNodes.get(0);
    }

    public boolean connect() {
        return connectWithRetry(MAX_RETRY_ATTEMPTS);
    }

    private boolean connectWithRetry(int maxAttempts) {
        int attempt = 0;
        int delay = INITIAL_RETRY_DELAY;
        
        while (attempt < maxAttempts) {
            try {
                String connectHost;
                int connectPort;
                
                if (clusterMode) {
                    ClusterNode targetNode = findBestNode();
                    if (targetNode == null) {
                        System.err.println("No available nodes in cluster");
                        return false;
                    }
                    
                    currentNode = targetNode;
                    connectHost = targetNode.getHost();
                    connectPort = targetNode.getGrpcPort();
                } else {
                    connectHost = this.host;
                    connectPort = this.port;
                }
                
                // Create gRPC channel
                if (channel != null) {
                    channel.shutdown();
                }
                
                String target = connectHost + ":" + connectPort;
                System.out.println("Connecting to gRPC broker at " + target + "...");
                
                channel = ManagedChannelBuilder.forTarget(target)
                        .usePlaintext()
                        .keepAliveTime(60, TimeUnit.SECONDS)
                        .keepAliveTimeout(10, TimeUnit.SECONDS)
                        .keepAliveWithoutCalls(false)
                        .maxInboundMessageSize(4 * 1024 * 1024) // 4MB
                        .build();
                
                // Create stubs without deadlines (we'll add them per-call)
                publisherStub = PublisherServiceGrpc.newBlockingStub(channel);
                dashboardStub = DashboardServiceGrpc.newBlockingStub(channel);
                
                // Test connection with health check
                HealthResponse health = publisherStub
                        .withDeadlineAfter(5, TimeUnit.SECONDS)
                        .getPublisherHealth(com.google.protobuf.Empty.getDefaultInstance());
                
                if (health.getHealthy()) {
                    isConnected = true;
                    System.out.println("Successfully connected to gRPC broker!");
                    
                    if (clusterMode) {
                        System.out.println("Connected to cluster node: " + currentNode);
                    }
                    
                    return true;
                } else {
                    throw new RuntimeException("Broker not healthy: " + health.getStatus());
                }
                
            } catch (Exception e) {
                attempt++;
                System.err.println("Connection attempt " + attempt + " failed: " + e.getMessage());
                
                if (attempt >= maxAttempts) {
                    System.err.println("💥 Failed to connect after " + maxAttempts + " attempts");
                    return false;
                }
                
                System.out.println("Retrying in " + delay + "ms...");
                try {
                    Thread.sleep(delay);
                } catch (InterruptedException ie) {
                    Thread.currentThread().interrupt();
                    return false;
                }
                
                delay = Math.min(delay * 2, MAX_RETRY_DELAY);
            }
        }
        
        return false;
    }

    public boolean isConnected() {
        return isConnected && channel != null && !channel.isShutdown();
    }

    public void disconnect() {
        isConnected = false;
        if (channel != null) {
            try {
                channel.shutdown();
                if (!channel.awaitTermination(5, TimeUnit.SECONDS)) {
                    channel.shutdownNow();
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                channel.shutdownNow();
            }
        }
        System.out.println("Disconnected from gRPC broker");
    }

    public boolean publishMessage(String topic, String content, MessageFormat format, String eventName) {
        if (!isConnected()) {
            System.err.println("Not connected to broker");
            return false;
        }
        
        try {
            PublishRequest request = PublishRequest.newBuilder()
                    .setTopic(topic)
                    .setContent(content)
                    .setFormat(format)
                    .setEventName(eventName != null ? eventName : "PublisherMessage")
                    .build();
            
            PublishResponse response = publisherStub
                    .withDeadlineAfter(10, TimeUnit.SECONDS)
                    .publishMessage(request);
            
            if (response.getSuccess()) {
                String historyEntry = String.format("[%s] Topic: %s, Format: %s, Forwarded to %d subscribers", 
                    java.time.LocalDateTime.now().toString(), topic, format.name(), response.getSubscriberCount());
                addToHistory(historyEntry);
                
                System.out.println("Message published successfully!");
                System.out.println("   Topic: " + topic);
                System.out.println("   Format: " + format.name());
                System.out.println("   Forwarded to: " + response.getSubscriberCount() + " subscribers");
                
                return true;
            } else {
                System.err.println("Failed to publish message: " + response.getMessage());
                return false;
            }
            
        } catch (StatusRuntimeException e) {
            System.err.println("gRPC error publishing message: " + e.getStatus());
            
            // Try reconnection on communication error
            if (clusterMode) {
                System.out.println("[INFO] Attempting to reconnect to cluster...");
                isConnected = false;
                return connect() && publishMessage(topic, content, format, eventName);
            }
            
            return false;
        } catch (Exception e) {
            System.err.println("Error publishing message: " + e.getMessage());
            return false;
        }
    }

    public boolean publishMessage(String topic, String content, String format) {
        MessageFormat messageFormat;
        try {
            messageFormat = MessageFormat.valueOf(format.toUpperCase());
        } catch (IllegalArgumentException e) {
            messageFormat = MessageFormat.RAW;
        }
        
        return publishMessage(topic, content, messageFormat, null);
    }

    public boolean publishMessage(String topic, String content, String format, String eventName) {
        MessageFormat messageFormat;
        try {
            messageFormat = MessageFormat.valueOf(format.toUpperCase());
        } catch (IllegalArgumentException e) {
            messageFormat = MessageFormat.RAW;
        }
        
        return publishMessage(topic, content, messageFormat, eventName);
    }

    public void startWebInterface() {
        try {
            HttpServer server = HttpServer.create(new InetSocketAddress(webPort), 0);
            server.createContext("/", new WebInterfaceHandler());
            server.createContext("/publish", new PublishHandler());
            server.createContext("/status", new StatusHandler());
            server.createContext("/history", new HistoryHandler());
            server.createContext("/topics", new TopicsHandler());
            server.setExecutor(Executors.newFixedThreadPool(4));
            server.start();
            
            System.out.println("Web interface started at http://localhost:" + webPort);
            System.out.println("   Publisher API: http://localhost:" + webPort + "/publish");
            System.out.println("   Status: http://localhost:" + webPort + "/status");
            System.out.println("   History: http://localhost:" + webPort + "/history");
            System.out.println("   Topics: http://localhost:" + webPort + "/topics");
            
        } catch (IOException e) {
            System.err.println("Failed to start web interface: " + e.getMessage());
        }
    }

    // HTTP handlers for web interface
    class WebInterfaceHandler implements HttpHandler {
        public void handle(HttpExchange exchange) throws IOException {
            String response = generateWebInterface();
            exchange.getResponseHeaders().set("Content-Type", "text/html; charset=UTF-8");
            exchange.getResponseHeaders().set("Access-Control-Allow-Origin", "*");
            exchange.sendResponseHeaders(200, response.getBytes().length);
            OutputStream os = exchange.getResponseBody();
            os.write(response.getBytes());
            os.close();
        }
    }

    class PublishHandler implements HttpHandler {
        public void handle(HttpExchange exchange) throws IOException {
            if ("POST".equals(exchange.getRequestMethod())) {
                // Handle CORS preflight
                exchange.getResponseHeaders().set("Access-Control-Allow-Origin", "*");
                exchange.getResponseHeaders().set("Access-Control-Allow-Methods", "POST, GET, OPTIONS");
                exchange.getResponseHeaders().set("Access-Control-Allow-Headers", "Content-Type");
                
                // Read request body
                InputStream is = exchange.getRequestBody();
                String body = new Scanner(is, "UTF-8").useDelimiter("\\A").next();
                
                // Parse simple form data (topic=...&content=...&format=...)
                Map<String, String> params = parseFormData(body);
                String topic = params.getOrDefault("topic", "default");
                String content = params.getOrDefault("content", "");
                String format = params.getOrDefault("format", "RAW");
                String eventName = params.getOrDefault("eventName", "WebPublisher");
                
                boolean success = publishMessage(topic, content, format, eventName);
                
                String response = "{\"success\": " + success + ", \"message\": \"" + 
                    (success ? "Message published" : "Failed to publish") + "\"}";
                
                exchange.getResponseHeaders().set("Content-Type", "application/json");
                exchange.sendResponseHeaders(200, response.getBytes().length);
                OutputStream os = exchange.getResponseBody();
                os.write(response.getBytes());
                os.close();
            } else if ("OPTIONS".equals(exchange.getRequestMethod())) {
                // Handle CORS preflight
                exchange.getResponseHeaders().set("Access-Control-Allow-Origin", "*");
                exchange.getResponseHeaders().set("Access-Control-Allow-Methods", "POST, GET, OPTIONS");
                exchange.getResponseHeaders().set("Access-Control-Allow-Headers", "Content-Type");
                exchange.sendResponseHeaders(200, 0);
                exchange.getResponseBody().close();
            }
        }
    }

    class StatusHandler implements HttpHandler {
        public void handle(HttpExchange exchange) throws IOException {
            String status = "{\"connected\": " + isConnected() + 
                          ", \"cluster_mode\": " + clusterMode;
            
            if (currentNode != null) {
                status += ", \"current_node\": \"" + currentNode.toString() + "\"";
            }
            
            status += "}";
            
            exchange.getResponseHeaders().set("Content-Type", "application/json");
            exchange.getResponseHeaders().set("Access-Control-Allow-Origin", "*");
            exchange.sendResponseHeaders(200, status.getBytes().length);
            OutputStream os = exchange.getResponseBody();
            os.write(status.getBytes());
            os.close();
        }
    }

    class HistoryHandler implements HttpHandler {
        public void handle(HttpExchange exchange) throws IOException {
            StringBuilder json = new StringBuilder("[");
            for (int i = 0; i < publishHistory.size(); i++) {
                if (i > 0) json.append(",");
                json.append("\"").append(publishHistory.get(i).replace("\"", "\\\"")).append("\"");
            }
            json.append("]");
            
            exchange.getResponseHeaders().set("Content-Type", "application/json");
            exchange.getResponseHeaders().set("Access-Control-Allow-Origin", "*");
            exchange.sendResponseHeaders(200, json.toString().getBytes().length);
            OutputStream os = exchange.getResponseBody();
            os.write(json.toString().getBytes());
            os.close();
        }
    }

    class TopicsHandler implements HttpHandler {
        public void handle(HttpExchange exchange) throws IOException {
            List<String> topics = getTopicsFromBroker();
            
            StringBuilder json = new StringBuilder("{\"topics\": [");
            for (int i = 0; i < topics.size(); i++) {
                if (i > 0) json.append(",");
                json.append("\"").append(topics.get(i)).append("\"");
            }
            json.append("]}");
            
            exchange.getResponseHeaders().set("Content-Type", "application/json");
            exchange.getResponseHeaders().set("Access-Control-Allow-Origin", "*");
            exchange.sendResponseHeaders(200, json.toString().getBytes().length);
            OutputStream os = exchange.getResponseBody();
            os.write(json.toString().getBytes());
            os.close();
        }
    }

    private Map<String, String> parseFormData(String body) {
        Map<String, String> params = new HashMap<>();
        String[] pairs = body.split("&");
        for (String pair : pairs) {
            String[] keyValue = pair.split("=", 2);
            if (keyValue.length == 2) {
                try {
                    String key = java.net.URLDecoder.decode(keyValue[0], "UTF-8");
                    String value = java.net.URLDecoder.decode(keyValue[1], "UTF-8");
                    params.put(key, value);
                } catch (Exception e) {
                    // Ignore malformed pairs
                }
            }
        }
        return params;
    }

    private String generateWebInterface() {
        List<String> availableTopics = getTopicsFromBroker();
        
        StringBuilder topicOptions = new StringBuilder();
        for (String topic : availableTopics) {
            topicOptions.append("<option value=\"").append(topic).append("\">").append(topic).append("</option>");
        }
        
        return "<!DOCTYPE html>\n" +
                "<html>\n" +
                "<head>\n" +
                "    <title>gRPC Message Publisher</title>\n" +
                "    <style>\n" +
                "        body { font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }\n" +
                "        .container { max-width: 800px; margin: 0 auto; background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }\n" +
                "        .form-group { margin-bottom: 15px; }\n" +
                "        label { display: block; margin-bottom: 5px; font-weight: bold; }\n" +
                "        input, select, textarea { width: 100%; padding: 8px; border: 1px solid #ddd; border-radius: 4px; box-sizing: border-box; }\n" +
                "        button { background: #007bff; color: white; padding: 10px 20px; border: none; border-radius: 4px; cursor: pointer; }\n" +
                "        button:hover { background: #0056b3; }\n" +
                "        .status { padding: 10px; margin: 10px 0; border-radius: 4px; }\n" +
                "        .success { background: #d4edda; color: #155724; border: 1px solid #c3e6cb; }\n" +
                "        .error { background: #f8d7da; color: #721c24; border: 1px solid #f5c6cb; }\n" +
                "        .history { margin-top: 20px; }\n" +
                "        .history-item { padding: 8px; margin: 4px 0; background: #f8f9fa; border-left: 4px solid #007bff; }\n" +
                "        .info { background: #d1ecf1; color: #0c5460; border: 1px solid #bee5eb; }\n" +
                "    </style>\n" +
                "</head>\n" +
                "<body>\n" +
                "    <div class=\"container\">\n" +
                "        <h1>gRPC Message Publisher</h1>\n" +
                "        \n" +
                "        <div id=\"connection-status\" class=\"status info\">\n" +
                "            <strong>Status:</strong> <span id=\"status-text\">Checking connection...</span>\n" +
                "        </div>\n" +
                "        \n" +
                "        <form id=\"publish-form\">\n" +
                "            <div class=\"form-group\">\n" +
                "                <label for=\"topic\">Topic:</label>\n" +
                "                <select id=\"topic\" name=\"topic\">\n" +
                "                    <option value=\"\">-- Select Topic --</option>\n" +
                "                    " + topicOptions + "\n" +
                "                </select>\n" +
                "            </div>\n" +
                "            \n" +
                "            <div class=\"form-group\">\n" +
                "                <label for=\"content\">Message Content:</label>\n" +
                "                <textarea id=\"content\" name=\"content\" rows=\"4\" placeholder=\"Enter your message content...\"></textarea>\n" +
                "            </div>\n" +
                "            \n" +
                "            <div class=\"form-group\">\n" +
                "                <label for=\"format\">Message Format:</label>\n" +
                "                <select id=\"format\" name=\"format\">\n" +
                "                    <option value=\"RAW\">RAW</option>\n" +
                "                    <option value=\"JSON\">JSON</option>\n" +
                "                    <option value=\"XML\">XML</option>\n" +
                "                </select>\n" +
                "            </div>\n" +
                "            \n" +
                "            <div class=\"form-group\">\n" +
                "                <label for=\"eventName\">Event Name:</label>\n" +
                "                <input type=\"text\" id=\"eventName\" name=\"eventName\" value=\"WebPublisher\" placeholder=\"Event name...\">\n" +
                "            </div>\n" +
                "            \n" +
                "            <button type=\"submit\">📤 Publish Message</button>\n" +
                "        </form>\n" +
                "        \n" +
                "        <div id=\"result\" style=\"margin-top: 20px;\"></div>\n" +
                "        \n" +
                "        <div class=\"history\">\n" +
                "            <h3>📜 Publishing History</h3>\n" +
                "            <div id=\"history-list\">Loading history...</div>\n" +
                "        </div>\n" +
                "    </div>\n" +
                "    \n" +
                "    <script>\n" +
                "        // Check connection status\n" +
                "        function updateStatus() {\n" +
                "            fetch('/status')\n" +
                "                .then(response => response.json())\n" +
                "                .then(data => {\n" +
                "                    const statusElement = document.getElementById('status-text');\n" +
                "                    const statusContainer = document.getElementById('connection-status');\n" +
                "                    \n" +
                "                    if (data.connected) {\n" +
                "                        statusElement.textContent = 'Connected to gRPC broker' + \n" +
                "                            (data.cluster_mode ? ' (Cluster: ' + (data.current_node || 'Unknown') + ')' : '');\n" +
                "                        statusContainer.className = 'status success';\n" +
                "                    } else {\n" +
                "                        statusElement.textContent = 'Not connected to broker';\n" +
                "                        statusContainer.className = 'status error';\n" +
                "                    }\n" +
                "                })\n" +
                "                .catch(err => {\n" +
                "                    document.getElementById('status-text').textContent = 'Connection check failed';\n" +
                "                    document.getElementById('connection-status').className = 'status error';\n" +
                "                });\n" +
                "        }\n" +
                "        \n" +
                "        // Load publishing history\n" +
                "        function loadHistory() {\n" +
                "            fetch('/history')\n" +
                "                .then(response => response.json())\n" +
                "                .then(data => {\n" +
                "                    const historyList = document.getElementById('history-list');\n" +
                "                    if (data.length === 0) {\n" +
                "                        historyList.innerHTML = '<p>No messages published yet.</p>';\n" +
                "                    } else {\n" +
                "                        historyList.innerHTML = data.reverse().slice(-10).map(item => \n" +
                "                            '<div class=\"history-item\">' + item + '</div>'\n" +
                "                        ).join('');\n" +
                "                    }\n" +
                "                })\n" +
                "                .catch(err => {\n" +
                "                    document.getElementById('history-list').innerHTML = '<p>Failed to load history.</p>';\n" +
                "                });\n" +
                "        }\n" +
                "        \n" +
                "        // Handle form submission\n" +
                "        document.getElementById('publish-form').addEventListener('submit', function(e) {\n" +
                "            e.preventDefault();\n" +
                "            \n" +
                "            const formData = new FormData(this);\n" +
                "            const data = new URLSearchParams();\n" +
                "            for (let [key, value] of formData) {\n" +
                "                data.append(key, value);\n" +
                "            }\n" +
                "            \n" +
                "            fetch('/publish', {\n" +
                "                method: 'POST',\n" +
                "                headers: {\n" +
                "                    'Content-Type': 'application/x-www-form-urlencoded',\n" +
                "                },\n" +
                "                body: data\n" +
                "            })\n" +
                "            .then(response => response.json())\n" +
                "            .then(result => {\n" +
                "                const resultDiv = document.getElementById('result');\n" +
                "                if (result.success) {\n" +
                "                    resultDiv.innerHTML = '<div class=\"status success\">Message published successfully!</div>';\n" +
                "                    this.reset();\n" +
                "                    loadHistory(); // Refresh history\n" +
                "                } else {\n" +
                "                    resultDiv.innerHTML = '<div class=\"status error\">Failed to publish message: ' + result.message + '</div>';\n" +
                "                }\n" +
                "            })\n" +
                "            .catch(error => {\n" +
                "                document.getElementById('result').innerHTML = '<div class=\"status error\">Network error: ' + error.message + '</div>';\n" +
                "            });\n" +
                "        });\n" +
                "        \n" +
                "        // Initialize\n" +
                "        updateStatus();\n" +
                "        loadHistory();\n" +
                "        setInterval(updateStatus, 10000); // Update status every 10 seconds\n" +
                "        setInterval(loadHistory, 15000);  // Update history every 15 seconds\n" +
                "    </script>\n" +
                "</body>\n" +
                "</html>";
    }

    public static void main(String[] args) {
        System.out.println("Starting gRPC Message Publisher...");
        
        Publisher publisher;
        
        // Check for cluster mode argument
        boolean clusterMode = args.length > 0 && "cluster".equalsIgnoreCase(args[0]);
        
        if (clusterMode) {
            publisher = new Publisher(); // Cluster mode constructor
        } else {
            // Single node mode
            String host = args.length > 1 ? args[1] : "127.0.0.1";
            int port = args.length > 2 ? Integer.parseInt(args[2]) : 50051;
            int webPort = args.length > 3 ? Integer.parseInt(args[3]) : 8080;
            
            publisher = new Publisher(host, port, webPort);
            System.out.println("Single node mode: " + host + ":" + port);
        }
        
        // Connect to broker
        if (!publisher.connect()) {
            System.err.println("💥 Failed to connect to broker. Exiting.");
            System.exit(1);
        }
        
        // Start web interface
        publisher.startWebInterface();
        
        // Interactive console
        Scanner scanner = new Scanner(System.in);
        System.out.println("\nInteractive gRPC Publisher Console");
        System.out.println("Commands: publish, topics, status, history, help, quit");
        
        while (true) {
            System.out.print("\n> ");
            String input = scanner.nextLine().trim();
            
            if (input.isEmpty()) continue;
            
            String[] parts = input.split("\\s+", 2);
            String command = parts[0].toLowerCase();
            
            switch (command) {
                case "publish":
                    handlePublishCommand(publisher, scanner);
                    break;
                    
                case "topics":
                    List<String> topics = publisher.getTopicsFromBroker();
                    System.out.println("📚 Available topics: " + topics);
                    break;
                    
                case "status":
                    if (publisher.isConnected()) {
                        System.out.println("Connected to gRPC broker");
                        if (publisher.clusterMode && publisher.currentNode != null) {
                            System.out.println("Current node: " + publisher.currentNode);
                        }
                    } else {
                        System.out.println("Not connected to broker");
                    }
                    break;
                    
                case "history":
                    System.out.println("📜 Publishing History:");
                    List<String> history = new ArrayList<>(publishHistory);
                    if (history.isEmpty()) {
                        System.out.println("  No messages published yet.");
                    } else {
                        for (int i = Math.max(0, history.size() - 10); i < history.size(); i++) {
                            System.out.println("  " + history.get(i));
                        }
                    }
                    break;
                    
                case "help":
                    System.out.println("📖 Available commands:");
                    System.out.println("  publish    - Publish a message");
                    System.out.println("  topics     - List available topics");
                    System.out.println("  status     - Check connection status");
                    System.out.println("  history    - Show publishing history");
                    System.out.println("  help       - Show this help");
                    System.out.println("  quit       - Exit the publisher");
                    break;
                    
                case "quit":
                case "exit":
                    System.out.println("👋 Shutting down gRPC publisher...");
                    publisher.disconnect();
                    scanner.close();
                    System.exit(0);
                    break;
                    
                default:
                    System.out.println("❓ Unknown command. Type 'help' for available commands.");
            }
        }
    }
    
    private static void handlePublishCommand(Publisher publisher, Scanner scanner) {
        try {
            System.out.print("Enter topic: ");
            String topic = scanner.nextLine().trim();
            if (topic.isEmpty()) {
                System.out.println("Topic cannot be empty");
                return;
            }
            
            System.out.print("Enter message content: ");
            String content = scanner.nextLine().trim();
            if (content.isEmpty()) {
                System.out.println("Content cannot be empty");
                return;
            }
            
            System.out.print("Enter format (RAW/JSON/XML) [RAW]: ");
            String format = scanner.nextLine().trim();
            if (format.isEmpty()) {
                format = "RAW";
            }
            
            System.out.print("Enter event name (optional) [PublisherMessage]: ");
            String eventName = scanner.nextLine().trim();
            if (eventName.isEmpty()) {
                eventName = "PublisherMessage";
            }
            
            boolean success = publisher.publishMessage(topic, content, format, eventName);
            if (!success) {
                System.out.println("Failed to publish message");
            }
            
        } catch (Exception e) {
            System.err.println("Error during publish: " + e.getMessage());
        }
    }
}