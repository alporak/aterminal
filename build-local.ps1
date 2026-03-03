# build-local.ps1
# Script to build the executable locally, similar to the GitHub Actions workflow

Write-Host "==== Installing Dependencies ====" -ForegroundColor Green
python -m pip install --upgrade pip
pip install -r requirements.txt
# Make sure numpy is installed (required by pandas and folium)
pip install numpy
pip install pyinstaller==6.3.0

Write-Host "==== Setting up UPX ====" -ForegroundColor Green
if (-not (Test-Path "upx-temp")) {
    mkdir upx-temp
}

if (-not (Test-Path "upx-temp\upx-4.2.4-win64\upx.exe")) {
    Write-Host "Downloading UPX..." -ForegroundColor Yellow
    Invoke-WebRequest -Uri "https://github.com/upx/upx/releases/download/v4.2.4/upx-4.2.4-win64.zip" -OutFile "upx-temp\upx.zip"
    Expand-Archive -Path "upx-temp\upx.zip" -DestinationPath "upx-temp" -Force
}

$env:PATH = "$PWD\upx-temp\upx-4.2.4-win64;$env:PATH"
Write-Host "UPX added to PATH for this session" -ForegroundColor Green

Write-Host "==== Cleaning Build Directories ====" -ForegroundColor Green
if (Test-Path "build") { Remove-Item -Recurse -Force build }
if (Test-Path "dist") { Remove-Item -Recurse -Force dist }

Write-Host "==== Building Executable ====" -ForegroundColor Green

# Check if debug parameter was passed
$debugMode = $args -contains "-debug"
if ($debugMode) {
    Write-Host "Running in DEBUG mode - will create a console window" -ForegroundColor Yellow
    # Create a simpler build for debugging purposes
    pyinstaller main.py --name aterminal_debug --onefile --clean --add-data "config.json;." --hidden-import numpy
} else {
    # Use the spec file for the optimized build
    pyinstaller aterminal.spec --noconfirm --clean
}

Write-Host "==== Verifying Build ====" -ForegroundColor Green

# Check which executable we should verify based on debug mode
$exeName = if ($debugMode) { "aterminal_debug.exe" } else { "aterminal.exe" }
$exePath = "dist\$exeName"

if (Test-Path $exePath) {
    Write-Host "Build successful - EXE file created at $exePath" -ForegroundColor Green
    
    # Get file size
    $exeSize = (Get-Item $exePath).Length / 1MB
    Write-Host "Executable size: $([math]::Round($exeSize, 2)) MB" -ForegroundColor Cyan
    
    # Only create ZIP for non-debug builds
    if (-not $debugMode) {
        # Create ZIP archive
        Write-Host "==== Creating ZIP Archive ====" -ForegroundColor Green
        Compress-Archive -Path $exePath -DestinationPath "dist\Teltonika_Device_Server.zip" -Force
        Write-Host "ZIP archive created at dist\Teltonika_Device_Server.zip" -ForegroundColor Green
    }
    
    Write-Host "To run the executable, use: $exePath" -ForegroundColor Green
    if ($debugMode) {
        Write-Host "Debug build will show console output - check for error messages" -ForegroundColor Yellow
    }
} else {
    Write-Host "Build failed - EXE file not found: $exePath" -ForegroundColor Red
}

Write-Host "==== Build Process Complete ====" -ForegroundColor Green
