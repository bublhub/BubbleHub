$ErrorActionPreference = "Stop"

$Repo = if ($env:AGEOS_REPO) { $env:AGEOS_REPO } else { "ageos-labs/ageos-runtime" }
$Version = if ($env:AGEOS_VERSION) { $env:AGEOS_VERSION } else { "latest" }

if ($Version -eq "latest") {
    $InstallUrl = "https://github.com/$Repo/releases/latest/download/install.sh"
} else {
    $InstallUrl = "https://github.com/$Repo/releases/download/$Version/install.sh"
}

function ConvertTo-BashSingleQuoted {
    param([string]$Value)
    return "'" + $Value.Replace("'", "'\''") + "'"
}

if ($env:OS -eq "Windows_NT") {
    if (-not (Get-Command wsl.exe -ErrorAction SilentlyContinue)) {
        throw "AgeOS installs on Linux. Install WSL first, then rerun this command."
    }

    $QuotedUrl = ConvertTo-BashSingleQuoted $InstallUrl
    $QuotedRepo = ConvertTo-BashSingleQuoted $Repo
    $QuotedVersion = ConvertTo-BashSingleQuoted $Version
    $Command = "tmp=`$(mktemp) && curl -fsSL $QuotedUrl -o `$tmp && AGEOS_REPO=$QuotedRepo AGEOS_VERSION=$QuotedVersion bash `$tmp"
    wsl.exe bash -lc $Command
    exit $LASTEXITCODE
}

$TempScript = New-TemporaryFile
try {
    Invoke-WebRequest -Uri $InstallUrl -OutFile $TempScript
    $env:AGEOS_REPO = $Repo
    $env:AGEOS_VERSION = $Version
    bash $TempScript
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}
finally {
    Remove-Item -Force $TempScript -ErrorAction SilentlyContinue
}
