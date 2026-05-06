param(
    [string]$TraderPath = "..\traders\trader_current.py"
)

$ErrorActionPreference = "Stop"

function Write-Info {
    param([string]$Message)
    Write-Host $Message
}

function Ensure-Cargo {
    $cargo = Get-Command cargo -ErrorAction SilentlyContinue
    if (-not $cargo) {
        Write-Host "Please manually install Rust from https://rustup.rs, then rerun this script."
        exit 1
    }
}

function Use-Gnu-Toolchain-If-Necessary {
    $link = Get-Command link.exe -ErrorAction SilentlyContinue
    $hasMsvcLinker = $false

    if ($link) {
        $source = $link.Source
        if ($source -match "Visual Studio|BuildTools|VC\\Tools|MSVC") {
            $hasMsvcLinker = $true
        }
    }

    if ($hasMsvcLinker) {
        Write-Info "MSVC linker detected on PATH."
        return
    }

    $rustup = Get-Command rustup -ErrorAction SilentlyContinue
    if (-not $rustup) {
        Write-Host "Rust is installed but rustup is not available, so the GNU toolchain cannot be selected automatically."
        exit 1
    }

    Write-Info "MSVC linker not found. Switching to the GNU Rust toolchain."
    & rustup default stable-x86_64-pc-windows-gnu
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }

    & rustup component add rust-mingw
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}

function Resolve-ExistingPath {
    param(
        [string]$BaseDirectory,
        [string]$InputPath
    )

    if ([System.IO.Path]::IsPathRooted($InputPath)) {
        return (Resolve-Path $InputPath).Path
    }

    $candidate = Join-Path $BaseDirectory $InputPath
    return (Resolve-Path $candidate).Path
}

function Ensure-Repository {
    param([string]$RepoDirectory)

    if (Test-Path $RepoDirectory) {
        Write-Info "Repository already exists at $RepoDirectory"
        return
    }

    Write-Info "Cloning prosperity_rust_backtester..."
    git clone https://github.com/GeyzsoN/prosperity_rust_backtester $RepoDirectory
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}

function Sync-Round3Data {
    param(
        [string]$ProjectRoot,
        [string]$RepoDirectory
    )

    $sourceDataDir = Join-Path $ProjectRoot "data"
    $targetDataDir = Join-Path $RepoDirectory "datasets\round3"
    New-Item -ItemType Directory -Force -Path $targetDataDir | Out-Null

    $requiredFiles = @(
        "prices_round_3_day_0.csv",
        "prices_round_3_day_1.csv",
        "prices_round_3_day_2.csv",
        "trades_round_3_day_0.csv",
        "trades_round_3_day_1.csv",
        "trades_round_3_day_2.csv"
    )

    foreach ($fileName in $requiredFiles) {
        $sourceFile = Join-Path $sourceDataDir $fileName
        $targetFile = Join-Path $targetDataDir $fileName

        if (Test-Path $sourceFile) {
            Copy-Item -Force $sourceFile $targetFile
        }
    }

    $missing = @()
    foreach ($fileName in $requiredFiles) {
        $targetFile = Join-Path $targetDataDir $fileName
        if (-not (Test-Path $targetFile)) {
            $missing += $fileName
        }
    }

    if ($missing.Count -gt 0) {
        Write-Host "Missing Round 3 CSVs in prosperity_rust_backtester/datasets/round3/:"
        foreach ($fileName in $missing) {
            Write-Host "  $fileName"
        }
        Write-Host "Copy the CSVs into the project's data folder and rerun this script."
        exit 1
    }

    Write-Info "Round 3 dataset verified in $targetDataDir"
}

function Copy-Trader {
    param(
        [string]$ScriptDirectory,
        [string]$RepoDirectory,
        [string]$TraderPathValue
    )

    $resolvedTrader = Resolve-ExistingPath -BaseDirectory $ScriptDirectory -InputPath $TraderPathValue
    $targetTrader = Join-Path $RepoDirectory "traders\latest_trader.py"

    Copy-Item -Force $resolvedTrader $targetTrader
    Write-Info "Copied trader to $targetTrader"
}

function Run-Backtester {
    param([string]$RepoDirectory)

    Push-Location $RepoDirectory
    try {
        Write-Info "Building Rust backtester..."
        & cargo build --release
        if ($LASTEXITCODE -ne 0) {
            exit $LASTEXITCODE
        }

        Write-Info "Running Rust backtester..."
        & cargo run --release -- --trader traders/latest_trader.py --dataset round3
        if ($LASTEXITCODE -ne 0) {
            exit $LASTEXITCODE
        }
    }
    finally {
        Pop-Location
    }
}

$scriptDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = (Resolve-Path (Join-Path $scriptDirectory "..")).Path
$repoDirectory = Join-Path $scriptDirectory "prosperity_rust_backtester"

Push-Location $scriptDirectory
try {
    Ensure-Cargo
    Use-Gnu-Toolchain-If-Necessary
    Ensure-Repository -RepoDirectory $repoDirectory
    Sync-Round3Data -ProjectRoot $projectRoot -RepoDirectory $repoDirectory
    Copy-Trader -ScriptDirectory $scriptDirectory -RepoDirectory $repoDirectory -TraderPathValue $TraderPath
    Run-Backtester -RepoDirectory $repoDirectory
}
finally {
    Pop-Location
}
