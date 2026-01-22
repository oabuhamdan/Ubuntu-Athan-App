"""
Main Window Module

The primary UI for the Athan application featuring:
- Daily prayer times display (all visible without scrolling)
- Current/next prayer highlighting
- Countdown timer
- Quick access to settings and controls
"""

import logging
import os
from datetime import datetime, timedelta
from typing import Optional, Dict

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GLib, Pango

from ..calculation.aladhan_api import PrayerTimesManager
from ..config.settings import get_settings
from ..audio.player import AudioPlayer, PlaybackState, get_default_athan_path, validate_audio_file

logger = logging.getLogger(__name__)


class MainWindow(Gtk.ApplicationWindow):
    """
    Main application window.
    
    Displays:
    - All prayer times for the current day (no scrolling)
    - Countdown to next prayer
    - Control buttons (stop, skip toggle, settings)
    """
    
    def __init__(self, application: Gtk.Application):
        super().__init__(application=application, title="Athan")
        
        self.app = application
        self.settings = get_settings()
        self.prayer_manager = PrayerTimesManager()
        self.player = AudioPlayer(on_state_change=self._on_playback_state_change)
        
        self._countdown_timer_id: Optional[int] = None
        self._athan_timer_id: Optional[int] = None
        self._skip_next_athan = False
        
        # Window setup
        self.set_default_size(380, 520)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.set_resizable(False)
        
        # Apply CSS styling
        self._setup_css()
        
        # Build UI
        self._build_ui()
        
        # Load prayer times
        self._load_prayer_times()
        
        # Start countdown timer
        self._start_countdown_timer()
        
        # Schedule next Athan
        self._schedule_next_athan()
        
        # Handle window close
        self.connect('delete-event', self._on_delete_event)
        
        logger.info("MainWindow created")
    
    def _setup_css(self) -> None:
        """Set up CSS styling."""
        css = b"""
        window {
            background-color: #1a1a2e;
        }
        
        .header-box {
            background-color: #16213e;
            padding: 16px;
        }
        
        .app-title {
            color: #e94560;
            font-size: 22px;
            font-weight: bold;
        }
        
        .date-label {
            color: #a0a0a0;
            font-size: 13px;
        }
        
        .location-label {
            color: #888888;
            font-size: 12px;
        }
        
        .countdown-box {
            background-color: #0f3460;
            border-radius: 12px;
            padding: 16px;
            margin: 12px 16px;
        }
        
        .countdown-label {
            color: #e94560;
            font-size: 42px;
            font-weight: bold;
            font-family: monospace;
        }
        
        .next-prayer-label {
            color: #ffffff;
            font-size: 16px;
        }
        
        .prayer-row {
            background-color: #16213e;
            border-radius: 8px;
            padding: 12px 16px;
            margin: 4px 16px;
        }
        
        .prayer-row-current {
            background-color: #1a3a2e;
            border-left: 4px solid #00ff88;
        }
        
        .prayer-row-next {
            background-color: #2a1a2e;
            border-left: 4px solid #e94560;
        }
        
        .prayer-name {
            color: #ffffff;
            font-size: 15px;
            font-weight: 500;
        }
        
        .prayer-name-arabic {
            color: #888888;
            font-size: 13px;
        }
        
        .prayer-time {
            color: #e94560;
            font-size: 18px;
            font-weight: bold;
            font-family: monospace;
        }
        
        .prayer-status {
            font-size: 12px;
        }
        
        .status-current {
            color: #00ff88;
        }
        
        .status-next {
            color: #e94560;
        }
        
        .control-box {
            padding: 12px 16px;
        }
        
        .control-button {
            background-color: #0f3460;
            color: #ffffff;
            border: none;
            border-radius: 8px;
            padding: 10px 20px;
            font-size: 13px;
            min-width: 100px;
        }
        
        .control-button:hover {
            background-color: #1f4770;
        }
        
        .stop-button {
            background-color: #e94560;
        }
        
        .stop-button:hover {
            background-color: #ff6b81;
        }
        
        .skip-active {
            background-color: #ff9800;
        }
        
        .settings-button {
            background-color: transparent;
            border: 1px solid #0f3460;
            min-width: 40px;
        }
        
        .no-location-box {
            padding: 40px;
        }
        
        .no-location-label {
            color: #888888;
            font-size: 14px;
        }
        
        .setup-button {
            background-color: #e94560;
            color: #ffffff;
            border: none;
            border-radius: 8px;
            padding: 12px 24px;
            font-size: 14px;
        }
        """
        
        provider = Gtk.CssProvider()
        provider.load_from_data(css)
        
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(),
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
    
    def _build_ui(self) -> None:
        """Build the main UI."""
        self.main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add(self.main_box)
        
        # Header
        header_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        header_box.get_style_context().add_class('header-box')
        
        # Title row
        title_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        
        title_label = Gtk.Label(label="🕌 Athan")
        title_label.get_style_context().add_class('app-title')
        title_label.set_xalign(0)
        title_row.pack_start(title_label, True, True, 0)
        
        # Settings button
        settings_btn = Gtk.Button(label="⚙")
        settings_btn.get_style_context().add_class('control-button')
        settings_btn.get_style_context().add_class('settings-button')
        settings_btn.connect('clicked', self._on_settings_clicked)
        title_row.pack_end(settings_btn, False, False, 0)
        
        header_box.pack_start(title_row, False, False, 0)
        
        # Date
        self.date_label = Gtk.Label()
        self.date_label.get_style_context().add_class('date-label')
        self.date_label.set_xalign(0)
        self._update_date_label()
        header_box.pack_start(self.date_label, False, False, 0)
        
        # Location
        self.location_label = Gtk.Label()
        self.location_label.get_style_context().add_class('location-label')
        self.location_label.set_xalign(0)
        header_box.pack_start(self.location_label, False, False, 0)
        
        self.main_box.pack_start(header_box, False, False, 0)
        
        # Content area (will be populated by _load_prayer_times)
        self.content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.main_box.pack_start(self.content_box, True, True, 0)
    
    def _format_time(self, time_str: str) -> str:
        """Format time string based on 24-hour setting."""
        if not time_str or time_str == '--:--':
            return time_str
        
        try:
            # Parse time string (format: "HH:MM")
            parts = time_str.split(':')
            if len(parts) != 2:
                return time_str
            
            hour = int(parts[0])
            minute = int(parts[1])
            
            # If 24-hour format is enabled, return as-is
            if self.settings.ui.use_24_hour:
                return f"{hour:02d}:{minute:02d}"
            
            # Convert to 12-hour format
            period = "AM" if hour < 12 else "PM"
            if hour == 0:
                hour_12 = 12
            elif hour > 12:
                hour_12 = hour - 12
            else:
                hour_12 = hour
            
            return f"{hour_12}:{minute:02d} {period}"
        except (ValueError, IndexError):
            return time_str
    
    def _build_prayer_times_ui(self) -> None:
        """Build the prayer times display."""
        # Clear content
        for child in self.content_box.get_children():
            self.content_box.remove(child)
        
        # Countdown box
        countdown_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        countdown_box.get_style_context().add_class('countdown-box')
        countdown_box.set_halign(Gtk.Align.FILL)
        
        self.next_prayer_label = Gtk.Label(label="Next Prayer")
        self.next_prayer_label.get_style_context().add_class('next-prayer-label')
        countdown_box.pack_start(self.next_prayer_label, False, False, 0)
        
        self.countdown_label = Gtk.Label(label="--:--:--")
        self.countdown_label.get_style_context().add_class('countdown-label')
        countdown_box.pack_start(self.countdown_label, False, False, 0)
        
        self.content_box.pack_start(countdown_box, False, False, 0)
        
        # Prayer times (all visible, no scrolling)
        self.prayer_rows = {}
        prayers_info = [
            ('Fajr', 'الفجر'),
            ('Sunrise', 'الشروق'),
            ('Dhuhr', 'الظهر'),
            ('Asr', 'العصر'),
            ('Maghrib', 'المغرب'),
            ('Isha', 'العشاء'),
        ]
        
        times = self.prayer_manager.get_today_times() or {}
        current = self.prayer_manager.get_current_prayer()
        next_prayer_info = self.prayer_manager.get_next_prayer()
        next_prayer = next_prayer_info[0] if next_prayer_info else None
        
        for prayer, arabic in prayers_info:
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            row.get_style_context().add_class('prayer-row')
            
            # Apply current/next styling
            if prayer == current:
                row.get_style_context().add_class('prayer-row-current')
            elif prayer == next_prayer:
                row.get_style_context().add_class('prayer-row-next')
            
            # Prayer name
            name_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
            name_label = Gtk.Label(label=prayer)
            name_label.get_style_context().add_class('prayer-name')
            name_label.set_xalign(0)
            name_box.pack_start(name_label, False, False, 0)
            
            arabic_label = Gtk.Label(label=arabic)
            arabic_label.get_style_context().add_class('prayer-name-arabic')
            arabic_label.set_xalign(0)
            name_box.pack_start(arabic_label, False, False, 0)
            
            row.pack_start(name_box, True, True, 0)
            
            # Status
            status_label = Gtk.Label()
            status_label.get_style_context().add_class('prayer-status')
            if prayer == current:
                status_label.set_text("● Current")
                status_label.get_style_context().add_class('status-current')
            elif prayer == next_prayer:
                status_label.set_text("▶ Next")
                status_label.get_style_context().add_class('status-next')
            row.pack_start(status_label, False, False, 8)
            
            # Time
            time_str = times.get(prayer, '--:--')
            formatted_time = self._format_time(time_str)
            time_label = Gtk.Label(label=formatted_time)
            time_label.get_style_context().add_class('prayer-time')
            row.pack_end(time_label, False, False, 0)
            
            self.content_box.pack_start(row, False, False, 0)
            self.prayer_rows[prayer] = (row, time_label, status_label)
        
        # Control buttons
        controls_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        controls_box.get_style_context().add_class('control-box')
        controls_box.set_halign(Gtk.Align.CENTER)
        
        # Stop button - always clickable
        self.stop_btn = Gtk.Button(label="⏹ Stop")
        self.stop_btn.get_style_context().add_class('control-button')
        self.stop_btn.get_style_context().add_class('stop-button')
        self.stop_btn.connect('clicked', self._on_stop_clicked)
        # Button is always enabled - handler will check if audio is playing
        self.stop_btn.set_sensitive(True)
        controls_box.pack_start(self.stop_btn, False, False, 0)
        
        # Skip toggle button
        self.skip_btn = Gtk.Button(label="⏭ Skip Next")
        self.skip_btn.get_style_context().add_class('control-button')
        self.skip_btn.connect('clicked', self._on_skip_clicked)
        controls_box.pack_start(self.skip_btn, False, False, 0)
        
        self.content_box.pack_end(controls_box, False, False, 8)
        
        self.content_box.show_all()
    
    def _build_no_location_ui(self) -> None:
        """Build UI shown when no location is configured."""
        # Clear content
        for child in self.content_box.get_children():
            self.content_box.remove(child)
        
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        box.get_style_context().add_class('no-location-box')
        box.set_valign(Gtk.Align.CENTER)
        box.set_halign(Gtk.Align.CENTER)
        
        icon_label = Gtk.Label(label="📍")
        icon_label.set_markup('<span size="72000">📍</span>')
        box.pack_start(icon_label, False, False, 0)
        
        msg_label = Gtk.Label(label="No location configured")
        msg_label.get_style_context().add_class('no-location-label')
        box.pack_start(msg_label, False, False, 0)
        
        setup_btn = Gtk.Button(label="Set Up Location")
        setup_btn.get_style_context().add_class('setup-button')
        setup_btn.connect('clicked', self._on_settings_clicked)
        box.pack_start(setup_btn, False, False, 0)
        
        self.content_box.pack_start(box, True, True, 0)
        self.content_box.show_all()
    
    def _update_date_label(self) -> None:
        """Update the date display."""
        now = datetime.now()
        self.date_label.set_text(now.strftime('%A, %B %d, %Y'))
    
    def _update_location_label(self) -> None:
        """Update the location display."""
        loc = self.settings.location
        if loc.city_name:
            text = f"📍 {loc.city_name}"
            if loc.country:
                text += f", {loc.country}"
            self.location_label.set_text(text)
        else:
            self.location_label.set_text("")
    
    def _load_prayer_times(self) -> None:
        """Load prayer times from cache or API."""
        self._update_location_label()
        
        loc = self.settings.location
        if not loc.city_name or not loc.country:
            self._build_no_location_ui()
            return
        
        # Try to load from cache first
        self.prayer_manager.refresh_if_needed()
        
        # Check if we have times
        times = self.prayer_manager.get_today_times()
        if times:
            self._build_prayer_times_ui()
        else:
            # Try to fetch
            success, msg, info = self.prayer_manager.set_location(loc.city_name, loc.country)
            if success:
                self._build_prayer_times_ui()
            else:
                self._build_no_location_ui()
    
    def _start_countdown_timer(self) -> None:
        """Start the countdown update timer."""
        self._countdown_timer_id = GLib.timeout_add_seconds(1, self._update_countdown)
    
    def _update_countdown(self) -> bool:
        """Update the countdown display."""
        if not hasattr(self, 'countdown_label'):
            return True
        
        next_prayer = self.prayer_manager.get_next_prayer()
        
        if next_prayer:
            name, time_str, prayer_dt = next_prayer
            formatted_time = self._format_time(time_str)
            self.next_prayer_label.set_text(f"Next: {name} at {formatted_time}")
            
            # Calculate countdown
            location = self.prayer_manager.cache.get_location()
            if location:
                import pytz
                try:
                    tz = pytz.timezone(location['timezone'])
                    now = datetime.now(tz)
                    delta = prayer_dt - now
                    
                    if delta.total_seconds() > 0:
                        hours, remainder = divmod(int(delta.total_seconds()), 3600)
                        minutes, seconds = divmod(remainder, 60)
                        
                        if hours > 0:
                            self.countdown_label.set_text(f"{hours:02d}:{minutes:02d}:{seconds:02d}")
                        else:
                            self.countdown_label.set_text(f"{minutes:02d}:{seconds:02d}")
                    else:
                        self.countdown_label.set_text("00:00")
                        # Refresh prayer times display
                        self._build_prayer_times_ui()
                except:
                    self.countdown_label.set_text("--:--")
        else:
            self.next_prayer_label.set_text("Next Prayer")
            self.countdown_label.set_text("--:--")
        
        return True
    
    def _schedule_next_athan(self) -> None:
        """Schedule the next Athan playback."""
        if self._athan_timer_id:
            GLib.source_remove(self._athan_timer_id)
            self._athan_timer_id = None
        
        next_prayer = self.prayer_manager.get_next_prayer()
        if not next_prayer:
            return
        
        name, time_str, prayer_dt = next_prayer
        
        # Skip sunrise
        if name == 'Sunrise':
            return
        
        location = self.prayer_manager.cache.get_location()
        if not location:
            return
        
        import pytz
        try:
            tz = pytz.timezone(location['timezone'])
            now = datetime.now(tz)
            delta = prayer_dt - now
            
            if delta.total_seconds() > 0:
                delay_seconds = delta.total_seconds()
                delay_seconds_int = int(delay_seconds)
                
                # Simple: schedule a timer that fires when it's time to play
                # Use a closure to capture the prayer name
                def athan_timer_callback():
                    self._on_athan_time(name)
                    return False  # One-shot timer
                
                if delay_seconds_int > 0:
                    self._athan_timer_id = GLib.timeout_add_seconds(delay_seconds_int, athan_timer_callback)
                else:
                    # For sub-second delays, use timeout_add with milliseconds
                    delay_ms = int(delay_seconds * 1000)
                    if delay_ms > 0:
                        self._athan_timer_id = GLib.timeout_add(delay_ms, athan_timer_callback)
                logger.info(f"Scheduled Athan for {name} in {delta.total_seconds():.0f} seconds")
            else:
                # Prayer time has already passed - play immediately
                logger.info(f"Prayer time {name} has already passed, playing immediately")
                GLib.idle_add(self._handle_athan_time, name, priority=GLib.PRIORITY_LOW)
        except Exception as e:
            logger.error(f"Error scheduling Athan: {e}")
    
    def _on_athan_time(self, prayer_name: str) -> bool:
        """Called when it's time to play Athan."""
        logger.info(f"Athan time for {prayer_name}")
        
        # Clear timer ID since it fired
        self._athan_timer_id = None
        
        # Call handler directly - timer callbacks run in main thread
        self._handle_athan_time(prayer_name)
        return False
    
    def _handle_athan_time(self, prayer_name: str) -> bool:
        """Handle Athan time (called in main thread)."""
        try:
            logger.info(f"_handle_athan_time called for {prayer_name}")
            
            # Check if skipped
            if self._skip_next_athan:
                logger.info("Athan skipped by user")
                self._skip_next_athan = False
                # Defer UI updates
                GLib.idle_add(self._update_skip_button, priority=GLib.PRIORITY_LOW)
                if hasattr(self.app, 'indicator') and self.app.indicator:
                    GLib.idle_add(lambda: self.app.indicator.update_skip_state(False), priority=GLib.PRIORITY_LOW)
                GLib.timeout_add(200, self._schedule_next_athan)
                GLib.timeout_add(200, self._build_prayer_times_ui)
                return False
            
            # Check if enabled for this prayer
            enabled = self.settings.is_athan_enabled_for_prayer(prayer_name)
            logger.info(f"Athan enabled for {prayer_name}: {enabled}")
            if not enabled:
                logger.info(f"Athan disabled for {prayer_name}")
                GLib.timeout_add(200, self._schedule_next_athan)
                GLib.timeout_add(200, self._build_prayer_times_ui)
                return False
            
            # Play Athan (defer to avoid blocking timer callback)
            audio_file = self.settings.audio.athan_file
            logger.info(f"Audio file from settings: {audio_file}")
            if not audio_file or not validate_audio_file(audio_file):
                audio_file = get_default_athan_path()
                logger.info(f"Using default audio file: {audio_file}")
            if validate_audio_file(audio_file):
                device = self.settings.audio.device_name
                logger.info(f"Device: {device}")
                # Play immediately - don't defer, we're already in main thread
                try:
                    logger.info(f"Calling player.play() for {prayer_name}: {audio_file}")
                    success = self.player.play(audio_file, device)
                    if not success:
                        logger.error(f"Failed to start Athan playback for {prayer_name}")
                    else:
                        logger.info(f"Athan playback started successfully for {prayer_name}")
                except Exception as e:
                    logger.error(f"Error playing Athan: {e}", exc_info=True)
            else:
                logger.error(f"No valid Athan audio file found: {audio_file}")
            
            # Schedule next (defer to avoid blocking)
            GLib.timeout_add(500, self._schedule_next_athan)
            GLib.timeout_add(500, self._build_prayer_times_ui)
            
        except Exception as e:
            logger.error(f"Error handling Athan time: {e}", exc_info=True)
        
        return False
    
    def _on_playback_state_change(self, state: PlaybackState) -> None:
        """Handle playback state changes."""
        if hasattr(self, 'stop_btn'):
            self.stop_btn.set_sensitive(state == PlaybackState.PLAYING)
    
    def _on_stop_clicked(self, button: Gtk.Button) -> None:
        """Handle stop button click."""
        
        # Check if audio is actually playing - if not, just ignore the click
        if not hasattr(self, 'player') or not self.player.is_playing:
            logger.debug("Stop button clicked but no audio playing - ignoring")
            return
        
        try:
            self.player.stop()
            logger.info("Athan stopped by user")
        except Exception as e:
            logger.error(f"Error stopping Athan: {e}", exc_info=True)
    
    def _on_skip_clicked(self, button: Gtk.Button) -> None:
        """Handle skip toggle button click."""
        self._skip_next_athan = not self._skip_next_athan
        self._update_skip_button()
        # Update indicator
        if hasattr(self.app, 'indicator') and self.app.indicator:
            self.app.indicator.update_skip_state(self._skip_next_athan)
    
    def _update_skip_button(self) -> None:
        """Update skip button appearance."""
        if hasattr(self, 'skip_btn'):
            if self._skip_next_athan:
                self.skip_btn.set_label("✓ Will Skip")
                self.skip_btn.get_style_context().add_class('skip-active')
            else:
                self.skip_btn.set_label("⏭ Skip Next")
                self.skip_btn.get_style_context().remove_class('skip-active')
    
    def _on_settings_clicked(self, button: Gtk.Button) -> None:
        """Handle settings button click."""
        from .settings_dialog import SettingsDialog
        dialog = SettingsDialog(self, self.settings)
        response = dialog.run()
        
        if response == Gtk.ResponseType.APPLY:
            # Settings were saved, reload everything
            self._load_prayer_times()
            self._schedule_next_athan()
            
            # Update indicator
            if hasattr(self.app, 'indicator') and self.app.indicator:
                self.app.indicator.refresh()
        
        dialog.destroy()
    
    def _on_delete_event(self, widget, event) -> bool:
        """Handle window close."""
        if self.settings.ui.minimize_to_tray:
            self.hide()
            return True
        return False
    
    def refresh(self) -> None:
        """Refresh the display."""
        self._load_prayer_times()
    
    def cleanup(self) -> None:
        """Clean up resources."""
        try:
            # Stop countdown timer
            if self._countdown_timer_id:
                try:
                    GLib.source_remove(self._countdown_timer_id)
                except Exception:
                    pass
                self._countdown_timer_id = None
            
            # Stop Athan timer
            if self._athan_timer_id:
                try:
                    GLib.source_remove(self._athan_timer_id)
                except Exception:
                    pass
                self._athan_timer_id = None
            
            # Stop player
            try:
                self.player.stop()
                self.player.cleanup()
            except Exception as e:
                logger.warning(f"Error cleaning up player: {e}")
        except Exception as e:
            logger.error(f"Error in cleanup: {e}", exc_info=True)
