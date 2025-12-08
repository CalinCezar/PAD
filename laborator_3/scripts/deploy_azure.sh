#!/bin/bash
# Azure Deployment Script for Employee Data Warehouse
# PAD Laboratory 3 - Cloud Deployment

set -e

echo "=========================================="
echo "  Employee Data Warehouse - Azure Deploy"
echo "=========================================="
echo ""

# Configuration
RESOURCE_GROUP="EmployeeDataWarehouse-RG"
LOCATION="eastus"
ACR_NAME="employeedwregistry"
AKS_NAME="employee-dw-aks"
COSMOSDB_NAME="employee-dw-cosmosdb"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Step 1: Check prerequisites
echo -e "${YELLOW}Step 1: Checking prerequisites...${NC}"
if ! command -v az &> /dev/null; then
    echo -e "${RED}Error: Azure CLI not installed${NC}"
    echo "Install from: https://docs.microsoft.com/cli/azure/install-azure-cli"
    exit 1
fi

if ! command -v kubectl &> /dev/null; then
    echo -e "${RED}Error: kubectl not installed${NC}"
    echo "Install from: https://kubernetes.io/docs/tasks/tools/"
    exit 1
fi

if ! command -v docker &> /dev/null; then
    echo -e "${RED}Error: Docker not installed${NC}"
    exit 1
fi

echo -e "${GREEN}✓ All prerequisites met${NC}"
echo ""

# Step 2: Azure Login
echo -e "${YELLOW}Step 2: Logging in to Azure...${NC}"
az login
echo -e "${GREEN}✓ Logged in to Azure${NC}"
echo ""

# Step 3: Create Resource Group
echo -e "${YELLOW}Step 3: Creating Resource Group...${NC}"
az group create \
    --name $RESOURCE_GROUP \
    --location $LOCATION \
    --tags Project="Employee Data Warehouse" Lab="PAD-Lab3"
echo -e "${GREEN}✓ Resource Group created${NC}"
echo ""

# Step 4: Create Azure Container Registry
echo -e "${YELLOW}Step 4: Creating Azure Container Registry...${NC}"
az acr create \
    --resource-group $RESOURCE_GROUP \
    --name $ACR_NAME \
    --sku Basic \
    --admin-enabled true
echo -e "${GREEN}✓ ACR created${NC}"
echo ""

# Step 5: Build and Push Docker Images
echo -e "${YELLOW}Step 5: Building and pushing Docker images...${NC}"

# Login to ACR
az acr login --name $ACR_NAME

# Build images
docker build -f data_warehouse/Dockerfile -t $ACR_NAME.azurecr.io/data-warehouse:latest .
docker build -f json_node/Dockerfile -t $ACR_NAME.azurecr.io/json-node:latest .
docker build -f xml_node/Dockerfile -t $ACR_NAME.azurecr.io/xml-node:latest .

# Push images
docker push $ACR_NAME.azurecr.io/data-warehouse:latest
docker push $ACR_NAME.azurecr.io/json-node:latest
docker push $ACR_NAME.azurecr.io/xml-node:latest

echo -e "${GREEN}✓ Images pushed to ACR${NC}"
echo ""

# Step 6: Create Cosmos DB
echo -e "${YELLOW}Step 6: Creating Azure Cosmos DB...${NC}"
az cosmosdb create \
    --name $COSMOSDB_NAME \
    --resource-group $RESOURCE_GROUP \
    --kind MongoDB \
    --enable-free-tier true \
    --capabilities EnableMongo EnableServerless \
    --default-consistency-level Session

# Create database
az cosmosdb mongodb database create \
    --account-name $COSMOSDB_NAME \
    --resource-group $RESOURCE_GROUP \
    --name employee_warehouse

# Create collection
az cosmosdb mongodb collection create \
    --account-name $COSMOSDB_NAME \
    --resource-group $RESOURCE_GROUP \
    --database-name employee_warehouse \
    --name employees \
    --idx '[{"key": {"keys": ["id"]},"options": {"unique": true}}]'

echo -e "${GREEN}✓ Cosmos DB created${NC}"
echo ""

# Step 7: Create AKS Cluster
echo -e "${YELLOW}Step 7: Creating Azure Kubernetes Service...${NC}"
az aks create \
    --resource-group $RESOURCE_GROUP \
    --name $AKS_NAME \
    --node-count 2 \
    --node-vm-size Standard_B2s \
    --enable-cluster-autoscaler \
    --min-count 1 \
    --max-count 3 \
    --generate-ssh-keys \
    --attach-acr $ACR_NAME

echo -e "${GREEN}✓ AKS cluster created${NC}"
echo ""

# Step 8: Get AKS credentials
echo -e "${YELLOW}Step 8: Getting AKS credentials...${NC}"
az aks get-credentials \
    --resource-group $RESOURCE_GROUP \
    --name $AKS_NAME \
    --overwrite-existing

echo -e "${GREEN}✓ Credentials configured${NC}"
echo ""

# Step 9: Get Cosmos DB connection string
echo -e "${YELLOW}Step 9: Getting Cosmos DB connection string...${NC}"
COSMOS_CONNECTION=$(az cosmosdb keys list \
    --name $COSMOSDB_NAME \
    --resource-group $RESOURCE_GROUP \
    --type connection-strings \
    --query "connectionStrings[0].connectionString" -o tsv)

echo -e "${GREEN}✓ Connection string retrieved${NC}"
echo ""

# Step 10: Create Kubernetes secret for Cosmos DB
echo -e "${YELLOW}Step 10: Creating Kubernetes secrets...${NC}"
kubectl create namespace employee-dw --dry-run=client -o yaml | kubectl apply -f -

kubectl create secret generic cosmosdb-connection \
    --from-literal=connection-string="$COSMOS_CONNECTION" \
    -n employee-dw \
    --dry-run=client -o yaml | kubectl apply -f -

echo -e "${GREEN}✓ Secrets created${NC}"
echo ""

# Step 11: Update Kubernetes manifests
echo -e "${YELLOW}Step 11: Updating Kubernetes manifests...${NC}"

# Create temporary directory
mkdir -p temp_k8s
cp kubernetes/*.yaml temp_k8s/

# Update image references
sed -i "s|image: employee-data-warehouse:latest|image: $ACR_NAME.azurecr.io/data-warehouse:latest|g" temp_k8s/datawarehouse-deployment.yaml
sed -i "s|imagePullPolicy: Never|imagePullPolicy: Always|g" temp_k8s/datawarehouse-deployment.yaml

sed -i "s|image: employee-json-node:latest|image: $ACR_NAME.azurecr.io/json-node:latest|g" temp_k8s/jsonnode-deployment.yaml
sed -i "s|imagePullPolicy: Never|imagePullPolicy: Always|g" temp_k8s/jsonnode-deployment.yaml

sed -i "s|image: employee-xml-node:latest|image: $ACR_NAME.azurecr.io/xml-node:latest|g" temp_k8s/xmlnode-deployment.yaml
sed -i "s|imagePullPolicy: Never|imagePullPolicy: Always|g" temp_k8s/xmlnode-deployment.yaml

echo -e "${GREEN}✓ Manifests updated${NC}"
echo ""

# Step 12: Deploy to AKS
echo -e "${YELLOW}Step 12: Deploying to AKS...${NC}"
kubectl apply -f temp_k8s/ -n employee-dw

# Wait for deployments
kubectl rollout status deployment/json-node -n employee-dw --timeout=300s
kubectl rollout status deployment/xml-node -n employee-dw --timeout=300s
kubectl rollout status deployment/data-warehouse -n employee-dw --timeout=300s

echo -e "${GREEN}✓ Deployed to AKS${NC}"
echo ""

# Clean up temp files
rm -rf temp_k8s

# Step 13: Get service endpoints
echo -e "${YELLOW}Step 13: Getting service endpoints...${NC}"
echo ""
echo "=== Deployed Services ==="
kubectl get services -n employee-dw
echo ""
echo "=== Pods Status ==="
kubectl get pods -n employee-dw
echo ""

# Get external IP
echo "Waiting for external IP assignment..."
sleep 30

DW_IP=$(kubectl get service data-warehouse -n employee-dw -o jsonpath='{.status.loadBalancer.ingress[0].ip}')

echo ""
echo -e "${GREEN}=========================================="
echo "  ✓ Deployment Complete!"
echo "==========================================${NC}"
echo ""
echo "Data Warehouse URL: http://$DW_IP:5000"
echo "Health Check: http://$DW_IP:5000/health"
echo "Employees API: http://$DW_IP:5000/employees"
echo ""
echo "To view logs: kubectl logs -f deployment/data-warehouse -n employee-dw"
echo "To scale: kubectl scale deployment/data-warehouse --replicas=3 -n employee-dw"
echo ""
echo -e "${YELLOW}Note: It may take a few minutes for the external IP to be fully accessible${NC}"
echo ""
