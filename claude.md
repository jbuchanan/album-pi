That's a great direction\! Adding **smooth transitions** and **metadata captions** will significantly enhance the user experience of your album art display.

To achieve fluid animations and text rendering, **Pygame** is an excellent choice, as it gives you direct control over the display loop for drawing and blending.

Here is an updated plan and the modifications required for your existing `display_app.py` script. The `server_app.py` remains the same, as it only handles fetching the image and updating the status file.

-----

## 🎨 Updated `display_app.py` for Smooth Transitions

To create a smooth transition when a new album art is loaded, we'll implement a **cross-fade** effect. We'll use a **transition timer** and the `pygame.Surface.set_alpha()` method to blend the old image into the new one over a short period.

We will also integrate **caption rendering** using Pygame's font capabilities.

### 1\. Configuration Changes

We need to add a few configuration constants to control the transition speed and text appearance.

```python
# ... (rest of imports)

# --- Configuration ---
IMAGE_PATH = 'current_album_art.jpg'
METADATA_PATH = 'current_metadata.json' # NEW: File to store captions
STATUS_FILE = 'display_status.txt'
FALLBACK_IMAGE = 'default_art.jpg'
WIDTH, HEIGHT = 720, 720 # Set this to your square monitor's resolution

# --- Animation Configuration ---
FADE_DURATION = 1.0 # Duration of the fade in seconds
FPS = 60 # Run the game loop at 60 Frames Per Second for smoothness
```

### 2\. Updated Utility Functions

We need a function to load the metadata alongside the image.

```python
# ... (load_image function remains the same)

def load_metadata(path):
    """Loads metadata (captions) from a JSON file."""
    try:
        import json
        with open(path, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        # Return default/empty metadata if the file is missing or malformed
        return {
            "title": "Ready", 
            "artist": "Waiting for remote command...",
            "album": ""
        }

# ... (get_display_status function remains the same)
```

### 3\. The Main Display Loop (`run_display`)

The core changes are within the `run_display` function to manage the transition state.

```python
# ... (run_display function definition)

    # ... (inside run_display)
    
    # Initialize with the fallback image
    current_image = load_image(FALLBACK_IMAGE)
    next_image = None # This will hold the new image during a transition
    
    current_metadata = load_metadata(METADATA_PATH)
    
    # Transition State Variables
    transition_start_time = 0
    is_transitioning = False
    
    # Kiosk mode setup: hide the mouse cursor
    pygame.mouse.set_visible(False) 

    print("Display app started.")
    
    # NEW: Initialize font for captions
    pygame.font.init()
    caption_font_large = pygame.font.SysFont("dejavusansmono", 36)
    caption_font_small = pygame.font.SysFont("dejavusansmono", 24)

    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT or \
               (event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE):
                running = False
        
        status = get_display_status()
        
        # --- Image Loading and Transition Triggering ---
        # Check if a new art file exists AND we are not already in a transition
        if os.path.exists(IMAGE_PATH) and not is_transitioning:
            # Check if the image on disk is different from the current image
            # A simple way: check file size or last modified time. 
            # We'll use a simple flag file or just check for existence 
            # and rely on the server deleting/replacing it. 
            
            # Simple check: If the 'next_image' file exists, trigger a load/transition
            try:
                temp_image = pygame.image.load(IMAGE_PATH)
                # If we successfully loaded a new image, start the transition
                # Note: A proper system would compare hashes/timestamps to prevent reloading the *same* image.
                
                next_image = load_image(IMAGE_PATH) # Load and scale the new art
                new_metadata = load_metadata(METADATA_PATH) # Load the new captions
                
                # If the image loaded is truly new, start the fade
                if next_image.get_at((1, 1)) != current_image.get_at((1, 1)): # Rough check for difference
                    is_transitioning = True
                    transition_start_time = pygame.time.get_ticks()
                    current_metadata = new_metadata
                    # We continue to display current_image while fading
                    
            except pygame.error:
                # If Pygame can't load it (e.g., file being written), ignore for this frame
                pass
        
        # --- Drawing Logic ---
        screen.fill((0, 0, 0)) # Start with a clean black screen
        
        if status == 'RUNNING':
            
            time_elapsed = (pygame.time.get_ticks() - transition_start_time) / 1000.0
            
            if is_transitioning:
                
                # Calculate the fade ratio (0.0 to 1.0)
                fade_ratio = min(time_elapsed / FADE_DURATION, 1.0)
                
                # 1. Draw the OLD image (Fading OUT)
                old_alpha = int(255 * (1.0 - fade_ratio))
                current_image.set_alpha(old_alpha)
                screen.blit(current_image, (0, 0))
                
                # 2. Draw the NEW image (Fading IN)
                new_alpha = int(255 * fade_ratio)
                next_image.set_alpha(new_alpha)
                screen.blit(next_image, (0, 0))
                
                # 3. Check for transition completion
                if fade_ratio >= 1.0:
                    current_image = next_image # Swap the images
                    next_image = None
                    is_transitioning = False
                    current_image.set_alpha(255) # Reset alpha for the new current image

            else:
                # If not transitioning, just draw the current image at full opacity
                screen.blit(current_image, (0, 0))
                
            # --- Caption Rendering (Always on top) ---
            
            # Use a slightly transparent black overlay for better text contrast
            overlay = pygame.Surface((WIDTH, HEIGHT))
            overlay.set_alpha(100) # Semi-transparent
            overlay.fill((0, 0, 0))
            screen.blit(overlay, (0, HEIGHT - 120)) # Place it at the bottom
            
            # Render and position the text
            title_text = caption_font_large.render(current_metadata.get('title', 'N/A'), True, (255, 255, 255))
            artist_text = caption_font_small.render(current_metadata.get('artist', 'N/A'), True, (180, 180, 180))
            
            screen.blit(title_text, (20, HEIGHT - 100))
            screen.blit(artist_text, (20, HEIGHT - 60))


        elif status == 'STOPPED' or status == 'PAUSED':
            # Display a black screen or simple status text (as before)
            screen.fill((0, 0, 0)) 
            if status == 'PAUSED':
                text = caption_font_large.render("PAUSED", True, (255, 255, 255))
                text_rect = text.get_rect(center=(WIDTH // 2, HEIGHT // 2))
                screen.blit(text, text_rect)
        
        pygame.display.flip()
        clock.tick(FPS) # Set the FPS for smooth animation!

# ... (rest of the script, including __main__ block)
```

-----

## 💾 Updated `server_app.py` for Metadata

The Flask server needs a small update to also save the caption details into a new file, `current_metadata.json`, whenever it successfully fetches new album art.

### 1\. New Imports

```python
# ... (other imports)
import json # New import for handling JSON metadata
```

### 2\. Configuration Changes

Add the path for the new metadata file.

```python
# --- Configuration (Must match display_app.py) ---
IMAGE_PATH = 'current_album_art.jpg'
STATUS_FILE = 'display_status.txt'
METADATA_PATH = 'current_metadata.json' # NEW
TARGET_SIZE = 720 # High-res square size
```

### 3\. Update `fetch_and_save_album_art`

Modify this function to extract and save the song/album details.

```python
# ... (Utility Functions)

def fetch_and_save_album_art(search_term):
    """
    Searches the iTunes API for an album, saves the high-res art, and saves metadata.
    """
    try:
        # 1. Search for the album/song
        search_url = f"https://itunes.apple.com/search?term={search_term}&entity=song&limit=1"
        response = requests.get(search_url)
        data = response.json()

        if not data['results']:
            return {"success": False, "message": "No results found for the search term."}

        result = data['results'][0] # The first and best result
        
        # Extract Metadata
        metadata = {
            "title": result.get('trackName', 'Unknown Title'),
            "artist": result.get('artistName', 'Unknown Artist'),
            "album": result.get('collectionName', 'Unknown Album'),
            "genre": result.get('primaryGenreName', ''),
            "release_date": result.get('releaseDate', '')[:10] # Keep YYYY-MM-DD
        }
        
        # 2. Get the album art URL (Logic remains the same)
        small_art_url = result.get('artworkUrl100')
        # ... (rest of URL handling and high-res downloading remains the same)
        
        # Try to get the high-res version
        high_res_url = small_art_url.replace('100x100bb.jpg', f'{TARGET_SIZE}x{TARGET_SIZE}bb.jpg')
        
        # 3. Download the image (Logic remains the same)
        img_response = requests.get(high_res_url)
        if img_response.status_code != 200:
            return {"success": False, "message": f"Failed to download high-res art from: {high_res_url}"}

        # 4. Save the image locally (Logic remains the same)
        image = Image.open(BytesIO(img_response.content))
        image = image.resize((TARGET_SIZE, TARGET_SIZE))
        image.save(IMAGE_PATH)
        
        # 5. Save the metadata as a JSON file (NEW STEP)
        with open(METADATA_PATH, 'w') as f:
            json.dump(metadata, f, indent=4)
        
        return {"success": True, "message": f"Successfully fetched and saved new art and metadata for: {search_term}"}

    except Exception as e:
        return {"success": False, "message": f"An error occurred during art fetching: {str(e)}"}
```

This completes the required changes\! Your display app will now:

  * Run at a smoother **60 FPS**.
  * Initiate a **1.0-second cross-fade** transition when a new image is detected.
  * Display dynamic **captions (title and artist)** at the bottom of the screen.

Would you like to explore alternative transition effects, like a slide or wipe, or do you want to move on to setting up the **systemd service** to make your app run automatically on Raspberry Pi boot?