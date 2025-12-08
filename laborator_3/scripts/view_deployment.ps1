# Quick View - Azure Deployment Status
# Employee Data Warehouse

$ResourceGroup = "EmployeeDataWarehouse-RG"
$AksName = "employee-dw-aks"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Azure Deployment Status" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 1. Azure Resources
Write-Host "1. Azure Resources:" -ForegroundColor Yellow
az resource list --resource-group $ResourceGroup -o table
Write-Host ""

# 2. AKS Cluster
Write-Host "2. AKS Cluster Nodes:" -ForegroundColor Yellow
kubectl get nodes
Write-Host ""

# 3. Pods
Write-Host "3. Application Pods:" -ForegroundColor Yellow
kubectl get pods -n employee-dw
Write-Host ""

# 4. Services
Write-Host "4. Services & External IP:" -ForegroundColor Yellow
kubectl get services -n employee-dw
Write-Host ""

# 5. External IP
$ExternalIP = kubectl get service data-warehouse -n employee-dw -o jsonpath='{.status.loadBalancer.ingress[0].ip}'
Write-Host "5. Application URL:" -ForegroundColor Yellow
Write-Host "   http://$ExternalIP:5000" -ForegroundColor Green
Write-Host ""

# 6. Quick Links
Write-Host "6. Quick Links:" -ForegroundColor Yellow
Write-Host "   Azure Portal:   https://portal.azure.com/#@/resource/subscriptions/$(az account show --query id -o tsv)/resourceGroups/$ResourceGroup/overview" -ForegroundColor Cyan
Write-Host "   Health Check:   http://$ExternalIP:5000/health" -ForegroundColor Cyan
Write-Host "   Employees API:  http://$ExternalIP:5000/employees" -ForegroundColor Cyan
Write-Host ""

# 7. Cosmos DB
Write-Host "7. Cosmos DB Status:" -ForegroundColor Yellow
az cosmosdb show --name employee-dw-cosmosdb --resource-group $ResourceGroup --query "{name:name, status:provisioningState, location:location}" -o table
Write-Host ""

# 8. Container Registry Images
Write-Host "8. Docker Images in ACR:" -ForegroundColor Yellow
az acr repository list --name employeedwregistry -o table
Write-Host ""

Write-Host "========================================" -ForegroundColor Green
Write-Host "  Open in browser?" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
$open = Read-Host "Open application in browser? (Y/n)"
if ($open -ne 'n') {
    Start-Process "http://$ExternalIP:5000/health"
    Start-Process "https://portal.azure.com/#@/resource/subscriptions/$(az account show --query id -o tsv)/resourceGroups/$ResourceGroup/overview"
}
