#!/usr/bin/env python3
from flask import Flask, request, jsonify, render_template_string
import requests
import json
import os
import tempfile
import shutil
from PIL import Image
from io import BytesIO
import time
import hashlib
from typing import Dict, Any, Optional
import base64

from config_manager import get_config
from image_cache import ImageCache
from utils import retry_with_backoff

app = Flask(__name__)

# Global instances
config = get_config()
image_cache = None  # Initialized in main

# Configuration
IMAGE_PATH = 'current_album_art.jpg'
METADATA_PATH = 'current_metadata.json'
STATUS_FILE = 'display_status.txt'

# In-memory cache for API responses (short-term)
_api_cache = {}

def get_image_size() -> int:
    """Get target image size based on display resolution"""
    width = config.get('display.width', 0)
    if width == 0:
        # If not detected yet, use configured or default
        size = config.get('image.target_size', 720)
        return size if size > 0 else 720
    # Use display width for square displays
    return width

def get_cached_api_response(search_term: str) -> Optional[Dict[str, Any]]:
    """Get cached API response if still valid"""
    cache_key = hashlib.md5(search_term.lower().encode()).hexdigest()
    if cache_key in _api_cache:
        cached_data, timestamp = _api_cache[cache_key]
        cache_duration = config.get('server.cache_duration', 3600)
        if time.time() - timestamp < cache_duration:
            return cached_data
    return None

def cache_api_response(search_term: str, data: Dict[str, Any]):
    """Cache API response"""
    cache_key = hashlib.md5(search_term.lower().encode()).hexdigest()
    _api_cache[cache_key] = (data, time.time())

    # Limit cache size
    if len(_api_cache) > 100:
        oldest_key = min(_api_cache.keys(), key=lambda k: _api_cache[k][1])
        del _api_cache[oldest_key]

def write_status(status: str):
    """Atomically write display status"""
    try:
        with tempfile.NamedTemporaryFile(mode='w', delete=False, dir='.') as temp_file:
            temp_file.write(status.upper())
            temp_file.flush()
            os.fsync(temp_file.fileno())

        shutil.move(temp_file.name, STATUS_FILE)
    except Exception as e:
        print(f"Error writing status: {e}")

# Spotify Integration
class SpotifyClient:
    """Spotify API client"""

    def __init__(self):
        self.enabled = config.get('music.spotify.enabled', False)
        self.client_id = config.get('music.spotify.client_id', '')
        self.client_secret = config.get('music.spotify.client_secret', '')
        self.access_token = None
        self.token_expires = 0

    def _get_access_token(self) -> bool:
        """Get Spotify access token"""
        if not self.enabled or not self.client_id or not self.client_secret:
            return False

        if self.access_token and time.time() < self.token_expires:
            return True

        try:
            auth_str = f"{self.client_id}:{self.client_secret}"
            auth_bytes = auth_str.encode('utf-8')
            auth_base64 = base64.b64encode(auth_bytes).decode('utf-8')

            headers = {
                'Authorization': f'Basic {auth_base64}',
                'Content-Type': 'application/x-www-form-urlencoded'
            }

            data = {'grant_type': 'client_credentials'}

            response = requests.post(
                'https://accounts.spotify.com/api/token',
                headers=headers,
                data=data,
                timeout=10
            )
            response.raise_for_status()

            token_data = response.json()
            self.access_token = token_data['access_token']
            self.token_expires = time.time() + token_data['expires_in'] - 60

            return True

        except Exception as e:
            print(f"Error getting Spotify token: {e}")
            return False

    @retry_with_backoff(max_attempts=3, initial_delay=1.0)
    def search(self, query: str) -> Optional[Dict[str, Any]]:
        """Search Spotify for track"""
        if not self._get_access_token():
            return None

        try:
            headers = {'Authorization': f'Bearer {self.access_token}'}
            params = {
                'q': query,
                'type': 'track',
                'limit': 5
            }

            response = requests.get(
                'https://api.spotify.com/v1/search',
                headers=headers,
                params=params,
                timeout=10
            )
            response.raise_for_status()

            data = response.json()

            if not data.get('tracks', {}).get('items'):
                return None

            # Get best match
            track = data['tracks']['items'][0]

            # Extract metadata
            metadata = {
                'title': track['name'],
                'artist': ', '.join([artist['name'] for artist in track['artists']]),
                'album': track['album']['name'],
                'release_date': track['album'].get('release_date', '')[:10],
                'spotify_url': track['external_urls'].get('spotify', ''),
                'preview_url': track.get('preview_url', ''),
                'genre': '',  # Spotify doesn't provide genre in track data
                'track_time': self._format_duration(track['duration_ms'])
            }

            # Get album art URL (highest quality)
            images = track['album']['images']
            artwork_url = images[0]['url'] if images else None

            return {
                'metadata': metadata,
                'artwork_url': artwork_url
            }

        except Exception as e:
            print(f"Spotify search error: {e}")
            return None

    def _format_duration(self, ms: int) -> str:
        """Format duration from milliseconds to MM:SS"""
        seconds = ms // 1000
        minutes = seconds // 60
        seconds = seconds % 60
        return f"{minutes}:{seconds:02d}"

spotify_client = SpotifyClient()

@retry_with_backoff(max_attempts=4, initial_delay=2.0, exponential=True)
def download_image(url: str) -> bytes:
    """Download image with retry logic"""
    response = requests.get(url, timeout=15)
    response.raise_for_status()
    return response.content

def fetch_and_save_album_art(search_term: str) -> Dict[str, Any]:
    """Search for album art and metadata, save atomically"""
    try:
        # Check image cache first
        cached = image_cache.get(search_term)
        if cached:
            print(f"Using cached image for: {search_term}")
            # Copy from cache to current
            shutil.copy(cached['file_path'], IMAGE_PATH)
            save_metadata_atomic(cached['metadata'])
            return {
                "success": True,
                "message": f"Loaded from cache: '{search_term}'",
                "metadata": cached['metadata']
            }

        # Check API cache
        cached_api = get_cached_api_response(search_term)
        if cached_api:
            print(f"Using cached API response for: {search_term}")
            return download_and_save_from_cache(cached_api, search_term)

        # Try Spotify first if enabled
        result = None
        if config.get('music.spotify.enabled', False):
            print(f"Searching Spotify for: {search_term}")
            result = spotify_client.search(search_term)

        # Fallback to iTunes if Spotify fails or disabled
        if not result and config.get('music.itunes.enabled', True):
            print(f"Searching iTunes for: {search_term}")
            result = search_itunes(search_term)

        if not result:
            return {"success": False, "message": f"No results found for '{search_term}'"}

        metadata = result['metadata']
        artwork_url = result['artwork_url']

        if not artwork_url:
            return {"success": False, "message": "No album art found"}

        # Cache the API response
        cache_api_response(search_term, result)

        # Download and save
        return download_and_save(artwork_url, metadata, search_term)

    except requests.RequestException as e:
        return {"success": False, "message": f"Network request failed: {str(e)}"}
    except Exception as e:
        return {"success": False, "message": f"Unexpected error: {str(e)}"}

@retry_with_backoff(max_attempts=4, initial_delay=2.0)
def search_itunes(search_term: str) -> Optional[Dict[str, Any]]:
    """Search iTunes API for album art and metadata"""
    search_url = "https://itunes.apple.com/search"
    params = {
        'term': search_term,
        'entity': 'song',
        'limit': 5,
        'media': 'music'
    }

    response = requests.get(search_url, params=params, timeout=10)
    response.raise_for_status()
    data = response.json()

    if not data.get('results'):
        return None

    # Find best match
    result = find_best_itunes_match(data['results'], search_term)

    # Extract metadata
    metadata = {
        "title": result.get('trackName', 'Unknown Title'),
        "artist": result.get('artistName', 'Unknown Artist'),
        "album": result.get('collectionName', 'Unknown Album'),
        "genre": result.get('primaryGenreName', ''),
        "release_date": (result.get('releaseDate', '') or '')[:10],
        "track_time": format_duration(result.get('trackTimeMillis', 0)),
        "preview_url": result.get('previewUrl', ''),
        "itunes_url": result.get('trackViewUrl', '')
    }

    # Get high-res artwork URL
    artwork_url = result.get('artworkUrl100', result.get('artworkUrl60'))
    if artwork_url:
        # Request higher resolution
        target_size = get_image_size()
        artwork_url = artwork_url.replace('100x100bb.jpg', f'{target_size}x{target_size}bb.jpg')

    return {
        'metadata': metadata,
        'artwork_url': artwork_url
    }

def find_best_itunes_match(results: list, search_term: str) -> Dict[str, Any]:
    """Find best matching result from iTunes search"""
    search_lower = search_term.lower()

    scored_results = []
    for result in results:
        score = 0

        track_name = result.get('trackName', '').lower()
        artist_name = result.get('artistName', '').lower()
        album_name = result.get('collectionName', '').lower()

        if search_lower == track_name or search_lower == f"{artist_name} {track_name}":
            score += 100
        elif search_lower in track_name or track_name in search_lower:
            score += 50

        if search_lower in artist_name or artist_name in search_lower:
            score += 30

        if search_lower in album_name or album_name in search_lower:
            score += 20

        if result.get('artworkUrl100'):
            score += 10

        scored_results.append((score, result))

    return max(scored_results, key=lambda x: x[0])[1]

def format_duration(milliseconds: int) -> str:
    """Format duration from milliseconds to MM:SS"""
    if not milliseconds:
        return ""

    seconds = milliseconds // 1000
    minutes = seconds // 60
    seconds = seconds % 60
    return f"{minutes}:{seconds:02d}"

def download_and_save_from_cache(cached_data: Dict[str, Any], search_term: str) -> Dict[str, Any]:
    """Download and save from cached API response"""
    try:
        return download_and_save(
            cached_data['artwork_url'],
            cached_data['metadata'],
            search_term
        )
    except Exception as e:
        return {"success": False, "message": f"Error saving cached content: {str(e)}"}

def download_and_save(artwork_url: str, metadata: Dict[str, str], search_term: str) -> Dict[str, Any]:
    """Download artwork and save both image and metadata atomically"""
    try:
        # Download with retry
        print(f"Downloading artwork from: {artwork_url}")
        img_data = download_image(artwork_url)

        # Process image
        image = Image.open(BytesIO(img_data))

        # Convert to RGB if necessary
        if image.mode != 'RGB':
            image = image.convert('RGB')

        # Get target size
        target_size = get_image_size()

        # Resize to target size
        image = image.resize((target_size, target_size), Image.Resampling.LANCZOS)

        # Save to BytesIO for caching
        img_bytes_io = BytesIO()
        jpeg_quality = config.get('image.jpeg_quality', 95)
        image.save(img_bytes_io, 'JPEG', quality=jpeg_quality, optimize=True)
        img_bytes = img_bytes_io.getvalue()

        # Save to image cache
        cache_path = image_cache.put(search_term, img_bytes, metadata, artwork_url)
        print(f"Saved to cache: {cache_path}")

        # Save current image atomically
        save_image_atomic_from_bytes(img_bytes)

        # Save metadata atomically
        save_metadata_atomic(metadata)

        print(f"Successfully saved album art and metadata for: {search_term}")

        return {
            "success": True,
            "message": f"Successfully fetched and saved album art for '{search_term}'",
            "metadata": metadata
        }

    except requests.RequestException as e:
        return {"success": False, "message": f"Failed to download artwork: {str(e)}"}
    except Exception as e:
        return {"success": False, "message": f"Error processing artwork: {str(e)}"}

def save_image_atomic_from_bytes(img_bytes: bytes):
    """Save image from bytes using atomic operation"""
    with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False, dir='.') as temp_file:
        temp_file.write(img_bytes)
        temp_file.flush()
        os.fsync(temp_file.fileno())

    shutil.move(temp_file.name, IMAGE_PATH)

def save_metadata_atomic(metadata: Dict[str, str]):
    """Save metadata using atomic operation"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, dir='.') as temp_file:
        json.dump(metadata, temp_file, indent=2, ensure_ascii=False)
        temp_file.flush()
        os.fsync(temp_file.fileno())

    shutil.move(temp_file.name, METADATA_PATH)

# Enhanced Web Interface with Configuration Controls
WEB_INTERFACE = """
<!DOCTYPE html>
<html>
<head>
    <title>Album Art Display Control</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * { box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif;
            max-width: 1000px;
            margin: 0 auto;
            padding: 20px;
            background: #f8f9fa;
        }
        .container {
            background: white;
            padding: 30px;
            border-radius: 12px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            margin-bottom: 20px;
        }
        h1 {
            color: #333;
            text-align: center;
            margin-top: 0;
            font-size: 28px;
        }
        h2 {
            color: #555;
            font-size: 20px;
            margin-top: 30px;
            border-bottom: 2px solid #007cba;
            padding-bottom: 8px;
        }
        input[type="text"], select {
            width: 100%;
            padding: 12px;
            font-size: 16px;
            border: 2px solid #ddd;
            border-radius: 6px;
            margin: 10px 0;
            transition: border-color 0.3s;
        }
        input[type="text"]:focus, select:focus {
            outline: none;
            border-color: #007cba;
        }
        button {
            background: #007cba;
            color: white;
            padding: 12px 24px;
            font-size: 16px;
            border: none;
            border-radius: 6px;
            cursor: pointer;
            margin: 10px 5px;
            transition: background 0.3s;
        }
        button:hover { background: #005a87; }
        button:active { transform: translateY(1px); }
        .controls { text-align: center; margin: 20px 0; }
        .status {
            margin: 20px 0;
            padding: 15px;
            border-radius: 6px;
            animation: fadeIn 0.3s;
        }
        @keyframes fadeIn {
            from { opacity: 0; }
            to { opacity: 1; }
        }
        .success { background: #d4edda; color: #155724; border: 1px solid #c3e6cb; }
        .error { background: #f8d7da; color: #721c24; border: 1px solid #f5c6cb; }
        .current-info {
            background: #e7f3ff;
            padding: 20px;
            border-radius: 6px;
            margin: 20px 0;
            border-left: 4px solid #007cba;
        }
        .current-info h3 { margin-top: 0; color: #007cba; }
        .metadata { font-size: 14px; color: #666; line-height: 1.8; }
        .config-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 20px;
            margin: 20px 0;
        }
        .config-item {
            background: #f8f9fa;
            padding: 15px;
            border-radius: 6px;
            border: 1px solid #e0e0e0;
        }
        .config-item label {
            display: block;
            font-weight: 600;
            margin-bottom: 8px;
            color: #444;
        }
        .config-item input[type="checkbox"] {
            width: auto;
            margin-right: 8px;
        }
        .config-item input[type="range"] {
            width: 100%;
        }
        .cache-stats {
            display: flex;
            justify-content: space-around;
            text-align: center;
            margin: 20px 0;
        }
        .cache-stat {
            padding: 15px;
            background: #f0f0f0;
            border-radius: 6px;
        }
        .cache-stat-value {
            font-size: 24px;
            font-weight: bold;
            color: #007cba;
        }
        .cache-stat-label {
            font-size: 12px;
            color: #666;
            text-transform: uppercase;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>🎵 Album Art Display Control</h1>

        <form id="searchForm">
            <input type="text" id="searchTerm" placeholder="Enter artist and song/album (e.g., 'Pink Floyd Dark Side')" required>
            <button type="submit">Update Display</button>
        </form>

        <div class="controls">
            <button onclick="controlDisplay('pause')">⏸️ Pause</button>
            <button onclick="controlDisplay('resume')">▶️ Resume</button>
            <button onclick="controlDisplay('stop')">⏹️ Stop</button>
        </div>

        <div id="status"></div>
        <div id="currentInfo" class="current-info" style="display:none;"></div>
    </div>

    <div class="container">
        <h2>⚙️ Display Configuration</h2>

        <div class="config-grid">
            <div class="config-item">
                <label for="transitionEffect">Transition Effect</label>
                <select id="transitionEffect" onchange="updateConfig()">
                    <option value="fade">Fade</option>
                    <option value="slide">Slide</option>
                    <option value="zoom">Zoom</option>
                    <option value="random">Random</option>
                </select>
            </div>

            <div class="config-item">
                <label for="transitionDuration">Transition Duration: <span id="durationValue">1.0s</span></label>
                <input type="range" id="transitionDuration" min="0.3" max="3.0" step="0.1" value="1.0"
                       oninput="updateDurationLabel(); updateConfig()">
            </div>

            <div class="config-item">
                <label>
                    <input type="checkbox" id="ambientLight" onchange="updateConfig()" checked>
                    Ambient Lighting
                </label>
            </div>

            <div class="config-item">
                <label>
                    <input type="checkbox" id="showClock" onchange="updateConfig()">
                    Show Clock
                </label>
            </div>

            <div class="config-item">
                <label>
                    <input type="checkbox" id="showQR" onchange="updateConfig()">
                    Show QR Code
                </label>
            </div>

            <div class="config-item">
                <label for="clockFormat">Clock Format</label>
                <select id="clockFormat" onchange="updateConfig()">
                    <option value="12h">12 Hour</option>
                    <option value="24h">24 Hour</option>
                </select>
            </div>
        </div>

        <button onclick="saveConfig()" style="width: 100%; margin-top: 20px;">💾 Save Configuration</button>
    </div>

    <div class="container">
        <h2>📊 Cache Statistics</h2>
        <div id="cacheStats" class="cache-stats"></div>
        <button onclick="clearCache()" style="background: #dc3545;">🗑️ Clear Cache</button>
    </div>

    <script>
        function showStatus(message, isSuccess = true) {
            const statusDiv = document.getElementById('status');
            statusDiv.innerHTML = message;
            statusDiv.className = 'status ' + (isSuccess ? 'success' : 'error');
            setTimeout(() => statusDiv.innerHTML = '', 5000);
        }

        function updateDurationLabel() {
            const value = document.getElementById('transitionDuration').value;
            document.getElementById('durationValue').textContent = value + 's';
        }

        document.getElementById('searchForm').addEventListener('submit', function(e) {
            e.preventDefault();
            const searchTerm = document.getElementById('searchTerm').value;

            showStatus('Searching...', true);

            fetch('/update', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ search: searchTerm })
            })
            .then(response => response.json())
            .then(data => {
                showStatus(data.message, data.success);
                if (data.success && data.metadata) {
                    updateCurrentInfo(data.metadata);
                }
                loadCacheStats();
            })
            .catch(error => showStatus('Request failed: ' + error.message, false));
        });

        function controlDisplay(action) {
            fetch('/' + action, { method: 'POST' })
            .then(response => response.json())
            .then(data => showStatus(data.message, data.success))
            .catch(error => showStatus('Request failed: ' + error.message, false));
        }

        function updateCurrentInfo(metadata) {
            const infoDiv = document.getElementById('currentInfo');
            infoDiv.innerHTML = `
                <h3>Currently Displaying:</h3>
                <strong style="font-size: 18px;">${metadata.title}</strong><br>
                <span class="metadata">by ${metadata.artist}</span><br>
                <span class="metadata">from ${metadata.album}</span><br>
                ${metadata.genre ? `<span class="metadata">Genre: ${metadata.genre}</span><br>` : ''}
                ${metadata.release_date ? `<span class="metadata">Released: ${metadata.release_date}</span><br>` : ''}
                ${metadata.track_time ? `<span class="metadata">Duration: ${metadata.track_time}</span>` : ''}
            `;
            infoDiv.style.display = 'block';
        }

        function updateConfig() {
            const config = {
                transitions: {
                    effect: document.getElementById('transitionEffect').value,
                    duration: parseFloat(document.getElementById('transitionDuration').value)
                },
                effects: {
                    ambient_light: {
                        enabled: document.getElementById('ambientLight').checked
                    }
                },
                overlays: {
                    clock: {
                        enabled: document.getElementById('showClock').checked,
                        format: document.getElementById('clockFormat').value
                    },
                    qr_code: {
                        enabled: document.getElementById('showQR').checked
                    }
                }
            };

            // Auto-save
            localStorage.setItem('displayConfig', JSON.stringify(config));
        }

        function saveConfig() {
            fetch('/config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: localStorage.getItem('displayConfig')
            })
            .then(response => response.json())
            .then(data => showStatus(data.message, data.success))
            .catch(error => showStatus('Failed to save config: ' + error.message, false));
        }

        function loadCacheStats() {
            fetch('/cache/stats')
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    const stats = data.stats;
                    document.getElementById('cacheStats').innerHTML = `
                        <div class="cache-stat">
                            <div class="cache-stat-value">${stats.entry_count}</div>
                            <div class="cache-stat-label">Cached Images</div>
                        </div>
                        <div class="cache-stat">
                            <div class="cache-stat-value">${stats.total_size_mb.toFixed(1)} MB</div>
                            <div class="cache-stat-label">Cache Size</div>
                        </div>
                        <div class="cache-stat">
                            <div class="cache-stat-value">${stats.total_accesses}</div>
                            <div class="cache-stat-label">Total Accesses</div>
                        </div>
                    `;
                }
            });
        }

        function clearCache() {
            if (confirm('Are you sure you want to clear the image cache?')) {
                fetch('/cache/clear', { method: 'POST' })
                .then(response => response.json())
                .then(data => {
                    showStatus(data.message, data.success);
                    loadCacheStats();
                });
            }
        }

        // Load current metadata on page load
        fetch('/current')
        .then(response => response.json())
        .then(data => {
            if (data.success && data.metadata) {
                updateCurrentInfo(data.metadata);
            }
        });

        // Load config from storage
        const savedConfig = localStorage.getItem('displayConfig');
        if (savedConfig) {
            try {
                const config = JSON.parse(savedConfig);
                document.getElementById('transitionEffect').value = config.transitions?.effect || 'fade';
                document.getElementById('transitionDuration').value = config.transitions?.duration || 1.0;
                document.getElementById('ambientLight').checked = config.effects?.ambient_light?.enabled !== false;
                document.getElementById('showClock').checked = config.overlays?.clock?.enabled || false;
                document.getElementById('clockFormat').value = config.overlays?.clock?.format || '12h';
                document.getElementById('showQR').checked = config.overlays?.qr_code?.enabled || false;
                updateDurationLabel();
            } catch (e) {}
        }

        // Load cache stats on page load
        loadCacheStats();
    </script>
</body>
</html>
"""

# Flask routes
@app.route('/')
def index():
    """Serve the web control interface"""
    return render_template_string(WEB_INTERFACE)

@app.route('/update', methods=['POST'])
def update_display():
    """Update the display with new album art"""
    try:
        data = request.get_json()
        search_term = data.get('search', '').strip()

        if not search_term:
            return jsonify({"success": False, "message": "Search term is required"})

        result = fetch_and_save_album_art(search_term)

        # Ensure display is running
        if result['success']:
            write_status('RUNNING')

        return jsonify(result)

    except Exception as e:
        return jsonify({"success": False, "message": f"Server error: {str(e)}"})

@app.route('/pause', methods=['POST'])
def pause_display():
    """Pause the display"""
    write_status('PAUSED')
    return jsonify({"success": True, "message": "Display paused"})

@app.route('/resume', methods=['POST'])
def resume_display():
    """Resume the display"""
    write_status('RUNNING')
    return jsonify({"success": True, "message": "Display resumed"})

@app.route('/stop', methods=['POST'])
def stop_display():
    """Stop the display"""
    write_status('STOPPED')
    return jsonify({"success": True, "message": "Display stopped"})

@app.route('/current', methods=['GET'])
def get_current():
    """Get current metadata"""
    try:
        if os.path.exists(METADATA_PATH):
            with open(METADATA_PATH, 'r') as f:
                metadata = json.load(f)
            return jsonify({"success": True, "metadata": metadata})
        else:
            return jsonify({"success": False, "message": "No current metadata"})
    except Exception as e:
        return jsonify({"success": False, "message": f"Error reading metadata: {str(e)}"})

@app.route('/status', methods=['GET'])
def get_status():
    """Get current display status"""
    try:
        if os.path.exists(STATUS_FILE):
            with open(STATUS_FILE, 'r') as f:
                status = f.read().strip()
            return jsonify({"success": True, "status": status})
        else:
            return jsonify({"success": True, "status": "RUNNING"})
    except Exception as e:
        return jsonify({"success": False, "message": f"Error reading status: {str(e)}"})

@app.route('/config', methods=['POST'])
def save_config_endpoint():
    """Save configuration"""
    try:
        updates = request.get_json()
        config.update_from_dict(updates)
        config.save()
        return jsonify({"success": True, "message": "Configuration saved successfully"})
    except Exception as e:
        return jsonify({"success": False, "message": f"Error saving config: {str(e)}"})

@app.route('/cache/stats', methods=['GET'])
def cache_stats():
    """Get cache statistics"""
    try:
        stats = image_cache.get_stats()
        return jsonify({"success": True, "stats": stats})
    except Exception as e:
        return jsonify({"success": False, "message": f"Error getting stats: {str(e)}"})

@app.route('/cache/clear', methods=['POST'])
def clear_cache_endpoint():
    """Clear image cache"""
    try:
        image_cache.clear()
        return jsonify({"success": True, "message": "Cache cleared successfully"})
    except Exception as e:
        return jsonify({"success": False, "message": f"Error clearing cache: {str(e)}"})

if __name__ == "__main__":
    # Initialize image cache
    cache_dir = config.get('image.cache_dir', 'image_cache')
    max_cache_mb = config.get('image.max_cache_size_mb', 500)
    image_cache = ImageCache(cache_dir, max_cache_mb)

    # Initialize with running status
    write_status('RUNNING')

    host = config.get('server.host', '0.0.0.0')
    port = config.get('server.port', 5000)

    print("Album Art Server starting...")
    print(f"Web interface will be available at http://localhost:{port}")
    print(f"Image cache: {cache_dir} (max {max_cache_mb} MB)")
    print(f"Spotify integration: {'enabled' if config.get('music.spotify.enabled') else 'disabled'}")

    # Run server
    app.run(host=host, port=port, debug=False)
