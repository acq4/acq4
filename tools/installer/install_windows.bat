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
if defined CONDA_EXE if exist "%CONDA_EXE%" goto :eof
for %%P in (conda.exe conda.bat) do (
    for %%Q in ("%%~$PATH:P") do (
        if not "%%~fQ"=="" if exist "%%~fQ" (
            set "CONDA_EXE=%%~fQ"
            goto :eof
        )
    )
)
set "CANDIDATES=%USERPROFILE%\Miniconda3\condabin\conda.bat;%USERPROFILE%\miniconda3\Scripts\conda.exe;%USERPROFILE%\Anaconda3\Scripts\conda.exe;%ProgramData%\Miniconda3\Scripts\conda.exe;C:\Miniconda3\condabin\conda.bat"
for %%C in (%CANDIDATES%) do (
    if exist "%%~fC" (
        set "CONDA_EXE=%%~fC"
        goto :eof
    )
)
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

:ensure_installer_env
    call :resolve_env_path
    if not defined INSTALLER_ENV_PATH goto :eof
    if not exist "%INSTALLER_ENV_PATH%\conda-meta" (
        echo Creating installer environment...
        set "CREATE_LOG=%TEMP%\acq4-conda-create-%RANDOM%.log"
        echo Running: "%CONDA_EXE%" create -y -n "%INSTALLER_ENV_NAME%" python=%PYTHON_VERSION% pip
        powershell -NoProfile -Command "$log = $env:CREATE_LOG; $args = @('create','-y','-n',$env:INSTALLER_ENV_NAME,'python=' + $env:PYTHON_VERSION,'pip'); & $env:CONDA_EXE @args 2>&1 | Tee-Object -FilePath $log; exit $LASTEXITCODE"
        set "CREATE_STATUS=%ERRORLEVEL%"
        if not "%CREATE_STATUS%"=="0" (
            findstr /C:"NoWritableEnvsDirError" "%CREATE_LOG%" >nul 2>&1 && (
                echo Conda could not create the installer environment: no writable envs directories are configured.
            echo Please ensure at least one entry in 'conda info --json' under envs_dirs is writable.
        )
        findstr /C:"NoWritablePkgsDirError" "%CREATE_LOG%" >nul 2>&1 && (
            echo Conda could not download packages: no writable package cache directories are configured.
        )
        type "%CREATE_LOG%"
        del "%CREATE_LOG%" >nul 2>&1
        exit /b %CREATE_STATUS%
    )
    del "%CREATE_LOG%" >nul 2>&1
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
