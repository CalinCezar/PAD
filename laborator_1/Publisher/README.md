# Java Publisher for PAD Message Broker

A lightweight Java-based message publisher that can send messages in JSON and XML formats to the PAD message broker.

## Features

- **Multi-format support**: Send messages in JSON, XML, or raw text format
- **Interactive mode**: Command-line interface for manual message publishing
- **Auto-publishing mode**: Automatic message generation for testing
- **Topic-based messaging**: Publish messages to specific topics
- **Cross-platform compatibility**: Works with Python broker and C# subscriber
- **Zero external dependencies**: Uses only Java standard library

## Requirements

- Java 8 or higher
- No external dependencies required!

## Building the Project

```bash
# Simple compilation (recommended)
javac -d target/classes src/main/java/com/pad/publisher/Publisher.java

# Run the publisher
java -cp target/classes com.pad.publisher.Publisher

# Or with Maven (optional)
mvn clean package
java -jar target/publisher-1.0.0.jar
```

## Usage

### Interactive Mode

Start the publisher and use these commands:

```
publisher> publish news "Breaking news update" json
publisher> publish alerts "Emergency alert" xml  
publisher> auto
publisher> quit
```

### Message Formats

**JSON Example:**
```json
{
  "Id": 1695389123456,
  "EventName": "UserMessage",
  "Value": "Breaking news update",
  "Topic": "news"
}
```

**XML Example:**
```xml
<Message>
  <Id>1695389123456</Id>
  <EventName>UserMessage</EventName>
  <Value>Emergency alert</Value>
  <Topic>alerts</Topic>
</Message>
```

## Configuration

Default broker connection:
- Host: `127.0.0.1`
- Port: `5000`

To modify these values, edit the `Publisher.java` file and recompile.

## Testing

The publisher works with:
- Python broker (`broker.py`)
- C# subscriber (`Subscriber.cs`)

Start all components to test the complete message flow.