#!/usr/bin/env python3
"""Utility functions for Album Art Display"""
import time
import requests
from typing import Callable, Any, Optional
from functools import wraps
import colorsys
from PIL import Image
import numpy as np

def retry_with_backoff(
    max_attempts: int = 4,
    initial_delay: float = 2.0,
    exponential: bool = True,
    exceptions: tuple = (requests.RequestException,)
):
    """Decorator for retrying functions with exponential backoff"""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            delay = initial_delay

            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    if attempt == max_attempts - 1:
                        # Last attempt, re-raise
                        raise

                    print(f"Attempt {attempt + 1}/{max_attempts} failed: {e}")
                    print(f"Retrying in {delay:.1f}s...")
                    time.sleep(delay)

                    if exponential:
                        delay *= 2

            return None  # Should never reach here

        return wrapper
    return decorator

def extract_dominant_colors(image: Image.Image, num_colors: int = 5) -> list:
    """Extract dominant colors from image using color quantization"""
    try:
        # Resize for faster processing
        img = image.copy()
        img.thumbnail((150, 150))

        # Convert to RGB if needed
        if img.mode != 'RGB':
            img = img.convert('RGB')

        # Get pixel data
        pixels = np.array(img)
        pixels = pixels.reshape(-1, 3)

        # Use simple clustering - find most common colors
        # (For production, consider using k-means clustering)
        from collections import Counter

        # Reduce color depth for clustering
        pixels = (pixels // 32) * 32

        # Count colors
        color_counts = Counter(map(tuple, pixels))

        # Get most common colors
        dominant = [color for color, count in color_counts.most_common(num_colors)]

        return dominant

    except Exception as e:
        print(f"Error extracting colors: {e}")
        return [(0, 0, 0)]

def get_complementary_color(rgb: tuple) -> tuple:
    """Get complementary color"""
    r, g, b = [x / 255.0 for x in rgb]
    h, s, v = colorsys.rgb_to_hsv(r, g, b)

    # Rotate hue by 180 degrees
    h = (h + 0.5) % 1.0

    r, g, b = colorsys.hsv_to_rgb(h, s, v)
    return tuple(int(x * 255) for x in (r, g, b))

def brighten_color(rgb: tuple, factor: float = 1.5) -> tuple:
    """Brighten a color by a factor"""
    return tuple(min(255, int(c * factor)) for c in rgb)

def apply_gaussian_blur(surface, radius: int = 20):
    """Apply gaussian blur to a pygame surface"""
    try:
        import pygame
        from PIL import Image
        import numpy as np
        from scipy.ndimage import gaussian_filter

        # Convert pygame surface to PIL Image
        w, h = surface.get_size()
        buffer = pygame.image.tostring(surface, 'RGB')
        img = Image.frombytes('RGB', (w, h), buffer)

        # Apply blur
        img_array = np.array(img)
        blurred = gaussian_filter(img_array, sigma=radius, axes=(0, 1))

        # Convert back to pygame surface
        img_blurred = Image.fromarray(blurred.astype('uint8'))
        buffer = img_blurred.tobytes()

        blurred_surface = pygame.image.fromstring(buffer, (w, h), 'RGB')
        return blurred_surface

    except ImportError:
        # Fallback if scipy not available - use PIL blur
        import pygame
        from PIL import Image, ImageFilter

        w, h = surface.get_size()
        buffer = pygame.image.tostring(surface, 'RGB')
        img = Image.frombytes('RGB', (w, h), buffer)

        # Apply blur
        img_blurred = img.filter(ImageFilter.GaussianBlur(radius=radius))

        # Convert back
        buffer = img_blurred.tobytes()
        blurred_surface = pygame.image.fromstring(buffer, (w, h), 'RGB')
        return blurred_surface

def format_time_12h(hour: int, minute: int) -> str:
    """Format time in 12-hour format"""
    period = "AM" if hour < 12 else "PM"
    display_hour = hour % 12
    if display_hour == 0:
        display_hour = 12
    return f"{display_hour}:{minute:02d} {period}"

def format_time_24h(hour: int, minute: int) -> str:
    """Format time in 24-hour format"""
    return f"{hour:02d}:{minute:02d}"

def safe_request_get(url: str, timeout: int = 15, **kwargs) -> Optional[requests.Response]:
    """Safe HTTP GET request with error handling"""
    try:
        response = requests.get(url, timeout=timeout, **kwargs)
        response.raise_for_status()
        return response
    except requests.RequestException as e:
        print(f"Request failed: {e}")
        return None

def truncate_text(text: str, max_length: int = 50) -> str:
    """Truncate text with ellipsis"""
    if len(text) <= max_length:
        return text
    return text[:max_length - 3] + "..."

def clamp(value: float, min_value: float, max_value: float) -> float:
    """Clamp value between min and max"""
    return max(min_value, min(max_value, value))

if __name__ == "__main__":
    # Test retry decorator
    @retry_with_backoff(max_attempts=3, initial_delay=1.0)
    def test_function():
        print("Testing retry...")
        raise requests.RequestException("Test error")

    try:
        test_function()
    except Exception as e:
        print(f"Final error: {e}")
