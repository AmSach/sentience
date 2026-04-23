# Sentience Windows Installer (PowerShell)
# Run as Administrator

param(
    [switch]$Uninstall
)

$ErrorActionPreference = "Stop"
$InstallDir = "$env:LOCALAPPDATA\Sentience"
$PythonUrl = "https://www.python.org/ftp/python/3.11.8/python-3.11.8-amd64.exe"

function Write-Status {
    param([string]$Message)
    Write-Host "[$(Get-Date -Format 'HH:mm:ss')] $Message" -ForegroundColor Cyan
}

if ($Uninstall) {
    Write-Status "Uninstalling Sentience..."
    if (Test-Path $InstallDir) {
        Remove-Item -Recurse -Force $InstallDir
    }
    # Remove from PATH
    $path = [Environment]::GetEnvironmentVariable("PATH", "User")
    $path = $path -replace [regex]::Escape($InstallDir), ""
    [Environment]::SetEnvironmentVariable("PATH", $path, "User")
    Write-Status "Uninstalled successfully."
    exit 0
}

Write-Status "Installing Sentience..."
Write-Status "Install directory: $InstallDir"

# Check Python
$pythonCmd = $null
try {
    $pythonCmd = Get-Command python -ErrorAction Stop
    $version = & python --version 2>&1
    Write-Status "Found Python: $version"
} catch {
    Write-Status "Python not found. Installing Python 3.11..."
    
    $pythonInstaller = "$env:TEMP\python-installer.exe"
    Invoke-WebRequest -Uri $PythonUrl -OutFile $pythonInstaller
    
    Start-Process -FilePath $pythonInstaller -ArgumentList "/quiet InstallAllUsers=0 PrependPath=1" -Wait
    
    # Refresh environment
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
    
    $pythonCmd = Get-Command python -ErrorAction Stop
    Write-Status "Python installed successfully."
}

# Create install directory
New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null

# Copy files
Write-Status "Copying files..."
$currentDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Copy-Item -Recurse -Force "$currentDir\*" $InstallDir -Exclude @("install.ps1", "*.pyc", "__pycache__")

# Install dependencies
Write-Status "Installing dependencies..."
Set-Location $InstallDir

& python -m pip install --upgrade pip --quiet
& python -m pip install -r requirements.txt --quiet

# Install Playwright browsers
Write-Status "Installing Playwright browsers..."
& python -m playwright install chromium

# Create launcher batch file
$launcherContent = @"
@echo off
cd /d "$InstallDir"
python cli.py %*
"@
Set-Content -Path "$InstallDir\sentience.bat" -Value $launcherContent

# Add to PATH
$path = [Environment]::GetEnvironmentVariable("PATH", "User")
if ($path -notlike "*$InstallDir*") {
    [Environment]::SetEnvironmentVariable("PATH", "$path;$InstallDir", "User")
    Write-Status "Added to PATH."
}

# Create desktop shortcut
$WScriptShell = New-Object -ComObject WScript.Shell
$shortcut = $WScriptShell.CreateShortcut("$env:USERPROFILE\Desktop\Sentience.lnk")
$shortcut.TargetPath = "$InstallDir\sentience.bat"
$shortcut.WorkingDirectory = $InstallDir
$shortcut.Description = "Sentience - Local AI Computer"
$shortcut.Save()

Write-Status "Installation complete!"
Write-Host ""
Write-Host "To start Sentience:" -ForegroundColor Green
Write-Host "  1. Open a new terminal" -ForegroundColor White
Write-Host "  2. Run: sentience" -ForegroundColor White
Write-Host "  Or double-click the desktop shortcut" -ForegroundColor White
Write-Host ""
Write-Host "First run will ask for your API key." -ForegroundColor Yellow
