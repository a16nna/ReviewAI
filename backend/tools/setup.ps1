<#
.SYNOPSIS
  Installs the optional non-Python analyzers (ESLint + security plugin, Checkstyle) and reports what ReviewAI can use.
.DESCRIPTION
  Run from the backend folder with your virtualenv ACTIVE:   .\tools\setup.ps1
  Ruff and Bandit come from `pip install -r requirements.txt`. cppcheck must be installed separately.
  Exit code 0 = every analyzer is available; 1 = something is missing (the list is printed).
#>
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"   # Invoke-WebRequest is very slow with the progress bar on PS 5.1
$ToolsDir = $PSScriptRoot
$BackendDir = Split-Path $ToolsDir -Parent
$Problems = New-Object System.Collections.Generic.List[string]
$CheckstyleUrl = "https://github.com/checkstyle/checkstyle/releases/download/checkstyle-10.18.2/checkstyle-10.18.2-all.jar"

function Has([string]$Name) { return [bool](Get-Command $Name -ErrorAction SilentlyContinue) }

# --- ESLint (JavaScript / TypeScript) -----------------------------------------------------------
if ((Has "node") -and (Has "npm")) {
    Push-Location (Join-Path $ToolsDir "js")
    try {
        npm install --no-audit --no-fund
        if ($LASTEXITCODE -ne 0) { $Problems.Add("npm install failed in tools/js (ESLint not installed)") }
    } finally { Pop-Location }
} else {
    $Problems.Add("Node.js/npm not found: JavaScript/TypeScript analysis unavailable. Install Node 20+ (e.g. winget install OpenJS.NodeJS.LTS) and re-run.")
}

# --- Checkstyle (Java) --------------------------------------------------------------------------
$Jar = Join-Path $ToolsDir "java\checkstyle.jar"
if (Has "java") {
    try {
        Invoke-WebRequest -Uri $CheckstyleUrl -OutFile $Jar -UseBasicParsing
        & java -jar $Jar --version
        if ($LASTEXITCODE -ne 0) { $Problems.Add("Checkstyle was downloaded but does not run (need Java 11+)") }
    } catch {
        $Problems.Add("Could not download Checkstyle: $($_.Exception.Message)")
    }
} else {
    $Problems.Add("Java not found: Java analysis unavailable. Install a JRE 11+ (e.g. winget install EclipseAdoptium.Temurin.21.JRE) and re-run.")
}

# --- cppcheck (C++) -----------------------------------------------------------------------------
$CppCandidates = @("C:\Program Files\Cppcheck\cppcheck.exe", "C:\Program Files (x86)\Cppcheck\cppcheck.exe")
if ((Has "cppcheck") -or ($env:CPPCHECK_PATH -and (Test-Path $env:CPPCHECK_PATH))) {
    Write-Host "cppcheck: found"
} elseif ($CppCandidates | Where-Object { Test-Path $_ }) {
    Write-Host "cppcheck: found in its default install folder (ReviewAI looks there automatically)"
} else {
    $Problems.Add("cppcheck not found: C++ analysis unavailable. Install it (choco install cppcheck, or https://cppcheck.sourceforge.io) and re-run, or set CPPCHECK_PATH to cppcheck.exe.")
}

# --- Report what the backend itself sees (the only result that matters) ----------------------------
Write-Host "`nAnalyzer availability as seen by ReviewAI:"
Push-Location $BackendDir
try {
    python -c "import json; from app import analysis; print(json.dumps(analysis.availability(), indent=2))"
    if ($LASTEXITCODE -ne 0) { $Problems.Add("Could not run the backend check: activate your virtualenv and run 'pip install -r requirements.txt' first") }
} finally { Pop-Location }

if ($Problems.Count -gt 0) {
    Write-Warning "Some analyzers are NOT available (ReviewAI reports them as unavailable and never fakes a scan):"
    $Problems | ForEach-Object { Write-Warning "  - $_" }
    exit 1
}
Write-Host "`nAll analyzers are available."
