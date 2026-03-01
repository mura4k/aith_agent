# run.ps1
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# Go to repo root (folder where this script lives)
Set-Location -Path $PSScriptRoot

if (-not (Test-Path ".env")) {
  Write-Host "ERROR: .env not found. Copy .env.example -> .env and fill tokens/paths." -ForegroundColor Red
  exit 1
}

# Load .env into process env
Get-Content ".env" | ForEach-Object {
  $line = $_.Trim()
  if ($line -eq "" -or $line.StartsWith("#")) { return }

  # split only on first '='
  $idx = $line.IndexOf("=")
  if ($idx -lt 1) { return }

  $key = $line.Substring(0, $idx).Trim()
  $val = $line.Substring($idx + 1).Trim()

  # remove surrounding quotes if present
  if (($val.StartsWith('"') -and $val.EndsWith('"')) -or ($val.StartsWith("'") -and $val.EndsWith("'"))) {
    $val = $val.Substring(1, $val.Length - 2)
  }

  [System.Environment]::SetEnvironmentVariable($key, $val, "Process")
}

function Require-Env($name) {
  $v = [System.Environment]::GetEnvironmentVariable($name, "Process")
  if ([string]::IsNullOrWhiteSpace($v)) {
    Write-Host "ERROR: Missing $name in .env" -ForegroundColor Red
    exit 1
  }
  return $v
}

$TELEGRAM_BOT_TOKEN = Require-Env "TELEGRAM_BOT_TOKEN"
$OPENROUTER_API_KEY = Require-Env "OPENROUTER_API_KEY"
$GOOGLE_SA_JSON      = Require-Env "GOOGLE_SA_JSON"

if (-not (Test-Path $GOOGLE_SA_JSON)) {
  Write-Host "ERROR: GOOGLE_SA_JSON file not found at: $GOOGLE_SA_JSON" -ForegroundColor Red
  exit 1
}

# Default REDIS_URL if not set
$REDIS_URL = [System.Environment]::GetEnvironmentVariable("REDIS_URL", "Process")
if ([string]::IsNullOrWhiteSpace($REDIS_URL)) {
  $REDIS_URL = "redis://localhost:6379/0"
  [System.Environment]::SetEnvironmentVariable("REDIS_URL", $REDIS_URL, "Process")
}

# Create venv if missing
if (-not (Test-Path ".venv")) {
  python -m venv .venv
}

# Activate venv
& ".\.venv\Scripts\Activate.ps1"

# Upgrade pip + install deps
python -m pip install --upgrade pip
pip install -r requirements.txt

# Try to start Redis via Docker if REDIS_URL points to localhost
if ($REDIS_URL -match "^redis://(localhost|127\.0\.0\.1):(\d+)/") {
  $redisPort = [int]$Matches[2]

  $dockerExists = Get-Command docker -ErrorAction SilentlyContinue
  if ($dockerExists) {
    # check if container exists
    $existing = docker ps -a --filter "name=uni_agent_redis" --format "{{.Names}}" 2>$null
    if (-not $existing) {
      Write-Host "Starting Redis via Docker on port $redisPort..."
      docker run --name uni_agent_redis -d -p "$redisPort`:6379" redis:7 | Out-Null
    } else {
      # ensure running
      $running = docker ps --filter "name=uni_agent_redis" --format "{{.Names}}" 2>$null
      if (-not $running) {
        Write-Host "Redis container exists but not running. Starting..."
        docker start uni_agent_redis | Out-Null
      }
    }
  } else {
    Write-Host "Note: Docker not found. If Redis isn't running, start it manually or set REDIS_URL to another Redis." -ForegroundColor Yellow
  }
}

# Run the bot
python -m app.main