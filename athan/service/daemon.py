"""
Athan Daemon Module

Background service that:
- Runs independently of the UI
- Schedules and plays Athan at correct times
- Exposes D-Bus interface for UI communication
- Handles system sleep/resume
- Auto-relaunches if crashed
"""

import os
import sys
import signal
import logging
import threading
from datetime import datetime
from typing import Optional, Dict

import dbus
import dbus.service
import dbus.mainloop.glib
from gi.repository import GLib

from .. import DBUS_SERVICE_NAME, DBUS_OBJECT_PATH, DBUS_INTERFACE
from ..calculation.prayer_times import Prayer, get_prayer_name
from ..config.settings import AppSettings, get_settings
from ..audio.player import AudioPlayer, PlaybackState, get_default_athan_path, validate_audio_file
from .scheduler import AthanScheduler

logger = logging.getLogger(__name__)


class AthanDBusService(dbus.service.Object):
    """
    D-Bus service interface for the Athan daemon.
    
    Provides methods for:
    - Getting prayer times
    - Controlling Athan playback
    - Updating settings
    - Status queries
    """
    
    def __init__(self, daemon: 'AthanDaemon', bus_name: dbus.service.BusName):
        super().__init__(bus_name, DBUS_OBJECT_PATH)
        self._daemon = daemon
        logger.info("D-Bus service initialized")
    
    @dbus.service.method(DBUS_INTERFACE, out_signature='a{ss}')
    def GetPrayerTimes(self) -> Dict[str, str]:
        """Get today's prayer times."""
        times = self._daemon.scheduler.get_current_times()
        return {
            p.value: t.strftime('%H:%M:%S') 
            for p, t in times.items()
        }
    
    @dbus.service.method(DBUS_INTERFACE, out_signature='ss')
    def GetNextPrayer(self) -> tuple:
        """Get next prayer name and time."""
        next_prayer = self._daemon.scheduler.get_next_prayer()
        if next_prayer:
            return (next_prayer.prayer.value, next_prayer.time.strftime('%H:%M:%S'))
        return ('', '')
    
    @dbus.service.method(DBUS_INTERFACE, out_signature='s')
    def GetCountdown(self) -> str:
        """Get countdown to next prayer as string."""
        return self._daemon.get_countdown_string()
    
    @dbus.service.method(DBUS_INTERFACE, out_signature='b')
    def IsPlaying(self) -> bool:
        """Check if Athan is currently playing."""
        return self._daemon.player.is_playing
    
    @dbus.service.method(DBUS_INTERFACE)
    def StopAthan(self) -> None:
        """Stop currently playing Athan."""
        self._daemon.stop_athan()
    
    @dbus.service.method(DBUS_INTERFACE)
    def SkipNextAthan(self) -> None:
        """Skip the next Athan."""
        self._daemon.scheduler.skip_next()
    
    @dbus.service.method(DBUS_INTERFACE)
    def UnskipNextAthan(self) -> None:
        """Cancel skip next Athan."""
        self._daemon.scheduler.unskip_next()
    
    @dbus.service.method(DBUS_INTERFACE, out_signature='b')
    def IsSkipNextSet(self) -> bool:
        """Check if skip next is set."""
        return self._daemon.settings.skip_next_athan
    
    @dbus.service.method(DBUS_INTERFACE)
    def RecalculateTimes(self) -> None:
        """Force recalculation of prayer times."""
        self._daemon.scheduler.recalculate()
    
    @dbus.service.method(DBUS_INTERFACE)
    def ReloadSettings(self) -> None:
        """Reload settings from disk."""
        self._daemon.settings.load()
        self._daemon.scheduler.recalculate()
    
    @dbus.service.method(DBUS_INTERFACE, out_signature='b')
    def Ping(self) -> bool:
        """Health check."""
        return True
    
    @dbus.service.method(DBUS_INTERFACE)
    def Quit(self) -> None:
        """Stop the daemon."""
        self._daemon.stop()
    
    @dbus.service.signal(DBUS_INTERFACE, signature='ss')
    def AthanStarted(self, prayer: str, time: str) -> None:
        """Signal emitted when Athan starts playing."""
        pass
    
    @dbus.service.signal(DBUS_INTERFACE)
    def AthanStopped(self) -> None:
        """Signal emitted when Athan stops playing."""
        pass
    
    @dbus.service.signal(DBUS_INTERFACE)
    def TimesUpdated(self) -> None:
        """Signal emitted when prayer times are updated."""
        pass


class AthanDaemon:
    """
    Main Athan daemon class.
    
    Responsibilities:
    - Initialize and manage scheduler
    - Handle Athan playback
    - Expose D-Bus interface
    - Manage lifecycle (start, stop, signals)
    """
    
    def __init__(self):
        """Initialize the daemon."""
        self._running = False
        self._main_loop: Optional[GLib.MainLoop] = None
        
        # Initialize D-Bus
        dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
        
        # Components
        self.settings = get_settings()
        self.player = AudioPlayer(on_state_change=self._on_playback_state_change)
        self.scheduler = AthanScheduler(
            settings=self.settings,
            on_athan_trigger=self._on_athan_trigger,
            on_times_updated=self._on_times_updated
        )
        
        # D-Bus service
        self._bus: Optional[dbus.SessionBus] = None
        self._bus_name: Optional[dbus.service.BusName] = None
        self._dbus_service: Optional[AthanDBusService] = None
        
        # Current playing prayer (for tracking)
        self._current_athan_prayer: Optional[Prayer] = None
        
        # Settings change callback
        self.settings.add_change_callback(self._on_settings_changed)
        
        logger.info("AthanDaemon initialized")
    
    def _setup_dbus(self) -> bool:
        """Set up D-Bus service."""
        try:
            self._bus = dbus.SessionBus()
            
            # Check if service is already running
            try:
                proxy = self._bus.get_object(DBUS_SERVICE_NAME, DBUS_OBJECT_PATH)
                interface = dbus.Interface(proxy, DBUS_INTERFACE)
                if interface.Ping():
                    logger.warning("Daemon already running")
                    return False
            except dbus.exceptions.DBusException:
                pass  # Service not running, we can start
            
            # Register our service
            self._bus_name = dbus.service.BusName(
                DBUS_SERVICE_NAME,
                bus=self._bus,
                do_not_queue=True
            )
            
            self._dbus_service = AthanDBusService(self, self._bus_name)
            
            logger.info("D-Bus service registered")
            return True
            
        except dbus.exceptions.NameExistsException:
            logger.error("D-Bus name already taken")
            return False
        except Exception as e:
            logger.error(f"Error setting up D-Bus: {e}")
            return False
    
    def _setup_signals(self) -> None:
        """Set up signal handlers."""
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)
    
    def _signal_handler(self, signum: int, frame) -> None:
        """Handle termination signals."""
        logger.info(f"Received signal {signum}")
        self.stop()
    
    def start(self) -> bool:
        """
        Start the daemon.
        
        Returns:
            True if started successfully
        """
        if self._running:
            return True
        
        # Set up D-Bus
        if not self._setup_dbus():
            return False
        
        # Set up signals
        self._setup_signals()
        
        # Start scheduler
        self.scheduler.start()
        
        # Create main loop
        self._main_loop = GLib.MainLoop()
        self._running = True
        
        logger.info("Daemon started")
        
        # Run main loop (blocks)
        try:
            self._main_loop.run()
        except KeyboardInterrupt:
            pass
        
        return True
    
    def stop(self) -> None:
        """Stop the daemon."""
        if not self._running:
            return
        
        logger.info("Stopping daemon...")
        
        self._running = False
        
        # Stop components
        self.scheduler.stop()
        self.player.cleanup()
        
        # Quit main loop
        if self._main_loop and self._main_loop.is_running():
            self._main_loop.quit()
        
        logger.info("Daemon stopped")
    
    def _on_athan_trigger(self, prayer: Prayer, prayer_time: datetime) -> None:
        """Called when it's time to play Athan."""
        logger.info(f"Athan triggered for {prayer.value} at {prayer_time}")
        
        # Get Athan audio file
        audio_file = self.settings.audio.athan_file
        
        if not audio_file or not validate_audio_file(audio_file):
            audio_file = get_default_athan_path()
        
        if not validate_audio_file(audio_file):
            logger.error(f"Athan audio file not found: {audio_file}")
            return
        
        # Get audio device
        device = self.settings.audio.device_name
        
        # Play Athan
        self._current_athan_prayer = prayer
        
        if self.player.play(audio_file, device):
            # Emit D-Bus signal
            if self._dbus_service:
                self._dbus_service.AthanStarted(
                    prayer.value,
                    prayer_time.strftime('%H:%M:%S')
                )
        else:
            logger.error("Failed to play Athan")
    
    def _on_playback_state_change(self, state: PlaybackState) -> None:
        """Called when playback state changes."""
        if state == PlaybackState.STOPPED:
            self._current_athan_prayer = None
            if self._dbus_service:
                self._dbus_service.AthanStopped()
    
    def _on_times_updated(self, times: Dict[Prayer, datetime]) -> None:
        """Called when prayer times are recalculated."""
        if self._dbus_service:
            self._dbus_service.TimesUpdated()
    
    def _on_settings_changed(self) -> None:
        """Called when settings change."""
        # Recalculate times if location or calculation settings changed
        if self.scheduler.is_running:
            self.scheduler.recalculate()
    
    def stop_athan(self) -> None:
        """Stop currently playing Athan."""
        self.player.stop()
        self._current_athan_prayer = None
    
    def get_countdown_string(self) -> str:
        """Get countdown to next prayer as formatted string."""
        next_prayer = self.scheduler.get_next_prayer()
        if not next_prayer:
            return "--:--"
        
        now = datetime.now(next_prayer.time.tzinfo)
        delta = next_prayer.time - now
        
        if delta.total_seconds() <= 0:
            return "00:00"
        
        hours, remainder = divmod(int(delta.total_seconds()), 3600)
        minutes, seconds = divmod(remainder, 60)
        
        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        else:
            return f"{minutes:02d}:{seconds:02d}"
    
    @property
    def is_running(self) -> bool:
        """Check if daemon is running."""
        return self._running


def run_daemon() -> int:
    """
    Run the Athan daemon.
    
    Returns:
        Exit code
    """
    # Set up logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(
                os.path.expanduser('~/.local/share/athan-app/logs/daemon.log')
            )
        ]
    )
    
    # Ensure log directory exists
    os.makedirs(os.path.expanduser('~/.local/share/athan-app/logs'), exist_ok=True)
    
    logger.info("Starting Athan daemon...")
    
    daemon = AthanDaemon()
    
    if daemon.start():
        return 0
    else:
        return 1


def get_daemon_proxy() -> Optional[dbus.Interface]:
    """
    Get a D-Bus proxy to the running daemon.
    
    Returns:
        D-Bus interface proxy or None if daemon not running
    """
    try:
        bus = dbus.SessionBus()
        proxy = bus.get_object(DBUS_SERVICE_NAME, DBUS_OBJECT_PATH)
        interface = dbus.Interface(proxy, DBUS_INTERFACE)
        
        # Test connection
        interface.Ping()
        
        return interface
    except dbus.exceptions.DBusException:
        return None


def is_daemon_running() -> bool:
    """Check if daemon is running."""
    return get_daemon_proxy() is not None
