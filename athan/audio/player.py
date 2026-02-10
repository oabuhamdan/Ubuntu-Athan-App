"""
Audio Player Module

Handles Athan audio playback with:
- GStreamer backend for reliable audio playback
- PulseAudio device selection
- Support for MP3, WAV, OGG formats
- Playback control (play, stop, pause)
"""

import os
import subprocess
import threading
import logging
from dataclasses import dataclass
from typing import List, Optional, Callable
from enum import Enum

import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst, GLib

# Initialize GStreamer
Gst.init(None)

logger = logging.getLogger(__name__)

# Constants
CLIENT_NAME = "Athan App"


class PlaybackState(Enum):
    """Audio playback states."""
    STOPPED = "stopped"
    PLAYING = "playing"
    PAUSED = "paused"


@dataclass
class AudioDevice:
    """Represents an audio output device."""
    name: str  # Internal device name/ID
    description: str  # Human-readable description
    is_default: bool = False
    
    def __str__(self) -> str:
        return self.description


class AudioPlayer:
    """
    GStreamer-based audio player with PulseAudio device selection.
    
    Features:
    - Plays audio files (MP3, WAV, OGG)
    - Routes output to specific audio device
    - Provides playback control
    - Thread-safe operation
    """
    
    def __init__(self, on_state_change: Optional[Callable[[PlaybackState], None]] = None):
        """
        Initialize the audio player.
        
        Args:
            on_state_change: Callback for playback state changes
        """
        self._pipeline: Optional[Gst.Pipeline] = None
        self._state = PlaybackState.STOPPED
        self._lock = threading.Lock()
        self._on_state_change = on_state_change
        self._current_device: Optional[str] = None
        self._current_file: Optional[str] = None
        self._bus_watch_id: Optional[int] = None
        
        # Create GLib main loop for async operations
        self._main_loop = GLib.MainLoop.new(None, False)
        
        logger.info("AudioPlayer initialized")
    
    @staticmethod
    def get_audio_devices() -> List[AudioDevice]:
        """
        Get list of available audio output devices.
        
        Uses pactl to query PulseAudio sinks.
        
        Returns:
            List of AudioDevice objects
        """
        devices = []
        
        try:
            # Get list of sinks from PulseAudio
            result = subprocess.run(
                ['pactl', 'list', 'sinks', 'short'],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0:
                for line in result.stdout.strip().split('\n'):
                    if line:
                        parts = line.split('\t')
                        if len(parts) >= 2:
                            sink_name = parts[1]
                            # Get more details
                            devices.append(AudioDevice(
                                name=sink_name,
                                description=sink_name.replace('_', ' ').title()
                            ))
            
            # Get default sink
            result = subprocess.run(
                ['pactl', 'get-default-sink'],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0:
                default_sink = result.stdout.strip()
                for device in devices:
                    if device.name == default_sink:
                        device.is_default = True
                        break
            
            # Get more detailed descriptions
            result = subprocess.run(
                ['pactl', 'list', 'sinks'],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0:
                current_name = None
                for line in result.stdout.split('\n'):
                    line = line.strip()
                    if line.startswith('Name:'):
                        current_name = line.split(':', 1)[1].strip()
                    elif line.startswith('Description:') and current_name:
                        description = line.split(':', 1)[1].strip()
                        for device in devices:
                            if device.name == current_name:
                                device.description = description
                                break
                        current_name = None
        
        except subprocess.TimeoutExpired:
            logger.error("Timeout getting audio devices")
        except FileNotFoundError:
            logger.error("pactl not found - PulseAudio may not be installed")
        except Exception as e:
            logger.error(f"Error getting audio devices: {e}")
        
        # Add system default if no devices found
        if not devices:
            devices.append(AudioDevice(
                name="@DEFAULT_SINK@",
                description="System Default",
                is_default=True
            ))
        
        return devices
    
    def _create_pipeline(self, file_path: str, device: Optional[str] = None) -> bool:
        """
        Create GStreamer pipeline for playback.
        
        Args:
            file_path: Path to audio file
            device: PulseAudio sink name (None for default)
        
        Returns:
            True if pipeline created successfully
        """
        try:
            # Validate file first (fast check, no lock needed)
            if not os.path.isfile(file_path):
                logger.error(f"Audio file not found: {file_path}")
                return False
            
            # Build pipeline string with improved error handling
            # Use pulsesink for device selection with client-name for better identification
            if device:
                # Escape device name for shell safety
                device_escaped = device.replace('"', '\\"')
                sink = f'pulsesink device="{device_escaped}" client-name="{CLIENT_NAME}"'
            else:
                sink = f'pulsesink client-name="{CLIENT_NAME}"'
            
            # Create pipeline based on file type
            # Using decodebin for automatic format detection
            # Escape file path for shell safety
            file_path_escaped = file_path.replace('"', '\\"')
            
            # Add volume control element for potential future use
            # The volume element is included in the pipeline for extensibility
            # (e.g., future per-prayer volume control or fade effects)
            # It currently uses default volume (1.0) but can be accessed via set_volume()
            pipeline_str = f'filesrc location="{file_path_escaped}" ! decodebin ! audioconvert ! audioresample ! volume name=volume ! {sink}'
            
            logger.debug(f"Creating pipeline: {pipeline_str}")
            
            # Parse pipeline (this might take time, but GStreamer handles it)
            pipeline = Gst.parse_launch(pipeline_str)
            
            if not pipeline:
                logger.error(f"Failed to create GStreamer pipeline: {pipeline_str}")
                return False
            
            # Verify we can get the sink element
            iterator = pipeline.iterate_sinks()
            has_sink = False
            while True:
                ret, element = iterator.next()
                if ret == Gst.IteratorResult.OK:
                    has_sink = True
                    break
                elif ret == Gst.IteratorResult.DONE:
                    break
                elif ret == Gst.IteratorResult.ERROR:
                    logger.warning("Error iterating pipeline sinks")
                    break
            
            if not has_sink:
                logger.warning("Pipeline has no sink elements")
            
            logger.debug(f"Pipeline created successfully")
            
            # Set up bus to watch for messages
            bus = pipeline.get_bus()
            if bus:
                bus.add_signal_watch()
                bus.connect("message", self._on_bus_message)
                logger.debug("Bus watch added")
            else:
                logger.warning("Failed to get pipeline bus")
            
            # Now update state with lock
            with self._lock:
                # Clean up old pipeline if exists
                if self._pipeline:
                    try:
                        self._pipeline.set_state(Gst.State.NULL)
                    except Exception:
                        pass
                
                self._pipeline = pipeline
                self._current_device = device
                self._current_file = file_path
                logger.debug(f"Pipeline stored, device: {device}, file: {file_path}")
            
            return True
            
        except Exception as e:
            logger.error(f"Error creating pipeline: {e}", exc_info=True)
            with self._lock:
                self._pipeline = None
            return False
    
    def _on_bus_message(self, bus: Gst.Bus, message: Gst.Message) -> bool:
        """Handle GStreamer bus messages."""
        try:
            msg_type = message.type
            
            if msg_type == Gst.MessageType.EOS:
                # End of stream
                logger.info("Playback finished")
                self._set_state(PlaybackState.STOPPED)
                self._cleanup_pipeline()
                
            elif msg_type == Gst.MessageType.ERROR:
                err, debug = message.parse_error()
                logger.error(f"GStreamer error: {err.message}")
                if debug:
                    logger.debug(f"Debug info: {debug}")
                
                # Log additional context about the error
                element_name = message.src.get_name() if message.src else "unknown"
                logger.error(f"Error from element: {element_name}")
                
                self._set_state(PlaybackState.STOPPED)
                self._cleanup_pipeline()
                
            elif msg_type == Gst.MessageType.WARNING:
                warn, debug = message.parse_warning()
                logger.warning(f"GStreamer warning: {warn.message}")
                if debug:
                    logger.debug(f"Debug info: {debug}")
                
            elif msg_type == Gst.MessageType.STATE_CHANGED:
                # Check if this message is from our pipeline
                # Use a lock to safely check pipeline reference
                pipeline_ref = None
                with self._lock:
                    pipeline_ref = self._pipeline
                
                if pipeline_ref and message.src == pipeline_ref:
                    old_state, new_state, pending = message.parse_state_changed()
                    logger.debug(f"Pipeline state changed: {old_state.value_nick} -> {new_state.value_nick}")
                    
                    if new_state == Gst.State.PLAYING:
                        self._set_state(PlaybackState.PLAYING)
                    elif new_state == Gst.State.PAUSED:
                        self._set_state(PlaybackState.PAUSED)
                    elif new_state == Gst.State.NULL:
                        self._set_state(PlaybackState.STOPPED)
                        
            elif msg_type == Gst.MessageType.ASYNC_DONE:
                logger.debug("Pipeline async state change completed")
                
        except Exception as e:
            logger.error(f"Error handling bus message: {e}", exc_info=True)
        
        return True
    
    def _set_state(self, state: PlaybackState) -> None:
        """Set playback state and notify callback."""
        self._state = state
        if self._on_state_change:
            try:
                self._on_state_change(state)
            except Exception as e:
                logger.error(f"Error in state change callback: {e}")
    
    def _cleanup_pipeline(self) -> None:
        """Clean up GStreamer pipeline."""
        with self._lock:
            if self._pipeline:
                self._pipeline.set_state(Gst.State.NULL)
                self._pipeline = None
    
    def _is_device_available(self, device: Optional[str]) -> bool:
        """
        Check if a specific device is currently available.
        
        Args:
            device: Device name to check (None means system default)
        
        Returns:
            True if device is available or None (default), False otherwise
        """
        if not device or device == "@DEFAULT_SINK@":
            return True  # System default is always "available"
        
        try:
            devices = self.get_audio_devices()
            return any(d.name == device for d in devices)
        except Exception as e:
            logger.warning(f"Error checking device availability: {e}")
            return False
    
    def play(self, file_path: str, device: Optional[str] = None) -> bool:
        """
        Play an audio file with automatic device fallback.
        
        Args:
            file_path: Path to audio file
            device: Audio device name (None for default)
        
        Returns:
            True if playback started successfully
        """
        try:
            # Stop any current playback quickly (with minimal lock time)
            old_pipeline = None
            with self._lock:
                old_pipeline = self._pipeline
                if old_pipeline:
                    self._pipeline = None  # Clear reference before stopping
            
            # Stop old pipeline outside lock to avoid blocking
            if old_pipeline:
                try:
                    old_pipeline.set_state(Gst.State.NULL)
                except Exception as e:
                    logger.warning(f"Error stopping previous pipeline: {e}")
            
            # Try playing with requested device first, then fallback options
            devices_to_try = []
            
            # 1. Try requested device if specified and available
            if device:
                if self._is_device_available(device):
                    devices_to_try.append(device)
                else:
                    logger.warning(f"Requested device '{device}' is not available, will try fallbacks")
            
            # 2. System default as fallback
            devices_to_try.append(None)  # None means system default
            
            # 3. Try any available device as last resort
            try:
                available_devices = self.get_audio_devices()
                # Build set of device names already queued to avoid duplicates
                tried_device_names = {d for d in devices_to_try if d is not None}
                
                for dev in available_devices:
                    # Skip if this device is already in our list to try
                    if dev.name in tried_device_names:
                        continue
                    devices_to_try.append(dev.name)
            except Exception:
                pass
            
            # Try each device in order
            last_error = None
            for attempt_device in devices_to_try:
                logger.info(f"Attempting playback with device: {attempt_device or 'system default'}")
                
                # Create new pipeline (may take time, but we're not holding lock)
                if not self._create_pipeline(file_path, attempt_device):
                    logger.warning(f"Failed to create pipeline for device: {attempt_device}")
                    continue
                
                # Start playback (non-blocking, async) - minimal lock time
                with self._lock:
                    if not self._pipeline:
                        logger.error("Pipeline is None after creation")
                        continue
                    
                    # Set state to PLAYING (async, non-blocking)
                    ret = self._pipeline.set_state(Gst.State.PLAYING)
                    
                    if ret == Gst.StateChangeReturn.FAILURE:
                        logger.warning(f"Failed to start playback on device {attempt_device} - state change returned FAILURE")
                        self._pipeline = None
                        continue
                    
                    # Both ASYNC and SUCCESS are fine - playback will start
                    device_desc = attempt_device or 'system default'
                    if attempt_device != device and device is not None:
                        logger.warning(f"Playing with fallback device: {device_desc} (requested: {device})")
                    else:
                        logger.info(f"Playing: {file_path} on device: {device_desc} (state change: {ret})")
                    return True
            
            # If we get here, all devices failed
            device_count = len(devices_to_try)
            logger.error(
                f"Failed to play audio on any of {device_count} available device(s). "
                f"Please check audio device configuration and ensure audio devices are not muted."
            )
            return False
            
        except Exception as e:
            logger.error(f"Error in play(): {e}", exc_info=True)
            with self._lock:
                self._pipeline = None
            return False
    
    def stop(self) -> None:
        """Stop playback."""
        try:
            # Get pipeline reference outside lock to avoid blocking
            pipeline_to_stop = None
            with self._lock:
                pipeline_to_stop = self._pipeline
                self._pipeline = None  # Clear reference immediately
                self._set_state(PlaybackState.STOPPED)
            
            # Stop pipeline outside lock to avoid blocking the main thread
            if pipeline_to_stop:
                try:
                    # Use async state change - don't wait for completion
                    ret = pipeline_to_stop.set_state(Gst.State.NULL)
                    # Don't wait for state change - it will complete asynchronously
                except Exception as e:
                    logger.warning(f"Error stopping pipeline: {e}")
            logger.info("Playback stopped")
        except Exception as e:
            logger.error(f"Error in stop(): {e}", exc_info=True)
            self._set_state(PlaybackState.STOPPED)
    
    def pause(self) -> None:
        """Pause playback."""
        with self._lock:
            if self._pipeline and self._state == PlaybackState.PLAYING:
                self._pipeline.set_state(Gst.State.PAUSED)
                logger.info("Playback paused")
    
    def resume(self) -> None:
        """Resume paused playback."""
        with self._lock:
            if self._pipeline and self._state == PlaybackState.PAUSED:
                self._pipeline.set_state(Gst.State.PLAYING)
                logger.info("Playback resumed")
    
    @property
    def state(self) -> PlaybackState:
        """Get current playback state."""
        return self._state
    
    @property
    def is_playing(self) -> bool:
        """Check if currently playing."""
        return self._state == PlaybackState.PLAYING
    
    def set_volume(self, volume: float) -> None:
        """
        Set playback volume.
        
        Args:
            volume: Volume level (0.0 to 1.0)
        """
        with self._lock:
            if self._pipeline:
                # Find the pulsesink element
                sink = self._pipeline.get_by_name("pulsesink0")
                if sink:
                    sink.set_property("volume", max(0.0, min(1.0, volume)))
    
    def get_position(self) -> Optional[float]:
        """Get current playback position in seconds."""
        with self._lock:
            if self._pipeline:
                success, position = self._pipeline.query_position(Gst.Format.TIME)
                if success:
                    return position / Gst.SECOND
        return None
    
    def get_duration(self) -> Optional[float]:
        """Get total duration in seconds."""
        with self._lock:
            if self._pipeline:
                success, duration = self._pipeline.query_duration(Gst.Format.TIME)
                if success:
                    return duration / Gst.SECOND
        return None
    
    def cleanup(self) -> None:
        """Clean up resources."""
        self.stop()
        logger.info("AudioPlayer cleaned up")


def validate_audio_file(file_path: str) -> bool:
    """
    Validate that an audio file exists and is a supported format.
    
    Args:
        file_path: Path to audio file
    
    Returns:
        True if file is valid
    """
    if not file_path or not os.path.isfile(file_path):
        return False
    
    supported_extensions = {'.mp3', '.wav', '.ogg', '.flac', '.m4a', '.aac'}
    ext = os.path.splitext(file_path)[1].lower()
    
    return ext in supported_extensions


def get_default_athan_path() -> str:
    """Get path to default Athan audio file."""
    # Check common locations
    paths = [
        '/usr/share/athan-app/sounds/default_athan.mp3',
        os.path.expanduser('~/.local/share/athan-app/sounds/default_athan.mp3'),
        os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'sounds', 'default_athan.mp3'),
    ]
    
    for path in paths:
        if os.path.isfile(path):
            return path
    
    return paths[0]  # Return expected system path
