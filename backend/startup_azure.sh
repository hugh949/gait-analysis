#!/bin/bash
# Startup script for Azure Native Architecture
# Minimal dependencies - fast startup!

set -e

echo "🚀 Starting Gait Analysis Backend (Azure Native)..."
echo "===================================================="

# Check if virtual environment exists (Oryx will create it during deployment)
if [ -d "/home/site/wwwroot/antenv" ]; then
  echo "📦 Activating virtual environment..."
  source /home/site/wwwroot/antenv/bin/activate
  export PATH="/home/site/wwwroot/antenv/bin:$PATH"
else
  echo "⚠️  Virtual environment not found"
  echo "   Oryx should create it during deployment"
  echo "   Trying to use system Python..."
fi

# Check if uvicorn is available
if ! command -v uvicorn &> /dev/null; then
  echo "⚠️  uvicorn not found - this should not happen with Oryx build"
  echo "   Trying to install minimal dependencies..."
  pip install --user uvicorn[standard] fastapi python-multipart || {
    echo "❌ Failed to install uvicorn"
    exit 1
  }
  export PATH="/root/.local/bin:$PATH"
fi

# Verify main file exists
if [ ! -f "/home/site/wwwroot/main_azure.py" ]; then
  echo "❌ main_azure.py not found!"
  echo "   Available files:"
  ls -la /home/site/wwwroot/ | head -10
  exit 1
fi

# Start the application
echo "🚀 Starting uvicorn server..."
echo "   App: main_azure:app"
echo "   Host: 0.0.0.0"
echo "   Port: 8000"
echo ""

cd /home/site/wwwroot
exec uvicorn main_azure:app --host 0.0.0.0 --port 8000 --timeout-keep-alive 300


