# Build Docker images directly in Azure (no local Docker needed)
# Uses Azure Container Registry Build Tasks

$ResourceGroup = "EmployeeDataWarehouse-RG"
$AcrName = "employeedwregistry"

Write-Host "Building images in Azure Container Registry..." -ForegroundColor Cyan
Write-Host "This builds directly in Azure - no local Docker needed!" -ForegroundColor Yellow
Write-Host ""

# Build Data Warehouse
Write-Host "Building data-warehouse in Azure..." -ForegroundColor Yellow
az acr build `
    --registry $AcrName `
    --resource-group $ResourceGroup `
    --image data-warehouse:latest `
    --file data_warehouse/Dockerfile `
    .

# Build JSON Node
Write-Host "Building json-node in Azure..." -ForegroundColor Yellow
az acr build `
    --registry $AcrName `
    --resource-group $ResourceGroup `
    --image json-node:latest `
    --file json_node/Dockerfile `
    .

# Build XML Node
Write-Host "Building xml-node in Azure..." -ForegroundColor Yellow
az acr build `
    --registry $AcrName `
    --resource-group $ResourceGroup `
    --image xml-node:latest `
    --file xml_node/Dockerfile `
    .

Write-Host ""
Write-Host "All images built successfully in Azure!" -ForegroundColor Green
Write-Host ""
Write-Host "Now run: .\DEPLOY_NOW.ps1 -SkipDockerBuild" -ForegroundColor Cyan
