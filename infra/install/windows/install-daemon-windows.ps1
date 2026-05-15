# SelfFork body daemon — Windows installer (.msi path).
#
# Run from an elevated PowerShell. The MSI is downloaded from the SelfFork
# release CDN, then registered as a Windows service.

$ErrorActionPreference = "Stop"

$Version = "0.5.0"
$Url = "https://releases.selffork.dev/v$Version/SelfForkDaemon.msi"
$Tmp = "$env:TEMP\SelfForkDaemon.msi"

Write-Host "→ downloading $Url"
Invoke-WebRequest -Uri $Url -OutFile $Tmp

Write-Host "→ installing MSI"
msiexec /i "$Tmp" /quiet

Write-Host "→ registering service"
sc.exe create SelfForkDaemon binPath= "C:\Program Files\SelfFork\selffork-daemon.exe" start= auto
sc.exe start SelfForkDaemon

Write-Host "✓ daemon installed; check status with: sc query SelfForkDaemon"
