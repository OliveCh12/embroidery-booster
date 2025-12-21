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
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
fi

# Activate venv
source venv/bin/activate

# Install dependencies
echo "⬇️  Installing dependencies..."
pip install numpy scipy scikit-image pillow svgelements

echo "✅ Setup complete!"
echo ""
echo "To run the generator:"
echo "python3 embroidery_auto_rung_generator.py <your_svg_file>"
