# nanobot-ai | Rasys Local Runner (ASCII Version)

$ErrorActionPreference = "Continue"
$PROJ_DIR = $PSScriptRoot
$BRIDGE_DIR = Join-Path $PROJ_DIR "bridge"
$VENV_DIR = Join-Path $PROJ_DIR ".venv"

Write-Host ""
Write-Host "=== Nanobot Rasys - Local Runner ===" -ForegroundColor Cyan
Write-Host ""

# 1. Database Check
Write-Host "[1/6] Verificando Banco de Dados..." -ForegroundColor Cyan
$dbRunning = docker ps -q --filter "name=nanobot-db" 2>$null
if ($dbRunning) {
    Write-Host "    -> Banco de Dados já está rodando." -ForegroundColor Green
}
else {
    $dbExists = docker ps -aq --filter "name=nanobot-db" 2>$null
    if ($dbExists) {
        Write-Host "    -> Iniciando container existente..." -ForegroundColor Cyan
        docker start nanobot-db
    }
    else {
        Write-Host "    -> Criando novo container Database (pgvector)..." -ForegroundColor Cyan
        docker run -d --name nanobot-db -e POSTGRES_DB=nanobot -e POSTGRES_USER=nanobot -e POSTGRES_PASSWORD=nanobot123 -p 5432:5432 pgvector/pgvector:pg16
    }
    Start-Sleep -Seconds 2
}

# 2. Python Environment
if (!(Test-Path "$VENV_DIR")) {
    Write-Host "[2/6] Criando Ambiente Virtual Python..." -ForegroundColor Yellow
    py -m venv "$VENV_DIR"
}

Write-Host "[2/6] Ativando ambiente Python..." -ForegroundColor Cyan
$VENV_ACTIVATE = Join-Path $VENV_DIR "Scripts\Activate.ps1"
& "$VENV_ACTIVATE"

Write-Host "[2/6] Atualizando Pip e Instalando dependencias..." -ForegroundColor Cyan
python.exe -m pip install --upgrade pip --quiet
if (!(Test-Path "$BRIDGE_DIR")) { New-Item -ItemType Directory -Path "$BRIDGE_DIR" -Force | Out-Null }
pip install -e "$PROJ_DIR" --quiet

# 3. WhatsApp Bridge
Write-Host "[3/6] Preparando WhatsApp Bridge..." -ForegroundColor Cyan
if (!(Test-Path "$BRIDGE_DIR\node_modules")) {
    Set-Location "$BRIDGE_DIR"
    npm install
    Set-Location "$PROJ_DIR"
}

Write-Host "[3/6] Compilando WhatsApp Bridge..." -ForegroundColor Cyan
Set-Location "$BRIDGE_DIR"
npm run build --silent
Set-Location "$PROJ_DIR"

# 4. Environment Variables
$env:DATABASE_URL = "postgresql://nanobot:nanobot123@localhost:5432/nanobot"
$env:WHATSAPP_ENABLED = "true"
$env:WHATSAPP_BRIDGE_URL = "ws://localhost:3001"
$env:WHISPER_API_URL = "http://172.16.51.5:8000/v1/audio/transcriptions"
$env:NANOBOT_AGENTS__DEFAULTS__MODEL = "ollama/qwen3.5:9b-86k"
$env:OLLAMA_API_KEY = "local-no-key-required"
$env:BRIDGE_PORT = "3001"

# 5. Start WhatsApp Bridge
Write-Host ""
Write-Host "[4/6] Iniciando WhatsApp Bridge na porta 3001..." -ForegroundColor Magenta
$bridgeScript = Join-Path $BRIDGE_DIR "dist\index.js"
$bridgeProcess = Start-Process -FilePath "node" -ArgumentList "`"$bridgeScript`"" -PassThru -WindowStyle Normal
Start-Sleep -Seconds 3

# 6. Start Nanobot Gateway
Write-Host ""
Write-Host "=== Iniciando Nanobot Gateway ===" -ForegroundColor Green
Write-Host "Logins e mensagens aparecerão abaixo." -ForegroundColor Yellow
Write-Host ""

try {
    $NANOBOT_EXE = Join-Path $VENV_DIR "Scripts\nanobot.exe"
    & "$NANOBOT_EXE" gateway
}
finally {
    Write-Host "Fechando processos..." -ForegroundColor Yellow
    if ($bridgeProcess) {
        if (!$bridgeProcess.HasExited) {
            Stop-Process -Id $bridgeProcess.Id -Force
        }
    }
}
