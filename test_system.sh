#!/bin/bash

echo "=== Multi-Language Message Broker System Test ==="
echo "Testing XML/JSON support with Java Publisher, Python Broker, and C# Subscriber"
echo

# Check if Python is available
if ! command -v python3 &> /dev/null; then
    echo "Python3 is required but not installed."
    exit 1
fi

# Check if Java is available
if ! command -v java &> /dev/null; then
    echo "Java is required but not installed."
    exit 1
fi

# Check if Maven is available
if ! command -v mvn &> /dev/null; then
    echo "Note: Maven not found, but not required. Using simple Java compilation."
fi

# Check if .NET is available for the subscriber
if ! command -v dotnet &> /dev/null; then
    echo "Warning: .NET SDK not found. C# Subscriber cannot be tested."
    echo "You can still test the Java Publisher with the Python Broker."
fi

echo "1. Start the broker in the background:"
echo "   cd /home/calin/Projects/UTM/PAD/Broker && python3 broker.py"
echo
echo "2. Start the C# subscriber:"
echo "   cd /home/calin/Projects/UTM/PAD/Subscriber && dotnet run"
echo "   (Enter topics like: news,alerts,weather)"
echo
echo "3. Start the Java publisher:"
echo "   cd /home/calin/Projects/UTM/PAD/Publisher"
echo "   javac -d target/classes src/main/java/com/pad/publisher/Publisher.java"
echo "   java -cp target/classes com.pad.publisher.Publisher"
echo "   (or with Maven: mvn exec:java)"
echo
echo "Test commands for the publisher:"
echo "   publish news 'Breaking news update' json"
echo "   publish alerts 'Emergency alert' xml"
echo "   auto  (for automatic message generation)"
echo
echo "Expected behavior:"
echo "- JSON messages should display as [JSON][topic] content"
echo "- XML messages should display as [XML][topic] content"
echo "- Messages are persisted and replayed to new subscribers"
echo "- Topic-based filtering works correctly"
echo
echo "Architecture:"
echo "- Publisher: Java (with Maven)"
echo "- Broker: Python (with SQLite persistence)"
echo "- Subscriber: C# (with .NET)"