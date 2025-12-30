#!/usr/bin/env python3
"""Configuration management for Album Art Display"""
import yaml
import os
import platform
from typing import Dict, Any
from pathlib import Path

class ConfigManager:
    """Manages application configuration"""

    DEFAULT_CONFIG_PATH = "config.yaml"

    def __init__(self, config_path: str = None):
        self.config_path = config_path or self.DEFAULT_CONFIG_PATH
        self.config = self._load_config()
        self._detect_platform()

    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from YAML file"""
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r') as f:
                    config = yaml.safe_load(f)
                    print(f"Loaded configuration from {self.config_path}")
                    return config or {}
            else:
                print(f"Config file not found: {self.config_path}, using defaults")
                return self._get_default_config()
        except Exception as e:
            print(f"Error loading config: {e}, using defaults")
            return self._get_default_config()

    def _get_default_config(self) -> Dict[str, Any]:
        """Return default configuration"""
        return {
            'display': {
                'width': 0,
                'height': 0,
                'fullscreen': True,
                'fps': 60
            },
            'image': {
                'target_size': 0,
                'jpeg_quality': 95,
                'cache_dir': 'image_cache',
                'max_cache_size_mb': 500
            },
            'transitions': {
                'effect': 'fade',
                'duration': 1.0
            },
            'effects': {
                'ambient_light': {
                    'enabled': True,
                    'intensity': 0.3
                },
                'blur_background': {
                    'enabled': False,
                    'blur_radius': 20
                }
            },
            'overlays': {
                'metadata': {
                    'enabled': True,
                    'position': 'bottom',
                    'font_size_title': 36,
                    'font_size_artist': 24
                },
                'clock': {
                    'enabled': False,
                    'position': 'top-right',
                    'format': '12h',
                    'font_size': 32
                },
                'weather': {
                    'enabled': False,
                    'position': 'top-left',
                    'api_key': '',
                    'location': '',
                    'units': 'imperial',
                    'update_interval': 1800,
                    'font_size': 24
                },
                'qr_code': {
                    'enabled': False,
                    'position': 'bottom-right',
                    'size': 150
                }
            },
            'music': {
                'spotify': {
                    'enabled': False,
                    'client_id': '',
                    'client_secret': '',
                    'auto_update': False
                },
                'itunes': {
                    'enabled': True
                }
            },
            'server': {
                'host': '0.0.0.0',
                'port': 5000,
                'cache_duration': 3600
            },
            'performance': {
                'file_check_interval': 0.1,
                'retry': {
                    'max_attempts': 4,
                    'initial_delay': 2.0,
                    'exponential_backoff': True
                },
                'preload_enabled': True
            },
            'platform': {
                'auto_detect': True,
                'override': ''
            }
        }

    def _detect_platform(self):
        """Detect platform and adjust settings accordingly"""
        if not self.get('platform.auto_detect', True):
            return

        system = platform.system()
        machine = platform.machine()

        # Check for override
        override = self.get('platform.override', '')
        if override:
            platform_type = override
        elif system == 'Darwin':
            platform_type = 'macos'
            # Mac-specific adjustments
            self.set('display.fullscreen', False)
        elif 'arm' in machine.lower() or 'aarch64' in machine.lower():
            platform_type = 'raspberry_pi'
            # Pi-specific adjustments
            self.set('display.fullscreen', True)
        else:
            platform_type = 'linux'

        print(f"Detected platform: {platform_type}")
        self.platform_type = platform_type

    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value using dot notation (e.g., 'display.width')"""
        keys = key.split('.')
        value = self.config

        try:
            for k in keys:
                value = value[k]
            return value if value is not None else default
        except (KeyError, TypeError):
            return default

    def set(self, key: str, value: Any):
        """Set configuration value using dot notation"""
        keys = key.split('.')
        config = self.config

        for k in keys[:-1]:
            if k not in config:
                config[k] = {}
            config = config[k]

        config[keys[-1]] = value

    def save(self, path: str = None):
        """Save configuration to file"""
        save_path = path or self.config_path
        try:
            with open(save_path, 'w') as f:
                yaml.dump(self.config, f, default_flow_style=False, sort_keys=False)
            print(f"Configuration saved to {save_path}")
            return True
        except Exception as e:
            print(f"Error saving config: {e}")
            return False

    def update_from_dict(self, updates: Dict[str, Any]):
        """Update configuration from dictionary"""
        def deep_update(base: dict, updates: dict):
            for key, value in updates.items():
                if isinstance(value, dict) and key in base and isinstance(base[key], dict):
                    deep_update(base[key], value)
                else:
                    base[key] = value

        deep_update(self.config, updates)

    def get_display_size(self) -> tuple:
        """Get display size (width, height)"""
        width = self.get('display.width', 0)
        height = self.get('display.height', 0)

        # If 0, will be auto-detected by display app
        return (width, height)

    def get_image_size(self) -> int:
        """Get target image size"""
        size = self.get('image.target_size', 0)
        return size if size > 0 else 720  # Default fallback

# Global config instance
_config_instance = None

def get_config() -> ConfigManager:
    """Get global config instance"""
    global _config_instance
    if _config_instance is None:
        _config_instance = ConfigManager()
    return _config_instance

def reload_config():
    """Reload configuration from file"""
    global _config_instance
    _config_instance = ConfigManager()
    return _config_instance

if __name__ == "__main__":
    # Test configuration
    config = ConfigManager()
    print(f"Display size: {config.get_display_size()}")
    print(f"Image size: {config.get_image_size()}")
    print(f"Fullscreen: {config.get('display.fullscreen')}")
    print(f"Transition effect: {config.get('transitions.effect')}")
    print(f"Platform: {config.platform_type}")
