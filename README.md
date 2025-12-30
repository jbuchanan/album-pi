# 🎵 Album Art Display for Raspberry Pi

A beautiful, full-featured album art display system for Raspberry Pi with smooth transitions, configurable overlays, and remote control via web interface. Perfect for square monitors and digital picture frames!

## ✨ Features

### Display & Visual Effects
- **Dynamic Resolution Detection**: Auto-detects your display size for optimal quality
- **High-Resolution Images**: Automatically fetches up to 3000x3000px album art
- **Multiple Transition Effects**: Choose from Fade, Slide, Zoom, or Random transitions
- **Ambient Lighting**: Gorgeous color glow effects extracted from album art
- **60 FPS Animations**: Buttery-smooth transitions

### Information Overlays (Configurable)
- **Metadata Display**: Song title, artist, and album information with elegant overlay
- **Clock**: Display current time (12h or 24h format, customizable position)
- **Weather**: Real-time weather information (requires OpenWeatherMap API)
- **QR Codes**: Scannable links to songs on Spotify/Apple Music

### Music Sources
- **Spotify Integration**: Primary source for high-quality metadata and artwork
- **iTunes API**: Automatic fallback for comprehensive music coverage
- **Smart Caching**: Persistent image cache with SQLite database

### Control & Configuration
- **Web Control Interface**: Remote control from any device on your network
- **Live Configuration**: Change effects and overlays in real-time via web UI
- **YAML Configuration**: Easy-to-edit configuration file
- **REST API**: Programmatic control endpoints

### Performance & Reliability
- **Enhanced Error Handling**: Automatic retry with exponential backoff
- **Persistent Cache**: Reduces API calls and speeds up repeated searches
- **Atomic File Operations**: Prevents corruption
- **Cross-Platform**: Works on macOS for testing, Raspberry Pi for production

## 🖥️ Hardware Requirements

- Raspberry Pi 3B+ or newer (Pi 4 recommended for best performance)
- MicroSD card (16GB+ recommended)
- Square display (any resolution - auto-detected: 720x720, 1024x1024, 1080x1080, etc.)
- Network connection (WiFi or Ethernet)

## 🚀 Quick Setup (Raspberry Pi)

1. **Clone and setup:**
   ```bash
   git clone <your-repo-url> album-pi
   cd album-pi
   chmod +x setup.sh
   ./setup.sh
   ```

2. **Configure (Optional):**
   Edit `config.yaml` to customize settings, enable overlays, or add Spotify credentials

3. **Start services:**
   ```bash
   sudo systemctl start album-server
   sudo systemctl start album-display
   ```

4. **Access web interface:**
   - Open browser to `http://[PI_IP_ADDRESS]:5000`
   - Search for any artist/song/album
   - Enjoy the display!

## 🍎 Testing on macOS

Perfect for testing before deploying to your Pi! See [TESTING_ON_MAC.md](TESTING_ON_MAC.md) for detailed instructions.

**Quick start:**
```bash
# Install dependencies
brew install python3 sdl2 sdl2_image sdl2_mixer sdl2_ttf

# Install uv (fast Python package manager)
curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.cargo/env

# Install Python packages
uv sync

# Run (in separate terminals)
uv run python server_app.py
uv run python display_app.py

# Open browser to http://localhost:5000
```

The system automatically detects macOS and runs in windowed mode for easy testing.

## ⚙️ Configuration

### Basic Configuration (`config.yaml`)

```yaml
# Display Settings
display:
  width: 0              # 0 for auto-detect
  height: 0             # 0 for auto-detect
  fullscreen: true      # Auto-detected (false on macOS, true on Pi)
  fps: 60

# Transition Effects
transitions:
  effect: "fade"        # fade, slide, zoom, or random
  duration: 1.0         # seconds

# Visual Effects
effects:
  ambient_light:
    enabled: true
    intensity: 0.3      # 0.0 - 1.0

# Overlays
overlays:
  metadata:
    enabled: true
    position: "bottom"  # top or bottom

  clock:
    enabled: false      # Enable to show clock
    position: "top-right"
    format: "12h"       # 12h or 24h

  weather:
    enabled: false
    api_key: "YOUR_OPENWEATHERMAP_API_KEY"
    location: "San Francisco"
    units: "imperial"   # imperial or metric

  qr_code:
    enabled: false
    position: "bottom-right"
    size: 150
```

### Spotify Integration

To enable Spotify (optional, but recommended for best results):

1. Create a Spotify App at https://developer.spotify.com/dashboard
2. Get your Client ID and Client Secret
3. Add to `config.yaml`:

```yaml
music:
  spotify:
    enabled: true
    client_id: "your_client_id_here"
    client_secret: "your_client_secret_here"
```

## 🌐 Web Interface

The web interface provides:
- **Search**: Find and display any album art
- **Controls**: Pause, resume, or stop the display
- **Live Configuration**: Change transition effects, enable overlays, adjust settings
- **Cache Management**: View cache statistics and clear cache
- **Current Status**: See what's currently playing

### API Endpoints

For programmatic control:

```bash
# Update display
curl -X POST http://localhost:5000/update \
  -H "Content-Type: application/json" \
  -d '{"search":"Pink Floyd Dark Side of the Moon"}'

# Control display
curl -X POST http://localhost:5000/pause
curl -X POST http://localhost:5000/resume
curl -X POST http://localhost:5000/stop

# Get current metadata
curl http://localhost:5000/current

# Get cache stats
curl http://localhost:5000/cache/stats

# Save configuration
curl -X POST http://localhost:5000/config \
  -H "Content-Type: application/json" \
  -d @config.json
```

## 📁 File Structure

```
album-pi/
├── config.yaml              # Main configuration file
├── config_manager.py        # Configuration management system
├── display_app.py           # Main display application
├── server_app.py            # Web server and API
├── image_cache.py           # Persistent image caching with SQLite
├── utils.py                 # Utility functions and retry logic
├── requirements.txt         # Python dependencies
├── setup.sh                 # Automated setup script (Pi)
├── album-display.service    # Systemd service for display
├── album-server.service     # Systemd service for server
├── default_art.jpg          # Fallback image (created by setup)
├── current_album_art.jpg    # Current display image (runtime)
├── current_metadata.json    # Current song info (runtime)
├── display_status.txt       # Display state (runtime)
├── image_cache/             # Persistent image cache directory
│   └── cache.db             # SQLite database
├── TESTING_ON_MAC.md        # macOS testing guide
└── README.md                # This file
```

## 🎨 Usage Examples

### Keyboard Controls (Display)

- **ESC**: Exit the application
- **F11**: Toggle fullscreen mode

### Transition Effects

**Fade** - Classic cross-fade (smooth and elegant)
**Slide** - Images slide in from the side
**Zoom** - Zoom in/out effect
**Random** - Randomly selects an effect for each transition

Try different effects via the web interface to find your favorite!

### Configuring Overlays

Enable/disable overlays via `config.yaml` or the web interface:

```yaml
overlays:
  clock:
    enabled: true
    position: "top-right"    # top-left, top-right, bottom-left, bottom-right
    format: "12h"

  qr_code:
    enabled: true
    position: "bottom-right"
```

Positions automatically adjust to corners without overlapping.

## 🔧 Troubleshooting

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

### Cache Issues

```bash
# Check cache stats via API
curl http://localhost:5000/cache/stats

# Clear cache via API
curl -X POST http://localhost:5000/cache/clear

# Manually delete cache
rm -rf image_cache/
```

### Network Issues

```bash
# Check if port 5000 is accessible
curl http://localhost:5000

# Find Pi's IP address
hostname -I

# Check if services can communicate
ps aux | grep python
```

## 🎯 Performance Tips

### For Raspberry Pi

- Use a fast MicroSD card (Class 10 or UHS-I recommended)
- Ensure good network connectivity for fast image downloads
- Use a heatsink on Pi 4 for sustained performance
- Use a 5V 3A power supply for Pi 4, 2.5A for Pi 3

### For Square Monitors

- System auto-detects resolution for optimal quality
- Higher resolutions (1080x1080, 1440x1440) work great on Pi 4
- Adjust `image.target_size` in config.yaml to match your display
- Enable cache to speed up repeated album loads

### Cache Configuration

```yaml
image:
  cache_dir: "image_cache"
  max_cache_size_mb: 500    # Adjust based on available storage
  jpeg_quality: 95          # 90-100 recommended
```

## 🆕 What's New

### Version 2.0 Features

- ✅ **Dynamic Resolution Detection**: Auto-adapts to any display size
- ✅ **Multiple Transition Effects**: Fade, slide, zoom, and random
- ✅ **Ambient Lighting**: Color-reactive glow effects
- ✅ **Configurable Overlays**: Clock, weather, QR codes
- ✅ **Spotify Integration**: Superior metadata and artwork
- ✅ **Persistent Caching**: SQLite database with smart cleanup
- ✅ **Enhanced Error Handling**: Automatic retry with backoff
- ✅ **Live Configuration**: Real-time settings via web UI
- ✅ **Cross-Platform**: Test on Mac, deploy to Pi
- ✅ **Improved Web UI**: Modern, responsive design

## 📝 Advanced Configuration

### Custom Transition Duration

```yaml
transitions:
  duration: 2.0    # Slower, more dramatic
  # or
  duration: 0.5    # Fast and snappy
```

### Ambient Light Intensity

```yaml
effects:
  ambient_light:
    intensity: 0.5   # Brighter glow
    # or
    intensity: 0.1   # Subtle effect
```

### Multiple Displays

Run multiple instances with different configs:

```bash
# Instance 1
python3 server_app.py &  # Port 5000

# Instance 2 (different directory)
cd ../album-pi-2
python3 server_app.py &  # Configure different port in config.yaml
```

## 🤝 Contributing

Pull requests welcome! Areas for future improvement:

- [ ] Additional transition effects (blur, rotate, 3D flip)
- [ ] Video background support
- [ ] Lyrics display with scrolling
- [ ] Audio visualizer synced to music playback
- [ ] Mobile app for remote control
- [ ] Local music library scanning
- [ ] Integration with other streaming services
- [ ] Multi-display synchronization

## 📄 License

MIT License - Feel free to modify and distribute.

## 🙏 Acknowledgments

- iTunes API for comprehensive music database
- Spotify API for high-quality metadata
- Pygame for excellent graphics library
- Flask for simple web framework

---

**Need help?** Check [TESTING_ON_MAC.md](TESTING_ON_MAC.md) for macOS testing or open an issue on GitHub.

**Ready to deploy?** Follow the Quick Setup guide above for Raspberry Pi installation.

**Want to customize?** Edit `config.yaml` and restart the services - no code changes needed!
