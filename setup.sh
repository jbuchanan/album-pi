#!/bin/bash

# Album Art Display Setup Script for Raspberry Pi

set -e

echo "🎵 Setting up Album Art Display..."

# Check if running on Raspberry Pi
if ! grep -q "Raspberry Pi" /proc/cpuinfo 2>/dev/null && ! grep -q "BCM" /proc/cpuinfo 2>/dev/null; then
    echo "⚠️  Warning: This doesn't appear to be a Raspberry Pi"
    echo "Continuing anyway..."
fi

# Update system
echo "📦 Updating system packages..."
sudo apt update
sudo apt upgrade -y

# Install system dependencies
echo "📦 Installing system dependencies..."
sudo apt install -y \
    python3 \
    python3-pip \
    python3-venv \
    python3-dev \
    libjpeg-dev \
    zlib1g-dev \
    libfreetype6-dev \
    liblcms2-dev \
    libopenjp2-7-dev \
    libtiff5-dev \
    libsdl2-dev \
    libsdl2-image-dev \
    libsdl2-mixer-dev \
    libsdl2-ttf-dev \
    libportmidi-dev \
    libswscale-dev \
    libavformat-dev \
    libavcodec-dev \
    git

# Create virtual environment
echo "🐍 Installing uv (fast Python package manager)..."
# Install uv if not already installed
if ! command -v uv &> /dev/null; then
    curl -LsSf https://astral.sh/uv/install.sh | sh
    # Add uv to PATH for current session
    export PATH="$HOME/.cargo/bin:$PATH"
fi

# Create virtual environment and install dependencies with uv
echo "📦 Installing Python packages with uv..."
uv sync

# Create default fallback image
echo "🖼️  Creating default fallback image..."
uv run python << 'EOF'
from PIL import Image, ImageDraw, ImageFont
import os

# Create a simple default image
img = Image.new('RGB', (720, 720), color=(40, 40, 40))
draw = ImageDraw.Draw(img)

# Try to use a nice font, fall back to default
try:
    font_large = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 48)
    font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 24)
except:
    font_large = ImageFont.load_default()
    font_small = ImageFont.load_default()

# Draw text
text1 = "♪ Album Art Display ♪"
text2 = "Ready to rock!"

# Get text dimensions and center
bbox1 = draw.textbbox((0, 0), text1, font=font_large)
bbox2 = draw.textbbox((0, 0), text2, font=font_small)

w1, h1 = bbox1[2] - bbox1[0], bbox1[3] - bbox1[1]
w2, h2 = bbox2[2] - bbox2[0], bbox2[3] - bbox2[1]

draw.text(((720 - w1) // 2, (720 - h1) // 2 - 30), text1, fill=(255, 255, 255), font=font_large)
draw.text(((720 - w2) // 2, (720 - h2) // 2 + 30), text2, fill=(180, 180, 180), font=font_small)

# Add a subtle border
draw.rectangle([10, 10, 710, 710], outline=(100, 100, 100), width=2)

img.save('default_art.jpg', quality=95)
print("Created default_art.jpg")
EOF

# Set up systemd services
echo "⚙️  Setting up systemd services..."
sudo cp album-display.service /etc/systemd/system/
sudo cp album-server.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable album-display.service
sudo systemctl enable album-server.service

# Set permissions
chmod +x display_app.py server_app.py

echo "✅ Setup complete!"
echo ""
echo "🚀 To start the services:"
echo "   sudo systemctl start album-server"
echo "   sudo systemctl start album-display"
echo ""
echo "🌐 Web interface will be available at: http://$(hostname -I | cut -d' ' -f1):5000"
echo ""
echo "📊 To check status:"
echo "   sudo systemctl status album-display"
echo "   sudo systemctl status album-server"
echo ""
echo "📝 To view logs:"
echo "   sudo journalctl -u album-display -f"
echo "   sudo journalctl -u album-server -f"
echo ""
echo "🔧 Manual testing:"
echo "   uv run python server_app.py &"
echo "   uv run python display_app.py"