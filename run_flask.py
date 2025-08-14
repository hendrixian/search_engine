#!/usr/bin/env python3
"""
Flask Search Engine Launcher
Run this script to start the Flask version of your search engine
"""

import os
import sys
import subprocess
from pathlib import Path

def check_requirements():
    """Check if required packages are installed"""
    try:
        import flask
        print("✅ Flask is installed")
    except ImportError:
        print("❌ Flask not found. Please install requirements:")
        print("   pip install -r requirements_flask.txt")
        return False
    
    return True

def setup_directories():
    """Ensure all required directories exist"""
    dirs = ['templates', 'static/css', 'static/js']
    for dir_path in dirs:
        Path(dir_path).mkdir(parents=True, exist_ok=True)
        print(f"✅ Directory {dir_path} ready")

def main():
    print("🚀 Starting Flask Academic Search Engine with ALL Your Services")
    print("=" * 70)
    
    # Check if we're in the right directory
    if not os.path.exists('flask_app.py'):
        print("❌ flask_app.py not found in current directory")
        print("   Please run this script from the project root directory")
        sys.exit(1)
    
    # Check requirements
    if not check_requirements():
        sys.exit(1)
    
    # Setup directories
    setup_directories()
    
    # Check for .env file
    if not os.path.exists('.env'):
        print("⚠️  No .env file found. Creating example...")
        print("   Please update .env with your actual configuration")
        
    # Start Flask app
    print("\n🌟 Starting Flask development server...")
    print("📱 Your app will be available at: http://localhost:5000")
    print("\n🔧 Integrated Services:")
    print("   • MultiSiteCrawler - Web search (GeeksforGeeks, MathWorld, Engineering.com)")
    print("   • Elasticsearch - Academic papers search") 
    print("   • MinIO - Document storage and passages")
    print("   • Mistral AI - Intelligent answer generation")
    print("   • Sentence Transformers - Semantic search")
    print("\n✨ Features:")
    print("   • Real-time auto-suggestions")
    print("   • No unwanted automatic searches") 
    print("   • Beautiful responsive interface")
    print("   • Search only on button click or suggestion selection")
    print("   • Service status monitoring")
    print("\n💡 Tips:")
    print("   • Check console output for service status")
    print("   • Services will gracefully degrade if unavailable")
    print("   • Update your .env file for API keys")
    print("\n⚡ Press Ctrl+C to stop the server")
    print("=" * 70)
    
    try:
        # Run Flask app
        os.environ['FLASK_APP'] = 'flask_app.py'
        os.environ['FLASK_ENV'] = 'development'
        subprocess.run([sys.executable, 'flask_app.py'])
    except KeyboardInterrupt:
        print("\n👋 Flask server stopped. Thanks for using the search engine!")

if __name__ == '__main__':
    main()
