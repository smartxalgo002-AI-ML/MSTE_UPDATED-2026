#!/bin/bash
# News Sentiment Pipeline Runner for Linux/AWS

cd "$(dirname "$0")"

echo "Starting News Sentiment Pipeline..."
python3 main.py
