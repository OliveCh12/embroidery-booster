#!/bin/bash

echo "🧵 Embroidery Auto Rung Generator Setup"
echo "========================================"

# Check for Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 could not be found. Please install Python 3."
    exit 1
fi

echo "✅ Python 3 found."

# Create virtual environment (optional but recommended)
if [ ! -d "venv" ]; then
    echo "�� Creating virtual environment..."
    python3 -m venv venv
fi

# Activate venv
source venv/bin/activate

# Install dependencies
echo "⬇️  Installing dependencies..."
pip install -r requirements.txt

echo "✅ Setup complete!"
echo ""
echo "To run the generator:"
echo "python3 -m embroidery_generator.main <your_svg_file>"
