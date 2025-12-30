# Testing Album Art Display on macOS

This guide will help you run the Album Art Display system on your Mac for testing before deploying to Raspberry Pi.

## Quick Start

### 1. Install Dependencies

```bash
# Install Python 3 (if not already installed)
# macOS usually comes with Python 3, but you can install via Homebrew:
brew install python3

# Install SDL2 for pygame (required on macOS)
brew install sdl2 sdl2_image sdl2_mixer sdl2_ttf

# Install uv (fast Python package manager)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Restart your shell or run:
source $HOME/.cargo/env

# Install Python packages with uv
uv sync
```

### 2. Configuration

The config system automatically detects macOS and sets appropriate defaults:
- **Fullscreen**: Disabled (runs in a window)
- **Display Size**: Auto-detected from your monitor

You can customize settings in `config.yaml`:

```yaml
display:
  fullscreen: false  # Window mode for Mac
  width: 800         # Or 0 for auto-detect
  height: 800
```

### 3. Run the Applications

#### Terminal 1 - Start the Server
```bash
uv run python server_app.py
```

#### Terminal 2 - Start the Display
```bash
uv run python display_app.py
```

#### Access Web Interface
Open your browser to: `http://localhost:5000`

## Platform Differences

### macOS (Testing)
- Runs in windowed mode by default
- Easy to test features and transitions
- Can enable fullscreen with `F11` key or in config

### Raspberry Pi (Production)
- Runs in fullscreen kiosk mode
- Auto-starts on boot via systemd
- Optimized for continuous display

## Testing Features

### Test Transition Effects
1. Open web interface
2. Change "Transition Effect" to: Fade, Slide, Zoom, or Random
3. Search for different albums to see transitions

### Test Overlays
- **Clock**: Enable in config to see current time
- **Ambient Lighting**: Toggle to see color glow effects
- **QR Codes**: Enable to show scannable links

### Test Caching
1. Search for an album
2. Search for it again - should load from cache instantly
3. Check cache stats in web interface

## Keyboard Controls

- `ESC`: Exit the display
- `F11`: Toggle fullscreen mode

## Troubleshooting

### pygame not working on macOS
```bash
# Reinstall pygame with proper SDL2 support
uv pip uninstall pygame
uv pip install pygame --no-binary :all:
```

### Display window too large
Set explicit dimensions in `config.yaml`:
```yaml
display:
  width: 600
  height: 600
```

### Port 5000 already in use
Change the port in `config.yaml`:
```yaml
server:
  port: 5001
```

## Transferring to Raspberry Pi

Once you've tested and configured everything:

1. Copy the entire directory to your Raspberry Pi:
   ```bash
   rsync -av album-pi/ pi@raspberrypi.local:~/album-pi/
   ```

2. On the Pi, run the setup script:
   ```bash
   cd ~/album-pi
   chmod +x setup.sh
   ./setup.sh
   ```

3. The system will auto-configure for Raspberry Pi (fullscreen, systemd services, etc.)

## Tips for Testing

1. **Use smaller images** - Faster testing on Mac
2. **Test with local config.yaml** - Tweak settings without editing code
3. **Enable/disable overlays** - See how each feature looks
4. **Try different transition durations** - Find what looks best
5. **Test Spotify integration** - Add credentials to config.yaml

## Configuration for Square Monitors

For your square monitor, the system will auto-detect the resolution. For manual control:

```yaml
display:
  width: 1024   # For 1024x1024 monitors
  height: 1024
  fullscreen: false  # Set to true when ready

image:
  target_size: 1024  # Match display size for best quality
```
