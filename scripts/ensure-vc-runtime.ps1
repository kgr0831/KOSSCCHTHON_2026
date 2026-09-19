$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$repoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$installer = Join-Path $repoRoot '.runtime\tools\vc_redist.x64.exe'
try {
    New-Item -ItemType Directory -Path (Split-Path -Parent $installer) -Force | Out-Null
    Write-Host '[setup] Windows needs the Microsoft C++ runtime. Downloading the signed Microsoft installer; Windows may request administrator approval.'
    Invoke-WebRequest -UseBasicParsing -Uri 'https://aka.ms/vc14/vc_redist.x64.exe' -OutFile $installer -TimeoutSec 180
    $signature = Get-AuthenticodeSignature -LiteralPath $installer
    if ($signature.Status -ne 'Valid' -or $signature.SignerCertificate.Subject -notmatch 'O=Microsoft Corporation') { throw 'Invalid signature' }
    $installed = Start-Process -FilePath $installer -ArgumentList '/install','/quiet','/norestart' -Verb RunAs -WindowStyle Hidden -Wait -PassThru
    if ($installed.ExitCode -notin @(0, 1638, 3010)) { throw 'Installer failed' }
    exit 0
} catch {
    Write-Host '[setup] Microsoft runtime setup did not complete. Retry and accept its Windows installation prompt.'
    exit 1
}
