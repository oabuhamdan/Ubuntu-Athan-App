"""
Configuration Management Module

Handles persistent storage and retrieval of:
- Location settings
- Calculation parameters
- Audio settings
- UI preferences
- Auto-relaunch settings

Configuration is stored as JSON in ~/.config/athan-app/config.json
"""

import json
import os
import logging
import threading
from dataclasses import dataclass, field, asdict
from typing import Optional, Dict, Any, Callable, List
from pathlib import Path

from ..calculation.prayer_times import CalculationSettings

logger = logging.getLogger(__name__)

# Default configuration directory
CONFIG_DIR = os.path.expanduser("~/.config/athan-app")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")
DATA_DIR = os.path.expanduser("~/.local/share/athan-app")
SOUNDS_DIR = os.path.join(DATA_DIR, "sounds")
LOGS_DIR = os.path.join(DATA_DIR, "logs")


@dataclass
class LocationSettings:
    """Location configuration."""
    latitude: float = 0.0
    longitude: float = 0.0
    timezone: str = "UTC"
    city_name: str = ""
    country: str = ""
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> 'LocationSettings':
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class AudioSettings:
    """Audio configuration."""
    device_name: Optional[str] = None  # None = system default
    athan_file: str = ""  # Path to custom Athan file
    volume: float = 1.0  # 0.0 to 1.0
    
    # Per-prayer Athan enabled settings
    fajr_enabled: bool = True
    dhuhr_enabled: bool = True
    asr_enabled: bool = True
    maghrib_enabled: bool = True
    isha_enabled: bool = True
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> 'AudioSettings':
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class AutoRelaunchSettings:
    """Auto-relaunch configuration."""
    enabled: bool = True
    delay_minutes: int = 5  # Relaunch after X minutes
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> 'AutoRelaunchSettings':
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class UISettings:
    """UI preferences."""
    show_seconds: bool = False
    use_24_hour: bool = True
    show_arabic_names: bool = True
    minimize_to_tray: bool = True
    start_minimized: bool = False
    dark_mode: bool = True
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> 'UISettings':
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class AppSettings:
    """
    Main application settings manager.
    
    Features:
    - Thread-safe configuration access
    - Automatic saving on changes
    - Change notification callbacks
    - Default value handling
    - Migration support for config versions
    """
    
    CONFIG_VERSION = 1
    
    def __init__(self, config_file: Optional[str] = None):
        """
        Initialize settings manager.
        
        Args:
            config_file: Path to config file (uses default if None)
        """
        self._config_file = config_file or CONFIG_FILE
        self._lock = threading.RLock()
        self._callbacks: List[Callable[[], None]] = []
        
        # Settings objects
        self._location = LocationSettings()
        self._calculation = CalculationSettings()
        self._audio = AudioSettings()
        self._auto_relaunch = AutoRelaunchSettings()
        self._ui = UISettings()
        
        # Skip next athan flag (runtime only, not persisted)
        self._skip_next_athan = False
        
        # Ensure directories exist
        self._ensure_directories()
        
        # Load existing settings
        self.load()
        
        logger.info(f"Settings loaded from {self._config_file}")
    
    def _ensure_directories(self) -> None:
        """Create necessary directories."""
        for directory in [CONFIG_DIR, DATA_DIR, SOUNDS_DIR, LOGS_DIR]:
            os.makedirs(directory, exist_ok=True)
    
    @property
    def location(self) -> LocationSettings:
        """Get location settings."""
        with self._lock:
            return self._location
    
    @location.setter
    def location(self, value: LocationSettings) -> None:
        """Set location settings."""
        with self._lock:
            self._location = value
            self._on_change()
    
    @property
    def calculation(self) -> CalculationSettings:
        """Get calculation settings."""
        with self._lock:
            return self._calculation
    
    @calculation.setter
    def calculation(self, value: CalculationSettings) -> None:
        """Set calculation settings."""
        with self._lock:
            self._calculation = value
            self._on_change()
    
    @property
    def audio(self) -> AudioSettings:
        """Get audio settings."""
        with self._lock:
            return self._audio
    
    @audio.setter
    def audio(self, value: AudioSettings) -> None:
        """Set audio settings."""
        with self._lock:
            self._audio = value
            self._on_change()
    
    @property
    def auto_relaunch(self) -> AutoRelaunchSettings:
        """Get auto-relaunch settings."""
        with self._lock:
            return self._auto_relaunch
    
    @auto_relaunch.setter
    def auto_relaunch(self, value: AutoRelaunchSettings) -> None:
        """Set auto-relaunch settings."""
        with self._lock:
            self._auto_relaunch = value
            self._on_change()
    
    @property
    def ui(self) -> UISettings:
        """Get UI settings."""
        with self._lock:
            return self._ui
    
    @ui.setter
    def ui(self, value: UISettings) -> None:
        """Set UI settings."""
        with self._lock:
            self._ui = value
            self._on_change()
    
    @property
    def skip_next_athan(self) -> bool:
        """Check if next Athan should be skipped."""
        with self._lock:
            return self._skip_next_athan
    
    @skip_next_athan.setter
    def skip_next_athan(self, value: bool) -> None:
        """Set skip next Athan flag."""
        with self._lock:
            self._skip_next_athan = value
    
    def add_change_callback(self, callback: Callable[[], None]) -> None:
        """Add callback for settings changes."""
        with self._lock:
            self._callbacks.append(callback)
    
    def remove_change_callback(self, callback: Callable[[], None]) -> None:
        """Remove change callback."""
        with self._lock:
            if callback in self._callbacks:
                self._callbacks.remove(callback)
    
    def _on_change(self) -> None:
        """Called when settings change."""
        self.save()
        for callback in self._callbacks:
            try:
                callback()
            except Exception as e:
                logger.error(f"Error in settings change callback: {e}")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert settings to dictionary."""
        return {
            'version': self.CONFIG_VERSION,
            'location': self._location.to_dict(),
            'calculation': self._calculation.to_dict(),
            'audio': self._audio.to_dict(),
            'auto_relaunch': self._auto_relaunch.to_dict(),
            'ui': self._ui.to_dict(),
        }
    
    def from_dict(self, data: Dict[str, Any]) -> None:
        """Load settings from dictionary."""
        # Check version for migrations
        version = data.get('version', 0)
        
        if 'location' in data:
            self._location = LocationSettings.from_dict(data['location'])
        
        if 'calculation' in data:
            self._calculation = CalculationSettings.from_dict(data['calculation'])
        
        if 'audio' in data:
            self._audio = AudioSettings.from_dict(data['audio'])
        
        if 'auto_relaunch' in data:
            self._auto_relaunch = AutoRelaunchSettings.from_dict(data['auto_relaunch'])
        
        if 'ui' in data:
            self._ui = UISettings.from_dict(data['ui'])
        
        # Handle migrations if needed
        if version < self.CONFIG_VERSION:
            self._migrate(version)
    
    def _migrate(self, from_version: int) -> None:
        """Migrate settings from older versions."""
        logger.info(f"Migrating settings from version {from_version} to {self.CONFIG_VERSION}")
        # Add migration logic here as needed
        self.save()
    
    def save(self) -> bool:
        """
        Save settings to file.
        
        Returns:
            True if saved successfully
        """
        with self._lock:
            try:
                # Write to temp file first for atomic update
                temp_file = self._config_file + '.tmp'
                with open(temp_file, 'w') as f:
                    json.dump(self.to_dict(), f, indent=2)
                
                # Atomic rename
                os.replace(temp_file, self._config_file)
                
                logger.debug("Settings saved")
                return True
                
            except Exception as e:
                logger.error(f"Error saving settings: {e}")
                return False
    
    def load(self) -> bool:
        """
        Load settings from file.
        
        Returns:
            True if loaded successfully
        """
        with self._lock:
            try:
                if os.path.exists(self._config_file):
                    with open(self._config_file, 'r') as f:
                        data = json.load(f)
                    self.from_dict(data)
                    return True
                else:
                    # Create with defaults
                    self.save()
                    return True
                    
            except json.JSONDecodeError as e:
                logger.error(f"Invalid config file: {e}")
                # Backup corrupted file and start fresh
                backup_file = self._config_file + '.backup'
                if os.path.exists(self._config_file):
                    os.rename(self._config_file, backup_file)
                self.save()
                return False
                
            except Exception as e:
                logger.error(f"Error loading settings: {e}")
                return False
    
    def reset_to_defaults(self) -> None:
        """Reset all settings to defaults."""
        with self._lock:
            self._location = LocationSettings()
            self._calculation = CalculationSettings()
            self._audio = AudioSettings()
            self._auto_relaunch = AutoRelaunchSettings()
            self._ui = UISettings()
            self._on_change()
    
    def is_location_set(self) -> bool:
        """Check if location has been configured."""
        return self._location.latitude != 0.0 or self._location.longitude != 0.0
    
    def is_athan_enabled_for_prayer(self, prayer_name: str) -> bool:
        """Check if Athan is enabled for a specific prayer."""
        prayer_map = {
            'fajr': self._audio.fajr_enabled,
            'dhuhr': self._audio.dhuhr_enabled,
            'asr': self._audio.asr_enabled,
            'maghrib': self._audio.maghrib_enabled,
            'isha': self._audio.isha_enabled,
        }
        return prayer_map.get(prayer_name.lower(), True)
    
    def set_athan_enabled_for_prayer(self, prayer_name: str, enabled: bool) -> None:
        """Enable/disable Athan for a specific prayer."""
        prayer_map = {
            'fajr': 'fajr_enabled',
            'dhuhr': 'dhuhr_enabled',
            'asr': 'asr_enabled',
            'maghrib': 'maghrib_enabled',
            'isha': 'isha_enabled',
        }
        attr = prayer_map.get(prayer_name.lower())
        if attr:
            setattr(self._audio, attr, enabled)
            self._on_change()


def get_settings() -> AppSettings:
    """
    Get or create the global settings instance.
    
    This is a singleton pattern for easy access throughout the app.
    """
    global _settings_instance
    if '_settings_instance' not in globals() or _settings_instance is None:
        _settings_instance = AppSettings()
    return _settings_instance


def reset_settings_instance() -> None:
    """Reset the global settings instance (for testing)."""
    global _settings_instance
    _settings_instance = None


# Module-level singleton
_settings_instance: Optional[AppSettings] = None
