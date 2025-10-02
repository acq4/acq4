@echo off
REM ACQ4 Installation Script for Windows
REM Interactive installer with hardware and optional dependency selection

setlocal EnableDelayedExpansion

echo === ACQ4 Interactive Installer ===
echo This script will install ACQ4 and its dependencies.
echo.

REM Check for conda (required) and mamba (optional for faster env creation)
where conda >nul 2>&1
if %errorlevel% neq 0 (
    echo Error: conda is not installed or not in PATH.
    echo Please install Anaconda or Miniconda first.
    echo Visit: https://docs.conda.io/en/latest/miniconda.html
    pause
    exit /b 1
)

set "ENV_CREATE_CMD=conda"
where mamba >nul 2>&1
if %errorlevel% equ 0 (
    set "ENV_CREATE_CMD=mamba"
    echo Found mamba - using for faster environment creation
) else (
    echo Using conda for environment creation
)

REM Get script directory and ACQ4 root
set "SCRIPT_DIR=%~dp0"
for %%i in ("%SCRIPT_DIR%..") do set "ACQ4_ROOT=%%~fi"

echo === Configuration ===
echo.

REM Get environment name
set "default_env=acq4"
set /p "env_name=Environment name [%default_env%]: "
if "%env_name%"=="" set "env_name=%default_env%"

echo.
echo === Non-dev Dependencies ===
echo These are required, but developns often use editable installs.
echo.

REM Read and select non_dev dependencies
set "non_dev_count=0"
set "selected_non_dev="
if exist "%SCRIPT_DIR%requirements\non-dev-deps.txt" (
    for /f "usebackq delims=" %%a in ("%SCRIPT_DIR%requirements\non-dev-deps.txt") do (
        set "line=%%a"
        REM Skip empty lines and comments
        if not "!line!"=="" if not "!line:~0,1!"=="#" (
            REM Split line on first # character
            for /f "tokens=1,* delims=#" %%x in ("!line!") do (
                set "package=%%x"
                set "desc=%%y"
                REM Remove leading/trailing spaces
                for /f "tokens=* delims= " %%p in ("!package!") do set "package=%%p"
                if not "!desc!"=="" for /f "tokens=* delims= " %%d in ("!desc!") do set "desc=%%d"

                if not "!package!"=="" (
                    set /p "install_opt=Install !package!? (!desc!) [Y/n]: "
                    if "!install_opt!"=="" set "install_opt=y"
                    if /i "!install_opt!"=="y" (
                        if "!selected_non_dev!"=="" (
                            set "selected_non_dev=!package!"
                        ) else (
                            set "selected_non_dev=!selected_non_dev! !package!"
                        )
                    )
                )
            )
        )
    )
) else (
    echo Warning: Optional dependencies file not found
)

echo.
echo === Hardware Dependencies ===
echo Only install packages for hardware you actually have.
echo.

REM Read and select hardware dependencies
set "hardware_count=0"
set "selected_hardware="
if exist "%SCRIPT_DIR%requirements\hardware-deps.txt" (
    for /f "usebackq delims=" %%a in ("%SCRIPT_DIR%requirements\hardware-deps.txt") do (
        set "line=%%a"
        REM Skip empty lines and comments
        if not "!line!"=="" if not "!line:~0,1!"=="#" (
            REM Split line on first # character
            for /f "tokens=1,* delims=#" %%x in ("!line!") do (
                set "package=%%x"
                set "desc=%%y"
                REM Remove leading/trailing spaces
                for /f "tokens=* delims= " %%p in ("!package!") do set "package=%%p"
                if not "!desc!"=="" for /f "tokens=* delims= " %%d in ("!desc!") do set "desc=%%d"

                if not "!package!"=="" (
                    set /p "install_hw=Install !package!? (!desc!) [y/N]: "
                    if "!install_hw!"=="" set "install_hw=n"
                    if /i "!install_hw!"=="y" (
                        if "!selected_hardware!"=="" (
                            set "selected_hardware=!package!"
                        ) else (
                            set "selected_hardware=!selected_hardware! !package!"
                        )
                    )
                )
            )
        )
    )
) else (
    echo Warning: Hardware dependencies file not found
)

echo.
echo === Installation Summary ===
echo Environment name: %env_name%
if "%selected_non_dev%"=="" (
    echo Optional dependencies: none
) else (
    echo Optional dependencies: %selected_non_dev%
)
if "%selected_hardware%"=="" (
    echo Hardware dependencies: none
) else (
    echo Hardware dependencies: %selected_hardware%
)
echo.

set /p "proceed=Proceed with installation? [Y/n]: "
if "%proceed%"=="" set "proceed=y"
if /i not "%proceed%"=="y" (
    echo Installation cancelled.
    pause
    exit /b 0
)

echo.
echo === Installing ACQ4 ===
echo.

REM Check if environment already exists
conda env list | findstr /r "^%env_name% " >nul 2>&1
if %errorlevel% equ 0 (
    echo Environment '%env_name%' already exists.
    set /p "recreate=Remove and recreate it? [y/N]: "
    if "%recreate%"=="" set "recreate=n"
    if /i not "!recreate!"=="y" (
        echo Installation cancelled.
        pause
        exit /b 1
    )
    echo Removing existing environment...
    conda env remove -n %env_name% -y
)

REM Create conda environment (use mamba if available for speed)
echo Creating conda environment '%env_name%'...
cd /d "%ACQ4_ROOT%"
%ENV_CREATE_CMD% env create --name=%env_name% --file=tools\requirements\acq4-torch.yml
if %errorlevel% neq 0 (
    echo Error creating conda environment
    pause
    exit /b 1
)

REM Activate environment (always use conda for activation)
echo Activating environment...
call conda activate %env_name%
if %errorlevel% neq 0 (
    echo Error activating environment
    pause
    exit /b 1
)

echo Environment activated successfully
echo.

REM Install ACQ4 in development mode
echo Installing ACQ4 in development mode...
pip install -e .
if %errorlevel% neq 0 (
    echo Error installing ACQ4
    pause
    exit /b 1
)

REM Install selected non_dev dependencies
if not "%selected_non_dev%"=="" (
    echo Installing non_dev dependencies...
    for %%d in (%selected_non_dev%) do (
        echo Installing %%d...
        pip install "%%d"
        if !errorlevel! neq 0 (
            echo Warning: Failed to install %%d
        )
    )
)

REM Install selected hardware dependencies
echo.
echo Checking hardware dependencies: "%selected_hardware%"
if not "%selected_hardware%"=="" (
    echo Installing hardware dependencies...
    for %%d in (%selected_hardware%) do (
        echo Installing %%d...
        pip install "%%d"
        if !errorlevel! neq 0 (
            echo Warning: Failed to install %%d
        )
    )
) else (
    echo No hardware dependencies selected
)

echo.
echo === Installation Complete! ===
echo.
echo To use ACQ4:
echo   conda activate %env_name%
echo   python -m acq4
echo.
echo To deactivate the environment:
echo   conda deactivate
echo.
pause