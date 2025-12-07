# PowerShell script to start Employee Data Warehouse System

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "  Starting Employee Data Warehouse System" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""

# Check if Docker is running
try {
    docker info | Out-Null
    Write-Host "√ Docker is running" -ForegroundColor Green
} catch {
    Write-Host "× Docker is not running. Please start Docker Desktop first." -ForegroundColor Red
    exit 1
}

# Check if docker-compose is available
try {
    docker-compose version | Out-Null
    Write-Host "√ docker-compose is available" -ForegroundColor Green
} catch {
    Write-Host "× docker-compose not found. Please install docker-compose." -ForegroundColor Red
    exit 1
}

# Stop any existing containers
Write-Host ""
Write-Host "Stopping any existing containers..." -ForegroundColor Yellow
docker-compose down

# Build and start services
Write-Host ""
Write-Host "Building and starting services..." -ForegroundColor Yellow
docker-compose up -d --build

# Wait for services to be healthy
Write-Host ""
Write-Host "Waiting for services to be healthy..." -ForegroundColor Yellow
Start-Sleep -Seconds 10

# Check service health
Write-Host ""
Write-Host "Checking service health..." -ForegroundColor Yellow

function Test-ServiceHealth {
    param (
        [string]$ServiceName,
        [int]$Port
    )

    $maxAttempts = 30
    $attempt = 1

    while ($attempt -le $maxAttempts) {
        try {
            $response = Invoke-WebRequest -Uri "http://localhost:$Port/health" -UseBasicParsing -TimeoutSec 2
            if ($response.StatusCode -eq 200) {
                Write-Host "√ $ServiceName is healthy" -ForegroundColor Green
                return $true
            }
        } catch {
            Write-Host "  Waiting for $ServiceName... (attempt $attempt/$maxAttempts)" -ForegroundColor Gray
            Start-Sleep -Seconds 2
            $attempt++
        }
    }

    Write-Host "× $ServiceName failed to start" -ForegroundColor Red
    return $false
}

$jsonHealthy = Test-ServiceHealth -ServiceName "JSON Node" -Port 5001
$xmlHealthy = Test-ServiceHealth -ServiceName "XML Node" -Port 5002
$dwHealthy = Test-ServiceHealth -ServiceName "Data Warehouse" -Port 5000

if ($jsonHealthy -and $xmlHealthy -and $dwHealthy) {
    Write-Host ""
    Write-Host "==========================================" -ForegroundColor Green
    Write-Host "  System Started Successfully!" -ForegroundColor Green
    Write-Host "==========================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "Services available at:" -ForegroundColor Cyan
    Write-Host "  - Data Warehouse: http://localhost:5000" -ForegroundColor White
    Write-Host "  - JSON Node:      http://localhost:5001" -ForegroundColor White
    Write-Host "  - XML Node:       http://localhost:5002" -ForegroundColor White
    Write-Host "  - MongoDB:        localhost:27017" -ForegroundColor White
    Write-Host ""
    Write-Host "Next steps:" -ForegroundColor Cyan
    Write-Host "  1. Seed data: python scripts\seed_data.py" -ForegroundColor White
    Write-Host "  2. Test endpoints: python scripts\test_endpoints.py" -ForegroundColor White
    Write-Host "  3. View logs: docker-compose logs -f" -ForegroundColor White
    Write-Host "  4. Stop system: docker-compose down" -ForegroundColor White
    Write-Host ""
} else {
    Write-Host ""
    Write-Host "× Some services failed to start. Check logs with: docker-compose logs" -ForegroundColor Red
    exit 1
}
