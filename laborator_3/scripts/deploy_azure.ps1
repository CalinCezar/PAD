# PowerShell script for Azure Deployment
# Employee Data Warehouse - PAD Laboratory 3

param(
    [string]$ResourceGroup = "EmployeeDataWarehouse-RG",
    [string]$Location = "eastus",
    [string]$AcrName = "employeedwregistry",
    [string]$AksName = "employee-dw-aks",
    [string]$CosmosDbName = "employee-dw-cosmosdb"
)

Write-Host "=========================================="  -ForegroundColor Cyan
Write-Host "  Employee Data Warehouse - Azure Deploy" -ForegroundColor Cyan
Write-Host "=========================================="  -ForegroundColor Cyan
Write-Host ""

# Step 1: Check prerequisites
Write-Host "Step 1: Checking prerequisites..." -ForegroundColor Yellow

if (!(Get-Command az -ErrorAction SilentlyContinue)) {
    Write-Host "Error: Azure CLI not installed" -ForegroundColor Red
    Write-Host "Install from: https://docs.microsoft.com/cli/azure/install-azure-cli"
    exit 1
}

if (!(Get-Command kubectl -ErrorAction SilentlyContinue)) {
    Write-Host "Error: kubectl not installed" -ForegroundColor Red
    Write-Host "Install from: https://kubernetes.io/docs/tasks/tools/"
    exit 1
}

if (!(Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Host "Error: Docker not installed" -ForegroundColor Red
    exit 1
}

Write-Host "√ All prerequisites met" -ForegroundColor Green
Write-Host ""

# Step 2: Azure Login
Write-Host "Step 2: Logging in to Azure..." -ForegroundColor Yellow
az login
Write-Host "√ Logged in to Azure" -ForegroundColor Green
Write-Host ""

# Step 3: Create Resource Group
Write-Host "Step 3: Creating Resource Group..." -ForegroundColor Yellow
az group create `
    --name $ResourceGroup `
    --location $Location `
    --tags Project="Employee Data Warehouse" Lab="PAD-Lab3"
Write-Host "√ Resource Group created" -ForegroundColor Green
Write-Host ""

# Step 4: Create Azure Container Registry
Write-Host "Step 4: Creating Azure Container Registry..." -ForegroundColor Yellow
az acr create `
    --resource-group $ResourceGroup `
    --name $AcrName `
    --sku Basic `
    --admin-enabled true
Write-Host "√ ACR created" -ForegroundColor Green
Write-Host ""

# Step 5: Build and Push Docker Images
Write-Host "Step 5: Building and pushing Docker images..." -ForegroundColor Yellow

# Login to ACR
az acr login --name $AcrName

# Build images
docker build -f data_warehouse/Dockerfile -t "$AcrName.azurecr.io/data-warehouse:latest" .
docker build -f json_node/Dockerfile -t "$AcrName.azurecr.io/json-node:latest" .
docker build -f xml_node/Dockerfile -t "$AcrName.azurecr.io/xml-node:latest" .

# Push images
docker push "$AcrName.azurecr.io/data-warehouse:latest"
docker push "$AcrName.azurecr.io/json-node:latest"
docker push "$AcrName.azurecr.io/xml-node:latest"

Write-Host "√ Images pushed to ACR" -ForegroundColor Green
Write-Host ""

# Step 6: Create Cosmos DB
Write-Host "Step 6: Creating Azure Cosmos DB..." -ForegroundColor Yellow
az cosmosdb create `
    --name $CosmosDbName `
    --resource-group $ResourceGroup `
    --kind MongoDB `
    --enable-free-tier true `
    --capabilities EnableMongo EnableServerless `
    --default-consistency-level Session

# Create database
az cosmosdb mongodb database create `
    --account-name $CosmosDbName `
    --resource-group $ResourceGroup `
    --name employee_warehouse

# Create collection
az cosmosdb mongodb collection create `
    --account-name $CosmosDbName `
    --resource-group $ResourceGroup `
    --database-name employee_warehouse `
    --name employees `
    --idx '[{\"key\": {\"keys\": [\"id\"]},\"options\": {\"unique\": true}}]'

Write-Host "√ Cosmos DB created" -ForegroundColor Green
Write-Host ""

# Step 7: Create AKS Cluster
Write-Host "Step 7: Creating Azure Kubernetes Service..." -ForegroundColor Yellow
az aks create `
    --resource-group $ResourceGroup `
    --name $AksName `
    --node-count 2 `
    --node-vm-size Standard_B2s `
    --enable-cluster-autoscaler `
    --min-count 1 `
    --max-count 3 `
    --generate-ssh-keys `
    --attach-acr $AcrName

Write-Host "√ AKS cluster created" -ForegroundColor Green
Write-Host ""

# Step 8: Get AKS credentials
Write-Host "Step 8: Getting AKS credentials..." -ForegroundColor Yellow
az aks get-credentials `
    --resource-group $ResourceGroup `
    --name $AksName `
    --overwrite-existing

Write-Host "√ Credentials configured" -ForegroundColor Green
Write-Host ""

# Step 9: Get Cosmos DB connection string
Write-Host "Step 9: Getting Cosmos DB connection string..." -ForegroundColor Yellow
$CosmosConnection = az cosmosdb keys list `
    --name $CosmosDbName `
    --resource-group $ResourceGroup `
    --type connection-strings `
    --query "connectionStrings[0].connectionString" -o tsv

Write-Host "√ Connection string retrieved" -ForegroundColor Green
Write-Host ""

# Step 10: Create Kubernetes secret
Write-Host "Step 10: Creating Kubernetes secrets..." -ForegroundColor Yellow
kubectl create namespace employee-dw --dry-run=client -o yaml | kubectl apply -f -

kubectl create secret generic cosmosdb-connection `
    --from-literal=connection-string="$CosmosConnection" `
    -n employee-dw `
    --dry-run=client -o yaml | kubectl apply -f -

Write-Host "√ Secrets created" -ForegroundColor Green
Write-Host ""

# Step 11: Deploy to AKS
Write-Host "Step 11: Deploying to AKS..." -ForegroundColor Yellow

# Create temporary manifests
$tempDir = "temp_k8s"
New-Item -ItemType Directory -Force -Path $tempDir | Out-Null
Copy-Item kubernetes/*.yaml $tempDir/

# Update image references
(Get-Content "$tempDir/datawarehouse-deployment.yaml") `
    -replace 'image: employee-data-warehouse:latest', "image: $AcrName.azurecr.io/data-warehouse:latest" `
    -replace 'imagePullPolicy: Never', 'imagePullPolicy: Always' |
    Set-Content "$tempDir/datawarehouse-deployment.yaml"

(Get-Content "$tempDir/jsonnode-deployment.yaml") `
    -replace 'image: employee-json-node:latest', "image: $AcrName.azurecr.io/json-node:latest" `
    -replace 'imagePullPolicy: Never', 'imagePullPolicy: Always' |
    Set-Content "$tempDir/jsonnode-deployment.yaml"

(Get-Content "$tempDir/xmlnode-deployment.yaml") `
    -replace 'image: employee-xml-node:latest', "image: $AcrName.azurecr.io/xml-node:latest" `
    -replace 'imagePullPolicy: Never', 'imagePullPolicy: Always' |
    Set-Content "$tempDir/xmlnode-deployment.yaml"

# Apply manifests
kubectl apply -f $tempDir/ -n employee-dw

# Wait for deployments
kubectl rollout status deployment/json-node -n employee-dw --timeout=300s
kubectl rollout status deployment/xml-node -n employee-dw --timeout=300s
kubectl rollout status deployment/data-warehouse -n employee-dw --timeout=300s

# Clean up temp files
Remove-Item -Recurse -Force $tempDir

Write-Host "√ Deployed to AKS" -ForegroundColor Green
Write-Host ""

# Step 12: Get service endpoints
Write-Host "Step 12: Getting service endpoints..." -ForegroundColor Yellow
Write-Host ""
Write-Host "=== Deployed Services ===" -ForegroundColor Cyan
kubectl get services -n employee-dw
Write-Host ""
Write-Host "=== Pods Status ===" -ForegroundColor Cyan
kubectl get pods -n employee-dw
Write-Host ""

# Get external IP
Write-Host "Waiting for external IP assignment..." -ForegroundColor Yellow
Start-Sleep -Seconds 30

$DwIp = kubectl get service data-warehouse -n employee-dw -o jsonpath='{.status.loadBalancer.ingress[0].ip}'

Write-Host ""
Write-Host "==========================================" -ForegroundColor Green
Write-Host "  √ Deployment Complete!" -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Data Warehouse URL: http://$DwIp:5000" -ForegroundColor White
Write-Host "Health Check: http://$DwIp:5000/health" -ForegroundColor White
Write-Host "Employees API: http://$DwIp:5000/employees" -ForegroundColor White
Write-Host ""
Write-Host "To view logs: kubectl logs -f deployment/data-warehouse -n employee-dw" -ForegroundColor Gray
Write-Host "To scale: kubectl scale deployment/data-warehouse --replicas=3 -n employee-dw" -ForegroundColor Gray
Write-Host ""
Write-Host "Note: It may take a few minutes for the external IP to be fully accessible" -ForegroundColor Yellow
Write-Host ""
