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

app = Flask(__name__)

# Configuration
IMAGE_PATH = 'current_album_art.jpg'
METADATA_PATH = 'current_metadata.json'
STATUS_FILE = 'display_status.txt'
TARGET_SIZE = 720
CACHE_DURATION = 3600  # Cache responses for 1 hour

# Cache for API responses
_cache = {}

def get_cached_response(search_term: str) -> Optional[Dict[str, Any]]:
    """Get cached API response if still valid"""
    cache_key = hashlib.md5(search_term.lower().encode()).hexdigest()
    if cache_key in _cache:
        cached_data, timestamp = _cache[cache_key]
        if time.time() - timestamp < CACHE_DURATION:
            return cached_data
    return None

def cache_response(search_term: str, data: Dict[str, Any]):
    """Cache API response"""
    cache_key = hashlib.md5(search_term.lower().encode()).hexdigest()
    _cache[cache_key] = (data, time.time())

    # Limit cache size
    if len(_cache) > 100:
        oldest_key = min(_cache.keys(), key=lambda k: _cache[k][1])
        del _cache[oldest_key]

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

def fetch_and_save_album_art(search_term: str) -> Dict[str, Any]:
    """
    Search iTunes API for album art and metadata, save atomically.
    """
    try:
        # Check cache first
        cached_result = get_cached_response(search_term)
        if cached_result:
            print(f"Using cached result for: {search_term}")
            # Still need to save files even if cached
            return save_content(cached_result, search_term)

        # Search iTunes API
        search_url = "https://itunes.apple.com/search"
        params = {
            'term': search_term,
            'entity': 'song',
            'limit': 5,
            'media': 'music'
        }

        print(f"Searching iTunes API for: {search_term}")
        response = requests.get(search_url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        if not data.get('results'):
            return {"success": False, "message": f"No results found for '{search_term}'"}

        # Find the best result (prefer exact matches)
        result = find_best_match(data['results'], search_term)

        # Extract metadata
        metadata = extract_metadata(result)

        # Get album art URL
        artwork_url = result.get('artworkUrl100', result.get('artworkUrl60'))
        if not artwork_url:
            return {"success": False, "message": "No album art found"}

        # Convert to high-res URL
        high_res_url = artwork_url.replace('100x100bb.jpg', f'{TARGET_SIZE}x{TARGET_SIZE}bb.jpg')

        # Cache the successful result
        cache_response(search_term, {
            'metadata': metadata,
            'artwork_url': high_res_url
        })

        # Download and save
        return download_and_save(high_res_url, metadata, search_term)

    except requests.RequestException as e:
        return {"success": False, "message": f"API request failed: {str(e)}"}
    except Exception as e:
        return {"success": False, "message": f"Unexpected error: {str(e)}"}

def find_best_match(results: list, search_term: str) -> Dict[str, Any]:
    """Find the best matching result from iTunes search"""
    search_lower = search_term.lower()

    # Score results based on relevance
    scored_results = []
    for result in results:
        score = 0

        # Exact matches get highest priority
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

        # Prefer results with high-quality artwork
        if result.get('artworkUrl100'):
            score += 10

        scored_results.append((score, result))

    # Return highest scoring result
    return max(scored_results, key=lambda x: x[0])[1]

def extract_metadata(result: Dict[str, Any]) -> Dict[str, str]:
    """Extract metadata from iTunes result"""
    return {
        "title": result.get('trackName', 'Unknown Title'),
        "artist": result.get('artistName', 'Unknown Artist'),
        "album": result.get('collectionName', 'Unknown Album'),
        "genre": result.get('primaryGenreName', ''),
        "release_date": (result.get('releaseDate', '') or '')[:10],
        "track_time": format_duration(result.get('trackTimeMillis', 0)),
        "preview_url": result.get('previewUrl', ''),
        "itunes_url": result.get('trackViewUrl', '')
    }

def format_duration(milliseconds: int) -> str:
    """Format duration from milliseconds to MM:SS"""
    if not milliseconds:
        return ""

    seconds = milliseconds // 1000
    minutes = seconds // 60
    seconds = seconds % 60
    return f"{minutes}:{seconds:02d}"

def save_content(cached_data: Dict[str, Any], search_term: str) -> Dict[str, Any]:
    """Save cached content to files"""
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
        # Download artwork
        print(f"Downloading artwork from: {artwork_url}")
        img_response = requests.get(artwork_url, timeout=15)
        img_response.raise_for_status()

        # Process image
        image = Image.open(BytesIO(img_response.content))

        # Convert to RGB if necessary (removes transparency)
        if image.mode != 'RGB':
            image = image.convert('RGB')

        # Resize to target size
        image = image.resize((TARGET_SIZE, TARGET_SIZE), Image.Resampling.LANCZOS)

        # Save image atomically
        save_image_atomic(image)

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

def save_image_atomic(image: Image.Image):
    """Save image using atomic operation"""
    with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False, dir='.') as temp_file:
        image.save(temp_file.name, 'JPEG', quality=95, optimize=True)
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

# Web interface template
WEB_INTERFACE = """
<!DOCTYPE html>
<html>
<head>
    <title>Album Art Display Control</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body { font-family: Arial, sans-serif; max-width: 800px; margin: 50px auto; padding: 20px; }
        .container { background: #f5f5f5; padding: 30px; border-radius: 10px; }
        input[type="text"] { width: 100%; padding: 15px; font-size: 16px; border: 1px solid #ddd; border-radius: 5px; margin: 10px 0; }
        button { background: #007cba; color: white; padding: 15px 30px; font-size: 16px; border: none; border-radius: 5px; cursor: pointer; margin: 10px 5px; }
        button:hover { background: #005a87; }
        .status { margin: 20px 0; padding: 15px; border-radius: 5px; }
        .success { background: #d4edda; color: #155724; border: 1px solid #c3e6cb; }
        .error { background: #f8d7da; color: #721c24; border: 1px solid #f5c6cb; }
        .current-info { background: #e2e3e5; padding: 20px; border-radius: 5px; margin: 20px 0; }
        .controls { text-align: center; margin: 20px 0; }
        h1 { color: #333; text-align: center; }
        .metadata { font-size: 14px; color: #666; }
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

    <script>
        function showStatus(message, isSuccess = true) {
            const statusDiv = document.getElementById('status');
            statusDiv.innerHTML = message;
            statusDiv.className = 'status ' + (isSuccess ? 'success' : 'error');
            setTimeout(() => statusDiv.innerHTML = '', 5000);
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
                <strong>${metadata.title}</strong><br>
                <span class="metadata">by ${metadata.artist}</span><br>
                <span class="metadata">from ${metadata.album}</span><br>
                ${metadata.genre ? `<span class="metadata">Genre: ${metadata.genre}</span><br>` : ''}
                ${metadata.release_date ? `<span class="metadata">Released: ${metadata.release_date}</span><br>` : ''}
                ${metadata.track_time ? `<span class="metadata">Duration: ${metadata.track_time}</span>` : ''}
            `;
            infoDiv.style.display = 'block';
        }

        // Load current metadata on page load
        fetch('/current')
        .then(response => response.json())
        .then(data => {
            if (data.success && data.metadata) {
                updateCurrentInfo(data.metadata);
            }
        });
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

if __name__ == "__main__":
    # Initialize with running status
    write_status('RUNNING')

    print("Album Art Server starting...")
    print("Web interface will be available at http://localhost:5000")

    # Run server
    app.run(host='0.0.0.0', port=5000, debug=False)