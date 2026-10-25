$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
& (Join-Path $PSScriptRoot 'setup.ps1')

function Test-Http([string]$url) {
  try { return (Invoke-WebRequest -UseBasicParsing $url -TimeoutSec 2).StatusCode -eq 200 }
  catch { return $false }
}

function Start-Local([string]$name, [string]$script) {
  $arguments = @('-NoProfile','-ExecutionPolicy','Bypass','-File',('"' + (Join-Path $PSScriptRoot $script) + '"'))
  $process = Start-Process -FilePath 'powershell.exe' -ArgumentList $arguments -WorkingDirectory $root `
    -WindowStyle Hidden -RedirectStandardOutput (Join-Path $root "work/$name.stdout.log") `
    -RedirectStandardError (Join-Path $root "work/$name.stderr.log") -PassThru
  Set-Content -LiteralPath (Join-Path $root "work/$name.pid") -Value $process.Id
}

function Start-Vm([string]$name) {
  $distro = if ($env:FORGEPULSE_WSL_DISTRO) { $env:FORGEPULSE_WSL_DISTRO } else { 'Ubuntu' }
  $linuxUser = if ($env:FORGEPULSE_WSL_USER) { $env:FORGEPULSE_WSL_USER } else { $env:USERNAME }
  $pattern = "[p]ython -m vm.$name"
  & wsl.exe -d $distro -u $linuxUser -- pgrep -f $pattern *> $null
  if ($LASTEXITCODE -eq 0) { return }
  $arguments = @('-NoProfile','-ExecutionPolicy','Bypass','-File',('"' + (Join-Path $PSScriptRoot 'start-vm.ps1') + '"'),'-Service',$name)
  $process = Start-Process -FilePath 'powershell.exe' -ArgumentList $arguments -WorkingDirectory $root `
    -WindowStyle Hidden -RedirectStandardOutput (Join-Path $root "work/$name.stdout.log") `
    -RedirectStandardError (Join-Path $root "work/$name.stderr.log") -PassThru
  Set-Content -LiteralPath (Join-Path $root "work/$name.pid") -Value $process.Id
}

if (-not (Test-Http 'http://127.0.0.1:8000/openapi.json')) { Start-Local 'api' 'start.ps1' }
if (-not (Test-Http 'http://127.0.0.1:5173')) { Start-Local 'web' 'start-web.ps1' }
Start-Vm 'modbus'
Start-Vm 'mqtt'

for ($i=0; $i -lt 30; $i++) {
  if ((Test-Http 'http://127.0.0.1:8000/openapi.json') -and (Test-Http 'http://127.0.0.1:5173')) { break }
  Start-Sleep -Seconds 1
}
if (-not (Test-Http 'http://127.0.0.1:8000/openapi.json') -or -not (Test-Http 'http://127.0.0.1:5173')) {
  throw 'API veya React başlamadı. work/*.stderr.log dosyalarını kontrol edin.'
}
Write-Host 'ForgePulse hazır: http://127.0.0.1:5173'
Write-Host 'VM servisleri: Modbus ve MQTT başlatıldı; kamera isteğe bağlıdır.'
