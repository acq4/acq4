@echo off
setlocal enabledelayedexpansion

set "SCRIPT_DIR="
if exist "%~f0" (
    set "SCRIPT_DIR=%~dp0"
)
set "DOWNLOADED_INSTALLER="
set "RESULT=0"
set "INSTALLER_URL=https://raw.githubusercontent.com/acq4/acq4/main/tools/installer/installer.py"
set "INSTALLER_ENV_NAME=_acq4_installer_env"
set "PYTHON_VERSION=3.12"
set "QT_PACKAGE=pyqt6"
set "TOML_PARSER_PACKAGE=tomli"
set "MIN_CONDA_VERSION=4.14.0"
set "MINICONDA_URL=https://repo.anaconda.com/miniconda/Miniconda3-latest-Windows-x86_64.exe"
set "MINICONDA_PREFIX=%USERPROFILE%\Miniconda3"
call :find_conda
if not defined CONDA_EXE (
    call :install_miniconda
)
if not defined CONDA_EXE (
    echo Failed to locate or install conda. Exiting.
    exit /b 1
)

call :check_conda_version
if errorlevel 1 exit /b 1

call :ensure_installer_env
call :download_installer
if not defined INSTALLER_SCRIPT (
    echo Failed to prepare installer script.
    set "RESULT=1"
    goto :cleanup_exit
)

call "%CONDA_EXE%" run -n "%INSTALLER_ENV_NAME%" python "%INSTALLER_SCRIPT%" %*
set "RESULT=%ERRORLEVEL%"
goto :cleanup_exit

:cleanup_exit
call :cleanup_installer
exit /b %RESULT%

:find_conda
set "BEST_CONDA="
set "BEST_VERSION="
set "FALLBACK_CONDA="
if defined CONDA_EXE (
    call :consider_conda "%CONDA_EXE%"
)
for %%P in (conda.exe conda.bat) do (
    for %%Q in ("%%~$PATH:P") do (
        if not "%%~fQ"=="" (
            call :consider_conda "%%~fQ"
        )
    )
)
for %%C in ("%USERPROFILE%\Miniconda3\condabin\conda.bat" "%USERPROFILE%\miniconda3\Scripts\conda.exe" "%USERPROFILE%\AppData\Local\miniconda3\condabin\conda.bat" "%USERPROFILE%\AppData\Local\miniconda3\Scripts\conda.exe" "%USERPROFILE%\Anaconda3\Scripts\conda.exe" "%ProgramData%\Miniconda3\Scripts\conda.exe" "C:\Miniconda3\condabin\conda.bat") do (
    call :consider_conda "%%~fC"
)
if defined HOME (
    for %%C in ("%HOME%\Miniconda3\condabin\conda.bat" "%HOME%\Miniconda3\Scripts\conda.exe" "%HOME%\miniconda3\condabin\conda.bat" "%HOME%\miniconda3\Scripts\conda.exe" "%HOME%\AppData\Local\Miniconda3\condabin\conda.bat" "%HOME%\AppData\Local\Miniconda3\Scripts\conda.exe" "%HOME%\AppData\Local\miniconda3\condabin\conda.bat" "%HOME%\AppData\Local\miniconda3\Scripts\conda.exe") do (
        call :consider_conda "%%~fC"
    )
)
if defined LOCALAPPDATA (
    for %%C in ("%LOCALAPPDATA%\Miniconda3\condabin\conda.bat" "%LOCALAPPDATA%\Miniconda3\Scripts\conda.exe" "%LOCALAPPDATA%\miniconda3\condabin\conda.bat" "%LOCALAPPDATA%\miniconda3\Scripts\conda.exe") do (
        call :consider_conda "%%~fC"
    )
)
if defined BEST_CONDA (
    set "CONDA_EXE=%BEST_CONDA%"
    if defined BEST_VERSION (
        echo Using conda at %CONDA_EXE% (version %BEST_VERSION%^)
    ) else (
        echo Using conda at %CONDA_EXE%
    )
) else (
    if defined FALLBACK_CONDA (
        set "CONDA_EXE=%FALLBACK_CONDA%"
        echo Using conda at %CONDA_EXE%
    )
)
set "BEST_CONDA="
set "BEST_VERSION="
set "FALLBACK_CONDA="
goto :eof

:consider_conda
set "ACQ4_CAND_PATH=%~1"
if "%ACQ4_CAND_PATH%"=="" goto :eof
for %%I in ("%ACQ4_CAND_PATH%") do set "ACQ4_CAND_PATH=%%~fI"
if not exist "%ACQ4_CAND_PATH%" goto :eof
set "CAND_VERSION="
for /f "tokens=1,2" %%S in ('cmd /d /c ""%ACQ4_CAND_PATH%" --version 2^>nul"') do (
    if not defined CAND_VERSION (
        if "%%T"=="" (
            set "CAND_VERSION=%%~S"
        ) else (
            set "CAND_VERSION=%%~T"
        )
    )
)
if defined CAND_VERSION (
    if not defined BEST_VERSION (
        set "BEST_VERSION=%CAND_VERSION%"
        set "BEST_CONDA=%ACQ4_CAND_PATH%"
    ) else (
        call :compare_versions "%CAND_VERSION%" "%BEST_VERSION%"
        if "%ACQ4_VER_CMP%"=="1" (
            set "BEST_VERSION=%CAND_VERSION%"
            set "BEST_CONDA=%ACQ4_CAND_PATH%"
        )
    )
) else if not defined FALLBACK_CONDA (
    set "FALLBACK_CONDA=%ACQ4_CAND_PATH%"
)
set "CAND_VERSION="
set "ACQ4_VER_CMP="
goto :eof

:compare_versions
set "ACQ4_VER_CMP="
powershell -NoProfile -Command "$a = '%~1'; $b = '%~2'; try { $v1 = [version]$a; $v2 = [version]$b } catch { exit 3 }; if ($v1 -gt $v2) { exit 1 } elseif ($v1 -lt $v2) { exit 2 } else { exit 0 }" >nul 2>&1
set "ACQ4_VER_CMP=%ERRORLEVEL%"
goto :eof

:install_miniconda
echo Conda executable not found.
set /p "RESP=Download and install Miniconda to %MINICONDA_PREFIX%? [y/N] "
if /I not "%RESP%"=="Y" (
    if /I not "%RESP%"=="Yes" goto :eof
)
set "TMP_INSTALLER=%TEMP%\miniconda-%RANDOM%.exe"
echo Downloading Miniconda installer...
powershell -NoProfile -Command "Invoke-WebRequest -Uri '%MINICONDA_URL%' -OutFile '%TMP_INSTALLER%'" || goto :fail_install

echo Running Miniconda installer...
"%TMP_INSTALLER%" /InstallationType=JustMe /AddToPath=0 /RegisterPython=0 /S /D=%MINICONDA_PREFIX%
del "%TMP_INSTALLER%" >nul 2>&1
if exist "%MINICONDA_PREFIX%\condabin\conda.bat" (
    set "CONDA_EXE=%MINICONDA_PREFIX%\condabin\conda.bat"
) else if exist "%MINICONDA_PREFIX%\Scripts\conda.exe" (
    set "CONDA_EXE=%MINICONDA_PREFIX%\Scripts\conda.exe"
)
goto :eof

:fail_install
echo Failed to install Miniconda.
if exist "%TMP_INSTALLER%" del "%TMP_INSTALLER%" >nul 2>&1
set "CONDA_EXE="
goto :eof

:check_conda_version
set "CONDA_VERSION="
for /f "tokens=2 delims= " %%V in ('"%CONDA_EXE%" --version 2^>nul') do (
    if not defined CONDA_VERSION set "CONDA_VERSION=%%~V"
)
if not defined CONDA_VERSION (
    echo Unable to determine conda version via "%CONDA_EXE% --version".
    exit /b 1
)
powershell -NoProfile -Command "$req = [version]'%MIN_CONDA_VERSION%'; $raw = '%CONDA_VERSION%'; try { $cur = [version]($raw.Split()[0]) } catch { $cur = $null }; if (-not $cur) { exit 2 }; if ($cur -lt $req) { exit 1 }" >nul 2>&1
set "ACQ4_CONDA_VERSION_RESULT=%ERRORLEVEL%"
if "%ACQ4_CONDA_VERSION_RESULT%"=="1" (
    echo Conda version %CONDA_VERSION% is too old; 'conda run' requires %MIN_CONDA_VERSION% or newer.
    exit /b 1
) else if "%ACQ4_CONDA_VERSION_RESULT%"=="2" (
    echo Unable to parse conda version "%CONDA_VERSION%".
    exit /b 1
)
set "ACQ4_CONDA_VERSION_RESULT="
exit /b 0

:ensure_installer_env
call :resolve_env_path
if not defined INSTALLER_ENV_PATH goto :eof
set "CREATE_LOG="
if not exist "%INSTALLER_ENV_PATH%\conda-meta" (
    echo Creating installer environment...
    set "CREATE_LOG=%TEMP%\acq4-conda-create-%RANDOM%.log"
    set "PYTHON_SPEC=python=%PYTHON_VERSION%"
    echo Running: "%CONDA_EXE%" create -y -n "%INSTALLER_ENV_NAME%" %PYTHON_SPEC% pip
    set "ACQ4_CREATE_CMD=""%CONDA_EXE%" create -y -n "%INSTALLER_ENV_NAME%" %PYTHON_SPEC% pip"
    powershell -NoProfile -Command "$ErrorActionPreference = 'SilentlyContinue'; $log = $env:CREATE_LOG; $cmd = $env:ACQ4_CREATE_CMD; cmd.exe /d /c $cmd 2>&1 | Tee-Object -FilePath $log; exit $LASTEXITCODE"
    set "CREATE_STATUS=%ERRORLEVEL%"
    set "ACQ4_CREATE_CMD="
    set "PYTHON_SPEC="
    if not "%CREATE_STATUS%"=="0" (
        if defined CREATE_LOG if exist "%CREATE_LOG%" (
            findstr /C:"NoWritableEnvsDirError" "%CREATE_LOG%" >nul 2>&1 && (
                echo Conda could not create the installer environment: no writable envs directories are configured.
                echo Please ensure at least one entry in 'conda info --json' under envs_dirs is writable.
            )
            findstr /C:"NoWritablePkgsDirError" "%CREATE_LOG%" >nul 2>&1 && (
                echo Conda could not download packages: no writable package cache directories are configured.
            )
            type "%CREATE_LOG%"
            del "%CREATE_LOG%" >nul 2>&1
        )
        exit /b %CREATE_STATUS%
    )
    if defined CREATE_LOG if exist "%CREATE_LOG%" del "%CREATE_LOG%" >nul 2>&1
    set "CREATE_LOG="
)
call "%CONDA_EXE%" run -n "%INSTALLER_ENV_NAME%" python -m pip install --quiet --upgrade %QT_PACKAGE% %TOML_PARSER_PACKAGE%
goto :eof

:download_installer
set "INSTALLER_SCRIPT="
if defined SCRIPT_DIR if exist "%SCRIPT_DIR%installer.py" (
    set "INSTALLER_SCRIPT=%SCRIPT_DIR%installer.py"
    goto :eof
)
set "TMP_INSTALLER="
for /f "usebackq tokens=* delims=" %%T in (`powershell -NoProfile -Command "Join-Path ([System.IO.Path]::GetTempPath()) ('acq4-installer-' + [guid]::NewGuid().ToString() + '.py')"`) do (
    if not defined TMP_INSTALLER set "TMP_INSTALLER=%%~T"
)
if not defined TMP_INSTALLER (
    echo Unable to create temporary file for installer download.
    goto :eof
)
echo Downloading installer from %INSTALLER_URL%
set "ACQ4_INSTALLER_OUTFILE=%TMP_INSTALLER%"
powershell -NoProfile -Command "try { Invoke-WebRequest -Uri '%INSTALLER_URL%' -OutFile $env:ACQ4_INSTALLER_OUTFILE -ErrorAction Stop } catch { Write-Host 'Download failed:' $_.Exception.Message; exit 1 }" >nul 2>&1
set "PS_STATUS=%ERRORLEVEL%"
set "ACQ4_INSTALLER_OUTFILE="
if not "%PS_STATUS%"=="0" (
    echo Unable to download installer.py.
    if exist "%TMP_INSTALLER%" del "%TMP_INSTALLER%" >nul 2>&1
    goto :eof
)
set "PS_STATUS="
set "DOWNLOADED_INSTALLER=%TMP_INSTALLER%"
set "INSTALLER_SCRIPT=%TMP_INSTALLER%"
goto :eof

:cleanup_installer
if defined DOWNLOADED_INSTALLER if exist "%DOWNLOADED_INSTALLER%" del "%DOWNLOADED_INSTALLER%" >nul 2>&1
goto :eof

:resolve_env_path
set "INSTALLER_ENV_PATH="
set "CONDA_BASE="
for /f "usebackq tokens=* delims=" %%B in (`cmd /c ""%CONDA_EXE%" info --base"`) do (
    if not defined CONDA_BASE set "CONDA_BASE=%%~B"
)
if not defined CONDA_BASE goto :eof
set "INSTALLER_ENV_PATH=%CONDA_BASE%\envs\%INSTALLER_ENV_NAME%"
goto :eof
