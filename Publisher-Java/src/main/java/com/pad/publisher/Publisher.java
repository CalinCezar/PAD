package com.pad.publisher;

import java.io.*;
import java.net.Socket;
import java.time.Instant;
import java.util.Random;
import java.util.Scanner;
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

public class Publisher {
    private String host;
    private int port;
    private Socket socket;
    private PrintWriter out;

    public Publisher(String host, int port) {
        this.host = host;
        this.port = port;
    }

    public boolean connect() {
        try {
            socket = new Socket(host, port);
            out = new PrintWriter(socket.getOutputStream(), true);
            
            // Send role identification
            out.print("PUBLISH");
            out.flush();
            
            System.out.println("Connected to broker at " + host + ":" + port);
            return true;
        } catch (IOException e) {
            System.err.println("Failed to connect to broker: " + e.getMessage());
            return false;
        }
    }

    public void disconnect() {
        try {
            if (socket != null && !socket.isClosed()) {
                socket.close();
            }
            System.out.println("Disconnected from broker");
        } catch (IOException e) {
            System.err.println("Error disconnecting: " + e.getMessage());
        }
    }

    public boolean publishMessage(Message message, String formatType) {
        if (socket == null || socket.isClosed()) {
            System.err.println("Not connected to broker. Call connect() first.");
            return false;
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
            
            System.out.println("Published [" + formatType + "] message: " + 
                             message.getEventName() + " to topic '" + message.getTopic() + "'");
            return true;

        } catch (Exception e) {
            System.err.println("Failed to publish message: " + e.getMessage());
            return false;
        }
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
        Publisher publisher = new Publisher("127.0.0.1", 5000);
        
        if (!publisher.connect()) {
            return;
        }

        Scanner scanner = new Scanner(System.in);
        System.out.println("\n=== Java Publisher Interactive Mode ===");
        System.out.println("Commands:");
        System.out.println("  publish <topic> <message> [json|xml] - Publish a message");
        System.out.println("  auto - Start auto-publishing demo messages");
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
                            Thread.currentThread().interrupt();
                        }
                    });
                    
                    autoThread.start();
                    
                    // Wait for user input to stop
                    scanner.nextLine();
                    autoThread.interrupt();
                    System.out.println("Stopped auto-publishing");

                } else {
                    System.out.println("Invalid command. Use: publish <topic> <message> [json|xml], auto, or quit");
                }
            }
        } finally {
            scanner.close();
            publisher.disconnect();
        }
    }

    public static void main(String[] args) {
        interactiveMode();
    }
}