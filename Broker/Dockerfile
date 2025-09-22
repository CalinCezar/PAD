# Python Broker Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Copy broker files
COPY broker.py .
COPY requirements.txt .

# Install Python dependencies (if any)
RUN pip install --no-cache-dir -r requirements.txt

# Create directory for SQLite database
RUN mkdir -p /app/data

# Expose broker port
EXPOSE 5000

# Run the broker
CMD ["python", "broker.py"]