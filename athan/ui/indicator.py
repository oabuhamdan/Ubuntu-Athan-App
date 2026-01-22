"""
Top Panel Indicator Module

Implements the GNOME top panel indicator showing:
- Next prayer name and countdown
- All prayer times in dropdown menu
- Quick access controls
"""

import logging
from datetime import datetime
from typing import Optional, Callable

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib

try:
    gi.require_version('AyatanaAppIndicator3', '0.1')
    from gi.repository import AyatanaAppIndicator3 as AppIndicator
except ImportError:
    gi.require_version('AppIndicator3', '0.1')
    from gi.repository import AppIndicator3 as AppIndicator

from ..calculation.aladhan_api import PrayerTimesManager
from ..config.settings import get_settings
import pytz

logger = logging.getLogger(__name__)


class AthanIndicator:
    """
    System tray/panel indicator for Athan application.
    
    Shows:
    - Next prayer and countdown in panel
    - All prayer times in dropdown menu
    - Stop/Skip controls
    """
    
    INDICATOR_ID = "athan-indicator"
    
    def __init__(
        self,
        prayer_manager: PrayerTimesManager,
        on_show_window: Optional[Callable[[], None]] = None,
        on_quit: Optional[Callable[[], None]] = None,
        on_stop: Optional[Callable[[], None]] = None,
        on_skip_toggle: Optional[Callable[[], bool]] = None,
    ):
        self._prayer_manager = prayer_manager
        self._on_show_window = on_show_window
        self._on_quit = on_quit
        self._on_stop = on_stop
        self._on_skip_toggle = on_skip_toggle
        self._update_timer_id: Optional[int] = None
        
        self.settings = get_settings()
        
        # Create indicator
        self._indicator = AppIndicator.Indicator.new(
            self.INDICATOR_ID,
            "appointment-soon",
            AppIndicator.IndicatorCategory.APPLICATION_STATUS
        )
        
        self._indicator.set_status(AppIndicator.IndicatorStatus.ACTIVE)
        self._indicator.set_title("Athan")
        
        # Create menu
        self._menu = self._create_menu()
        self._indicator.set_menu(self._menu)
        
        # Start update timer
        self._start_update_timer()
        
        # Initial update
        self._update_indicator()
        
        logger.info("AthanIndicator initialized")
    
    def _create_menu(self) -> Gtk.Menu:
        """Create the indicator menu."""
        menu = Gtk.Menu()
        
        # Header
        header = Gtk.MenuItem(label="🕌 Athan Prayer Times")
        header.set_sensitive(False)
        menu.append(header)
        
        menu.append(Gtk.SeparatorMenuItem())
        
        # Prayer times section
        self._prayer_items = {}
        prayers = ['Fajr', 'Sunrise', 'Dhuhr', 'Asr', 'Maghrib', 'Isha']
        
        for prayer in prayers:
            item = Gtk.MenuItem(label=f"{prayer}: --:--")
            item.set_sensitive(False)
            menu.append(item)
            self._prayer_items[prayer] = item
        
        menu.append(Gtk.SeparatorMenuItem())
        
        # Next prayer info
        self._next_info_item = Gtk.MenuItem(label="Next: --")
        self._next_info_item.set_sensitive(False)
        menu.append(self._next_info_item)
        
        self._countdown_item = Gtk.MenuItem(label="⏱ --:--:--")
        self._countdown_item.set_sensitive(False)
        menu.append(self._countdown_item)
        
        menu.append(Gtk.SeparatorMenuItem())
        
        # Controls
        self._stop_item = Gtk.MenuItem(label="⏹ Stop Athan")
        self._stop_item.connect('activate', self._on_stop_clicked)
        menu.append(self._stop_item)
        
        self._skip_item = Gtk.MenuItem(label="⏭ Skip Next")
        self._skip_item.connect('activate', self._on_skip_clicked)
        menu.append(self._skip_item)
        
        menu.append(Gtk.SeparatorMenuItem())
        
        # Show window
        show_item = Gtk.MenuItem(label="📋 Open Athan")
        show_item.connect('activate', self._on_show_clicked)
        menu.append(show_item)
        
        menu.append(Gtk.SeparatorMenuItem())
        
        # Quit
        quit_item = Gtk.MenuItem(label="❌ Quit")
        quit_item.connect('activate', self._on_quit_clicked)
        menu.append(quit_item)
        
        menu.show_all()
        return menu
    
    def _start_update_timer(self) -> None:
        """Start the periodic update timer."""
        self._update_timer_id = GLib.timeout_add_seconds(1, self._update_indicator)
    
    def _update_indicator(self) -> bool:
        """Update the indicator label and menu."""
        try:
            # Update prayer times in menu
            times = self._prayer_manager.get_today_times()
            if times:
                current = self._prayer_manager.get_current_prayer()
                next_info = self._prayer_manager.get_next_prayer()
                next_prayer = next_info[0] if next_info else None
                
                for prayer, item in self._prayer_items.items():
                    time_str = times.get(prayer, '--:--')
                    
                    # Add status indicator
                    if prayer == current:
                        label = f"● {prayer}: {time_str}"
                    elif prayer == next_prayer:
                        label = f"▶ {prayer}: {time_str}"
                    else:
                        label = f"   {prayer}: {time_str}"
                    
                    item.set_label(label)
                
                # Update next prayer info
                if next_info:
                    name, time_str, prayer_dt = next_info
                    self._next_info_item.set_label(f"Next: {name} at {time_str}")
                    
                    # Calculate countdown
                    location = self._prayer_manager.cache.get_location()
                    if location:
                        try:
                            tz = pytz.timezone(location['timezone'])
                            now = datetime.now(tz)
                            delta = prayer_dt - now
                            
                            if delta.total_seconds() > 0:
                                hours, remainder = divmod(int(delta.total_seconds()), 3600)
                                minutes, seconds = divmod(remainder, 60)
                                
                                if hours > 0:
                                    countdown = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
                                else:
                                    countdown = f"{minutes:02d}:{seconds:02d}"
                                
                                self._countdown_item.set_label(f"⏱ {countdown}")
                                
                                # Update panel label
                                self._indicator.set_label(f"{name} {countdown}", "")
                            else:
                                self._countdown_item.set_label("⏱ 00:00")
                                self._indicator.set_label(f"{name} now", "")
                        except:
                            pass
                else:
                    self._indicator.set_label("Athan", "")
            else:
                self._indicator.set_label("Athan", "")
                for item in self._prayer_items.values():
                    item.set_label("--:--")
            
        except Exception as e:
            logger.debug(f"Error updating indicator: {e}")
            self._indicator.set_label("Athan", "")
        
        return True
    
    def _on_stop_clicked(self, item: Gtk.MenuItem) -> None:
        """Handle stop click."""
        if self._on_stop:
            try:
                self._on_stop()
            except Exception as e:
                logger.error(f"Error stopping Athan from indicator: {e}", exc_info=True)
    
    def _on_skip_clicked(self, item: Gtk.MenuItem) -> None:
        """Handle skip toggle click."""
        if self._on_skip_toggle:
            is_skipped = self._on_skip_toggle()
            if is_skipped:
                self._skip_item.set_label("✓ Will Skip Next")
            else:
                self._skip_item.set_label("⏭ Skip Next")
    
    def _on_show_clicked(self, item: Gtk.MenuItem) -> None:
        """Handle show window click."""
        if self._on_show_window:
            self._on_show_window()
    
    def _on_quit_clicked(self, item: Gtk.MenuItem) -> None:
        """Handle quit click."""
        if self._on_quit:
            try:
                self._on_quit()
            except Exception as e:
                logger.error(f"Error quitting from indicator: {e}", exc_info=True)
    
    def refresh(self) -> None:
        """Refresh the indicator."""
        self._update_indicator()
    
    def update_skip_state(self, is_skipped: bool) -> None:
        """Update the skip button state."""
        if is_skipped:
            self._skip_item.set_label("✓ Will Skip Next")
        else:
            self._skip_item.set_label("⏭ Skip Next")
    
    def cleanup(self) -> None:
        """Clean up resources."""
        try:
            if self._update_timer_id:
                try:
                    GLib.source_remove(self._update_timer_id)
                except Exception:
                    pass
                self._update_timer_id = None
            
            logger.info("AthanIndicator cleaned up")
        except Exception as e:
            logger.error(f"Error cleaning up indicator: {e}", exc_info=True)
