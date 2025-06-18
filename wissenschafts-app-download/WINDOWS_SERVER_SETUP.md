# Windows Server Deployment Guide

## Prerequisites

### 1. Install Python
- Download Python 3.11+ from https://www.python.org/downloads/windows/
- During installation, check "Add Python to PATH"
- Verify installation: `python --version`

### 2. Install Git (optional)
- Download from https://git-scm.com/download/win
- Or download the ZIP file directly

## Quick Setup

### Option 1: Automated Setup
1. Extract the ZIP file to `C:\inetpub\wissenschafts-app\`
2. Open Command Prompt as Administrator
3. Navigate to the folder: `cd C:\inetpub\wissenschafts-app`
4. Run: `windows-setup.bat`

### Option 2: Manual Setup
1. Extract files to your preferred directory
2. Open Command Prompt in that directory
3. Create virtual environment: `python -m venv venv`
4. Activate: `venv\Scripts\activate`
5. Install dependencies: `pip install -r app_requirements.txt`
6. Start app: `python main.py`

## Production Deployment on Windows Server

### IIS with FastCGI (Recommended)

1. **Install IIS and Python Support**
   - Enable IIS through Windows Features
   - Install Python 3.11+
   - Install wfastcgi: `pip install wfastcgi`

2. **Configure wfastcgi**
   ```cmd
   wfastcgi-enable
   ```

3. **IIS Configuration**
   - Create new website in IIS Manager
   - Point to your app directory
   - Add FastCGI module for Python

### Windows Service (Alternative)

Use the provided `windows-service.py` script to run as a service.

## Firewall Configuration

```cmd
netsh advfirewall firewall add rule name="Flask App" dir=in action=allow protocol=TCP localport=5000
```

## Auto-Start on Boot

### Method 1: Task Scheduler
1. Open Task Scheduler
2. Create Basic Task
3. Set trigger: "When computer starts"
4. Action: Start program
5. Program: `C:\path\to\your\app\venv\Scripts\python.exe`
6. Arguments: `main.py`
7. Start in: `C:\path\to\your\app\`

### Method 2: Windows Service
Run `python windows-service-install.py` as Administrator

## Reverse Proxy with IIS

### web.config for IIS URL Rewrite
```xml
<?xml version="1.0" encoding="utf-8"?>
<configuration>
  <system.webServer>
    <rewrite>
      <rules>
        <rule name="Flask" stopProcessing="true">
          <match url="(.*)" />
          <action type="Rewrite" url="http://localhost:5000/{R:1}" />
        </rule>
      </rules>
    </rewrite>
  </system.webServer>
</configuration>
```

## SSL/HTTPS Setup

1. **Obtain SSL Certificate**
   - Use Let's Encrypt with win-acme
   - Or commercial certificate

2. **Configure in IIS**
   - Bind certificate to website
   - Redirect HTTP to HTTPS

## Monitoring and Logs

### Application Logs
Logs are written to the console. For production, modify `main.py`:

```python
import logging
logging.basicConfig(
    filename='app.log',
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s'
)
```

### Windows Event Viewer
Service logs appear in Windows Event Viewer under Applications.

## Troubleshooting

### Common Issues:

1. **Port 5000 in use**
   ```cmd
   netstat -ano | findstr :5000
   taskkill /PID <process_id> /F
   ```

2. **Python not found**
   - Add Python to PATH
   - Use full path to python.exe

3. **Permission denied**
   - Run Command Prompt as Administrator
   - Check folder permissions

4. **Service won't start**
   - Check Windows Event Viewer
   - Verify file paths in service configuration

## Performance Optimization

### 1. Use Gunicorn for Windows
```cmd
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:5000 main:app
```

### 2. Enable Compression in IIS
- Install Dynamic Content Compression
- Enable in IIS Manager

### 3. Static File Optimization
- Serve static files directly through IIS
- Configure caching headers

## Security Considerations

1. **Firewall Rules**
   - Only open necessary ports
   - Restrict access to management interfaces

2. **User Accounts**
   - Run service under limited user account
   - Avoid running as Administrator

3. **Updates**
   - Regularly update Python and dependencies
   - Monitor security advisories

## Backup Strategy

1. **Application Files**
   - Backup entire application directory
   - Include virtual environment or requirements.txt

2. **Configuration**
   - Export IIS configuration
   - Backup service configurations

3. **Logs**
   - Rotate and archive log files
   - Monitor disk space