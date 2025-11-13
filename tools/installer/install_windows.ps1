Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$scriptDir = try {
    if ($MyInvocation.MyCommand.Path) {
        Split-Path -Path $MyInvocation.MyCommand.Path -Parent
    } else {
        $null
    }
} catch {
    $null
}

$installerUrl = 'https://raw.githubusercontent.com/acq4/acq4/main/tools/installer/installer.py'
$installerEnvName = '_acq4_installer_env'
$pythonVersion = '3.12'
$qtPackage = 'pyqt6'
$tomlParserPackage = 'tomli'
$minCondaVersion = [version]'4.14.0'
$minicondaUrl = 'https://repo.anaconda.com/miniconda/Miniconda3-latest-Windows-x86_64.exe'
$minicondaPrefix = Join-Path -Path $env:USERPROFILE -ChildPath 'Miniconda3'
$downloadedInstaller = $null
$installerEnvPath = $null

function Write-Log {
    param([string]$Message)
    Write-Host "[acq4-installer] $Message"
}

function Get-CondaVersionString {
    param([string]$CondaPath)
    try {
        $output = & $CondaPath --version 2>$null
    } catch {
        return $null
    }
    if (-not $output) {
        return $null
    }
    $line = ($output | Select-Object -First 1).Trim()
    if (-not $line) {
        return $null
    }
    $tokens = $line -split '\s+'
    if (-not $tokens) {
        return $null
    }
    return $tokens[-1]
}

function Compare-Version {
    param(
        [string]$Left,
        [string]$Right
    )
    try {
        $v1 = [version]$Left
        $v2 = [version]$Right
    } catch {
        return 0
    }
    return $v1.CompareTo($v2)
}

function Resolve-CandidatePath {
    param([string]$Candidate)
    if ([string]::IsNullOrWhiteSpace($Candidate)) {
        return $null
    }
    try {
        $resolved = Resolve-Path -LiteralPath $Candidate -ErrorAction Stop
        return $resolved.ProviderPath
    } catch {
        return $null
    }
}

function Find-Conda {
    $candidates = @()
    if ($env:CONDA_EXE) {
        $candidates += $env:CONDA_EXE
    }
    foreach ($name in @('conda.exe', 'conda.bat')) {
        $cmd = Get-Command -Name $name -ErrorAction SilentlyContinue
        if ($cmd) {
            $candidates += $cmd.Source
        }
    }
    $candidates += @(
        (Join-Path $env:USERPROFILE 'Miniconda3\condabin\conda.bat'),
        (Join-Path $env:USERPROFILE 'Miniconda3\Scripts\conda.exe'),
        (Join-Path $env:USERPROFILE 'AppData\Local\miniconda3\condabin\conda.bat'),
        (Join-Path $env:USERPROFILE 'AppData\Local\miniconda3\Scripts\conda.exe'),
        (Join-Path $env:USERPROFILE 'Anaconda3\Scripts\conda.exe'),
        (Join-Path $env:ProgramData 'Miniconda3\Scripts\conda.exe'),
        'C:\Miniconda3\condabin\conda.bat'
    )
    $unique = $candidates | Where-Object { $_ } | Select-Object -Unique
    $bestPath = $null
    $bestVersion = $null
    $fallbackPath = $null
    foreach ($candidate in $unique) {
        $resolved = Resolve-CandidatePath -Candidate $candidate
        if (-not $resolved) {
            continue
        }
        $candidateVersion = Get-CondaVersionString -CondaPath $resolved
        if ($candidateVersion) {
            if (-not $bestVersion -or (Compare-Version -Left $candidateVersion -Right $bestVersion) -gt 0) {
                $bestVersion = $candidateVersion
                $bestPath = $resolved
            }
        } elseif (-not $fallbackPath) {
            $fallbackPath = $resolved
        }
    }
    if ($bestPath) {
        if ($bestVersion) {
            Write-Log "Using conda at $bestPath (version $bestVersion)"
        } else {
            Write-Log "Using conda at $bestPath"
        }
        return $bestPath
    }
    if ($fallbackPath) {
        Write-Log "Using conda at $fallbackPath"
        return $fallbackPath
    }
    return $null
}

function Install-Miniconda {
    Write-Log 'Conda executable not found.'
    $reply = Read-Host "Download and install Miniconda to $minicondaPrefix? [y/N]"
    if ($reply -notmatch '^(?i)(y|yes)$') {
        return $null
    }
    $tmpInstaller = Join-Path -Path ([System.IO.Path]::GetTempPath()) -ChildPath ("miniconda-$([guid]::NewGuid().ToString()).exe")
    Write-Log 'Downloading Miniconda installer...'
    try {
        Invoke-WebRequest -Uri $minicondaUrl -OutFile $tmpInstaller -ErrorAction Stop | Out-Null
    } catch {
        if (Test-Path $tmpInstaller) {
            Remove-Item $tmpInstaller -Force
        }
        throw "Failed to download Miniconda: $($_.Exception.Message)"
    }
    Write-Log 'Running Miniconda installer...'
    try {
        $arguments = @(
            '/InstallationType=JustMe',
            '/AddToPath=0',
            '/RegisterPython=0',
            '/S',
            "/D=$minicondaPrefix"
        )
        $process = Start-Process -FilePath $tmpInstaller -ArgumentList $arguments -Wait -PassThru -WindowStyle Hidden
        if ($process.ExitCode -ne 0) {
            throw "Installer exited with code $($process.ExitCode)."
        }
    } finally {
        if (Test-Path $tmpInstaller) {
            Remove-Item $tmpInstaller -Force
        }
    }
    $defaultPaths = @(
        (Join-Path $minicondaPrefix 'condabin\conda.bat'),
        (Join-Path $minicondaPrefix 'Scripts\conda.exe')
    )
    foreach ($path in $defaultPaths) {
        if (Test-Path $path) {
            return (Resolve-CandidatePath -Candidate $path)
        }
    }
    return $null
}

function Check-CondaVersion {
    param([string]$CondaExe)
    $versionString = Get-CondaVersionString -CondaPath $CondaExe
    if (-not $versionString) {
        throw "Unable to determine conda version via '$CondaExe --version'."
    }
    try {
        $currentVersion = [version]$versionString
    } catch {
        throw "Unable to parse conda version '$versionString'."
    }
    if ($currentVersion -lt $minCondaVersion) {
        throw "Conda version $versionString is too old; 'conda run' requires $minCondaVersion or newer."
    }
}

function Get-CondaBasePath {
    param([string]$CondaExe)
    try {
        $output = & $CondaExe info --base 2>$null
    } catch {
        return $null
    }
    if (-not $output) {
        return $null
    }
    $line = ($output | Select-Object -First 1).Trim()
    if (-not $line) {
        return $null
    }
    return $line
}

function Get-InstallerEnvPath {
    param([string]$CondaExe)
    $basePath = Get-CondaBasePath -CondaExe $CondaExe
    if (-not $basePath) {
        return $null
    }
    return Join-Path -Path $basePath -ChildPath ("envs\$installerEnvName")
}

function Ensure-InstallerEnv {
    param([string]$CondaExe)
    $envPath = Get-InstallerEnvPath -CondaExe $CondaExe
    if (-not $envPath) {
        throw 'Unable to determine installer environment path.'
    }
    $script:installerEnvPath = $envPath
    $condaMeta = Join-Path -Path $envPath -ChildPath 'conda-meta'
    if (-not (Test-Path $condaMeta)) {
        Write-Log 'Creating installer environment...'
        $createArgs = @('create', '-y', '-n', $installerEnvName, "python=$pythonVersion", 'pip')
        $createLog = Join-Path -Path ([System.IO.Path]::GetTempPath()) -ChildPath ("acq4-conda-create-$([guid]::NewGuid().ToString()).log")
        try {
            Write-Log ("Running: {0} {1}" -f $CondaExe, ($createArgs -join ' '))
            & $CondaExe @createArgs 2>&1 | Tee-Object -FilePath $createLog | Write-Host
            $exitCode = $LASTEXITCODE
            if ($exitCode -ne 0) {
                $noWritableEnv = Select-String -Path $createLog -Pattern 'NoWritableEnvsDirError' -Quiet -ErrorAction SilentlyContinue
                if ($noWritableEnv) {
                    Write-Log "Conda could not create the installer environment: no writable envs directories are configured."
                    Write-Log "Please ensure at least one entry in 'conda info --json' under envs_dirs is writable."
                }
                $noWritablePkgs = Select-String -Path $createLog -Pattern 'NoWritablePkgsDirError' -Quiet -ErrorAction SilentlyContinue
                if ($noWritablePkgs) {
                    Write-Log 'Conda could not download packages: no writable package cache directories are configured.'
                }
                Get-Content -Path $createLog | Write-Host
                throw "Conda environment creation failed with exit code $exitCode."
            }
        } finally {
            if (Test-Path $createLog) {
                Remove-Item $createLog -Force
            }
        }
    }
    $pipArgs = @('run', '-n', $installerEnvName, 'python', '-m', 'pip', 'install', '--quiet', '--upgrade', $qtPackage, $tomlParserPackage)
    & $CondaExe @pipArgs
    if ($LASTEXITCODE -ne 0) {
        throw 'Failed to install required Python packages into the installer environment.'
    }
}

function Get-InstallerScript {
    if ($scriptDir) {
        $localInstaller = Join-Path -Path $scriptDir -ChildPath 'installer.py'
        if (Test-Path $localInstaller) {
            return $localInstaller
        }
    }
    $tmpPath = Join-Path -Path ([System.IO.Path]::GetTempPath()) -ChildPath ("acq4-installer-$([guid]::NewGuid().ToString()).py")
    Write-Log "Downloading installer from $installerUrl"
    try {
        Invoke-WebRequest -Uri $installerUrl -OutFile $tmpPath -ErrorAction Stop | Out-Null
    } catch {
        if (Test-Path $tmpPath) {
            Remove-Item $tmpPath -Force
        }
        throw "Unable to download installer.py: $($_.Exception.Message)"
    }
    $script:downloadedInstaller = $tmpPath
    return $tmpPath
}

function Run-Installer {
    param(
        [string]$CondaExe,
        [string]$InstallerScript,
        [string[]]$InstallerArgs
    )
    $arguments = @('run', '-n', $installerEnvName, 'python', $InstallerScript) + $InstallerArgs
    & $CondaExe @arguments
    return $LASTEXITCODE
}

function Cleanup-Installer {
    if ($script:downloadedInstaller -and (Test-Path $script:downloadedInstaller)) {
        Remove-Item $script:downloadedInstaller -Force
    }
}

$exitCode = 0
try {
    $condaExe = Find-Conda
    if (-not $condaExe) {
        $condaExe = Install-Miniconda
    }
    if (-not $condaExe) {
        throw 'Failed to locate or install conda.'
    }
    $env:CONDA_EXE = $condaExe
    Check-CondaVersion -CondaExe $condaExe
    Ensure-InstallerEnv -CondaExe $condaExe
    if (-not $installerEnvPath) {
        $installerEnvPath = Get-InstallerEnvPath -CondaExe $condaExe
    }
    $installerScript = Get-InstallerScript
    $exitCode = Run-Installer -CondaExe $condaExe -InstallerScript $installerScript -InstallerArgs $args
} catch {
    Write-Error $_
    if (-not $exitCode) {
        $exitCode = 1
    }
} finally {
    Cleanup-Installer
}
exit $exitCode
