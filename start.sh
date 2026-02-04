#!/bin/bash
# All-in-one script for Linux/AWS - Setup + Run
# Just run: ./start.sh

echo ""
echo "========================================"
echo "News Sentiment Pipeline - Auto Setup"
echo "========================================"
echo ""

# Get script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Check if virtual environment exists
if [ ! -d ".venv" ]; then
    echo "First-time setup detected. Running setup..."
    echo ""
    chmod +x setup.sh
    ./setup.sh
    if [ $? -ne 0 ]; then
        echo "Setup failed!"
        exit 1
    fi
fi

# Activate virtual environment
echo "Activating virtual environment..."
source .venv/bin/activate

# Check for Dhan token (for OHLCV collector)
if [ ! -f "CORRECT OHLCV TICK DATA/dhan_token.json" ]; then
    echo ""
    echo "========================================"
    echo "WARNING: Dhan token file not found!"
    echo "========================================"
    echo ""
    echo "The OHLCV collector requires: CORRECT OHLCV TICK DATA/dhan_token.json"
    echo ""
    echo "Create the file with this format:"
    echo '{'
    echo '  "access_token": "YOUR_TOKEN_HERE",'
    echo '  "client_id": "YOUR_CLIENT_ID",'
    echo '  "expires_at": 1770277211,'
    echo '  "renewed_at": 1738645228'
    echo '}'
    echo ""
    echo "The news pipeline will still run, but OHLCV data won't be collected."
    echo ""
    sleep 3
fi

# Start OHLCV Data Collector (in background)
echo ""
echo "========================================"
echo "Starting OHLCV Market Data Collector..."
echo "========================================"
echo ""
cd "CORRECT OHLCV TICK DATA"
python3 "new ohlcv.py" &
OHLCV_PID=$!
echo "OHLCV Collector started with PID $OHLCV_PID"
cd ..

# Start the pipeline
echo ""
echo "========================================"
echo "Starting News Sentiment Pipeline..."
echo "========================================"
echo ""
python3 main.py

# Kill background process when main pipeline stops
kill $OHLCV_PID
