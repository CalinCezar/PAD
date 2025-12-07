# PowerShell script to stop Employee Data Warehouse System

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "  Stopping Employee Data Warehouse System" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""

# Stop all containers
Write-Host "Stopping all containers..." -ForegroundColor Yellow
docker-compose down

Write-Host ""
Write-Host "√ All services stopped" -ForegroundColor Green
Write-Host ""
Write-Host "To remove all data including MongoDB volumes:" -ForegroundColor Yellow
Write-Host "  docker-compose down -v" -ForegroundColor White
Write-Host ""
