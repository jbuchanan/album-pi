#!/usr/bin/env python3
import pygame
import os
import json
import time
import threading
import queue
from typing import Optional, Dict, Any, Tuple
from datetime import datetime
from PIL import Image as PILImage
import qrcode
import requests

from config_manager import get_config
from utils import extract_dominant_colors, apply_gaussian_blur, format_time_12h, format_time_24h, clamp

# File paths
IMAGE_PATH = 'current_album_art.jpg'
METADATA_PATH = 'current_metadata.json'
STATUS_FILE = 'display_status.txt'
FALLBACK_IMAGE = 'default_art.jpg'

class ImageLoader:
    """Handles image loading and change detection in a separate thread"""

    def __init__(self, config):
        self.config = config
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
        check_interval = self.config.get('performance.file_check_interval', 0.1)

        while self.running:
            try:
                if os.path.exists(IMAGE_PATH):
                    current_mtime = os.path.getmtime(IMAGE_PATH)
                    if current_mtime > self.last_image_mtime:
                        self.last_image_mtime = current_mtime

                        try:
                            # Load PIL image for color extraction
                            pil_image = PILImage.open(IMAGE_PATH)

                            # Extract dominant colors for ambient lighting
                            dominant_colors = extract_dominant_colors(pil_image, num_colors=3)

                            # Load as pygame surface
                            image = self._load_and_scale_image(IMAGE_PATH)
                            metadata = self._load_metadata()

                            self.queue.put({
                                'image': image,
                                'pil_image': pil_image,
                                'metadata': metadata,
                                'dominant_colors': dominant_colors
                            })
                        except Exception as e:
                            print(f"Error loading new content: {e}")

                time.sleep(check_interval)
            except Exception as e:
                print(f"File monitor error: {e}")
                time.sleep(check_interval)

    def _load_and_scale_image(self, path: str) -> pygame.Surface:
        """Load and scale image to fit screen with high quality"""
        image = pygame.image.load(path)
        width = self.config.get('display.width', 720)
        height = self.config.get('display.height', 720)

        # Use smoothscale for high-quality scaling (much better than scale())
        # This uses a box filter for downscaling which produces crisp results
        return pygame.transform.smoothscale(image, (width, height))

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

def load_fallback_image(config) -> pygame.Surface:
    """Load fallback image or create a default one"""
    width = config.get('display.width', 720)
    height = config.get('display.height', 720)

    try:
        if os.path.exists(FALLBACK_IMAGE):
            image = pygame.image.load(FALLBACK_IMAGE)
            return pygame.transform.smoothscale(image, (width, height))
    except pygame.error:
        pass

    # Create a simple gradient fallback
    surface = pygame.Surface((width, height))
    for y in range(height):
        color = int(20 + (y / height) * 40)
        pygame.draw.line(surface, (color, color, color), (0, y), (width, y))
    return surface

def get_display_status() -> str:
    """Read current display status"""
    try:
        with open(STATUS_FILE, 'r') as f:
            return f.read().strip().upper()
    except FileNotFoundError:
        return 'RUNNING'

class OverlayRenderer:
    """Handles rendering of various overlays"""

    def __init__(self, config, width, height):
        self.config = config
        self.width = width
        self.height = height
        pygame.font.init()

        # Initialize fonts
        self.fonts = {}
        self._init_fonts()

        # Weather cache
        self.weather_data = None
        self.weather_last_update = 0

        # QR code cache
        self.qr_cache = {}

    def _init_fonts(self):
        """Initialize fonts based on configuration"""
        try:
            # Try to load a nice font
            font_name = "dejavusansmono"
            self.fonts['title'] = pygame.font.SysFont(font_name,
                self.config.get('overlays.metadata.font_size_title', 36), bold=True)
            self.fonts['artist'] = pygame.font.SysFont(font_name,
                self.config.get('overlays.metadata.font_size_artist', 24))
            self.fonts['clock'] = pygame.font.SysFont(font_name,
                self.config.get('overlays.clock.font_size', 32), bold=True)
            self.fonts['weather'] = pygame.font.SysFont(font_name,
                self.config.get('overlays.weather.font_size', 24))
        except:
            # Fallback to default font
            self.fonts['title'] = pygame.font.Font(None, 36)
            self.fonts['artist'] = pygame.font.Font(None, 24)
            self.fonts['clock'] = pygame.font.Font(None, 32)
            self.fonts['weather'] = pygame.font.Font(None, 24)

    def render_all_overlays(self, screen, metadata: Dict[str, str]):
        """Render all enabled overlays"""
        # Metadata overlay
        if self.config.get('overlays.metadata.enabled', True):
            self._render_metadata(screen, metadata)

        # Clock overlay
        if self.config.get('overlays.clock.enabled', False):
            self._render_clock(screen)

        # Weather overlay
        if self.config.get('overlays.weather.enabled', False):
            self._render_weather(screen)

        # QR code overlay
        if self.config.get('overlays.qr_code.enabled', False):
            self._render_qr_code(screen, metadata)

    def _render_metadata(self, screen, metadata: Dict[str, str]):
        """Render metadata overlay"""
        title = metadata.get('title', 'N/A')
        artist = metadata.get('artist', 'N/A')

        # Create semi-transparent overlay
        overlay = pygame.Surface((self.width, 120), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 120))

        # Render text
        title_text = self._truncate_render(title, self.fonts['title'], (255, 255, 255), self.width - 40)
        artist_text = self._truncate_render(artist, self.fonts['artist'], (180, 180, 180), self.width - 40)

        # Blit to overlay
        overlay.blit(title_text, (20, 20))
        overlay.blit(artist_text, (20, 60))

        # Position based on config
        position = self.config.get('overlays.metadata.position', 'bottom')
        y_pos = self.height - 120 if position == 'bottom' else 0

        screen.blit(overlay, (0, y_pos))

    def _render_clock(self, screen):
        """Render clock overlay"""
        now = datetime.now()
        format_type = self.config.get('overlays.clock.format', '12h')

        if format_type == '12h':
            time_str = format_time_12h(now.hour, now.minute)
        else:
            time_str = format_time_24h(now.hour, now.minute)

        text = self.fonts['clock'].render(time_str, True, (255, 255, 255))

        # Add semi-transparent background
        padding = 15
        bg = pygame.Surface((text.get_width() + padding * 2, text.get_height() + padding * 2), pygame.SRCALPHA)
        bg.fill((0, 0, 0, 120))

        # Position based on config
        position = self.config.get('overlays.clock.position', 'top-right')
        x, y = self._get_position(position, bg.get_width(), bg.get_height(), padding)

        screen.blit(bg, (x, y))
        screen.blit(text, (x + padding, y + padding))

    def _render_weather(self, screen):
        """Render weather overlay"""
        # Update weather data if needed
        update_interval = self.config.get('overlays.weather.update_interval', 1800)
        if time.time() - self.weather_last_update > update_interval:
            self._fetch_weather()

        if not self.weather_data:
            return

        # Format weather text
        temp = self.weather_data.get('temp', 'N/A')
        desc = self.weather_data.get('description', '')
        units = self.config.get('overlays.weather.units', 'imperial')
        unit_symbol = '°F' if units == 'imperial' else '°C'

        weather_str = f"{temp}{unit_symbol} {desc}"
        text = self.fonts['weather'].render(weather_str, True, (255, 255, 255))

        # Add background
        padding = 12
        bg = pygame.Surface((text.get_width() + padding * 2, text.get_height() + padding * 2), pygame.SRCALPHA)
        bg.fill((0, 0, 0, 120))

        # Position
        position = self.config.get('overlays.weather.position', 'top-left')
        x, y = self._get_position(position, bg.get_width(), bg.get_height(), padding)

        screen.blit(bg, (x, y))
        screen.blit(text, (x + padding, y + padding))

    def _render_qr_code(self, screen, metadata: Dict[str, str]):
        """Render QR code overlay"""
        # Get URL from metadata - prioritize Spotify over iTunes
        url = metadata.get('spotify_url') or metadata.get('itunes_url', '')
        if not url:
            return

        # Check cache
        if url in self.qr_cache:
            qr_surface = self.qr_cache[url]
        else:
            # Generate QR code with white background for better scanning
            qr = qrcode.QRCode(version=1, box_size=3, border=2)
            qr.add_data(url)
            qr.make(fit=True)

            qr_img = qr.make_image(fill_color="black", back_color="white")

            # Convert to pygame surface
            qr_size = self.config.get('overlays.qr_code.size', 150)
            qr_img = qr_img.resize((qr_size, qr_size), PILImage.Resampling.NEAREST)

            # Convert to RGB mode (QR codes are generated in '1' binary mode)
            qr_img = qr_img.convert('RGB')

            # Convert PIL to pygame
            mode = qr_img.mode
            size = qr_img.size
            data = qr_img.tobytes()

            qr_surface = pygame.image.fromstring(data, size, mode)

            # Cache it
            if len(self.qr_cache) > 10:
                self.qr_cache.clear()
            self.qr_cache[url] = qr_surface

        # Position
        position = self.config.get('overlays.qr_code.position', 'bottom-right')
        padding = 15
        x, y = self._get_position(position, qr_surface.get_width(), qr_surface.get_height(), padding)

        screen.blit(qr_surface, (x, y))

    def _fetch_weather(self):
        """Fetch weather data from OpenWeatherMap"""
        api_key = self.config.get('overlays.weather.api_key', '')
        location = self.config.get('overlays.weather.location', '')

        if not api_key or not location:
            return

        try:
            units = self.config.get('overlays.weather.units', 'imperial')
            url = f"http://api.openweathermap.org/data/2.5/weather?q={location}&appid={api_key}&units={units}"

            response = requests.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()

            self.weather_data = {
                'temp': int(data['main']['temp']),
                'description': data['weather'][0]['description'].title()
            }
            self.weather_last_update = time.time()

        except Exception as e:
            print(f"Error fetching weather: {e}")

    def _get_position(self, position: str, width: int, height: int, padding: int) -> Tuple[int, int]:
        """Calculate position based on position string"""
        positions = {
            'top-left': (padding, padding),
            'top-right': (self.width - width - padding, padding),
            'bottom-left': (padding, self.height - height - padding),
            'bottom-right': (self.width - width - padding, self.height - height - padding)
        }
        return positions.get(position, (padding, padding))

    def _truncate_render(self, text: str, font: pygame.font.Font, color: tuple, max_width: int) -> pygame.Surface:
        """Render text, truncating with ellipsis if too long"""
        rendered = font.render(text, True, color)
        if rendered.get_width() <= max_width:
            return rendered

        while text and font.size(text + "...")[0] > max_width:
            text = text[:-1]
        return font.render(text + "..." if text else "...", True, color)

class TransitionManager:
    """Manages smooth transitions between images with multiple effects"""

    def __init__(self, config, width, height):
        self.config = config
        self.width = width
        self.height = height
        self.is_transitioning = False
        self.transition_start_time = 0
        self.current_image = None
        self.next_image = None
        self.effect = config.get('transitions.effect', 'fade')
        self.duration = config.get('transitions.duration', 1.0)

    def start_transition(self, current: pygame.Surface, next_img: pygame.Surface):
        """Start a transition from current to next image"""
        self.current_image = current.copy()
        self.next_image = next_img.copy()
        self.is_transitioning = True
        self.transition_start_time = pygame.time.get_ticks()

        # Randomly select effect if configured
        if self.effect == 'random':
            import random
            self.current_effect = random.choice(['fade', 'slide', 'zoom'])
        else:
            self.current_effect = self.effect

    def get_transition_surface(self) -> Tuple[Optional[pygame.Surface], bool]:
        """Get the current transition surface and completion status"""
        if not self.is_transitioning:
            return None, False

        time_elapsed = (pygame.time.get_ticks() - self.transition_start_time) / 1000.0
        progress = min(time_elapsed / self.duration, 1.0)

        # Apply easing
        progress = self._ease_in_out(progress)

        # Generate transition based on effect type
        if self.current_effect == 'fade':
            transition_surface = self._fade_transition(progress)
        elif self.current_effect == 'slide':
            transition_surface = self._slide_transition(progress)
        elif self.current_effect == 'zoom':
            transition_surface = self._zoom_transition(progress)
        else:
            transition_surface = self._fade_transition(progress)

        # Check if complete
        is_complete = progress >= 1.0
        if is_complete:
            self.is_transitioning = False
            self.current_image.set_alpha(255)
            self.next_image.set_alpha(255)

        return transition_surface, is_complete

    def _fade_transition(self, progress: float) -> pygame.Surface:
        """Classic cross-fade transition"""
        surface = pygame.Surface((self.width, self.height))

        old_alpha = int(255 * (1.0 - progress))
        new_alpha = int(255 * progress)

        self.current_image.set_alpha(old_alpha)
        self.next_image.set_alpha(new_alpha)

        surface.blit(self.current_image, (0, 0))
        surface.blit(self.next_image, (0, 0))

        return surface

    def _slide_transition(self, progress: float) -> pygame.Surface:
        """Slide transition from right to left"""
        surface = pygame.Surface((self.width, self.height))

        # Current image slides out to the left
        x_current = -int(self.width * progress)
        # Next image slides in from the right
        x_next = self.width - int(self.width * progress)

        surface.blit(self.current_image, (x_current, 0))
        surface.blit(self.next_image, (x_next, 0))

        return surface

    def _zoom_transition(self, progress: float) -> pygame.Surface:
        """Zoom transition - old zooms out, new zooms in"""
        surface = pygame.Surface((self.width, self.height))

        # Old image zooms out and fades
        scale_old = 1.0 + (progress * 0.2)
        alpha_old = int(255 * (1.0 - progress))

        old_w = int(self.width * scale_old)
        old_h = int(self.height * scale_old)
        old_scaled = pygame.transform.smoothscale(self.current_image, (old_w, old_h))
        old_scaled.set_alpha(alpha_old)

        old_x = -(old_w - self.width) // 2
        old_y = -(old_h - self.height) // 2

        # New image zooms in from small
        scale_new = 0.8 + (progress * 0.2)
        alpha_new = int(255 * progress)

        new_w = int(self.width * scale_new)
        new_h = int(self.height * scale_new)
        new_scaled = pygame.transform.smoothscale(self.next_image, (new_w, new_h))
        new_scaled.set_alpha(alpha_new)

        new_x = (self.width - new_w) // 2
        new_y = (self.height - new_h) // 2

        surface.fill((0, 0, 0))
        surface.blit(old_scaled, (old_x, old_y))
        surface.blit(new_scaled, (new_x, new_y))

        return surface

    def _ease_in_out(self, t: float) -> float:
        """Smooth easing function"""
        return t * t * (3.0 - 2.0 * t)

class AmbientLightRenderer:
    """Renders ambient lighting effects based on album art colors"""

    def __init__(self, config, width, height):
        self.config = config
        self.width = width
        self.height = height
        self.enabled = config.get('effects.ambient_light.enabled', True)
        self.intensity = config.get('effects.ambient_light.intensity', 0.3)

    def render(self, screen, dominant_colors: list):
        """Render ambient glow effect"""
        if not self.enabled or not dominant_colors:
            return

        # Create glow surface
        glow = pygame.Surface((self.width, self.height), pygame.SRCALPHA)

        # Use the most dominant color
        color = dominant_colors[0] if dominant_colors else (100, 100, 100)

        # Create radial gradient effect
        border_size = int(self.width * 0.15)  # 15% of width

        for i in range(border_size):
            alpha = int(self.intensity * 255 * (1 - i / border_size))

            # Top and bottom
            pygame.draw.line(glow, (*color, alpha), (0, i), (self.width, i))
            pygame.draw.line(glow, (*color, alpha), (0, self.height - i - 1), (self.width, self.height - i - 1))

            # Left and right
            pygame.draw.line(glow, (*color, alpha), (i, 0), (i, self.height))
            pygame.draw.line(glow, (*color, alpha), (self.width - i - 1, 0), (self.width - i - 1, self.height))

        screen.blit(glow, (0, 0))

def detect_display_resolution() -> Tuple[int, int]:
    """Detect native display resolution"""
    try:
        pygame.init()
        info = pygame.display.Info()
        return (info.current_w, info.current_h)
    except:
        return (720, 720)  # Default fallback

def run_display():
    """Main display loop"""
    # Load configuration
    config = get_config()

    # Initialize pygame
    pygame.init()

    # Detect resolution if set to 0
    config_width = config.get('display.width', 0)
    config_height = config.get('display.height', 0)

    if config_width == 0 or config_height == 0:
        detected_w, detected_h = detect_display_resolution()
        # For square monitors, use the smaller dimension
        size = min(detected_w, detected_h)
        WIDTH = HEIGHT = size
        print(f"Auto-detected display size: {WIDTH}x{HEIGHT}")
    else:
        WIDTH = config_width
        HEIGHT = config_height

    # Update config with detected values
    config.set('display.width', WIDTH)
    config.set('display.height', HEIGHT)

    FPS = config.get('display.fps', 60)

    # Setup display
    fullscreen = config.get('display.fullscreen', True)
    if fullscreen:
        screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.FULLSCREEN)
    else:
        screen = pygame.display.set_mode((WIDTH, HEIGHT))

    pygame.display.set_caption("Album Art Display")
    clock = pygame.time.Clock()

    # Hide cursor for kiosk mode (only in fullscreen)
    if fullscreen:
        pygame.mouse.set_visible(False)

    # Initialize components
    image_loader = ImageLoader(config)
    overlay_renderer = OverlayRenderer(config, WIDTH, HEIGHT)
    transition_manager = TransitionManager(config, WIDTH, HEIGHT)
    ambient_light = AmbientLightRenderer(config, WIDTH, HEIGHT)

    # Load initial state
    current_image = load_fallback_image(config)
    current_metadata = {"title": "Ready", "artist": "Waiting for remote command...", "album": ""}
    dominant_colors = [(40, 40, 40)]

    # Start background image loading
    image_loader.start()

    print(f"Display app started ({WIDTH}x{HEIGHT})")

    running = True
    while running:
        # Handle events
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key == pygame.K_F11:
                    pygame.display.toggle_fullscreen()

        # Check for new content
        new_content = image_loader.get_new_content()
        if new_content and not transition_manager.is_transitioning:
            transition_manager.start_transition(current_image, new_content['image'])
            current_metadata = new_content['metadata']
            dominant_colors = new_content.get('dominant_colors', [(40, 40, 40)])

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

            # Apply ambient lighting
            ambient_light.render(screen, dominant_colors)

            # Render all overlays
            overlay_renderer.render_all_overlays(screen, current_metadata)

        elif status == 'PAUSED':
            screen.fill((0, 0, 0))
            font = pygame.font.SysFont("dejavusansmono", 48, bold=True)
            pause_text = font.render("PAUSED", True, (255, 255, 255))
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
        import traceback
        traceback.print_exc()
