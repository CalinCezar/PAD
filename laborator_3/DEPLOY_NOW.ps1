# ========================================
# AZURE DEPLOYMENT - ONE CLICK SCRIPT
# Employee Data Warehouse - PAD Lab 3
# ========================================

param(
    [switch]$SkipDockerBuild = $false
)

$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Azure Deployment - Employee DW" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Configuration
$ResourceGroup = "EmployeeDataWarehouse-RG"
$Location = "spaincentral"
$AcrName = "employeedwregistry"
$AksName = "employee-dw-aks"
$CosmosDbName = "employee-dw-cosmosdb"

# Step 0: Prerequisites check
Write-Host "Step 0: Checking prerequisites..." -ForegroundColor Yellow
$missingTools = @()

if (!(Get-Command az -ErrorAction SilentlyContinue)) {
    $missingTools += "Azure CLI"
}
if (!(Get-Command docker -ErrorAction SilentlyContinue)) {
    $missingTools += "Docker"
}
if (!(Get-Command kubectl -ErrorAction SilentlyContinue)) {
    $missingTools += "kubectl"
}

if ($missingTools.Count -gt 0) {
    Write-Host "ERROR: Missing tools: $($missingTools -join ', ')" -ForegroundColor Red
    Write-Host "Please install missing tools and try again." -ForegroundColor Red
    exit 1
}

Write-Host "All prerequisites met" -ForegroundColor Green
Write-Host ""

# Step 1: Verify Azure login
Write-Host "Step 1: Verifying Azure login..." -ForegroundColor Yellow
try {
    $account = az account show 2>$null | ConvertFrom-Json
    Write-Host "Logged in as: $($account.user.name)" -ForegroundColor Green
    Write-Host "Subscription: $($account.name)" -ForegroundColor Gray
} catch {
    Write-Host "Please login to Azure first:" -ForegroundColor Red
    az login
}
Write-Host ""

# Step 2: Verify existing resources
Write-Host "Step 2: Verifying existing resources..." -ForegroundColor Yellow
$resources = az resource list --resource-group $ResourceGroup 2>$null | ConvertFrom-Json

$hasACR = $resources | Where-Object { $_.type -eq "Microsoft.ContainerRegistry/registries" }
$hasCosmosDB = $resources | Where-Object { $_.type -eq "Microsoft.DocumentDb/databaseAccounts" }
$hasAKS = $resources | Where-Object { $_.type -eq "Microsoft.ContainerService/managedClusters" }

Write-Host "ACR (Container Registry): $(if($hasACR){'Found'}else{'Missing'})" -ForegroundColor $(if($hasACR){'Green'}else{'Yellow'})
Write-Host "Cosmos DB: $(if($hasCosmosDB){'Found'}else{'Missing'})" -ForegroundColor $(if($hasCosmosDB){'Green'}else{'Yellow'})
Write-Host "AKS (Kubernetes): $(if($hasAKS){'Found'}else{'Missing'})" -ForegroundColor $(if($hasAKS){'Green'}else{'Yellow'})
Write-Host ""

# Step 3: Get Cosmos DB connection string
Write-Host "Step 3: Getting Cosmos DB connection string..." -ForegroundColor Yellow
$CosmosConnection = az cosmosdb keys list `
    --name $CosmosDbName `
    --resource-group $ResourceGroup `
    --type connection-strings `
    --query "connectionStrings[0].connectionString" -o tsv

if (!$CosmosConnection) {
    Write-Host "ERROR: Failed to get Cosmos DB connection string" -ForegroundColor Red
    exit 1
}
Write-Host "Connection string retrieved" -ForegroundColor Green
Write-Host ""

# Step 4: Build and Push Docker images (if not skipped)
if (!$SkipDockerBuild) {
    Write-Host "Step 4: Building and pushing Docker images..." -ForegroundColor Yellow
    Write-Host "This will take 5-10 minutes..." -ForegroundColor Gray

    # Login to ACR
    Write-Host "Logging in to ACR..." -ForegroundColor Gray
    az acr login --name $AcrName

    # Build and push Data Warehouse
    Write-Host "Building data-warehouse..." -ForegroundColor Gray
    docker build -f data_warehouse/Dockerfile -t "$AcrName.azurecr.io/data-warehouse:latest" .
    Write-Host "Pushing data-warehouse..." -ForegroundColor Gray
    docker push "$AcrName.azurecr.io/data-warehouse:latest"

    # Build and push JSON Node
    Write-Host "Building json-node..." -ForegroundColor Gray
    docker build -f json_node/Dockerfile -t "$AcrName.azurecr.io/json-node:latest" .
    Write-Host "Pushing json-node..." -ForegroundColor Gray
    docker push "$AcrName.azurecr.io/json-node:latest"

    # Build and push XML Node
    Write-Host "Building xml-node..." -ForegroundColor Gray
    docker build -f xml_node/Dockerfile -t "$AcrName.azurecr.io/xml-node:latest" .
    Write-Host "Pushing xml-node..." -ForegroundColor Gray
    docker push "$AcrName.azurecr.io/xml-node:latest"

    Write-Host "All images pushed to ACR" -ForegroundColor Green
} else {
    Write-Host "Step 4: Skipping Docker build (using existing images)" -ForegroundColor Yellow
}
Write-Host ""

# Step 5: Create AKS cluster (if not exists)
if (!$hasAKS) {
    Write-Host "Step 5: Creating AKS cluster..." -ForegroundColor Yellow
    Write-Host "WARNING: This will take 10-15 minutes!" -ForegroundColor Red
    Write-Host "Go get a coffee..." -ForegroundColor Gray
    Write-Host ""

    az aks create `
        --resource-group $ResourceGroup `
        --name $AksName `
        --location $Location `
        --node-count 2 `
        --node-vm-size Standard_B2s_v2 `
        --enable-cluster-autoscaler `
        --min-count 1 `
        --max-count 3 `
        --generate-ssh-keys `
        --attach-acr $AcrName

    Write-Host "AKS cluster created" -ForegroundColor Green
} else {
    Write-Host "Step 5: AKS cluster already exists, skipping creation" -ForegroundColor Yellow

    # Ensure ACR is attached
    Write-Host "Ensuring ACR is attached to AKS..." -ForegroundColor Gray
    az aks update `
        --name $AksName `
        --resource-group $ResourceGroup `
        --attach-acr $AcrName `
        2>$null | Out-Null
}
Write-Host ""

# Step 6: Configure kubectl
Write-Host "Step 6: Configuring kubectl..." -ForegroundColor Yellow
az aks get-credentials `
    --resource-group $ResourceGroup `
    --name $AksName `
    --overwrite-existing

# Verify connection
$nodes = kubectl get nodes --no-headers 2>$null
if ($nodes) {
    Write-Host "kubectl configured successfully" -ForegroundColor Green
    Write-Host "Nodes: $($nodes.Count)" -ForegroundColor Gray
} else {
    Write-Host "ERROR: Failed to connect to AKS cluster" -ForegroundColor Red
    exit 1
}
Write-Host ""

# Step 7: Create namespace and secrets
Write-Host "Step 7: Creating Kubernetes namespace and secrets..." -ForegroundColor Yellow

# Create namespace (idempotent)
kubectl create namespace employee-dw --dry-run=client -o yaml | kubectl apply -f - | Out-Null

# Delete old secret if exists
kubectl delete secret cosmosdb-connection -n employee-dw 2>$null | Out-Null

# Create new secret
kubectl create secret generic cosmosdb-connection `
    --from-literal=connection-string="$CosmosConnection" `
    -n employee-dw | Out-Null

Write-Host "Namespace and secrets created" -ForegroundColor Green
Write-Host ""

# Step 8: Deploy application
Write-Host "Step 8: Deploying application to AKS..." -ForegroundColor Yellow

kubectl apply -f kubernetes/deploy-all-azure.yaml

Write-Host "Application deployed" -ForegroundColor Green
Write-Host ""

# Step 9: Wait for pods to be ready
Write-Host "Step 9: Waiting for pods to be ready..." -ForegroundColor Yellow
Write-Host "This may take 2-3 minutes..." -ForegroundColor Gray

$timeout = 300
$elapsed = 0
$ready = $false

while ($elapsed -lt $timeout -and !$ready) {
    Start-Sleep -Seconds 5
    $elapsed += 5

    $pods = kubectl get pods -n employee-dw --no-headers 2>$null
    $totalPods = ($pods | Measure-Object).Count
    $runningPods = ($pods | Where-Object { $_ -match "Running" } | Measure-Object).Count

    if ($totalPods -gt 0) {
        Write-Host "Pods: $runningPods/$totalPods running..." -ForegroundColor Gray

        if ($runningPods -eq $totalPods) {
            $ready = $true
        }
    }
}

if ($ready) {
    Write-Host "All pods are ready" -ForegroundColor Green
} else {
    Write-Host "WARNING: Some pods may not be ready yet" -ForegroundColor Yellow
    Write-Host "Check status with: kubectl get pods -n employee-dw" -ForegroundColor Gray
}
Write-Host ""

# Step 10: Get External IP
Write-Host "Step 10: Getting External IP..." -ForegroundColor Yellow
Write-Host "Waiting for Load Balancer to assign IP (2-3 minutes)..." -ForegroundColor Gray

$timeout = 180
$elapsed = 0
$externalIP = $null

while ($elapsed -lt $timeout -and !$externalIP) {
    Start-Sleep -Seconds 10
    $elapsed += 10

    $externalIP = kubectl get service data-warehouse -n employee-dw -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>$null

    if (!$externalIP) {
        Write-Host "Still waiting... ($elapsed seconds)" -ForegroundColor Gray
    }
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "  DEPLOYMENT COMPLETE!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""

if ($externalIP) {
    Write-Host "Data Warehouse URL:" -ForegroundColor Cyan
    Write-Host "  http://$externalIP:5000" -ForegroundColor White
    Write-Host ""
    Write-Host "Test Endpoints:" -ForegroundColor Cyan
    Write-Host "  Health Check:     http://$externalIP:5000/health" -ForegroundColor White
    Write-Host "  All Employees:    http://$externalIP:5000/employees" -ForegroundColor White
    Write-Host "  Update Nodes:     http://$externalIP:5000/update/employees" -ForegroundColor White
    Write-Host "  Circuit Breakers: http://$externalIP:5000/circuit-breakers" -ForegroundColor White
    Write-Host ""
    Write-Host "Open in browser now:" -ForegroundColor Cyan
    Write-Host "  Start-Process 'http://$externalIP:5000/health'" -ForegroundColor Yellow
    Write-Host ""

    # Ask to open browser
    $open = Read-Host "Open health check in browser? (Y/n)"
    if ($open -ne 'n') {
        Start-Process "http://$externalIP:5000/health"
    }
} else {
    Write-Host "WARNING: External IP not assigned yet" -ForegroundColor Yellow
    Write-Host "Wait a few more minutes, then check with:" -ForegroundColor Gray
    Write-Host "  kubectl get service data-warehouse -n employee-dw" -ForegroundColor White
}

Write-Host ""
Write-Host "Useful Commands:" -ForegroundColor Cyan
Write-Host "  View pods:        kubectl get pods -n employee-dw" -ForegroundColor Gray
Write-Host "  View services:    kubectl get services -n employee-dw" -ForegroundColor Gray
Write-Host "  View logs:        kubectl logs -f deployment/data-warehouse -n employee-dw" -ForegroundColor Gray
Write-Host "  Scale up:         kubectl scale deployment data-warehouse --replicas=5 -n employee-dw" -ForegroundColor Gray
Write-Host ""
Write-Host "Update Postman base_url to: http://$externalIP:5000" -ForegroundColor Cyan
Write-Host ""
