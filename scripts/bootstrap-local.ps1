param([Parameter(ValueFromRemainingArguments = $true)][string[]]$AppArguments)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$repoRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$toolsRoot = Join-Path $repoRoot '.runtime\tools'
$utf8 = New-Object Text.UTF8Encoding($false)
$startupMutex = $null
$ownsStartup = $false
$connectorMode = $AppArguments.Count -ge 1 -and $AppArguments[0] -eq '--connector'

function Install-VerifiedZip($Uri, $Checksum, $ArchiveName, $Destination) {
    $archive = Join-Path $toolsRoot $ArchiveName
    if (-not (Test-Path -LiteralPath $archive) -or
        (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant() -ne $Checksum) {
        Write-Host "[setup] Downloading $ArchiveName from its official release..."
        Invoke-WebRequest -UseBasicParsing -Uri $Uri -OutFile $archive -TimeoutSec 180
    }
    if ((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant() -ne $Checksum) {
        throw 'Release checksum mismatch. Installation stopped; retry the download.'
    }
    Expand-Archive -LiteralPath $archive -DestinationPath $Destination -Force
}

function Test-NodeInstallation($Directory) {
    foreach ($relative in @('node.exe', 'npm.cmd', 'node_modules\npm\bin\npm-cli.js', '.dudri-install-complete')) {
        if (-not (Test-Path -LiteralPath (Join-Path $Directory $relative))) { return $false }
    }
    $version = & (Join-Path $Directory 'node.exe') --version 2>$null
    if ($LASTEXITCODE -ne 0 -or $version -ne 'v22.23.2') { return $false }
    $null = & (Join-Path $Directory 'node.exe') (Join-Path $Directory 'node_modules\npm\bin\npm-cli.js') --version 2>$null
    return $LASTEXITCODE -eq 0
}

function Invoke-ExistingLauncher {
    $python = Join-Path $repoRoot 'backend\.venv\Scripts\python.exe'
    Write-Host '[setup] This workspace is already in use. Checking its existing services without changing dependencies...'
    if (-not (Test-Path -LiteralPath $python)) {
        throw 'Startup already in progress. Wait for the original terminal to finish installing, then retry.'
    }
    & $python (Join-Path $repoRoot 'scripts\run_local.py') --reuse-only @AppArguments | Out-Host
    return $LASTEXITCODE
}

function Initialize-Environment {
    $template = Get-Content -LiteralPath (Join-Path $repoRoot '.env.example') -Encoding UTF8
    $dotenv = Join-Path $repoRoot '.env'
    if (-not (Test-Path -LiteralPath $dotenv)) {
        [IO.File]::WriteAllLines($dotenv, $template, $utf8)
        Write-Host '[setup] Created .env from the blank template. Add your own DB URI and AI key; values are never printed.'
        return
    }
    $present = @{}
    foreach ($line in [IO.File]::ReadAllLines($dotenv)) {
        if ($line -match '^\s*(?:export\s+)?([A-Z][A-Z0-9_]*)\s*=') { $present[$Matches[1]] = $true }
    }
    $missing = @($template | Where-Object { $_ -match '^([A-Z][A-Z0-9_]*)=' -and -not $present.ContainsKey($Matches[1]) })
    if ($missing.Count) {
        [IO.File]::AppendAllText($dotenv, "`r`n# Added missing local configuration fields.`r`n" + ($missing -join "`r`n") + "`r`n", $utf8)
        Write-Host "[setup] Added $($missing.Count) missing .env fields. Existing values were preserved."
    }
}

try {
    if (-not [Environment]::Is64BitOperatingSystem) { throw '64-bit Windows 10 or newer is required.' }
    # A paired connector is allowed to run beside the local development app.
    # Reuse its managed Python without touching a live environment or taking
    # ownership of the app supervisor.
    $existingPython = Join-Path $repoRoot 'backend\.venv\Scripts\python.exe'
    if ($connectorMode -and (Test-Path -LiteralPath $existingPython)) {
        Push-Location (Join-Path $repoRoot 'backend')
        try { & $existingPython -m app.cli_connector @AppArguments } finally { Pop-Location }
        exit $LASTEXITCODE
    }
    # Held through the supervisor lifetime, including the first installation.
    # A concurrent BAT must never run uv sync against a live virtual environment.
    $hasher = [Security.Cryptography.SHA256]::Create()
    $rootHash = [BitConverter]::ToString($hasher.ComputeHash($utf8.GetBytes($repoRoot.ToLowerInvariant()))).Replace('-', '')
    $hasher.Dispose()
    $startupMutex = New-Object Threading.Mutex($false, ('Local\DudriStartup-' + $rootHash))
    try { $ownsStartup = $startupMutex.WaitOne(0) } catch [Threading.AbandonedMutexException] { $ownsStartup = $true }
    if (-not $ownsStartup) { $code = Invoke-ExistingLauncher; exit $code }
    # Also cover a directly started supervisor or a surviving child whose outer
    # bootstrap was closed. Inspect only the exact workspace Python executable.
    $venvPython = Join-Path $repoRoot 'backend\.venv\Scripts\python.exe'
    $activePython = @(Get-CimInstance Win32_Process -Filter "Name = 'python.exe' OR Name = 'pythonw.exe'" |
        Where-Object { $_.ExecutablePath -and [IO.Path]::GetFullPath($_.ExecutablePath) -eq $venvPython })
    if ($activePython.Count) { $code = Invoke-ExistingLauncher; exit $code }
    New-Item -ItemType Directory -Path $toolsRoot -Force | Out-Null
    Initialize-Environment
    # Matching x64 runtimes; Windows 11 ARM can run them through x64 emulation.
    $uvDir = Join-Path $toolsRoot 'uv-0.12.17'
    $uvExe = Join-Path $uvDir 'uv.exe'
    $uvStamp = Join-Path $uvDir '.dudri-install-complete'
    if (-not (Test-Path -LiteralPath $uvExe) -or -not (Test-Path -LiteralPath $uvStamp)) {
        Install-VerifiedZip 'https://github.com/astral-sh/uv/releases/download/0.12.17/uv-x86_64-pc-windows-msvc.zip' `
            'a252121d5b59398fcb137c6ea448176459a44010f33f67e0072305a637119ca7' 'uv-0.12.17.zip' $uvDir
        $null = & $uvExe --version
        if ($LASTEXITCODE -ne 0) { throw 'Runtime verification failed for uv. Retry startup.' }
        [IO.File]::WriteAllText($uvStamp, '0.12.17', $utf8)
    }
    $nodeDir = Join-Path $toolsRoot 'node-v22.23.2-win-x64'
    $nodeExe = Join-Path $nodeDir 'node.exe'
    if (-not (Test-NodeInstallation $nodeDir)) {
        Install-VerifiedZip 'https://nodejs.org/dist/v22.23.2/node-v22.23.2-win-x64.zip' `
            '1177b4137ba5adaa56354ae40f1080c7450e8ae09cecb47da459d1c52ac99f97' 'node-v22.23.2-win-x64.zip' $toolsRoot
        # Written after extraction; an interrupted unzip cannot look complete.
        [IO.File]::WriteAllText((Join-Path $nodeDir '.dudri-install-complete'), '22.23.2', $utf8)
        if (-not (Test-NodeInstallation $nodeDir)) { throw 'Runtime verification failed for Node/npm. Retry startup.' }
    }
    $env:PATH = "$nodeDir;$uvDir;$env:PATH"
    $env:UV_PYTHON_INSTALL_DIR = Join-Path $toolsRoot 'python'
    $env:UV_CACHE_DIR = Join-Path $repoRoot '.runtime\cache\uv'
    $env:PLAYWRIGHT_BROWSERS_PATH = Join-Path $toolsRoot 'browsers'
    $pythonRequest = 'cpython-3.12.14-windows-x86_64-none'
    Write-Host '[setup] Preparing managed Python and locked backend dependencies...'
    & $uvExe python install $pythonRequest --no-bin --no-registry
    if ($LASTEXITCODE -ne 0) { throw 'Python download failed. Check network access to GitHub and retry.' }
    & $uvExe sync --locked --no-build --managed-python --python $pythonRequest --directory (Join-Path $repoRoot 'backend')
    if ($LASTEXITCODE -ne 0) { throw 'Backend dependency installation failed. Check the package download message above.' }
    if ($connectorMode) {
        & $uvExe run --no-sync --directory (Join-Path $repoRoot 'backend') python -m app.cli_connector @AppArguments
    } else {
        & $uvExe run --no-sync --directory (Join-Path $repoRoot 'backend') python (Join-Path $repoRoot 'scripts\run_local.py') @AppArguments
    }
    exit $LASTEXITCODE
} catch {
    Write-Host '[setup] Could not finish startup. Check internet access, available disk space and permission to write this project folder.'
    if ($_.Exception.Message -match '^(Release checksum|64-bit Windows|Python download|Backend dependency|Runtime verification|Startup already)') { Write-Host $_.Exception.Message }
    exit 1
} finally {
    if ($startupMutex) {
        if ($ownsStartup) { $startupMutex.ReleaseMutex() }
        $startupMutex.Dispose()
    }
}
