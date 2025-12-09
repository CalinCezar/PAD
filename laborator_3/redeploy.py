# ===========================================
# Redeploy Azure - După modificări în cod
# PowerShell Version
# ===========================================

param(
    [string]$Service = "all"
)

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "  Redeploy Azure - Employee Data Warehouse" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""

# Configurare
$AcrName = "employeedwregistry"
$Namespace = "employee-dw"

# Login în ACR
Write-Host "Step 1: Login în Azure Container Registry..." -ForegroundColor Yellow
az acr login --name $AcrName
if ($LASTEXITCODE -ne 0) {
    Write-Host "✗ Eroare la login ACR. Rulează 'az login' mai întâi." -ForegroundColor Red
    exit 1
}
Write-Host "✓ Logged in" -ForegroundColor Green
Write-Host ""

function Rebuild-Service {
    param(
        [string]$ServiceName,
        [string]$Dockerfile,
        [string]$Deployment
    )
    
    Write-Host "--- Rebuild $ServiceName ---" -ForegroundColor Yellow
    
    # Build
    Write-Host "Building..."
    docker build -f $Dockerfile -t "$AcrName.azurecr.io/${ServiceName}:latest" .
    if ($LASTEXITCODE -ne 0) {
        Write-Host "✗ Build failed pentru $ServiceName" -ForegroundColor Red
        return $false
    }
    
    # Push
    Write-Host "Pushing to ACR..."
    docker push "$AcrName.azurecr.io/${ServiceName}:latest"
    if ($LASTEXITCODE -ne 0) {
        Write-Host "✗ Push failed pentru $ServiceName" -ForegroundColor Red
        return $false
    }
    
    # Restart deployment
    Write-Host "Restarting deployment..."
    kubectl rollout restart deployment/$Deployment -n $Namespace
    
    Write-Host "✓ $ServiceName redeployed!" -ForegroundColor Green
    Write-Host ""
    return $true
}

switch ($Service.ToLower()) {
    { $_ -in "data-warehouse", "dw" } {
        Rebuild-Service -ServiceName "data-warehouse" -Dockerfile "data_warehouse/Dockerfile" -Deployment "data-warehouse"
    }
    { $_ -in "json-node", "json" } {
        Rebuild-Service -ServiceName "json-node" -Dockerfile "json_node/Dockerfile" -Deployment "json-node"
    }
    { $_ -in "xml-node", "xml" } {
        Rebuild-Service -ServiceName "xml-node" -Dockerfile "xml_node/Dockerfile" -Deployment "xml-node"
    }
    "all" {
        Write-Host "Reconstruiesc TOATE serviciile..." -ForegroundColor Yellow
        Write-Host ""
        Rebuild-Service -ServiceName "data-warehouse" -Dockerfile "data_warehouse/Dockerfile" -Deployment "data-warehouse"
        Rebuild-Service -ServiceName "json-node" -Dockerfile "json_node/Dockerfile" -Deployment "json-node"
        Rebuild-Service -ServiceName "xml-node" -Dockerfile "xml_node/Dockerfile" -Deployment "xml-node"
    }
    default {
        Write-Host "Serviciu necunoscut: $Service" -ForegroundColor Red
        Write-Host "Opțiuni: data-warehouse, json-node, xml-node, all"
        exit 1
    }
}

Write-Host ""
Write-Host "Step 3: Verificare status..." -ForegroundColor Yellow
kubectl rollout status deployment/data-warehouse -n $Namespace --timeout=60s
kubectl rollout status deployment/json-node -n $Namespace --timeout=60s
kubectl rollout status deployment/xml-node -n $Namespace --timeout=60s

Write-Host ""
Write-Host "Pod-uri:"
kubectl get pods -n $Namespace

Write-Host ""
Write-Host "==========================================" -ForegroundColor Green
Write-Host "  Redeploy Azure complet!" -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Utilizare:"
Write-Host "  .\scripts\redeploy_azure.ps1              # Toate serviciile"
Write-Host "  .\scripts\redeploy_azure.ps1 -Service data-warehouse  # Doar DW"
Write-Host "  .\scripts\redeploy_azure.ps1 -Service json-node       # Doar JSON"
Write-Host "  .\scripts\redeploy_azure.ps1 -Service xml-node        # Doar XML"
Write-Host ""
Write-Host "IP Public:" -ForegroundColor Yellow
kubectl get service data-warehouse -n $Namespace -o jsonpath='{.status.loadBalancer.ingress[0].ip}'
Write-Host ""
Write-Host ""