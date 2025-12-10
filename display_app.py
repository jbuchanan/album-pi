#!/usr/bin/env python3
import pygame
import os
import json
import time
import threading
import queue
from typing import Optional, Dict, Any

# Configuration
IMAGE_PATH = 'current_album_art.jpg'
METADATA_PATH = 'current_metadata.json'
STATUS_FILE = 'display_status.txt'
FALLBACK_IMAGE = 'default_art.jpg'
WIDTH, HEIGHT = 720, 720

# Animation Configuration
FADE_DURATION = 1.0
FPS = 60

# Performance Configuration
FILE_CHECK_INTERVAL = 0.1  # Check for file changes every 100ms

class ImageLoader:
    """Handles image loading and change detection in a separate thread"""

    def __init__(self):
        self.queue = queue.Queue()
        self.last_image_mtime = 0
        self.last_metadata_mtime = 0
        self.running = True
        self.thread = threading.Thread(target=self._monitor_files, daemon=True)

    def start(self):
        self.thread.start()

    def stop(self):
        self.running = False

    def get_new_content(self) -> Optional[Dict[str, Any]]:
        """Get new image/metadata if available, non-blocking"""
        try:
            return self.queue.get_nowait()
        except queue.Empty:
            return None

    def _monitor_files(self):
        """Monitor files for changes in background thread"""
        while self.running:
            try:
                # Check if image file has changed
                if os.path.exists(IMAGE_PATH):
                    current_mtime = os.path.getmtime(IMAGE_PATH)
                    if current_mtime > self.last_image_mtime:
                        self.last_image_mtime = current_mtime

                        # Load new image and metadata
                        try:
                            image = self._load_and_scale_image(IMAGE_PATH)
                            metadata = self._load_metadata()

                            self.queue.put({
                                'image': image,
                                'metadata': metadata
                            })
                        except Exception as e:
                            print(f"Error loading new content: {e}")

                time.sleep(FILE_CHECK_INTERVAL)
            except Exception as e:
                print(f"File monitor error: {e}")
                time.sleep(FILE_CHECK_INTERVAL)

    def _load_and_scale_image(self, path: str) -> pygame.Surface:
        """Load and scale image to fit screen"""
        image = pygame.image.load(path)
        return pygame.transform.scale(image, (WIDTH, HEIGHT))

    def _load_metadata(self) -> Dict[str, str]:
        """Load metadata from JSON file"""
        try:
            with open(METADATA_PATH, 'r') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return {
                "title": "Ready",
                "artist": "Waiting for remote command...",
                "album": ""
            }

def load_fallback_image() -> pygame.Surface:
    """Load fallback image or create a default one"""
    try:
        if os.path.exists(FALLBACK_IMAGE):
            image = pygame.image.load(FALLBACK_IMAGE)
            return pygame.transform.scale(image, (WIDTH, HEIGHT))
    except pygame.error:
        pass

    # Create a simple gradient fallback
    surface = pygame.Surface((WIDTH, HEIGHT))
    for y in range(HEIGHT):
        color = int(20 + (y / HEIGHT) * 40)
        pygame.draw.line(surface, (color, color, color), (0, y), (WIDTH, y))
    return surface

def get_display_status() -> str:
    """Read current display status"""
    try:
        with open(STATUS_FILE, 'r') as f:
            return f.read().strip().upper()
    except FileNotFoundError:
        return 'RUNNING'

class TextRenderer:
    """Handles text rendering with caching"""

    def __init__(self):
        pygame.font.init()
        self.large_font = pygame.font.SysFont("dejavusansmono", 36, bold=True)
        self.small_font = pygame.font.SysFont("dejavusansmono", 24)
        self.cache = {}

        # Create reusable overlay
        self.overlay = pygame.Surface((WIDTH, 120))
        self.overlay.set_alpha(120)
        self.overlay.fill((0, 0, 0))

    def render_metadata(self, metadata: Dict[str, str]) -> pygame.Surface:
        """Render metadata text with caching"""
        title = metadata.get('title', 'N/A')
        artist = metadata.get('artist', 'N/A')

        cache_key = f"{title}|{artist}"
        if cache_key in self.cache:
            return self.cache[cache_key]

        # Create surface for text
        text_surface = pygame.Surface((WIDTH, 120), pygame.SRCALPHA)

        # Render title (truncate if too long)
        title_text = self._render_truncated(title, self.large_font, (255, 255, 255), WIDTH - 40)
        artist_text = self._render_truncated(artist, self.small_font, (180, 180, 180), WIDTH - 40)

        # Blit overlay and text
        text_surface.blit(self.overlay, (0, 0))
        text_surface.blit(title_text, (20, 20))
        text_surface.blit(artist_text, (20, 60))

        # Cache the result (limit cache size)
        if len(self.cache) > 10:
            self.cache.clear()
        self.cache[cache_key] = text_surface

        return text_surface

    def _render_truncated(self, text: str, font: pygame.font.Font, color: tuple, max_width: int) -> pygame.Surface:
        """Render text, truncating with ellipsis if too long"""
        rendered = font.render(text, True, color)
        if rendered.get_width() <= max_width:
            return rendered

        # Truncate with ellipsis
        while text and font.size(text + "...")[0] > max_width:
            text = text[:-1]
        return font.render(text + "..." if text else "...", True, color)

class TransitionManager:
    """Manages smooth transitions between images"""

    def __init__(self):
        self.is_transitioning = False
        self.transition_start_time = 0
        self.current_image = None
        self.next_image = None

    def start_transition(self, current: pygame.Surface, next_img: pygame.Surface):
        """Start a transition from current to next image"""
        # Create copies to avoid modifying originals
        self.current_image = current.copy()
        self.next_image = next_img.copy()
        self.is_transitioning = True
        self.transition_start_time = pygame.time.get_ticks()

    def get_transition_surface(self) -> tuple[pygame.Surface, bool]:
        """Get the current transition surface and completion status"""
        if not self.is_transitioning:
            return None, False

        time_elapsed = (pygame.time.get_ticks() - self.transition_start_time) / 1000.0
        fade_ratio = min(time_elapsed / FADE_DURATION, 1.0)

        # Create transition surface
        transition_surface = pygame.Surface((WIDTH, HEIGHT))

        # Blend images
        old_alpha = int(255 * (1.0 - fade_ratio))
        new_alpha = int(255 * fade_ratio)

        self.current_image.set_alpha(old_alpha)
        self.next_image.set_alpha(new_alpha)

        transition_surface.blit(self.current_image, (0, 0))
        transition_surface.blit(self.next_image, (0, 0))

        # Check if transition is complete
        is_complete = fade_ratio >= 1.0
        if is_complete:
            self.is_transitioning = False
            # Reset alphas
            self.current_image.set_alpha(255)
            self.next_image.set_alpha(255)

        return transition_surface, is_complete

def run_display():
    """Main display loop"""
    pygame.init()

    # Setup display
    screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.FULLSCREEN)
    pygame.display.set_caption("Album Art Display")
    clock = pygame.time.Clock()

    # Hide cursor for kiosk mode
    pygame.mouse.set_visible(False)

    # Initialize components
    image_loader = ImageLoader()
    text_renderer = TextRenderer()
    transition_manager = TransitionManager()

    # Load initial state
    current_image = load_fallback_image()
    current_metadata = {"title": "Ready", "artist": "Waiting for remote command...", "album": ""}

    # Start background image loading
    image_loader.start()

    print("Display app started.")

    running = True
    while running:
        # Handle events
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key == pygame.K_F11:  # Toggle fullscreen
                    pygame.display.toggle_fullscreen()

        # Check for new content
        new_content = image_loader.get_new_content()
        if new_content and not transition_manager.is_transitioning:
            transition_manager.start_transition(current_image, new_content['image'])
            current_metadata = new_content['metadata']

        # Get display status
        status = get_display_status()

        # Clear screen
        screen.fill((0, 0, 0))

        if status == 'RUNNING':
            # Handle transitions
            if transition_manager.is_transitioning:
                transition_surface, is_complete = transition_manager.get_transition_surface()
                if transition_surface:
                    screen.blit(transition_surface, (0, 0))
                if is_complete:
                    current_image = transition_manager.next_image.copy()
            else:
                screen.blit(current_image, (0, 0))

            # Render metadata overlay
            metadata_surface = text_renderer.render_metadata(current_metadata)
            screen.blit(metadata_surface, (0, HEIGHT - 120))

        elif status == 'PAUSED':
            screen.fill((0, 0, 0))
            pause_text = text_renderer.large_font.render("PAUSED", True, (255, 255, 255))
            text_rect = pause_text.get_rect(center=(WIDTH // 2, HEIGHT // 2))
            screen.blit(pause_text, text_rect)

        # Update display
        pygame.display.flip()
        clock.tick(FPS)

    # Cleanup
    image_loader.stop()
    pygame.quit()

if __name__ == "__main__":
    try:
        run_display()
    except KeyboardInterrupt:
        print("\nDisplay app stopped.")
    except Exception as e:
        print(f"Error: {e}")