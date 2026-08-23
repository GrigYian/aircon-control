$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$WebProject = Join-Path $ProjectRoot "react-webview-app"
$ReleaseRoot = Join-Path $ProjectRoot "release"
$ReleaseFolder = Join-Path $ReleaseRoot "AirConControl"
$ReleaseZip = Join-Path $ReleaseRoot "AirConControl-Windows-x64-1.0.0.zip"
$BuildWork = Join-Path $ProjectRoot "build\pyinstaller"
$SpecFile = Join-Path $ProjectRoot "packaging\AirConControl.spec"
$IconGenerator = Join-Path $ProjectRoot "packaging\generate_icon.py"

if (-not (Test-Path -LiteralPath $Python)) {
    throw "Virtual environment not found. Create .venv and install requirements-build.txt first."
}

Push-Location $ProjectRoot
try {
    npm --prefix $WebProject run build
    if ($LASTEXITCODE -ne 0) { throw "React build failed." }

    & $Python $IconGenerator
    if ($LASTEXITCODE -ne 0) { throw "Application icon generation failed." }

    & $Python -m PyInstaller --noconfirm --clean --distpath $ReleaseRoot --workpath $BuildWork $SpecFile
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed." }

    if (-not (Test-Path -LiteralPath (Join-Path $ReleaseFolder "AirConControl.exe"))) {
        throw "Release executable was not created."
    }
    Copy-Item -LiteralPath (Join-Path $ProjectRoot "packaging\DISTRIBUTION_README.txt") -Destination (Join-Path $ReleaseFolder "README.txt") -Force
    if (Test-Path -LiteralPath $ReleaseZip) {
        Remove-Item -LiteralPath $ReleaseZip -Force
    }
    tar.exe -a -c -f $ReleaseZip -C $ReleaseRoot "AirConControl"
    if ($LASTEXITCODE -ne 0) { throw "Release archive creation failed." }
    Write-Host "Release ready: $ReleaseZip"
}
finally {
    Pop-Location
}
