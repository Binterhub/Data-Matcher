"""
Windows Service implementation for Wissenschafts-Wissensplattform
"""

import sys
import os
import servicemanager
import socket
import win32event
import win32service
import win32serviceutil
import win32api
import win32con
import threading
import subprocess
import time

class WissenschaftsAppService(win32serviceutil.ServiceFramework):
    _svc_name_ = "WissenschaftsApp"
    _svc_display_name_ = "Wissenschafts-Wissensplattform"
    _svc_description_ = "Flask-based scientific knowledge platform"
    
    def __init__(self, args):
        win32serviceutil.ServiceFramework.__init__(self, args)
        self.hWaitStop = win32event.CreateEvent(None, 0, 0, None)
        self.is_alive = True
        self.app_process = None
        
        # Get the directory where this script is located
        self.app_dir = os.path.dirname(os.path.abspath(__file__))
        self.python_exe = os.path.join(self.app_dir, 'venv', 'Scripts', 'python.exe')
        self.main_py = os.path.join(self.app_dir, 'main.py')
        
    def SvcStop(self):
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        win32event.SetEvent(self.hWaitStop)
        self.is_alive = False
        
        # Terminate the Flask app process
        if self.app_process:
            try:
                self.app_process.terminate()
                self.app_process.wait(timeout=10)
            except:
                try:
                    self.app_process.kill()
                except:
                    pass
        
        servicemanager.LogMsg(
            servicemanager.EVENTLOG_INFORMATION_TYPE,
            servicemanager.PYS_SERVICE_STOPPED,
            (self._svc_name_, '')
        )
        
    def SvcDoRun(self):
        servicemanager.LogMsg(
            servicemanager.EVENTLOG_INFORMATION_TYPE,
            servicemanager.PYS_SERVICE_STARTED,
            (self._svc_name_, '')
        )
        
        self.main()
        
    def main(self):
        """Main service loop"""
        while self.is_alive:
            try:
                # Start the Flask application
                servicemanager.LogInfoMsg(f"Starting Flask app from {self.main_py}")
                
                # Change to app directory
                os.chdir(self.app_dir)
                
                # Start the Flask app process
                self.app_process = subprocess.Popen(
                    [self.python_exe, self.main_py],
                    cwd=self.app_dir,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
                
                servicemanager.LogInfoMsg(f"Flask app started with PID {self.app_process.pid}")
                
                # Monitor the process
                while self.is_alive:
                    # Check if service stop was requested
                    if win32event.WaitForSingleObject(self.hWaitStop, 1000) == win32event.WAIT_OBJECT_0:
                        break
                        
                    # Check if Flask process is still running
                    if self.app_process.poll() is not None:
                        servicemanager.LogErrorMsg("Flask app process died, restarting...")
                        break
                        
                # If we get here and service is still alive, restart the process
                if self.is_alive:
                    servicemanager.LogInfoMsg("Restarting Flask app in 5 seconds...")
                    time.sleep(5)
                    
            except Exception as e:
                servicemanager.LogErrorMsg(f"Service error: {str(e)}")
                if self.is_alive:
                    time.sleep(10)  # Wait before retry

def install_service():
    """Install the service"""
    try:
        win32serviceutil.InstallService(
            WissenschaftsAppService,
            WissenschaftsAppService._svc_name_,
            WissenschaftsAppService._svc_display_name_,
            startType=win32service.SERVICE_AUTO_START,
            description=WissenschaftsAppService._svc_description_
        )
        print(f"Service '{WissenschaftsAppService._svc_display_name_}' installed successfully")
        print("You can start it with: net start WissenschaftsApp")
        return True
    except Exception as e:
        print(f"Failed to install service: {e}")
        return False

def uninstall_service():
    """Uninstall the service"""
    try:
        win32serviceutil.RemoveService(WissenschaftsAppService._svc_name_)
        print(f"Service '{WissenschaftsAppService._svc_display_name_}' uninstalled successfully")
        return True
    except Exception as e:
        print(f"Failed to uninstall service: {e}")
        return False

def start_service():
    """Start the service"""
    try:
        win32serviceutil.StartService(WissenschaftsAppService._svc_name_)
        print(f"Service '{WissenschaftsAppService._svc_display_name_}' started successfully")
        return True
    except Exception as e:
        print(f"Failed to start service: {e}")
        return False

def stop_service():
    """Stop the service"""
    try:
        win32serviceutil.StopService(WissenschaftsAppService._svc_name_)
        print(f"Service '{WissenschaftsAppService._svc_display_name_}' stopped successfully")
        return True
    except Exception as e:
        print(f"Failed to stop service: {e}")
        return False

if __name__ == '__main__':
    if len(sys.argv) == 1:
        # Called by Windows Service Manager
        servicemanager.Initialize()
        servicemanager.PrepareToHostSingle(WissenschaftsAppService)
        servicemanager.StartServiceCtrlDispatcher()
    else:
        # Command line interface
        command = sys.argv[1].lower()
        
        if command == 'install':
            install_service()
        elif command == 'uninstall':
            uninstall_service()
        elif command == 'start':
            start_service()
        elif command == 'stop':
            stop_service()
        elif command == 'restart':
            stop_service()
            time.sleep(2)
            start_service()
        else:
            print("Usage: python windows-service.py [install|uninstall|start|stop|restart]")
            print("       python windows-service.py install - Install the service")
            print("       python windows-service.py start   - Start the service")
            print("       python windows-service.py stop    - Stop the service")
            print("       python windows-service.py restart - Restart the service")
            print("       python windows-service.py uninstall - Remove the service")