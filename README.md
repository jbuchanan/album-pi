# 🎵 Album Art Display for Raspberry Pi

A beautiful, fullscreen album art display system for Raspberry Pi with smooth transitions and remote control via web interface.

## Features

- **Smooth Transitions**: 60 FPS cross-fade animations between album artworks
- **High-Resolution Images**: Automatically fetches 720x720px album art from iTunes
- **Metadata Display**: Shows song title, artist, and album information with elegant overlay
- **Web Control Interface**: Remote control via any device on your network
- **Smart Caching**: Reduces API calls and improves response times
- **Robust File Handling**: Atomic file operations prevent corruption
- **Kiosk Mode**: Fullscreen display perfect for picture frames or dedicated displays
- **Auto-Start**: Systemd services for automatic startup on boot

## Hardware Requirements

- Raspberry Pi 3B+ or newer (Pi 4 recommended)
- MicroSD card (16GB+ recommended)
- Square display (720x720 or similar)
- Network connection (WiFi or Ethernet)

## Quick Setup

1. **Clone and setup:**
   ```bash
   git clone <your-repo-url> album-pi
   cd album-pi
   chmod +x setup.sh
   ./setup.sh
   ```

2. **Start services:**
   ```bash
   sudo systemctl start album-server
   sudo systemctl start album-display
   ```

3. **Access web interface:**
   - Open browser to `http://[PI_IP_ADDRESS]:5000`
   - Search for any artist/song/album
   - Enjoy the display!

## Manual Installation

If you prefer manual setup:

```bash
# Install system dependencies
sudo apt update && sudo apt upgrade -y
sudo apt install python3 python3-pip python3-venv libsdl2-dev

# Setup Python environment
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Create default image (optional)
python3 -c "from PIL import Image; Image.new('RGB', (720,720), 'black').save('default_art.jpg')"

# Test the applications
python3 server_app.py &    # Starts web server on port 5000
python3 display_app.py     # Starts fullscreen display
```

## Usage

### Web Interface

Navigate to `http://[raspberry-pi-ip]:5000` to control the display:

- **Search**: Enter artist name, song title, or album name
- **Controls**: Pause, resume, or stop the display
- **Status**: View currently playing information

### Keyboard Controls (Display)

- **ESC**: Exit the application
- **F11**: Toggle fullscreen mode

### API Endpoints

The server provides REST API endpoints:

- `POST /update` - Update display with new album art
- `POST /pause` - Pause the display
- `POST /resume` - Resume the display
- `POST /stop` - Stop the display
- `GET /current` - Get current metadata
- `GET /status` - Get display status

## Configuration

Edit the configuration constants at the top of each file:

### `display_app.py`
```python
WIDTH, HEIGHT = 720, 720    # Display resolution
FADE_DURATION = 1.0         # Transition duration in seconds
FPS = 60                    # Frame rate
```

### `server_app.py`
```python
TARGET_SIZE = 720           # Image resolution
CACHE_DURATION = 3600       # Cache duration in seconds
```

## File Structure

```
album-pi/
├── display_app.py          # Main display application
├── server_app.py           # Web server and API
├── requirements.txt        # Python dependencies
├── setup.sh               # Automated setup script
├── album-display.service  # Systemd service for display
├── album-server.service   # Systemd service for server
├── default_art.jpg        # Fallback image (created by setup)
├── current_album_art.jpg  # Current display image (runtime)
├── current_metadata.json  # Current song info (runtime)
└── display_status.txt     # Display state (runtime)
```

## Troubleshooting

### Display Issues
```bash
# Check if display service is running
sudo systemctl status album-display

# View display logs
sudo journalctl -u album-display -f

# Test display manually
source venv/bin/activate
DISPLAY=:0 python3 display_app.py
```

### Server Issues
```bash
# Check server status
sudo systemctl status album-server

# View server logs
sudo journalctl -u album-server -f

# Test server manually
source venv/bin/activate
python3 server_app.py
```

### Network Issues
```bash
# Check if port 5000 is accessible
curl http://localhost:5000

# Find Pi's IP address
hostname -I
```

### Permission Issues
```bash
# Fix file permissions
sudo chown -R pi:pi /home/pi/album-pi
chmod +x display_app.py server_app.py setup.sh
```

## Performance Tips

- Use a fast MicroSD card (Class 10 or better)
- Ensure good network connectivity for fast image downloads
- Consider using a heatsink on Pi 4 for sustained performance
- Use a 5V 3A power supply for Pi 4

## Customization

### Different Display Sizes
Edit `WIDTH, HEIGHT` and `TARGET_SIZE` in both files to match your display.

### Transition Effects
The `TransitionManager` class in `display_app.py` can be modified for different transition effects (slide, zoom, etc.).

### Alternative Data Sources
Replace the iTunes API calls in `server_app.py` with other music APIs like Spotify, Last.fm, or local music databases.

## License

MIT License - Feel free to modify and distribute.

## Contributing

Pull requests welcome! Areas for improvement:
- Additional transition effects
- Support for video backgrounds
- Integration with music streaming services
- Mobile app for remote control