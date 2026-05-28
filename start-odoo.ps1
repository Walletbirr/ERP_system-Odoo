$ErrorActionPreference = 'Stop'

$dockerBin = "C:\Program Files\Docker\Docker\resources\bin"
if (Test-Path $dockerBin) {
  $env:PATH = "$dockerBin;$env:PATH"
}

$dockerExe = "docker"
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
  $candidate = "C:\Program Files\Docker\Docker\resources\bin\docker.exe"
  if (Test-Path $candidate) {
    $dockerExe = $candidate
  } else {
    Write-Error "Docker CLI not found. Install Docker Desktop and reopen terminal."
  }
}

& $dockerExe compose up -d
& $dockerExe compose ps
Write-Host "Odoo should be available at http://localhost:8069"
