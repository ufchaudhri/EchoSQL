# Prerequisites:
# 1. Ensure Docker Desktop is running.
# 2. Ensure Ollama is installed and in your PATH.
# 3. Ensure Node.js/npm is installed.
# 4. Ensure backend virtual environment exists at 'backend/venv'.
# 5. Ensure 'npm install' has been run in the 'frontend/' directory.

$components = @{
    # Starts Docker containers for pgvector and Redis
    "Docker Stack (pgvector + Redis)" = { docker compose up -d }
    
    # Starts the Ollama inference engine
    "Ollama"              = { Start-Process ollama -ArgumentList "serve" -WindowStyle Hidden }
    
    # Starts the FastAPI backend server
    "FastAPI Backend"     = { 
        Get-Process -Name "python" -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -like "*uvicorn*" } | Stop-Process -Force
        Start-Process powershell -ArgumentList "-Command `".\venv\Scripts\activate; python -m uvicorn main:app --port 8000`"" -WorkingDirectory "backend" -NoNewWindow 
    }
    
    # Starts the Next.js frontend development server
    "Next.js Frontend"    = { 
        Get-Process -Name "node" -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -like "*next-dev*" } | Stop-Process -Force
        Start-Process npm -ArgumentList "run dev" -WorkingDirectory "frontend" -NoNewWindow 
    }

}

$failed = @()

Write-Host "Starting EchoSQL components..." -ForegroundColor Cyan

foreach ($name in $components.Keys) {
    try {
        Write-Host "Starting $name..." -NoNewline
        & $components[$name]
        Write-Host " [OK]" -ForegroundColor Green
    } catch {
        Write-Host " [FAILED]" -ForegroundColor Red
        $failed += $name
    }
}

if ($failed.Count -gt 0) {
    Write-Host "`nThe following components failed to start:" -ForegroundColor Yellow
    foreach ($f in $failed) { Write-Host "- $f" }
} else {
    Write-Host "`nAll components started successfully." -ForegroundColor Green
}
