# Quick Deploy Script pentru Azure
# Presupune că ai deja Cosmos DB creat

Write-Host "=== Azure Quick Deploy ===" -ForegroundColor Cyan

# Variabile
$ResourceGroup = "EmployeeDataWarehouse-RG"
$AcrName = "employeedwregistry"
$AksName = "employee-dw-aks"
$CosmosDbName = "employee-dw-cosmosdb"

# Pas 1: Obține Connection String
Write-Host "Step 1: Getting Cosmos DB connection string..." -ForegroundColor Yellow
$CosmosConnection = az cosmosdb keys list `
  --name $CosmosDbName `
  --resource-group $ResourceGroup `
  --type connection-strings `
  --query "connectionStrings[0].connectionString" -o tsv

Write-Host "Connection string retrieved" -ForegroundColor Green

# Pas 2: Creează ACR
Write-Host "Step 2: Creating Azure Container Registry..." -ForegroundColor Yellow
az acr create `
  --resource-group $ResourceGroup `
  --name $AcrName `
  --sku Basic `
  --admin-enabled true

Write-Host "ACR created" -ForegroundColor Green

# Pas 3: Build și Push imagini
Write-Host "Step 3: Building and pushing Docker images..." -ForegroundColor Yellow
az acr login --name $AcrName

docker build -f data_warehouse/Dockerfile -t "$AcrName.azurecr.io/data-warehouse:latest" .
docker push "$AcrName.azurecr.io/data-warehouse:latest"

docker build -f json_node/Dockerfile -t "$AcrName.azurecr.io/json-node:latest" .
docker push "$AcrName.azurecr.io/json-node:latest"

docker build -f xml_node/Dockerfile -t "$AcrName.azurecr.io/xml-node:latest" .
docker push "$AcrName.azurecr.io/xml-node:latest"

Write-Host "Images pushed to ACR" -ForegroundColor Green

# Pas 4: Creează AKS
Write-Host "Step 4: Creating AKS cluster (this takes 10-15 minutes)..." -ForegroundColor Yellow
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

Write-Host "AKS cluster created" -ForegroundColor Green

# Pas 5: Get AKS credentials
Write-Host "Step 5: Getting AKS credentials..." -ForegroundColor Yellow
az aks get-credentials `
  --resource-group $ResourceGroup `
  --name $AksName `
  --overwrite-existing

Write-Host "Credentials configured" -ForegroundColor Green

# Pas 6: Creează namespace și secret
Write-Host "Step 6: Creating namespace and secrets..." -ForegroundColor Yellow
kubectl create namespace employee-dw

kubectl create secret generic cosmosdb-connection `
  --from-literal=connection-string="$CosmosConnection" `
  -n employee-dw

Write-Host "Secrets created" -ForegroundColor Green

# Pas 7: Deploy aplicația
Write-Host "Step 7: Deploying application..." -ForegroundColor Yellow
kubectl apply -f kubernetes/deploy-all-azure.yaml

Write-Host "Application deployed" -ForegroundColor Green

# Pas 8: Wait for pods
Write-Host "Step 8: Waiting for pods to be ready..." -ForegroundColor Yellow
kubectl wait --for=condition=ready pod -l app=data-warehouse -n employee-dw --timeout=300s

Write-Host "Pods are ready" -ForegroundColor Green

# Pas 9: Get External IP
Write-Host "Step 9: Getting external IP..." -ForegroundColor Yellow
Write-Host "Waiting for external IP assignment (this may take 2-3 minutes)..." -ForegroundColor Yellow
Start-Sleep -Seconds 30

$ExternalIp = kubectl get service data-warehouse -n employee-dw -o jsonpath='{.status.loadBalancer.ingress[0].ip}'

Write-Host ""
Write-Host "==========================================" -ForegroundColor Green
Write-Host "  Deployment Complete!" -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Data Warehouse URL: http://$ExternalIp:5000" -ForegroundColor White
Write-Host "Health Check: http://$ExternalIp:5000/health" -ForegroundColor White
Write-Host "Employees API: http://$ExternalIp:5000/employees" -ForegroundColor White
Write-Host ""
Write-Host "Test it:" -ForegroundColor Yellow
Write-Host "  curl http://$ExternalIp:5000/health" -ForegroundColor Gray
Write-Host "  curl http://$ExternalIp:5000/employees" -ForegroundColor Gray
Write-Host ""
