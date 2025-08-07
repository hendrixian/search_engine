#!/usr/bin/env python3
"""
System Monitor Dashboard Runner
Run this script to start the monitoring dashboard on port 8502
"""

import subprocess
import sys
import os

def run_monitor_dashboard():
    """Run the system monitor dashboard on port 8502"""
    
    # Path to the monitor dashboard file
    monitor_file = "system_monitor_dashboard.py"
    
    # Check if the file exists
    if not os.path.exists(monitor_file):
        print(f"❌ Error: {monitor_file} not found!")
        print("Make sure you've saved the system monitor dashboard code as 'system_monitor_dashboard.py'")
        return
    
    print("🚀 Starting Academic Search System Monitor Dashboard...")
    print("📊 Dashboard will be available at: http://localhost:8502")
    print("🔄 Auto-refresh and real-time monitoring enabled")
    print("\n" + "="*60)
    
    try:
        # Run streamlit on port 8502
        subprocess.run([
            sys.executable, "-m", "streamlit", "run", 
            monitor_file,
            "--server.port", "8502",
            "--server.address", "0.0.0.0",
            "--server.headless", "true",
            "--browser.serverAddress", "localhost",
            "--theme.base", "light"
        ])
    except KeyboardInterrupt:
        print("\n🛑 Monitor dashboard stopped by user")
    except Exception as e:
        print(f"❌ Error running monitor dashboard: {e}")

if __name__ == "__main__":
    run_monitor_dashboard()