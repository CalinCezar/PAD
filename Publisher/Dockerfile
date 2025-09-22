# Java Publisher Dockerfile
FROM openjdk:11-jre-slim

WORKDIR /app

# Copy the compiled JAR file
COPY target/publisher-1.0.0.jar app.jar

# Expose any port if needed (the publisher connects to broker, doesn't listen)
EXPOSE 8080

# Run the publisher
CMD ["java", "-jar", "app.jar"]