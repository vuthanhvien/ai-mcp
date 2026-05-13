# Load .env
Get-Content "$PSScriptRoot\.env" | ForEach-Object {
    if ($_ -match '^\s*([^#][^=]+)=(.*)$') {
        [System.Environment]::SetEnvironmentVariable($Matches[1].Trim(), $Matches[2].Trim())
    }
}

$port = if ($env:PORT) { $env:PORT } else { "8000" }

Write-Host "=== Ollama MCP HTTP Server ===" -ForegroundColor Cyan
Write-Host "Port   : $port"
Write-Host "Ollama : $env:OLLAMA_HOST"
if ($env:API_KEY) {
    Write-Host "APIKey : $env:API_KEY" -ForegroundColor Yellow
} else {
    Write-Host "APIKey : (none - WARNING: open access!)" -ForegroundColor Red
}
Write-Host ""

# Find cloudflared
$cfBin = $null
$cfCandidates = @(
    "cloudflared",
    "C:\Program Files (x86)\cloudflared\cloudflared.exe",
    "C:\Program Files\cloudflared\cloudflared.exe"
)
foreach ($p in $cfCandidates) {
    if (Get-Command $p -ErrorAction SilentlyContinue) { $cfBin = $p; break }
    if (Test-Path $p) { $cfBin = $p; break }
}

if ($cfBin) {
    Write-Host "Starting Cloudflare Tunnel in background..." -ForegroundColor Green
    $cfJob = Start-Job -ScriptBlock {
        param($p, $bin)
        & $bin tunnel --url "http://localhost:$p" 2>&1
    } -ArgumentList $port, $cfBin

    # Wait up to 15s for tunnel URL
    $tunnelUrl = ""
    $tries = 0
    while ($tries -lt 15 -and -not $tunnelUrl) {
        Start-Sleep -Seconds 1
        $tries++
        $output = Receive-Job $cfJob -Keep 2>&1
        $match = $output | Select-String -Pattern 'https://[a-z0-9-]+\.trycloudflare\.com'
        if ($match) {
            $tunnelUrl = $match.Matches[0].Value
        }
    }

    if ($tunnelUrl) {
        Write-Host ""
        Write-Host "[PUBLIC URL]  $tunnelUrl/mcp" -ForegroundColor Green
        Write-Host ""
        Write-Host "Paste into ~/.claude/settings.json on any remote machine:" -ForegroundColor Cyan
        $config = @"
{
  "mcpServers": {
    "ollama-remote": {
      "type": "http",
      "url": "$tunnelUrl/mcp",
      "headers": { "X-API-Key": "$env:API_KEY" }
    }
  }
}
"@
        Write-Host $config
    } else {
        Write-Host "Tunnel started but URL not detected yet. Check cloudflared logs." -ForegroundColor Yellow
    }
} else {
    Write-Host "cloudflared not found. Install with:" -ForegroundColor Yellow
    Write-Host "  winget install Cloudflare.cloudflared"
    Write-Host ""
    Write-Host "Local URL: http://localhost:$port/mcp" -ForegroundColor Cyan
}

Write-Host ""
Write-Host "Starting MCP server... (Ctrl+C to stop)" -ForegroundColor Cyan

& "$PSScriptRoot\.venv\Scripts\python.exe" "$PSScriptRoot\server.py" http
