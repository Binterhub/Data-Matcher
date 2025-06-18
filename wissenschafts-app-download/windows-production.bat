@echo off
echo ================================================
echo    Windows Production Server Setup
echo    Wissenschafts-Wissensplattform
echo ================================================

:: Check administrator privileges
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo ERROR: Administrator privileges required
    echo Right-click and select "Run as administrator"
    pause
    exit /b 1
)

:: Set production directory
set APP_DIR=C:\inetpub\wissenschafts-app
set PYTHON_DIR=C:\Python311

echo Setting up production environment in %APP_DIR%

:: Create production directory
if not exist "%APP_DIR%" (
    echo Creating production directory...
    mkdir "%APP_DIR%"
)

:: Copy application files if not already there
if not exist "%APP_DIR%\main.py" (
    echo Copying application files...
    xcopy /E /I /Y . "%APP_DIR%"
)

:: Change to production directory
cd /d "%APP_DIR%"

:: Install Python if not found
if not exist "%PYTHON_DIR%\python.exe" (
    echo Python not found at %PYTHON_DIR%
    echo Please install Python 3.11+ to C:\Python311
    echo Download from: https://www.python.org/downloads/
    pause
    exit /b 1
)

:: Create virtual environment
echo Creating production virtual environment...
"%PYTHON_DIR%\python.exe" -m venv venv-prod

:: Activate virtual environment
call venv-prod\Scripts\activate.bat

:: Upgrade pip
python -m pip install --upgrade pip

:: Install dependencies
echo Installing production dependencies...
pip install -r app_requirements.txt
pip install gunicorn waitress wfastcgi pywin32

:: Configure wfastcgi for IIS
echo Configuring wfastcgi...
wfastcgi-enable

:: Set up IIS application pool (requires IIS to be installed)
echo Setting up IIS Application Pool...
%windir%\system32\inetsrv\appcmd add apppool /name:"WissenschaftsApp" /managedRuntimeVersion:"" /processModel.identityType:ApplicationPoolIdentity

:: Create IIS website
echo Creating IIS website...
%windir%\system32\inetsrv\appcmd add site /name:"WissenschaftsApp" /physicalPath:"%APP_DIR%" /bindings:"http/*:80:"

:: Set application pool for website
%windir%\system32\inetsrv\appcmd set app "WissenschaftsApp/" /applicationPool:"WissenschaftsApp"

:: Configure firewall
echo Configuring Windows Firewall...
netsh advfirewall firewall add rule name="HTTP-In" dir=in action=allow protocol=TCP localport=80
netsh advfirewall firewall add rule name="HTTPS-In" dir=in action=allow protocol=TCP localport=443
netsh advfirewall firewall add rule name="Flask-Dev" dir=in action=allow protocol=TCP localport=5000

:: Set permissions
echo Setting directory permissions...
icacls "%APP_DIR%" /grant "IIS_IUSRS:(OI)(CI)F" /T
icacls "%APP_DIR%" /grant "IUSR:(OI)(CI)F" /T
icacls "%APP_DIR%" /grant "Everyone:(OI)(CI)RX" /T

:: Create logs directory
if not exist "%APP_DIR%\logs" mkdir "%APP_DIR%\logs"
icacls "%APP_DIR%\logs" /grant "IIS_IUSRS:(OI)(CI)F" /T

:: Install Windows Service
echo Installing Windows Service...
python windows-service.py install

:: Create management scripts
echo Creating management scripts...

:: Create start service script
(
echo @echo off
echo net start WissenschaftsApp
echo echo Service started
echo pause
) > start-service.bat

:: Create stop service script
(
echo @echo off
echo net stop WissenschaftsApp
echo echo Service stopped
echo pause
) > stop-service.bat

:: Create restart script
(
echo @echo off
echo net stop WissenschaftsApp
echo timeout /t 3
echo net start WissenschaftsApp
echo echo Service restarted
echo pause
) > restart-service.bat

:: Create IIS management script
(
echo @echo off
echo echo IIS Management Commands:
echo echo Start website: %%windir%%\system32\inetsrv\appcmd start site "WissenschaftsApp"
echo echo Stop website:  %%windir%%\system32\inetsrv\appcmd stop site "WissenschaftsApp"
echo echo.
echo echo Current status:
echo %%windir%%\system32\inetsrv\appcmd list sites /name:"WissenschaftsApp"
echo pause
) > manage-iis.bat

:: Create backup script
(
echo @echo off
echo set BACKUP_DIR=C:\Backups\wissenschafts-app-%%date:~-4,4%%%%date:~-10,2%%%%date:~-7,2%%
echo mkdir "%%BACKUP_DIR%%"
echo xcopy /E /I /Y "%APP_DIR%" "%%BACKUP_DIR%%"
echo echo Backup created at %%BACKUP_DIR%%
echo pause
) > backup.bat

echo ================================================
echo           Production Setup Complete!
echo ================================================
echo.
echo Application installed to: %APP_DIR%
echo.
echo Service Management:
echo   start-service.bat   - Start Windows Service
echo   stop-service.bat    - Stop Windows Service
echo   restart-service.bat - Restart Windows Service
echo.
echo IIS Management:
echo   manage-iis.bat      - IIS commands and status
echo.
echo Backup:
echo   backup.bat          - Create application backup
echo.
echo Access Points:
echo   IIS Website:        http://localhost
echo   Direct Service:     http://localhost:5000
echo.
echo Next Steps:
echo 1. Start the service: start-service.bat
echo 2. Test the website: http://localhost
echo 3. Configure SSL certificate (optional)
echo 4. Set up domain name (optional)
echo.
pause