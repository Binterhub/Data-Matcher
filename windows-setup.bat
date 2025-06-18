@echo off
echo ================================================
echo    Windows Server Setup - Wissenschafts-App
echo ================================================

:: Check if running as Administrator
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo ERROR: This script must be run as Administrator
    echo Right-click and select "Run as administrator"
    pause
    exit /b 1
)

:: Check Python installation
echo Checking Python installation...
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH
    echo Please install Python 3.11+ from https://www.python.org/downloads/
    echo Make sure to check "Add Python to PATH" during installation
    pause
    exit /b 1
)

:: Get Python version
for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PYTHON_VERSION=%%i
echo Python %PYTHON_VERSION% detected

:: Create virtual environment
echo Creating virtual environment...
if exist "venv" (
    echo Virtual environment already exists, skipping creation
) else (
    python -m venv venv
    if errorlevel 1 (
        echo ERROR: Failed to create virtual environment
        pause
        exit /b 1
    )
)

:: Activate virtual environment
echo Activating virtual environment...
call venv\Scripts\activate.bat
if errorlevel 1 (
    echo ERROR: Failed to activate virtual environment
    pause
    exit /b 1
)

:: Upgrade pip
echo Upgrading pip...
python -m pip install --upgrade pip

:: Install dependencies
echo Installing application dependencies...
pip install -r app_requirements.txt
if errorlevel 1 (
    echo ERROR: Failed to install dependencies
    pause
    exit /b 1
)

:: Install production server
echo Installing Gunicorn for production...
pip install gunicorn
if errorlevel 1 (
    echo Warning: Gunicorn installation failed (Windows compatibility)
    echo Continuing with Flask development server...
)

:: Install Windows service support
echo Installing Windows service support...
pip install pywin32
if errorlevel 1 (
    echo Warning: pywin32 installation failed
    echo Service installation will not be available
)

:: Configure firewall
echo Configuring Windows Firewall...
netsh advfirewall firewall add rule name="Wissenschafts-App-HTTP" dir=in action=allow protocol=TCP localport=5000 >nul 2>&1
if errorlevel 1 (
    echo Warning: Could not configure firewall automatically
    echo Please manually allow port 5000 in Windows Firewall
)

:: Create application directories
echo Creating application directories...
if not exist "logs" mkdir logs
if not exist "instance" mkdir instance

:: Set permissions
echo Setting directory permissions...
icacls . /grant "IIS_IUSRS:(OI)(CI)F" /T >nul 2>&1
icacls . /grant "IUSR:(OI)(CI)F" /T >nul 2>&1

:: Create startup script
echo Creating production startup script...
(
echo @echo off
echo cd /d "%~dp0"
echo call venv\Scripts\activate.bat
echo echo Starting Wissenschafts-App on http://localhost:5000
echo echo Press Ctrl+C to stop
echo python main.py
echo pause
) > start-production.bat

:: Create service installer script
echo Creating service installer script...
(
echo @echo off
echo cd /d "%~dp0"
echo call venv\Scripts\activate.bat
echo python windows-service-install.py
echo pause
) > install-service.bat

echo ================================================
echo           Setup Complete!
echo ================================================
echo.
echo Next steps:
echo 1. Test the application: start-production.bat
echo 2. Install as service: install-service.bat
echo 3. Configure IIS (optional): See WINDOWS_SERVER_SETUP.md
echo.
echo The application will be available at:
echo http://localhost:5000
echo.
echo For production deployment, see WINDOWS_SERVER_SETUP.md
echo.
pause