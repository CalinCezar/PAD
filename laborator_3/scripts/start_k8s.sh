#!/bin/bash

echo "=========================================="
echo "  Deploying to Kubernetes"
echo "=========================================="

# Check if kubectl is available
if ! command -v kubectl &> /dev/null; then
    echo "✗ kubectl not found. Please install kubectl."
    exit 1
fi

echo "✓ kubectl is available"

# Check if cluster is running
if ! kubectl cluster-info &> /dev/null; then
    echo "✗ Kubernetes cluster is not running."
    echo "  Please start Minikube or your Kubernetes cluster."
    exit 1
fi

echo "✓ Kubernetes cluster is running"

# Build Docker images
echo ""
echo "Building Docker images..."
docker build -t employee-data-warehouse:latest -f data_warehouse/Dockerfile .
docker build -t employee-json-node:latest -f json_node/Dockerfile .
docker build -t employee-xml-node:latest -f xml_node/Dockerfile .

# If using Minikube, load images into Minikube
if command -v minikube &> /dev/null; then
    echo ""
    echo "Loading images into Minikube..."
    minikube image load employee-data-warehouse:latest
    minikube image load employee-json-node:latest
    minikube image load employee-xml-node:latest
fi

# Apply Kubernetes configurations
echo ""
echo "Applying Kubernetes configurations..."

# MongoDB
kubectl apply -f kubernetes/mongodb-pvc.yaml
kubectl apply -f kubernetes/mongodb-deployment.yaml
kubectl apply -f kubernetes/mongodb-service.yaml

# JSON Node
kubectl apply -f kubernetes/jsonnode-deployment.yaml
kubectl apply -f kubernetes/jsonnode-service.yaml

# XML Node
kubectl apply -f kubernetes/xmlnode-deployment.yaml
kubectl apply -f kubernetes/xmlnode-service.yaml

# Data Warehouse
kubectl apply -f kubernetes/datawarehouse-deployment.yaml
kubectl apply -f kubernetes/datawarehouse-service.yaml

echo ""
echo "Waiting for deployments to be ready..."
kubectl wait --for=condition=ready pod -l app=mongodb --timeout=120s
kubectl wait --for=condition=ready pod -l app=json-node --timeout=120s
kubectl wait --for=condition=ready pod -l app=xml-node --timeout=120s
kubectl wait --for=condition=ready pod -l app=data-warehouse --timeout=120s

echo ""
echo "=========================================="
echo "  Deployment Complete!"
echo "=========================================="
echo ""
echo "Check status:"
echo "  kubectl get pods"
echo "  kubectl get services"
echo ""
echo "Access Data Warehouse:"
echo "  minikube service data-warehouse"
echo ""
echo "View logs:"
echo "  kubectl logs -l app=data-warehouse"
echo ""
