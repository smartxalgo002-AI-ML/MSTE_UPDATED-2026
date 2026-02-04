#!/bin/bash
# Dashboard Runner for Linux/AWS

cd "$(dirname "$0")/Dashboard_mste"

echo "Starting Streamlit Dashboard..."
streamlit run app.py --server.port 8501 --server.address 0.0.0.0
