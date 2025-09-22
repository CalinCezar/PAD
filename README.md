# Multi-Language Message Broker

A distributed message broker system with **Java Publisher**, **Python Broker**, and **C# Subscriber**.

## Requirements

- **Java** 8+
- **Python** 3.8+  
- **.NET** 8+

## Quick Start

**1. Start Broker (Python)**
```bash
cd Broker && python3 broker.py
```

**2. Start Subscriber (C#)**  
```bash
cd Subscriber && dotnet run
# Enter topics: news,weather,alerts
```

**3. Start Publisher (Java)**
```bash
cd Publisher
javac -d target/classes src/main/java/com/pad/publisher/Publisher.java
java -cp target/classes com.pad.publisher.Publisher
```

## Usage

**Publisher commands:**
```
publish news "Breaking news" json
publish weather "Sunny day" xml  
auto
quit
```

## Features

- **Multi-format**: JSON, XML, RAW messages
- **Topic routing**: Subscribe to specific topics
- **Persistence**: SQLite message storage
- **Docker ready**: Each component containerized

## Authors

- **Pinzaru Ciprian** - PinzaruCiprian
- **Toma Daniel** - Daneil05  
- **Popan Calin Cezar** - CalinCezar
