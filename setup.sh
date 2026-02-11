#!/bin/bash
# First-time setup script for Linux/AWS
# Run this once to set up the environment

echo "🚀 News Sentiment Model - Setup Script"
echo "========================================"

# Check Python version
python_version=$(python3 --version 2>&1 | awk '{print $2}')
echo "✓ Python version: $python_version"

# Create virtual environment
echo ""
echo "📦 Creating virtual environment..."
python3 -m venv .venv
source .venv/bin/activate

# Upgrade pip
echo ""
echo "📦 Upgrading pip..."
pip install --upgrade pip

# Install dependencies
echo ""
echo "📦 Installing dependencies from requirements.txt..."
pip install -r requirements.txt

# Download NLTK data
echo ""
echo "📚 Downloading NLTK data..."
python3 << EOF
import nltk
import ssl

try:
    _create_unverified_https_context = ssl._create_unverified_context
except AttributeError:
    pass
else:
    ssl._create_default_https_context = _create_unverified_https_context

nltk.download('punkt')
nltk.download('stopwords')
nltk.download('wordnet')
print("✓ NLTK data downloaded")
EOF

# Create required directories
echo ""
echo "📁 Creating required directories..."
mkdir -p logs
mkdir -p output/news_fetcher
mkdir -p output/company_tagger
mkdir -p output/longformer
mkdir -p output/deberta_fin
mkdir -p output/features
mkdir -p output/ohlcv_merger
mkdir -p output/labels
mkdir -p output/signals
mkdir -p models
mkdir -p "correct_ohlcv_tick_data/data_ohlcv/group_XX"

# Make scripts executable
echo ""
echo "🔧 Making scripts executable..."
chmod +x run_news_pipeline.sh
chmod +x run_ohlcv_collector.sh
chmod +x run_dashboard.sh

# Check for mapping files
echo ""
echo "📋 Checking mapping files..."
if [ -f "mapping/companywise_keyword_mapping.csv" ]; then
    echo "✓ Company mapping file found"
else
    echo "⚠️  WARNING: mapping/companywise_keyword_mapping.csv not found"
fi

if [ -f "mapping/index_mapping.csv" ]; then
    echo "✓ Index mapping file found"
else
    echo "⚠️  WARNING: mapping/index_mapping.csv not found"
fi

# Reminder about Dhan token
echo ""
echo "========================================"
echo "✅ Setup complete!"
echo ""
echo "📝 Next steps:"
echo "1. Activate virtual environment: source .venv/bin/activate"
echo "2. Create correct_ohlcv_tick_data/dhan_token.json with your Dhan credentials"
echo "3. Run the pipeline: ./run_news_pipeline.sh"
echo ""
echo "For AWS deployment, see aws_deployment_guide.md"
echo "========================================"
