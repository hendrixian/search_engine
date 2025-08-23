#!/usr/bin/env python3
"""
WSGI Entry Point for Flask Academic Search Engine
Fixed to prevent multiple initialization issues
"""

import os
import sys

# Add the current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import the Flask app - services will be lazy loaded
from flask_app import app

# Set Gunicorn environment variable to prevent duplicate initialization
os.environ["GUNICORN"] = "true"

# Only show startup message once
if not os.environ.get("WERKZEUG_RUN_MAIN"):
    print("🚀 WSGI Flask app starting with lazy loading...")
    print("✅ Services will initialize on first request")

if __name__ == "__main__":
    app.run()