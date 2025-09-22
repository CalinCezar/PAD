# PAD Message Broker System

A **multi-language publish-subscribe message broker** demonstrating modern distributed system patterns with comprehensive resilience features.

## 🎯 Core Features

- **Multi-Language Architecture**: Python broker, Java publisher, C# subscriber
- **Dual Interface Support**: TCP sockets for persistent connections + HTTP REST API for web integration
- **Enterprise-Grade Resilience**: Auto-reconnection, exponential backoff, heartbeat monitoring
- **Real-time Web Dashboard**: Live monitoring and message publishing interface
- **Message Persistence**: SQLite database with fault-tolerant storage
- **Multiple Message Formats**: JSON, XML, and raw text support

## 🏗️ System Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Java Publisher│───▶│  Python Broker   │───▶│ C# Subscriber   │
│   (TCP Client)  │    │                  │    │ (TCP Client)    │
└─────────────────┘    │  ┌─────────────┐ │    └─────────────────┘
                       │  │ SQLite DB   │ │
┌─────────────────┐    │  └─────────────┘ │    ┌─────────────────┐
│ Web Dashboard   │───▶│                  │───▶│ More Subscribers│
│ (HTTP Client)   │    │  HTTP + TCP      │    │ (TCP Clients)   │
└─────────────────┘    └──────────────────┘    └─────────────────┘
```

## 🔧 Technologies Used

| Component | Language | Key Technologies |
|-----------|----------|-----------------|
| **Broker** | Python 3.11+ | TCP Sockets, HTTP Server, SQLite, Threading |
| **Publisher** | Java 17+ | Socket Programming, Exception Handling, Retry Logic |
| **Subscriber** | C# (.NET 9.0) | TCP Client, JSON/XML Parsing, Heartbeat Monitoring |
| **Dashboard** | JavaScript | Fetch API, Real-time Polling, Responsive UI |

## 🚀 Quick Start

### Prerequisites
```bash
# Required software
- Python 3.11+
- Java 17+
- .NET 9.0 SDK
- Modern web browser
```

### 1. Start the System
```bash
# Clone and navigate to project
git clone <repository-url>
cd PAD

# Compile Java Publisher (required first time)
cd Publisher
javac -d target/classes src/main/java/com/pad/publisher/*.java
cd ..

# Start all components
./start.sh
```

### 2. Access Interfaces
- **Web Dashboard**: http://localhost:3000
- **Broker API**: http://localhost:8080
- **Broker TCP**: localhost:5000

### 3. Test Publishing
```bash
# Via Java Publisher (Terminal) - after compilation
cd Publisher
java -cp target/classes com.pad.publisher.Publisher

# Via Web Dashboard
# Open http://localhost:3000 and use the publish form
```

### 4. Test Subscribing
```bash
# Via C# Subscriber
cd Subscriber
dotnet run
```

### 5. Stop the System
```bash
./stop.sh
```

## 🛡️ Resilience Features

### Auto-Reconnection with Exponential Backoff
- **Java Publisher**: Retries connection with progressive delays (1s → 2s → 4s → 8s)
- **C# Subscriber**: Infinite reconnection loop with 5-second intervals
- **Connection Health**: Proactive dead connection detection

### Heartbeat Monitoring
- **Subscriber → Broker**: PING every 30 seconds
- **Broker Tracking**: 90-second timeout with missed heartbeat counting
- **Health Endpoints**: Real-time subscriber status via `/subscribers` API

### Database Resilience
- **Write-Ahead Pattern**: Messages persisted before acknowledgment
- **Retry Logic**: Exponential backoff for database connection failures
- **Error Recovery**: Graceful handling of permission and disk space issues

### Publish Retry Logic
- **Multiple Attempts**: Up to 3 retry attempts for failed publishes
- **Automatic Reconnection**: Health checks trigger reconnection before retry
- **Error Propagation**: Clear error messages and status tracking

## 📊 Monitoring & APIs

### Broker HTTP Endpoints
```bash
GET  /status       # System health and statistics
GET  /messages     # Retrieve all stored messages
GET  /subscribers  # Active subscriber information
POST /publish      # Publish new messages
```

### Real-time Dashboard Features
- Live message monitoring with auto-refresh
- Publisher interface with format selection (JSON/XML/Raw)
- Subscriber health tracking
- System statistics (uptime, message count, active connections)
- Message filtering and search capabilities

## 🧪 Testing Resilience

### Test Broker Failure Recovery
```bash
# 1. Start system and establish connections
./start.sh

# 2. In separate terminals, start publisher and subscriber
cd Publisher && java -cp target/classes com.pad.publisher.Publisher
cd Subscriber && dotnet run

# 3. Stop broker to simulate failure
./stop.sh

# 4. Observe retry behavior in publisher/subscriber logs

# 5. Restart broker and observe automatic reconnection
./start.sh
```

### Test Network Partitioning
```bash
# Simulate network issues by temporarily blocking ports
sudo iptables -A INPUT -p tcp --dport 5000 -j DROP

# Observe resilience behavior, then restore connectivity
sudo iptables -D INPUT -p tcp --dport 5000 -j DROP
```

## � Project Structure

```
PAD/
├── Broker/                 # Python message broker
│   ├── broker.py          # Main broker implementation
│   ├── requirements.txt   # Python dependencies
│   └── messages.db        # SQLite database (auto-created)
├── Publisher/             # Java publisher client
│   ├── src/main/java/com/pad/publisher/
│   │   └── Publisher.java # Publisher with resilience
│   └── target/classes/    # Compiled Java classes
├── Subscriber/            # C# subscriber client
│   ├── Subscriber.cs      # Subscriber with heartbeat
│   ├── Subscriber.csproj  # .NET project file
│   └── bin/               # Compiled assemblies
├── Dashboard/             # Web monitoring interface
│   ├── index.html         # Dashboard UI
│   ├── script.js          # JavaScript functionality
│   └── style.css          # Responsive styling
├── logs/                  # System logs (auto-created)
├── start.sh              # System startup script
├── stop.sh               # System shutdown script
└── README.md             # This documentation
```

## � Build Instructions

### First-Time Setup
```bash
# Compile Java Publisher
cd Publisher
javac -d target/classes src/main/java/com/pad/publisher/*.java

# Build C# Subscriber (optional - can run with dotnet run)
cd ../Subscriber
dotnet build

# Python Broker requires no compilation
```

### Development Mode (Manual Start)
```bash
# Terminal 1: Start Broker
cd Broker
python3 broker.py

# Terminal 2: Start Dashboard
cd Dashboard
python3 -m http.server 3000

# Terminal 3: Run Publisher (after compilation)
cd Publisher
java -cp target/classes com.pad.publisher.Publisher

# Terminal 4: Run Subscriber
cd Subscriber
dotnet run
```

## �🔍 Message Flow Example

### 1. Publishing a Message
```bash
# Java Publisher sends via TCP
FORMAT:JSON|{"Id":123,"EventName":"UserLogin","Value":"user123","Topic":"auth"}

# Web Dashboard sends via HTTP POST
{
  "topic": "auth",
  "content": "user login event",
  "format": "JSON"
}
```

### 2. Broker Processing
1. Receives message via TCP/HTTP
2. Validates and formats content
3. Stores in SQLite database
4. Forwards to interested subscribers
5. Updates statistics and logs

### 3. Subscriber Reception
```csharp
// C# Subscriber receives formatted message
FORMAT:JSON|{"Id":123,"EventName":"UserLogin","Value":"user123","Topic":"auth"}

// Parses and processes based on format
// Sends heartbeat confirmation
```

## 🎓 Educational Objectives Demonstrated

### Interface Design
- **TCP Socket Programming**: Low-level network communication
- **HTTP REST API**: Web-standard request/response patterns
- **Multi-protocol Support**: Flexible client integration options

### Multi-Language Integration
- **Python**: Server-side processing and persistence
- **Java**: Enterprise client with robust error handling
- **C#**: Modern application client with real-time features
- **JavaScript**: Web-based user interface and monitoring

### Resilience Patterns
- **Circuit Breaker**: Stop retrying after repeated failures
- **Exponential Backoff**: Progressive retry delays to avoid overwhelming systems
- **Heartbeat/Health Checks**: Proactive failure detection
- **Graceful Degradation**: Continue operating with reduced functionality

## 🚧 Future Enhancements

- **Message Acknowledgments**: Guaranteed delivery confirmation
- **Dead Letter Queue**: Handle undeliverable messages
- **Load Balancing**: Multiple broker instances
- **Message Compression**: Reduce network overhead
- **Security**: Authentication and encryption
- **Metrics Collection**: Prometheus/Grafana integration

## 📝 License

This project is developed for educational purposes as part of distributed systems coursework.

---

**Built with ❤️ for learning distributed systems and resilience patterns**

## ✨ Features

- **Multi-format**: JSON, XML, RAW messages with validation
- **Topic routing**: Subscribe to specific topics or "all"
- **Persistence**: SQLite message storage with history
- **Production ready**: HTTP API, monitoring, health checks
- **Docker ready**: Full containerization with compose
- **Real-time UI**: Live message monitoring and publishing

## 👥 Authors

- **Pinzaru Ciprian** - PinzaruCiprian
- **Toma Daniel** - Daneil05  
- **Popan Calin Cezar** - CalinCezar
