@echo off
setlocal enabledelayedexpansion

echo ===============================================================================
echo ACQ4 Windows Bootstrap Installer
echo ===============================================================================
echo.

set "SCRIPT_DIR="
if exist "%~f0" (
    set "SCRIPT_DIR=%~dp0"
)
set "DOWNLOADED_INSTALLER="
set "RESULT=0"
set "INSTALLER_URL=https://raw.githubusercontent.com/acq4/acq4/main/tools/installer/installer.py"
set "INSTALLER_ENV_NAME=_acq4_installer"
set "PYTHON_VERSION=3.12"
set "QT_PACKAGE=pyqt6"
set "TOML_PARSER_PACKAGE=tomli"
set "MIN_CONDA_VERSION=4.14.0"
set "MINICONDA_URL=https://repo.anaconda.com/miniconda/Miniconda3-latest-Windows-x86_64.exe"
set "MINICONDA_PREFIX=%USERPROFILE%\Miniconda3"
echo Searching for conda installation...
call :find_conda
if not defined CONDA_EXE (
    echo Conda not found, attempting to install Miniconda...
    call :install_miniconda
)
if not defined CONDA_EXE (
    echo ERROR: Failed to locate or install conda. Exiting.
    exit /b 1
)

echo Checking conda version...
call :check_conda_version
if errorlevel 1 (
    echo ERROR: Conda version check failed
    exit /b 1
)

call :ensure_installer_env
echo.
echo Downloading installer script...
call :download_installer
if not defined INSTALLER_SCRIPT (
    echo ERROR: Failed to prepare installer script.
    set "RESULT=1"
    goto :cleanup_exit
)

echo.
echo ===============================================================================
echo Starting the ACQ4 installation script...
echo ===============================================================================
echo.
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

rem Check if CONDA_EXE is already defined
if defined CONDA_EXE (
    call :consider_conda "%CONDA_EXE%"
)

rem Check PATH for conda
for %%P in (conda.exe conda.bat) do (
    for %%Q in ("%%~$PATH:P") do (
        if not "%%~fQ"=="" (
            call :consider_conda "%%~fQ"
        )
    )
)

rem Check most common conda installation locations
for %%C in (
    "%USERPROFILE%\miniconda3\Scripts\conda.exe"
    "%USERPROFILE%\anaconda3\Scripts\conda.exe"
    "%LOCALAPPDATA%\miniconda3\Scripts\conda.exe"
    "%LOCALAPPDATA%\anaconda3\Scripts\conda.exe"
    "%ProgramData%\miniconda3\Scripts\conda.exe"
    "%ProgramData%\anaconda3\Scripts\conda.exe"
    "C:\miniconda3\Scripts\conda.exe"
    "C:\anaconda3\Scripts\conda.exe"
) do (
    if exist "%%~C" (
        call :consider_conda "%%~C"
    )
)

if defined BEST_CONDA (
    set "CONDA_EXE=%BEST_CONDA%"
    echo.
    echo Selected conda: !CONDA_EXE! ^(version %BEST_VERSION%^)
    echo.
) else if defined FALLBACK_CONDA (
    set "CONDA_EXE=%FALLBACK_CONDA%"
    echo.
    echo Selected conda: !CONDA_EXE! ^(version unknown^)
    echo.
) else (
    echo.
    echo No conda installation found
    echo.
)

set "BEST_CONDA="
set "BEST_VERSION="
set "FALLBACK_CONDA="
goto :eof

:consider_conda
set "ACQ4_CAND_PATH=%~1"
if "%ACQ4_CAND_PATH%"=="" goto :eof
if not exist "%ACQ4_CAND_PATH%" goto :eof

rem Get version from conda --version
set "CAND_VERSION="
for /f "tokens=2" %%V in ('cmd /d /c ""%ACQ4_CAND_PATH%" --version 2^>nul"') do (
    if not defined CAND_VERSION set "CAND_VERSION=%%V"
)

if defined CAND_VERSION (
    echo Found conda: %ACQ4_CAND_PATH% ^(version %CAND_VERSION%^)
    if not defined BEST_VERSION (
        set "BEST_VERSION=%CAND_VERSION%"
        set "BEST_CONDA=%ACQ4_CAND_PATH%"
    ) else (
        call :compare_versions "%CAND_VERSION%" "%BEST_VERSION%"
        if "!ACQ4_VER_CMP!"=="1" (
            set "BEST_VERSION=%CAND_VERSION%"
            set "BEST_CONDA=%ACQ4_CAND_PATH%"
        )
    )
) else (
    echo Found conda: %ACQ4_CAND_PATH% ^(version unknown^)
    if not defined FALLBACK_CONDA (
        set "FALLBACK_CONDA=%ACQ4_CAND_PATH%"
    )
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
echo.
echo ===============================================================================
echo Conda was not found on this system.
echo Downloading the Miniconda installer to set up Python environments for ACQ4...
echo ===============================================================================
echo.
set "TMP_INSTALLER=%TEMP%\miniconda-%RANDOM%.exe"
echo Downloading from: %MINICONDA_URL%
curl -L -o "%TMP_INSTALLER%" "%MINICONDA_URL%" || goto :fail_install

echo.
echo ===============================================================================
echo Starting the Conda installer.
echo This is needed to set up the Python environments used by ACQ4.
echo Please complete the installation wizard and then this script will continue.
echo ===============================================================================
echo.
"%TMP_INSTALLER%"
del "%TMP_INSTALLER%" >nul 2>&1

rem Re-search for conda after installation
call :find_conda
goto :eof

:fail_install
echo Failed to download the Miniconda installer.
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
    echo Conda version %CONDA_VERSION% is too old^; 'conda run' requires %MIN_CONDA_VERSION% or newer.
    exit /b 1
) else if "%ACQ4_CONDA_VERSION_RESULT%"=="2" (
    echo Unable to parse conda version "%CONDA_VERSION%".
    exit /b 1
)
set "ACQ4_CONDA_VERSION_RESULT="
exit /b 0

:ensure_installer_env
echo.
echo Checking for installer environment...
rem Check if the environment exists by querying conda
set "ENV_EXISTS="
set "ENV_CHECK_FILE=%TEMP%\acq4-env-check-%RANDOM%.txt"
call "%CONDA_EXE%" env list > "%ENV_CHECK_FILE%" 2>&1
findstr /C:"%INSTALLER_ENV_NAME%" "%ENV_CHECK_FILE%" >nul 2>&1
if not errorlevel 1 (
    set "ENV_EXISTS=1"
)
del "%ENV_CHECK_FILE%" >nul 2>&1

if defined ENV_EXISTS (
    echo Installer environment "%INSTALLER_ENV_NAME%" already exists, reusing it
) else (
    echo Installer environment "%INSTALLER_ENV_NAME%" does not exist, creating it now...
    set "CREATE_LOG=%TEMP%\acq4-conda-create-%RANDOM%.log"
    set "PYTHON_SPEC=python=%PYTHON_VERSION%"
    echo Running: "%CONDA_EXE%" create -y -n "%INSTALLER_ENV_NAME%" !PYTHON_SPEC!
    call "%CONDA_EXE%" create -y -n "%INSTALLER_ENV_NAME%" !PYTHON_SPEC! > "!CREATE_LOG!" 2>&1
    set "CREATE_STATUS=%ERRORLEVEL%"
    set "PYTHON_SPEC="
    if not "!CREATE_STATUS!"=="0" (
        echo ERROR: Environment creation failed with exit code !CREATE_STATUS!
        if defined CREATE_LOG if exist "!CREATE_LOG!" (
            findstr /C:"NoWritableEnvsDirError" "!CREATE_LOG!" >nul 2>&1 && (
                echo Conda could not create the installer environment: no writable envs directories are configured.
                echo Please ensure at least one entry in 'conda info --json' under envs_dirs is writable.
            )
            findstr /C:"NoWritablePkgsDirError" "!CREATE_LOG!" >nul 2>&1 && (
                echo Conda could not download packages: no writable package cache directories are configured.
            )
            type "!CREATE_LOG!"
            del "!CREATE_LOG!" >nul 2>&1
        )
        exit /b !CREATE_STATUS!
    )
    echo Environment created successfully
    if defined CREATE_LOG if exist "!CREATE_LOG!" del "!CREATE_LOG!" >nul 2>&1
    set "CREATE_LOG="
)

echo Verifying Python is available in installer environment...
call "%CONDA_EXE%" run -n "%INSTALLER_ENV_NAME%" python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found in installer environment "%INSTALLER_ENV_NAME%"
    echo Try running: conda env remove -n "%INSTALLER_ENV_NAME%" and then re-run this script
    exit /b 1
)
echo Python verified successfully

echo Installing dependencies in installer environment...
echo Running: "%CONDA_EXE%" run -n "%INSTALLER_ENV_NAME%" python -m pip install --upgrade %QT_PACKAGE% %TOML_PARSER_PACKAGE%
call "%CONDA_EXE%" run -n "%INSTALLER_ENV_NAME%" python -m pip install --upgrade %QT_PACKAGE% %TOML_PARSER_PACKAGE% --index-url=https://pypi.org/simple/
if errorlevel 1 (
    echo ERROR: Failed to install dependencies in installer environment
    exit /b 1
)
echo Dependencies installed successfully
goto :eof

:download_installer
set "INSTALLER_SCRIPT="
if defined SCRIPT_DIR if exist "%SCRIPT_DIR%installer.py" (
    echo Using local installer script: %SCRIPT_DIR%installer.py
    set "INSTALLER_SCRIPT=%SCRIPT_DIR%installer.py"
    goto :eof
)
set "TMP_INSTALLER="
echo Generating temporary file path...
for /f "usebackq tokens=* delims=" %%T in (`powershell -NoProfile -Command "Join-Path ([System.IO.Path]::GetTempPath()) ('acq4-installer-' + [guid]::NewGuid().ToString() + '.py')"`) do (
    if not defined TMP_INSTALLER set "TMP_INSTALLER=%%~T"
)
if not defined TMP_INSTALLER (
    echo ERROR: Unable to create temporary file for installer download.
    goto :eof
)
echo Temporary installer path: %TMP_INSTALLER%
echo Downloading installer from %INSTALLER_URL%
curl -L -o "%TMP_INSTALLER%" "%INSTALLER_URL%" >nul 2>&1
if errorlevel 1 (
    echo ERROR: Unable to download installer.py
    if exist "%TMP_INSTALLER%" del "%TMP_INSTALLER%" >nul 2>&1
    goto :eof
)
echo Download completed successfully
set "DOWNLOADED_INSTALLER=%TMP_INSTALLER%"
set "INSTALLER_SCRIPT=%TMP_INSTALLER%"
goto :eof

:cleanup_installer
if defined DOWNLOADED_INSTALLER if exist "%DOWNLOADED_INSTALLER%" del "%DOWNLOADED_INSTALLER%" >nul 2>&1
goto :eof
