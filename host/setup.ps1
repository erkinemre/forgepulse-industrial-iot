$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
$tempPath = Join-Path $root 'work/tmp'
New-Item -ItemType Directory -Force -Path $tempPath | Out-Null
$env:TEMP = $tempPath
$env:TMP = $tempPath
$env:TMPDIR = $tempPath
$venvPython = Join-Path $root '.venv/Scripts/python.exe'
$basePython = $null
if (-not (Test-Path -LiteralPath $venvPython)) {
  $launcher = Get-Command py -ErrorAction SilentlyContinue
  if ($launcher) {
    & $launcher.Source -3 -m venv (Join-Path $root '.venv')
  } else {
    $candidate = Get-Command python -ErrorAction SilentlyContinue
    if ($candidate -and $candidate.Source -notlike '*WindowsApps*') {
      $basePython = $candidate.Source
    } else {
      $basePython = Join-Path $env:USERPROFILE '.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe'
    }
    if (-not (Test-Path -LiteralPath $basePython)) {
      throw 'Python 3.11+ bulunamadı. Python kurup yeniden deneyin.'
    }
    & $basePython -m venv --without-pip (Join-Path $root '.venv')
  }
  if ($LASTEXITCODE -ne 0) { throw 'Python sanal ortamı oluşturulamadı.' }
}
if (-not (Test-Path -LiteralPath (Join-Path $root '.venv/Lib/site-packages/pip'))) {
  & $venvPython -m ensurepip --upgrade
  if ($LASTEXITCODE -ne 0) { throw 'Sanal ortama pip kurulamadı.' }
}
& $venvPython -c 'import fastapi, uvicorn, pymodbus, paho.mqtt, pytest'
if ($LASTEXITCODE -ne 0) {
  & $venvPython -m pip install -e '.[test]'
  if ($LASTEXITCODE -ne 0) { throw 'Python bağımlılıkları kurulamadı.' }
}
& $venvPython (Join-Path $PSScriptRoot 'generate_runtime.py')
if ($LASTEXITCODE -ne 0) { throw 'Çalışma kimlik bilgileri hazırlanamadı.' }
