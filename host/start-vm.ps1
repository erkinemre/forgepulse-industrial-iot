param(
  [Parameter(Mandatory=$true)]
  [ValidateSet('modbus','mqtt','camera')]
  [string]$Service,
  [string]$CameraUrl = ''
)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$distro = if ($env:FORGEPULSE_WSL_DISTRO) { $env:FORGEPULSE_WSL_DISTRO } else { 'Ubuntu' }
$linuxUser = if ($env:FORGEPULSE_WSL_USER) { $env:FORGEPULSE_WSL_USER } else { $env:USERNAME }
$linuxRoot = (& wsl.exe -d $distro -u $linuxUser -- wslpath -a $root).Trim()
if ($LASTEXITCODE -ne 0 -or -not $linuxRoot) { throw 'Ubuntu WSL2 proje yoluna erişemiyor.' }
$script = "$linuxRoot/vm/run_$Service.sh"
if ($Service -eq 'mqtt') {
  & wsl.exe -d $distro -u root -- systemctl start mosquitto
  if ($LASTEXITCODE -ne 0) { throw 'Mosquitto başlatılamadı.' }
}
if ($Service -eq 'camera') {
  if (-not $CameraUrl) { throw 'Kamera için -CameraUrl http://telefon-ip:8080/stream.mjpg verin.' }
  & wsl.exe -d $distro -u $linuxUser -- bash $script $CameraUrl --preview
} else {
  & wsl.exe -d $distro -u $linuxUser -- bash $script
}
