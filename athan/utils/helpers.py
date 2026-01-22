"""
Utility Helper Functions

Common utilities used throughout the application.
"""

import os
import logging
from datetime import datetime, timedelta
from typing import Optional, Tuple

import pytz

logger = logging.getLogger(__name__)


def format_time(
    dt: datetime,
    use_24_hour: bool = True,
    show_seconds: bool = False
) -> str:
    """
    Format a datetime object for display.
    
    Args:
        dt: Datetime to format
        use_24_hour: Use 24-hour format
        show_seconds: Include seconds
    
    Returns:
        Formatted time string
    """
    if use_24_hour:
        if show_seconds:
            return dt.strftime('%H:%M:%S')
        return dt.strftime('%H:%M')
    else:
        if show_seconds:
            return dt.strftime('%I:%M:%S %p')
        return dt.strftime('%I:%M %p')


def format_countdown(delta: timedelta) -> str:
    """
    Format a timedelta as countdown string.
    
    Args:
        delta: Time difference
    
    Returns:
        Formatted countdown string (HH:MM:SS or MM:SS)
    """
    total_seconds = int(delta.total_seconds())
    
    if total_seconds <= 0:
        return "00:00"
    
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    else:
        return f"{minutes:02d}:{seconds:02d}"


def get_timezone_from_coordinates(
    latitude: float,
    longitude: float
) -> Optional[str]:
    """
    Get timezone string from coordinates.
    
    Uses a simple approximation based on longitude.
    For more accurate results, consider using a timezone database.
    
    Args:
        latitude: Latitude
        longitude: Longitude
    
    Returns:
        Timezone string or None
    """
    try:
        # Try to use timezonefinder if available
        from timezonefinder import TimezoneFinder
        tf = TimezoneFinder()
        return tf.timezone_at(lng=longitude, lat=latitude)
    except ImportError:
        pass
    
    # Fallback: rough estimate based on longitude
    # This is not accurate but provides a reasonable default
    offset_hours = round(longitude / 15)
    
    # Map to common timezones
    if -5 <= offset_hours <= -4:
        return "America/New_York"
    elif -6 <= offset_hours <= -5:
        return "America/Chicago"
    elif -7 <= offset_hours <= -6:
        return "America/Denver"
    elif -8 <= offset_hours <= -7:
        return "America/Los_Angeles"
    elif 0 <= offset_hours <= 1:
        return "Europe/London"
    elif 1 <= offset_hours <= 2:
        return "Europe/Paris"
    elif 2 <= offset_hours <= 3:
        return "Asia/Riyadh"
    elif 5 <= offset_hours <= 6:
        return "Asia/Karachi"
    elif 8 <= offset_hours <= 9:
        return "Asia/Singapore"
    
    return "UTC"


def validate_coordinates(latitude: float, longitude: float) -> Tuple[bool, str]:
    """
    Validate geographic coordinates.
    
    Args:
        latitude: Latitude value
        longitude: Longitude value
    
    Returns:
        Tuple of (is_valid, error_message)
    """
    if not isinstance(latitude, (int, float)):
        return False, "Latitude must be a number"
    
    if not isinstance(longitude, (int, float)):
        return False, "Longitude must be a number"
    
    if latitude < -90 or latitude > 90:
        return False, "Latitude must be between -90 and 90"
    
    if longitude < -180 or longitude > 180:
        return False, "Longitude must be between -180 and 180"
    
    return True, ""


def validate_timezone(timezone_str: str) -> Tuple[bool, str]:
    """
    Validate a timezone string.
    
    Args:
        timezone_str: Timezone string to validate
    
    Returns:
        Tuple of (is_valid, error_message)
    """
    if not timezone_str:
        return False, "Timezone cannot be empty"
    
    try:
        pytz.timezone(timezone_str)
        return True, ""
    except pytz.exceptions.UnknownTimeZoneError:
        return False, f"Unknown timezone: {timezone_str}"


def ensure_dir(path: str) -> bool:
    """
    Ensure a directory exists.
    
    Args:
        path: Directory path
    
    Returns:
        True if directory exists or was created
    """
    try:
        os.makedirs(path, exist_ok=True)
        return True
    except OSError as e:
        logger.error(f"Failed to create directory {path}: {e}")
        return False


def get_data_dir() -> str:
    """Get the application data directory."""
    return os.path.expanduser("~/.local/share/athan-app")


def get_config_dir() -> str:
    """Get the application config directory."""
    return os.path.expanduser("~/.config/athan-app")


def get_cache_dir() -> str:
    """Get the application cache directory."""
    return os.path.expanduser("~/.cache/athan-app")


def singleton_check(lock_file: Optional[str] = None) -> bool:
    """
    Check if another instance is running.
    
    Args:
        lock_file: Path to lock file
    
    Returns:
        True if this is the only instance
    """
    import fcntl
    
    if lock_file is None:
        lock_file = os.path.join(get_cache_dir(), 'athan-ui.lock')
    
    ensure_dir(os.path.dirname(lock_file))
    
    try:
        lock_fd = open(lock_file, 'w')
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        # Keep the file handle open to maintain the lock
        return True
    except (IOError, OSError):
        return False


def setup_logging(
    name: str = 'athan',
    level: int = logging.INFO,
    log_file: Optional[str] = None
) -> logging.Logger:
    """
    Set up logging for the application.
    
    Args:
        name: Logger name
        level: Logging level
        log_file: Optional log file path
    
    Returns:
        Configured logger
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_format = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    console_handler.setFormatter(console_format)
    logger.addHandler(console_handler)
    
    # File handler
    if log_file:
        ensure_dir(os.path.dirname(log_file))
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(level)
        file_handler.setFormatter(console_format)
        logger.addHandler(file_handler)
    
    return logger
