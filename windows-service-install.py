"""
Windows Service Installation Helper
"""

import sys
import os
import subprocess

def check_admin():
    """Check if running as administrator"""
    try:
        import ctypes
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

def main():
    print("Windows Service Installation Helper")
    print("=" * 40)
    
    if not check_admin():
        print("ERROR: This script must be run as Administrator")
        print("Right-click and select 'Run as administrator'")
        input("Press Enter to exit...")
        return
    
    # Check if pywin32 is installed
    try:
        import win32serviceutil
        print("✓ pywin32 is installed")
    except ImportError:
        print("Installing pywin32...")
        subprocess.run([sys.executable, "-m", "pip", "install", "pywin32"])
        try:
            import win32serviceutil
            print("✓ pywin32 installed successfully")
        except ImportError:
            print("ERROR: Failed to install pywin32")
            input("Press Enter to exit...")
            return
    
    # Import and install service
    try:
        from windows_service import install_service, start_service
        
        print("\nInstalling Windows Service...")
        if install_service():
            print("✓ Service installed successfully")
            
            start_choice = input("\nStart the service now? (y/n): ").lower()
            if start_choice in ['y', 'yes']:
                if start_service():
                    print("✓ Service started successfully")
                    print("\nThe app is now running as a Windows Service")
                    print("It will start automatically when Windows boots")
                    print("\nService Management:")
                    print("- Start: net start WissenschaftsApp")
                    print("- Stop: net stop WissenschaftsApp")
                    print("- Check status: sc query WissenschaftsApp")
                else:
                    print("✗ Failed to start service")
            
        else:
            print("✗ Service installation failed")
            
    except ImportError as e:
        print(f"ERROR: Could not import service module: {e}")
    except Exception as e:
        print(f"ERROR: {e}")
    
    input("\nPress Enter to exit...")

if __name__ == "__main__":
    main()