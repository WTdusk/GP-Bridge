param([string]$Python)

$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
$previousPythonPath = $env:PYTHONPATH
try {
$pythonCandidates = @(
    $Python,
    (Join-Path $PSScriptRoot '.venv\Scripts\python.exe'),
    (Get-Command python -ErrorAction SilentlyContinue).Source,
    "$env:LocalAppData\Programs\Python\Python313\python.exe",
    "$env:LocalAppData\Programs\Python\Python312\python.exe",
    "$env:LocalAppData\Programs\Python\Python311\python.exe"
) | Where-Object { $_ -and (Test-Path $_) }
$python = $null
$localPackages = Join-Path (Get-Location) '.buildenv\Lib\site-packages'
if (Test-Path $localPackages) { $env:PYTHONPATH = $localPackages }
foreach ($candidate in $pythonCandidates) {
    try {
        $ErrorActionPreference = 'Continue'
        & $candidate -c "import sys; assert sys.platform == 'win32', 'Native Windows Python required'; import PyInstaller, tkinter, tkinterdnd2" *> $null
        $ok = ($LASTEXITCODE -eq 0)
        $ErrorActionPreference = 'Stop'
        if ($ok) { $python = $candidate; break }
    } catch { $ErrorActionPreference = 'Stop' }
}
if (-not $python) { throw "PyInstaller-capable Windows Python was not found." }
& $python -m PyInstaller --clean --noconfirm gpbridge.spec
if ($LASTEXITCODE -ne 0) { throw "GUI build failed." }
& $python -m PyInstaller --clean --noconfirm gpbridge_mcp.spec
if ($LASTEXITCODE -ne 0) { throw "MCP build failed." }
if (-not (Test-Path "dist\GPBridge.exe")) { throw "Build failed: dist\GPBridge.exe is missing." }
if (-not (Test-Path "dist\GPBridgeMCP.exe")) { throw "Build failed: dist\GPBridgeMCP.exe is missing." }
$archive = "dist\GPBridge-portable.zip"
if (Test-Path $archive) { Remove-Item -LiteralPath $archive -Force }
$profileStage = "installer\package-stage\GPBridgeData"
$workspaceRoot = (Get-Location).Path
$stagePath = [System.IO.Path]::GetFullPath((Join-Path $workspaceRoot 'installer\package-stage'))
if (-not $stagePath.StartsWith($workspaceRoot.TrimEnd('\') + '\', [System.StringComparison]::OrdinalIgnoreCase)) { throw "Package stage must stay inside the workspace." }
if (Test-Path -LiteralPath $stagePath) { Remove-Item -LiteralPath $stagePath -Recurse -Force }
New-Item -ItemType Directory -Force (Join-Path $profileStage "Profiles") | Out-Null
New-Item -ItemType Directory -Force (Join-Path $profileStage "Profiles\kontakt") | Out-Null
Copy-Item "GPBridgeData\Profiles\kontakt\shreddage_3_5_archtop.json", "GPBridgeData\Profiles\kontakt\shreddage_3_5_archtop.verification.md" (Join-Path $profileStage "Profiles\kontakt") -Force
New-Item -ItemType Directory -Force "dist\GPBridgeData\Profiles" | Out-Null
Copy-Item (Join-Path $profileStage "Profiles\*") "dist\GPBridgeData\Profiles" -Recurse -Force
Compress-Archive -Path "dist\GPBridge.exe", "dist\GPBridgeMCP.exe", "README.md", "AUTHORS.md", "THIRD_PARTY_NOTICES.md", "licenses", "mcp-config.example.json", "AGENT_KONTAKT_PROFILE_WORKFLOW.md", "assets", "profiles", $profileStage -DestinationPath $archive -CompressionLevel Optimal
Write-Host "Built dist\GPBridge.exe"
Write-Host "Built $archive"

# Build a self-contained installer. The legacy C# compiler is part of Windows,
# so this step does not require Inno Setup, .NET restore, or a user-installed SDK.
$installerPayload = "installer\payload.zip"
if (Test-Path $installerPayload) { Remove-Item -LiteralPath $installerPayload -Force }
Compress-Archive -Path "dist\GPBridge.exe", "dist\GPBridgeMCP.exe", "README.md", "AUTHORS.md", "THIRD_PARTY_NOTICES.md", "licenses", "mcp-config.example.json", "AGENT_KONTAKT_PROFILE_WORKFLOW.md", "assets", "profiles", $profileStage -DestinationPath $installerPayload -CompressionLevel Optimal
$csc = "C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe"
if (-not (Test-Path $csc)) { throw "Windows C# compiler was not found." }
& $csc /nologo /target:winexe /platform:x64 /optimize+ /win32icon:assets\gpbridge.ico /resource:installer\payload.zip,payload.zip /out:dist\GPBridge-Setup.exe /reference:System.Windows.Forms.dll /reference:System.Drawing.dll /reference:System.IO.Compression.dll /reference:System.IO.Compression.FileSystem.dll installer\LegacyInstaller.cs
if ($LASTEXITCODE -ne 0) { throw "Installer build failed." }
Write-Host "Built dist\GPBridge-Setup.exe"
} finally {
    $env:PYTHONPATH = $previousPythonPath
    Pop-Location
}
