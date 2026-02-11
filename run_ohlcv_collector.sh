#!/bin/bash
# OHLCV Data Collector Runner for Linux/AWS

cd "$(dirname "$0")/correct_ohlcv_tick_data"

echo "Starting OHLCV Data Collector..."
python3 "new_ohlcv.py"
