# nanobot-ai | Rasys Local Runner

$ErrorActionPreference = "Continue"
$PROJ_DIR = $PSScriptRoot
$BRIDGE_DIR = Join-Path $PROJ_DIR "bridge"
$VENV_DIR = Join-Path $PROJ_DIR ".venv"

Write-Host ""
Write-Host "=== Nanobot Rasys - Local Runner ===" -ForegroundColor Cyan
Write-Host ""

# 1. Update from GitHub
Write-Host "[1/5] Atualizando código..." -ForegroundColor Cyan
git pull origin main

# 2. Database Check
Write-Host "[2/5] Verificando Banco de Dados..." -ForegroundColor Cyan
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

# 3. Python Environment
if (!(Test-Path "$VENV_DIR")) {
    Write-Host "[3/5] Criando Ambiente Virtual..." -ForegroundColor Yellow
    py -m venv "$VENV_DIR"
}

Write-Host "[3/5] Ativando ambiente e instalando dependências..." -ForegroundColor Cyan
$VENV_ACTIVATE = Join-Path $VENV_DIR "Scripts\Activate.ps1"
& "$VENV_ACTIVATE"
python.exe -m pip install --upgrade pip --quiet
pip install -e "$PROJ_DIR" --quiet

# 4. WhatsApp Bridge Build
Write-Host "[4/5] Preparando Bridge do WhatsApp..." -ForegroundColor Cyan
if (!(Test-Path "$BRIDGE_DIR\node_modules")) {
    Set-Location "$BRIDGE_DIR"
    npm install
    Set-Location "$PROJ_DIR"
}
Set-Location "$BRIDGE_DIR"
npm run build --silent
Set-Location "$PROJ_DIR"

# 5. Configurar Ambiente e Testar Conectividade
Write-Host "[5/5] Configurando ambiente e testando conectividade..." -ForegroundColor Cyan

$env:NANOBOT_DATABASE_URL = "postgresql://nanobot:nanobot123@localhost:5432/nanobot"
$env:BRAVE_API_KEY = "" # Adicione sua chave aqui para pesquisa na web
$env:WHATSAPP_ENABLED = "true"
$env:WHATSAPP_ALLOW_FROM = "*"
$env:WHATSAPP_BRIDGE_URL = "ws://localhost:3001"
$env:BRIDGE_PORT = "3001"

# Endereços dos serviços (Públicos via Reverse Proxy)
$OLLAMA_BASE = "https://ollama.rasys.net.br/v1"
$WHISPER_URL = "https://whisper.rasys.net.br/v1/audio/transcriptions"

# Configurações para o Nanobot (Modo Custom/Direct para máxima estabilidade)
$env:NANOBOT_AGENTS__DEFAULTS__MODEL = "custom/qwen3.5:9b-86k"
$env:NANOBOT_PROVIDERS__CUSTOM__API_BASE = "$OLLAMA_BASE"
$env:NANOBOT_PROVIDERS__CUSTOM__API_KEY = "local-no-key-required"
$env:WHISPER_API_URL = "$WHISPER_URL"

# Teste de Conexão
Write-Host "    -> Verificando Ollama ($OLLAMA_BASE)..." -NoNewline
try {
    $ollamaTest = Invoke-WebRequest -Uri "$OLLAMA_BASE/models" -Method Get -TimeoutSec 5 -UseBasicParsing -ErrorAction SilentlyContinue
    if ($ollamaTest.StatusCode -eq 200) { Write-Host " [OK]" -ForegroundColor Green } else { Write-Host " [Status: $($ollamaTest.StatusCode)]" -ForegroundColor Yellow }
} catch {
    Write-Host " [FALHA] - Servidor não respondeu!" -ForegroundColor Red -BackgroundColor Black
}

Write-Host "    -> Verificando Whisper ($WHISPER_URL)..." -NoNewline
try {
    $whisperTest = Invoke-WebRequest -Uri "$($WHISPER_URL.Replace('/v1/audio/transcriptions', '/docs'))" -Method Get -TimeoutSec 5 -UseBasicParsing -ErrorAction SilentlyContinue
    if ($whisperTest.StatusCode -eq 200) { Write-Host " [OK]" -ForegroundColor Green } else { Write-Host " [Aviso: $($whisperTest.StatusCode)]" -ForegroundColor Yellow }
} catch {
    Write-Host " [FALHA] - Servidor não respondeu!" -ForegroundColor Red -BackgroundColor Black
}

# Telegram (Ativado com o token fornecido)
$env:TELEGRAM_ENABLED = "true"
$env:TELEGRAM_TOKEN = "8436144323:AAEPjla33hAsODgtXYcWTpaP8A9P_xeizoI"
$env:TELEGRAM_ALLOW_FROM = "*"

# 6. Iniciar Nanobot
Write-Host ""
Write-Host "=== Iniciando Nanobot Gateway ===" -ForegroundColor Green
Write-Host "O QR CODE aparecerá abaixo no terminal." -ForegroundColor Yellow
Write-Host ">>> POSSIBILIDADE CERTEIRA: Se o QR Code falhar no terminal, abra:" -ForegroundColor Cyan
Write-Host ">>> http://localhost:3002" -ForegroundColor White -BackgroundColor Blue
Write-Host ""

$NANOBOT_EXE = Join-Path $VENV_DIR "Scripts\nanobot.exe"
& "$NANOBOT_EXE" gateway
