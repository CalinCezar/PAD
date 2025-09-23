package com.pad.publisher;

import java.io.*;
import java.net.Socket;
import java.time.Instant;
import java.util.Random;
import java.util.Scanner;
import java.util.concurrent.TimeUnit;
import com.sun.net.httpserver.HttpServer;
import com.sun.net.httpserver.HttpHandler;
import com.sun.net.httpserver.HttpExchange;
import java.net.InetSocketAddress;
import java.util.concurrent.Executors;
import java.util.List;
import java.util.ArrayList;
import java.util.Collections;
import java.net.HttpURLConnection;
import java.net.URL;

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
    private int tcpPort;
    private int httpPort;
    private String name;
    private boolean isLeader;
    private boolean isAvailable;
    
    public ClusterNode(String host, int tcpPort, int httpPort, String name) {
        this.host = host;
        this.tcpPort = tcpPort;
        this.httpPort = httpPort;
        this.name = name;
        this.isLeader = false;
        this.isAvailable = true;
    }
    
    // Getters
    public String getHost() { return host; }
    public int getTcpPort() { return tcpPort; }
    public int getHttpPort() { return httpPort; }
    public String getName() { return name; }
    public boolean isLeader() { return isLeader; }
    public boolean isAvailable() { return isAvailable; }
    
    // Setters
    public void setLeader(boolean leader) { this.isLeader = leader; }
    public void setAvailable(boolean available) { this.isAvailable = available; }
    
    public String getHttpUrl() {
        return "http://" + host + ":" + httpPort;
    }
    
    public String getConnectionString() {
        return host + ":" + tcpPort;
    }
    
    @Override
    public String toString() {
        return name + " (" + getConnectionString() + ")" + 
               (isLeader ? " [LEADER]" : "") + 
               (isAvailable ? " [ONLINE]" : " [OFFLINE]");
    }
}

public class Publisher {
    private String host;
    private int port;
    private int webPort;
    private Socket socket;
    private PrintWriter out;
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
    private static final int CONNECTION_TIMEOUT = 5000; // 5 seconds

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
        // Add cluster nodes (matches the cluster configuration)
        clusterNodes.add(new ClusterNode("127.0.0.1", 5000, 8080, "Node 0"));
        clusterNodes.add(new ClusterNode("127.0.0.1", 5001, 8081, "Node 1"));
        clusterNodes.add(new ClusterNode("127.0.0.1", 5002, 8082, "Node 2"));
        
        System.out.println("🌐 Cluster mode enabled with " + clusterNodes.size() + " nodes");
        updateClusterStatus();
    }
    
    private void updateClusterStatus() {
        System.out.println("🔍 Checking cluster status...");
        
        for (ClusterNode node : clusterNodes) {
            try {
                // Check if node is available via HTTP status
                URL url = new URL(node.getHttpUrl() + "/raft");
                HttpURLConnection conn = (HttpURLConnection) url.openConnection();
                conn.setConnectTimeout(2000);
                conn.setReadTimeout(2000);
                
                if (conn.getResponseCode() == 200) {
                    // Read response to check if it's a leader
                    BufferedReader reader = new BufferedReader(new InputStreamReader(conn.getInputStream()));
                    String line;
                    StringBuilder response = new StringBuilder();
                    while ((line = reader.readLine()) != null) {
                        response.append(line);
                    }
                    reader.close();
                    
                    // Simple JSON parsing for state
                    String responseStr = response.toString();
                    boolean isLeader = responseStr.contains("\"state\":\"LEADER\"") || 
                                     responseStr.contains("\"state\": \"LEADER\"");
                    
                    node.setAvailable(true);
                    node.setLeader(isLeader);
                    
                    if (isLeader) {
                        System.out.println("👑 Found leader: " + node.toString());
                    } else {
                        System.out.println("📡 Available node: " + node.toString());
                    }
                } else {
                    node.setAvailable(false);
                    node.setLeader(false);
                    System.out.println("❌ Unavailable node: " + node.toString());
                }
                
                conn.disconnect();
                
            } catch (Exception e) {
                node.setAvailable(false);
                node.setLeader(false);
                System.out.println("❌ Unreachable node: " + node.toString() + " (" + e.getMessage() + ")");
            }
        }
    }
    
    private ClusterNode findBestNode() {
        // Update cluster status first
        updateClusterStatus();
        
        // Prefer leader nodes
        for (ClusterNode node : clusterNodes) {
            if (node.isAvailable() && node.isLeader()) {
                System.out.println("🎯 Selecting leader node: " + node.toString());
                return node;
            }
        }
        
        // Fallback to any available node
        for (ClusterNode node : clusterNodes) {
            if (node.isAvailable()) {
                System.out.println("🔄 Selecting available node: " + node.toString());
                return node;
            }
        }
        
        System.out.println("⚠️  No available nodes found, trying first node as fallback");
        return clusterNodes.isEmpty() ? null : clusterNodes.get(0);
    }

    public boolean connect() {
        if (clusterMode) {
            return connectToCluster();
        } else {
            return connectWithRetry(MAX_RETRY_ATTEMPTS);
        }
    }
    
    public boolean connectToCluster() {
        System.out.println("🌐 Attempting cluster connection...");
        
        int maxAttempts = 3; // Try up to 3 times to find a working node
        
        for (int attempt = 0; attempt < maxAttempts; attempt++) {
            ClusterNode targetNode = findBestNode();
            
            if (targetNode == null) {
                System.out.println("❌ No cluster nodes available (attempt " + (attempt + 1) + "/" + maxAttempts + ")");
                if (attempt < maxAttempts - 1) {
                    try {
                        Thread.sleep(2000); // Wait before retry
                    } catch (InterruptedException ie) {
                        Thread.currentThread().interrupt();
                        return false;
                    }
                }
                continue;
            }
            
            // Try to connect to the selected node
            if (connectToNode(targetNode)) {
                currentNode = targetNode;
                addToHistory("Connected to cluster via " + targetNode.toString());
                System.out.println("✅ Connected to cluster via " + targetNode.toString());
                return true;
            } else {
                System.out.println("⚠️  Failed to connect to " + targetNode.toString() + ", trying next...");
            }
        }
        
        System.out.println("❌ Failed to connect to any cluster node after " + maxAttempts + " attempts");
        return false;
    }
    
    private boolean connectToNode(ClusterNode node) {
        try {
            // Close existing socket if any
            if (socket != null && !socket.isClosed()) {
                socket.close();
            }
            
            socket = new Socket();
            socket.connect(new java.net.InetSocketAddress(node.getHost(), node.getTcpPort()), CONNECTION_TIMEOUT);
            out = new PrintWriter(socket.getOutputStream(), true);
            
            // Send role identification
            out.print("PUBLISH");
            out.flush();
            
            isConnected = true;
            return true;
            
        } catch (IOException e) {
            System.out.println("Connection failed to " + node.toString() + ": " + e.getMessage());
            return false;
        }
    }
    
    public boolean connectWithRetry(int maxAttempts) {
        int attempt = 0;
        int delay = INITIAL_RETRY_DELAY;
        
        while (attempt < maxAttempts) {
            try {
                // Close existing socket if any
                if (socket != null && !socket.isClosed()) {
                    socket.close();
                }
                
                System.out.println("Attempting to connect to broker... (attempt " + (attempt + 1) + "/" + maxAttempts + ")");
                
                socket = new Socket();
                socket.connect(new java.net.InetSocketAddress(host, port), CONNECTION_TIMEOUT);
                out = new PrintWriter(socket.getOutputStream(), true);
                
                // Send role identification
                out.print("PUBLISH");
                out.flush();
                
                isConnected = true;
                addToHistory("Connected to broker at " + host + ":" + port + " (attempt " + (attempt + 1) + ")");
                System.out.println("Successfully connected to broker at " + host + ":" + port);
                return true;
                
            } catch (IOException e) {
                attempt++;
                isConnected = false;
                
                String errorMsg = "Connection attempt " + attempt + " failed: " + e.getMessage();
                addToHistory(errorMsg);
                System.err.println(errorMsg);
                
                if (attempt < maxAttempts) {
                    try {
                        System.out.println("Retrying in " + (delay / 1000) + " seconds...");
                        Thread.sleep(delay);
                        delay = Math.min(delay * 2, MAX_RETRY_DELAY); // Exponential backoff with cap
                    } catch (InterruptedException ie) {
                        Thread.currentThread().interrupt();
                        System.err.println("Connection retry interrupted");
                        return false;
                    }
                } else {
                    addToHistory("Failed to connect after " + maxAttempts + " attempts");
                    System.err.println("Failed to connect to broker after " + maxAttempts + " attempts");
                }
            }
        }
        return false;
    }
    
    public boolean isConnectionHealthy() {
        if (socket == null || socket.isClosed() || !isConnected) {
            return false;
        }
        
        try {
            // Test connection by checking socket status
            if (socket.getInputStream().available() == -1) {
                return false;
            }
            
            // Additional check: try to get socket info
            socket.getKeepAlive(); // This will throw exception if socket is dead
            return true;
            
        } catch (IOException e) {
            isConnected = false;
            System.err.println("Connection health check failed: " + e.getMessage());
            return false;
        }
    }

    public void disconnect() {
        try {
            if (socket != null && !socket.isClosed()) {
                socket.close();
            }
            isConnected = false;
            addToHistory("Disconnected from broker");
            System.out.println("Disconnected from broker");
        } catch (IOException e) {
            System.err.println("Error disconnecting: " + e.getMessage());
        }
    }

    public boolean publishMessage(Message message, String formatType) {
        return publishMessageWithRetry(message, formatType, 3);
    }
    
    public boolean publishMessageWithRetry(Message message, String formatType, int maxAttempts) {
        for (int attempt = 0; attempt < maxAttempts; attempt++) {
            // Check connection health before attempting to publish
            if (!isConnectionHealthy()) {
                System.out.println("Connection unhealthy, attempting to reconnect...");
                if (!connectWithRetry(3)) {
                    System.err.println("Failed to reconnect for publish attempt " + (attempt + 1));
                    continue;
                }
            }
            
            try {
                String body;
                String formattedMessage;

                switch (formatType.toUpperCase()) {
                    case "JSON":
                        body = message.toJson();
                        formattedMessage = "FORMAT:JSON|" + body;
                        break;
                    case "XML":
                        body = message.toXml();
                        formattedMessage = "FORMAT:XML|" + body;
                        break;
                    default:
                        // Fallback to raw format
                        body = "[" + message.getTopic() + "] " + message.getValue();
                        formattedMessage = "FORMAT:RAW|" + body;
                        break;
                }

                out.print(formattedMessage);
                out.flush();
                
                // Check if the message was actually sent
                if (out.checkError()) {
                    throw new IOException("PrintWriter encountered an error");
                }
                
                String historyEntry = String.format("[%s] Published to '%s': %s", 
                    formatType, message.getTopic(), message.getValue());
                addToHistory(historyEntry);
                
                System.out.println("Published [" + formatType + "] message: " + 
                                 message.getEventName() + " to topic '" + message.getTopic() + "'");
                return true;

            } catch (Exception e) {
                isConnected = false;
                String errorMsg = "Publish attempt " + (attempt + 1) + " failed: " + e.getMessage();
                addToHistory(errorMsg);
                System.err.println(errorMsg);
                
                if (attempt < maxAttempts - 1) {
                    try {
                        System.out.println("Retrying publish in 1 second...");
                        Thread.sleep(1000);
                    } catch (InterruptedException ie) {
                        Thread.currentThread().interrupt();
                        return false;
                    }
                }
            }
        }
        
        addToHistory("Failed to publish message after " + maxAttempts + " attempts");
        System.err.println("Failed to publish message after " + maxAttempts + " attempts");
        return false;
    }

    public boolean publishRawMessage(String topic, String value, String eventName, String formatType) {
        Message message = new Message(
            eventName.isEmpty() ? "DefaultEvent" : eventName,
            value,
            topic
        );
        return publishMessage(message, formatType);
    }

    public static void interactiveMode() {
        interactiveMode(false); // Default to single-node mode
    }
    
    public static void interactiveMode(boolean useCluster) {
        Publisher publisher;
        
        if (useCluster) {
            System.out.println("🌐 Starting interactive mode with CLUSTER support");
            publisher = new Publisher(); // Cluster constructor
        } else {
            String host = System.getenv("BROKER_HOST");
            if (host == null) host = "127.0.0.1";
            
            String portStr = System.getenv("BROKER_PORT");
            int port = portStr != null ? Integer.parseInt(portStr) : 5000;
            
            System.out.println("📡 Starting interactive mode with SINGLE NODE");
            publisher = new Publisher(host, port);
        }
        
        if (!publisher.connect()) {
            return;
        }

        Scanner scanner = new Scanner(System.in);
        System.out.println("\n=== Java Publisher Interactive Mode ===");
        if (useCluster) {
            System.out.println("🌐 Cluster Mode - Connected to Raft cluster");
        } else {
            System.out.println("📡 Single Node Mode");
        }
        System.out.println("Commands:");
        System.out.println("  publish <topic> <message> [json|xml] - Publish a message");
        System.out.println("  auto - Start auto-publishing demo messages");
        if (useCluster) {
            System.out.println("  cluster - Show cluster status");
            System.out.println("  reconnect - Reconnect to cluster (find new leader)");
        }
        System.out.println("  quit - Exit");
        System.out.println();

        try {
            while (true) {
                System.out.print("publisher> ");
                String input = scanner.nextLine().trim();
                
                if (input.isEmpty()) {
                    continue;
                }

                String[] command = input.split("\\s+");

                if (command[0].equalsIgnoreCase("quit")) {
                    break;
                }

                if (command[0].equalsIgnoreCase("publish") && command.length >= 3) {
                    String topic = command[1];
                    String formatType = "JSON"; // default
                    
                    // Find format type and construct message
                    StringBuilder messageBuilder = new StringBuilder();
                    for (int i = 2; i < command.length; i++) {
                        if (i == command.length - 1 && 
                           (command[i].equalsIgnoreCase("json") || command[i].equalsIgnoreCase("xml"))) {
                            formatType = command[i].toUpperCase();
                        } else {
                            if (messageBuilder.length() > 0) {
                                messageBuilder.append(" ");
                            }
                            messageBuilder.append(command[i]);
                        }
                    }

                    String messageText = messageBuilder.toString();
                    if (messageText.isEmpty()) {
                        System.out.println("Message cannot be empty");
                        continue;
                    }

                    publisher.publishRawMessage(topic, messageText, "UserMessage", formatType);

                } else if (command[0].equalsIgnoreCase("auto")) {
                    System.out.println("Starting auto-publishing mode (press Enter to stop)...");
                    
                    String[] topics = {"news", "alerts", "weather", "sports"};
                    String[] formats = {"JSON", "XML"};
                    Random random = new Random();
                    
                    // Start auto-publishing in a separate thread
                    Thread autoThread = new Thread(() -> {
                        int counter = 1;
                        try {
                            while (!Thread.currentThread().isInterrupted()) {
                                String topic = topics[random.nextInt(topics.length)];
                                String formatType = formats[random.nextInt(formats.length)];
                                String messageText = "Auto message #" + counter + " for " + topic;

                                publisher.publishRawMessage(topic, messageText, "AutoEvent", formatType);
                                
                                counter++;
                                TimeUnit.SECONDS.sleep(2);
                            }
                        } catch (InterruptedException e) {
                            System.out.println("Auto-publishing stopped");
                        }
                    });
                    
                    autoThread.start();
                    scanner.nextLine(); // Wait for Enter
                    autoThread.interrupt();
                    
                } else if (useCluster && command[0].equalsIgnoreCase("cluster")) {
                    System.out.println("\n🌐 Cluster Status:");
                    System.out.println("==================");
                    if (publisher.clusterNodes != null) {
                        for (ClusterNode node : publisher.clusterNodes) {
                            System.out.println(node.toString());
                        }
                        if (publisher.currentNode != null) {
                            System.out.println("Current connection: " + publisher.currentNode.toString());
                        }
                    }
                    System.out.println();
                    
                } else if (useCluster && command[0].equalsIgnoreCase("reconnect")) {
                    System.out.println("🔄 Reconnecting to cluster...");
                    publisher.disconnect();
                    if (publisher.connect()) {
                        System.out.println("✅ Reconnected successfully");
                    } else {
                        System.out.println("❌ Reconnection failed");
                    }
                    
                } else {
                    System.out.println("Invalid command. Use: publish <topic> <message> [json|xml], auto, cluster, reconnect, or quit");
                }
            }
        } catch (Exception e) {
            System.out.println("Error in interactive mode: " + e.getMessage());
        } finally {
            scanner.close();
            publisher.disconnect();
        }
    }

    public static void main(String[] args) {
        // Check for cluster mode argument
        boolean clusterMode = args.length > 0 && args[0].equals("cluster");
        
        // Check if running in Docker mode
        if (System.getenv("BROKER_HOST") != null) {
            // Docker mode - run auto publishing
            autoPublishMode(clusterMode);
        } else {
            // Interactive mode
            interactiveMode(clusterMode);
        }
    }
    
    public static void autoPublishMode() {
        autoPublishMode(false); // Default to single-node mode
    }
    
    public static void autoPublishMode(boolean useCluster) {
        Publisher publisher;
        
        if (useCluster) {
            System.out.println("🌐 Starting auto-publishing in CLUSTER mode");
            publisher = new Publisher(); // Cluster constructor
        } else {
            String host = System.getenv("BROKER_HOST");
            if (host == null) host = "127.0.0.1";
            
            String portStr = System.getenv("BROKER_PORT");
            int port = portStr != null ? Integer.parseInt(portStr) : 5000;
            
            System.out.println("📡 Starting auto-publishing in SINGLE NODE mode");
            publisher = new Publisher(host, port);
        }
        
        if (!publisher.connect()) {
            System.err.println("Failed to connect to broker in auto mode");
            return;
        }
        
        System.out.println("Starting auto-publishing mode for Docker...");
        
        String[] topics = {"news", "alerts", "updates"};
        String[] eventTypes = {"UserLogin", "DataUpdate", "SystemAlert", "NewsPublished"};
        Random random = new Random();
        
        while (true) {
            try {
                String topic = topics[random.nextInt(topics.length)];
                String eventType = eventTypes[random.nextInt(eventTypes.length)];
                String content = "Auto message " + System.currentTimeMillis();
                String format = random.nextBoolean() ? "JSON" : "XML";
                
                boolean success = publisher.publishRawMessage(topic, content, eventType, format);
                System.out.println("Published to " + topic + " [" + format + "]: " + success);
                
                TimeUnit.SECONDS.sleep(10); // Publish every 10 seconds
            } catch (InterruptedException e) {
                System.out.println("Auto-publishing interrupted");
                break;
            } catch (Exception e) {
                System.err.println("Error in auto-publishing: " + e.getMessage());
                try {
                    TimeUnit.SECONDS.sleep(5);
                } catch (InterruptedException ie) {
                    break;
                }
            }
        }
        
        publisher.disconnect();
    }
}