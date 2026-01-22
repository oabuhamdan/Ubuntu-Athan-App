"""
Settings Dialog Module

Provides settings interface for:
- Location configuration (city/country with verification)
- Audio device and file selection
- UI preferences
- Auto-relaunch settings
"""

import os
import logging
import threading
from typing import Optional

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GLib

from ..config.settings import (
    AppSettings, LocationSettings, AudioSettings,
    AutoRelaunchSettings, UISettings
)
from ..calculation.aladhan_api import AladhanAPI, PrayerTimesManager
from ..audio.player import AudioPlayer

logger = logging.getLogger(__name__)


class SettingsDialog(Gtk.Dialog):
    """
    Settings dialog with multiple pages.
    """
    
    def __init__(self, parent: Gtk.Window, settings: AppSettings):
        super().__init__(
            title="Settings",
            parent=parent,
            flags=Gtk.DialogFlags.MODAL | Gtk.DialogFlags.DESTROY_WITH_PARENT
        )
        
        self.settings = settings
        self.parent_window = parent
        self._location_verified = False
        self._verified_info = None
        
        self.set_default_size(450, 500)
        self.add_button("Cancel", Gtk.ResponseType.CANCEL)
        self.save_btn = self.add_button("Save", Gtk.ResponseType.APPLY)
        
        self._setup_css()
        self._build_ui()
        self._load_settings()
        
        self.show_all()
    
    def _setup_css(self) -> None:
        """Set up CSS styling."""
        css = b"""
        .settings-page {
            background-color: #1a1a2e;
            padding: 16px;
        }
        
        .section-label {
            color: #e94560;
            font-size: 13px;
            font-weight: bold;
            margin-top: 12px;
            margin-bottom: 6px;
        }
        
        .settings-row {
            background-color: #16213e;
            border-radius: 8px;
            padding: 12px;
            margin-bottom: 6px;
        }
        
        .settings-label {
            color: #ffffff;
            font-size: 13px;
        }
        
        .settings-sublabel {
            color: #888888;
            font-size: 11px;
        }
        
        .coords-label {
            color: #00ff88;
            font-size: 12px;
            font-family: monospace;
        }
        
        entry, spinbutton {
            background-color: #0f3460;
            color: #ffffff;
            border: none;
            border-radius: 4px;
            padding: 8px;
            min-height: 20px;
        }
        
        entry:focus {
            border: 1px solid #e94560;
        }
        
        button.verify-button {
            background-color: #e94560;
            color: #ffffff;
            border: none;
            border-radius: 4px;
            padding: 8px 16px;
        }
        
        button.verify-button:hover {
            background-color: #ff6b81;
        }
        
        button.file-button {
            background-color: #0f3460;
            color: #ffffff;
            border: none;
            border-radius: 4px;
            padding: 8px 12px;
        }
        
        .verify-success {
            color: #00ff88;
            font-size: 12px;
        }
        
        .verify-error {
            color: #ff6b6b;
            font-size: 12px;
        }
        
        .verify-pending {
            color: #888888;
            font-size: 12px;
        }
        
        .location-info-box {
            background-color: #0a2a1e;
            border: 1px solid #00ff88;
            border-radius: 6px;
            padding: 10px;
            margin-top: 8px;
        }
        
        /* Compact switch styling */
        switch {
            min-width: 36px;
            min-height: 18px;
        }
        
        switch slider {
            min-width: 16px;
            min-height: 16px;
            border-radius: 8px;
        }
        
        combobox {
            background-color: #0f3460;
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
        """Build the settings UI."""
        content = self.get_content_area()
        content.set_spacing(0)
        
        notebook = Gtk.Notebook()
        
        notebook.append_page(
            self._build_location_page(),
            Gtk.Label(label="📍 Location")
        )
        
        notebook.append_page(
            self._build_audio_page(),
            Gtk.Label(label="🔊 Audio")
        )
        
        notebook.append_page(
            self._build_preferences_page(),
            Gtk.Label(label="⚙ Preferences")
        )
        
        content.pack_start(notebook, True, True, 0)
    
    def _build_location_page(self) -> Gtk.Widget:
        """Build the location settings page."""
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        page.get_style_context().add_class('settings-page')
        
        section_label = Gtk.Label(label="Enter Your Location")
        section_label.get_style_context().add_class('section-label')
        section_label.set_xalign(0)
        page.pack_start(section_label, False, False, 0)
        
        # City entry
        city_row = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        city_row.get_style_context().add_class('settings-row')
        
        city_label = Gtk.Label(label="City")
        city_label.get_style_context().add_class('settings-label')
        city_label.set_xalign(0)
        city_row.pack_start(city_label, False, False, 0)
        
        self.city_entry = Gtk.Entry()
        self.city_entry.set_placeholder_text("e.g., New York")
        self.city_entry.connect('changed', self._on_location_changed)
        city_row.pack_start(self.city_entry, False, False, 0)
        
        page.pack_start(city_row, False, False, 0)
        
        # Country entry
        country_row = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        country_row.get_style_context().add_class('settings-row')
        
        country_label = Gtk.Label(label="Country")
        country_label.get_style_context().add_class('settings-label')
        country_label.set_xalign(0)
        country_row.pack_start(country_label, False, False, 0)
        
        self.country_entry = Gtk.Entry()
        self.country_entry.set_placeholder_text("e.g., United States")
        self.country_entry.connect('changed', self._on_location_changed)
        country_row.pack_start(self.country_entry, False, False, 0)
        
        page.pack_start(country_row, False, False, 0)
        
        # Verify button row
        verify_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        verify_box.set_margin_top(8)
        
        self.verify_btn = Gtk.Button(label="🔍 Verify Location")
        self.verify_btn.get_style_context().add_class('verify-button')
        self.verify_btn.connect('clicked', self._on_verify_clicked)
        verify_box.pack_start(self.verify_btn, False, False, 0)
        
        self.verify_spinner = Gtk.Spinner()
        verify_box.pack_start(self.verify_spinner, False, False, 0)
        
        page.pack_start(verify_box, False, False, 0)
        
        # Status message
        self.verify_status = Gtk.Label(label="Enter city and country, then click Verify")
        self.verify_status.get_style_context().add_class('verify-pending')
        self.verify_status.set_xalign(0)
        self.verify_status.set_line_wrap(True)
        page.pack_start(self.verify_status, False, False, 4)
        
        # Verified location info box
        self.location_info_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.location_info_box.get_style_context().add_class('location-info-box')
        self.location_info_box.set_no_show_all(True)
        
        info_title = Gtk.Label(label="✓ Location Found:")
        info_title.get_style_context().add_class('verify-success')
        info_title.set_xalign(0)
        self.location_info_box.pack_start(info_title, False, False, 0)
        
        self.coords_label = Gtk.Label()
        self.coords_label.get_style_context().add_class('coords-label')
        self.coords_label.set_xalign(0)
        self.location_info_box.pack_start(self.coords_label, False, False, 0)
        
        self.timezone_label = Gtk.Label()
        self.timezone_label.get_style_context().add_class('settings-sublabel')
        self.timezone_label.set_xalign(0)
        self.location_info_box.pack_start(self.timezone_label, False, False, 0)
        
        self.method_label = Gtk.Label()
        self.method_label.get_style_context().add_class('settings-sublabel')
        self.method_label.set_xalign(0)
        self.location_info_box.pack_start(self.method_label, False, False, 0)
        
        # Confirm checkbox
        self.confirm_check = Gtk.CheckButton(label="Confirm: This location is correct")
        self.confirm_check.connect('toggled', self._on_confirm_toggled)
        self.location_info_box.pack_start(self.confirm_check, False, False, 4)
        
        page.pack_start(self.location_info_box, False, False, 0)
        
        return page
    
    def _build_audio_page(self) -> Gtk.Widget:
        """Build the audio settings page."""
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        page.get_style_context().add_class('settings-page')
        
        # Audio device
        section_label = Gtk.Label(label="Audio Output")
        section_label.get_style_context().add_class('section-label')
        section_label.set_xalign(0)
        page.pack_start(section_label, False, False, 0)
        
        device_row = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        device_row.get_style_context().add_class('settings-row')
        
        device_label = Gtk.Label(label="Output Device")
        device_label.get_style_context().add_class('settings-label')
        device_label.set_xalign(0)
        device_row.pack_start(device_label, False, False, 0)
        
        self.device_combo = Gtk.ComboBoxText()
        self.device_combo.append('', 'System Default')
        
        devices = AudioPlayer.get_audio_devices()
        for device in devices:
            self.device_combo.append(device.name, device.description)
        
        device_row.pack_start(self.device_combo, False, False, 0)
        page.pack_start(device_row, False, False, 0)
        
        # Athan file
        section_label = Gtk.Label(label="Athan Audio")
        section_label.get_style_context().add_class('section-label')
        section_label.set_xalign(0)
        page.pack_start(section_label, False, False, 0)
        
        file_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        file_row.get_style_context().add_class('settings-row')
        
        self.file_entry = Gtk.Entry()
        self.file_entry.set_placeholder_text("Default Athan")
        self.file_entry.set_editable(False)
        file_row.pack_start(self.file_entry, True, True, 0)
        
        browse_btn = Gtk.Button(label="Browse")
        browse_btn.get_style_context().add_class('file-button')
        browse_btn.connect('clicked', self._on_browse_audio)
        file_row.pack_end(browse_btn, False, False, 0)
        
        page.pack_start(file_row, False, False, 0)
        
        # Per-prayer enables
        section_label = Gtk.Label(label="Enable Athan For")
        section_label.get_style_context().add_class('section-label')
        section_label.set_xalign(0)
        page.pack_start(section_label, False, False, 0)
        
        prayers_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        prayers_box.get_style_context().add_class('settings-row')
        
        self.prayer_switches = {}
        for prayer in ['Fajr', 'Dhuhr', 'Asr', 'Maghrib', 'Isha']:
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            
            label = Gtk.Label(label=prayer)
            label.get_style_context().add_class('settings-label')
            label.set_xalign(0)
            row.pack_start(label, True, True, 0)
            
            switch = Gtk.Switch()
            switch.set_active(True)
            switch.set_valign(Gtk.Align.CENTER)
            row.pack_end(switch, False, False, 0)
            self.prayer_switches[prayer.lower()] = switch
            
            prayers_box.pack_start(row, False, False, 0)
        
        page.pack_start(prayers_box, False, False, 0)
        
        return page
    
    def _build_preferences_page(self) -> Gtk.Widget:
        """Build the preferences page."""
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        page.get_style_context().add_class('settings-page')
        
        # Display section
        section_label = Gtk.Label(label="Display")
        section_label.get_style_context().add_class('section-label')
        section_label.set_xalign(0)
        page.pack_start(section_label, False, False, 0)
        
        prefs_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        prefs_box.get_style_context().add_class('settings-row')
        
        # 24-hour time
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        label = Gtk.Label(label="Use 24-hour time")
        label.get_style_context().add_class('settings-label')
        label.set_xalign(0)
        row.pack_start(label, True, True, 0)
        self.time_24h_switch = Gtk.Switch()
        self.time_24h_switch.set_valign(Gtk.Align.CENTER)
        row.pack_end(self.time_24h_switch, False, False, 0)
        prefs_box.pack_start(row, False, False, 0)
        
        # Minimize to tray
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        label = Gtk.Label(label="Minimize to tray on close")
        label.get_style_context().add_class('settings-label')
        label.set_xalign(0)
        row.pack_start(label, True, True, 0)
        self.tray_switch = Gtk.Switch()
        self.tray_switch.set_valign(Gtk.Align.CENTER)
        row.pack_end(self.tray_switch, False, False, 0)
        prefs_box.pack_start(row, False, False, 0)
        
        page.pack_start(prefs_box, False, False, 0)
        
        # Auto-relaunch section
        section_label = Gtk.Label(label="Auto-Relaunch")
        section_label.get_style_context().add_class('section-label')
        section_label.set_xalign(0)
        page.pack_start(section_label, False, False, 0)
        
        relaunch_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        relaunch_box.get_style_context().add_class('settings-row')
        
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        label = Gtk.Label(label="Auto-relaunch when closed")
        label.get_style_context().add_class('settings-label')
        label.set_xalign(0)
        row.pack_start(label, True, True, 0)
        self.relaunch_switch = Gtk.Switch()
        self.relaunch_switch.set_valign(Gtk.Align.CENTER)
        row.pack_end(self.relaunch_switch, False, False, 0)
        relaunch_box.pack_start(row, False, False, 0)
        
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        label = Gtk.Label(label="Delay (minutes)")
        label.get_style_context().add_class('settings-label')
        label.set_xalign(0)
        row.pack_start(label, True, True, 0)
        self.relaunch_delay_spin = Gtk.SpinButton.new_with_range(1, 60, 1)
        self.relaunch_delay_spin.set_valign(Gtk.Align.CENTER)
        row.pack_end(self.relaunch_delay_spin, False, False, 0)
        relaunch_box.pack_start(row, False, False, 0)
        
        page.pack_start(relaunch_box, False, False, 0)
        
        return page
    
    def _on_location_changed(self, entry: Gtk.Entry) -> None:
        """Handle location entry changes."""
        self._location_verified = False
        self._verified_info = None
        self.location_info_box.hide()
        self.confirm_check.set_active(False)
        self.verify_status.set_text("Enter city and country, then click Verify")
        self.verify_status.get_style_context().remove_class('verify-success')
        self.verify_status.get_style_context().remove_class('verify-error')
        self.verify_status.get_style_context().add_class('verify-pending')
    
    def _on_verify_clicked(self, button: Gtk.Button) -> None:
        """Handle verify button click."""
        city = self.city_entry.get_text().strip()
        country = self.country_entry.get_text().strip()
        
        if not city or not country:
            self.verify_status.set_text("⚠ Please enter both city and country")
            self.verify_status.get_style_context().remove_class('verify-success')
            self.verify_status.get_style_context().remove_class('verify-pending')
            self.verify_status.get_style_context().add_class('verify-error')
            return
        
        self.verify_btn.set_sensitive(False)
        self.verify_spinner.start()
        self.verify_status.set_text("Searching...")
        self.verify_status.get_style_context().remove_class('verify-error')
        self.verify_status.get_style_context().add_class('verify-pending')
        
        def verify():
            try:
                pm = PrayerTimesManager()
                result = pm.validate_location(city, country)
                GLib.idle_add(lambda: self._on_verify_complete(result))
            except Exception as e:
                logger.error(f"Verification failed: {e}")
                error_result = (False, f"Error: {str(e)}", None)
                GLib.idle_add(lambda: self._on_verify_complete(error_result))
        
        thread = threading.Thread(target=verify, daemon=True)
        thread.start()
    
    def _on_verify_complete(self, result: tuple) -> bool:
        """Handle verification completion."""
        self.verify_btn.set_sensitive(True)
        self.verify_spinner.stop()
        
        success, message, info = result
        
        if success and info:
            self._verified_info = info
            
            self.verify_status.set_text("")
            self.verify_status.get_style_context().remove_class('verify-error')
            self.verify_status.get_style_context().remove_class('verify-pending')
            
            # Show location info with real coordinates
            lat = info.get('latitude', 0)
            lon = info.get('longitude', 0)
            tz = info.get('timezone', 'Unknown')
            method = info.get('method_name', 'ISNA')
            display_name = info.get('display_name', f"{info.get('city', '')}, {info.get('country', '')}")
            
            self.coords_label.set_text(f"📍 {display_name}\n\nCoordinates: {lat:.4f}°, {lon:.4f}°")
            self.timezone_label.set_text(f"Timezone: {tz}")
            self.method_label.set_text(f"Calculation: {method}")
            
            self.confirm_check.set_active(False)
            
            # Must show each child explicitly since set_no_show_all(True) is set
            for child in self.location_info_box.get_children():
                child.show()
            self.location_info_box.show()
        else:
            self.verify_status.set_text(f"✗ {message}")
            self.verify_status.get_style_context().remove_class('verify-success')
            self.verify_status.get_style_context().remove_class('verify-pending')
            self.verify_status.get_style_context().add_class('verify-error')
            self.location_info_box.hide()
        
        return False  # Don't repeat
    
    def _on_confirm_toggled(self, check: Gtk.CheckButton) -> None:
        """Handle confirm checkbox toggle."""
        self._location_verified = check.get_active() and self._verified_info is not None
    
    def _on_browse_audio(self, button: Gtk.Button) -> None:
        """Handle audio file browse."""
        dialog = Gtk.FileChooserDialog(
            title="Select Athan Audio",
            parent=self,
            action=Gtk.FileChooserAction.OPEN
        )
        dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
        dialog.add_button("Select", Gtk.ResponseType.OK)
        
        audio_filter = Gtk.FileFilter()
        audio_filter.set_name("Audio Files")
        audio_filter.add_pattern("*.mp3")
        audio_filter.add_pattern("*.wav")
        audio_filter.add_pattern("*.ogg")
        dialog.add_filter(audio_filter)
        
        if dialog.run() == Gtk.ResponseType.OK:
            self.file_entry.set_text(dialog.get_filename())
        
        dialog.destroy()
    
    def _load_settings(self) -> None:
        """Load current settings into UI."""
        # Location
        loc = self.settings.location
        self.city_entry.set_text(loc.city_name or '')
        self.country_entry.set_text(loc.country or '')
        
        if loc.city_name and loc.country:
            self._location_verified = True
            self._verified_info = {
                'city': loc.city_name,
                'country': loc.country,
                'latitude': loc.latitude,
                'longitude': loc.longitude,
                'timezone': loc.timezone,
            }
            self.verify_status.set_text("✓ Location previously saved")
            self.verify_status.get_style_context().remove_class('verify-pending')
            self.verify_status.get_style_context().add_class('verify-success')
        
        # Audio
        audio = self.settings.audio
        self.device_combo.set_active_id(audio.device_name or '')
        self.file_entry.set_text(audio.athan_file or '')
        
        self.prayer_switches['fajr'].set_active(audio.fajr_enabled)
        self.prayer_switches['dhuhr'].set_active(audio.dhuhr_enabled)
        self.prayer_switches['asr'].set_active(audio.asr_enabled)
        self.prayer_switches['maghrib'].set_active(audio.maghrib_enabled)
        self.prayer_switches['isha'].set_active(audio.isha_enabled)
        
        # UI
        ui = self.settings.ui
        self.time_24h_switch.set_active(ui.use_24_hour)
        self.tray_switch.set_active(ui.minimize_to_tray)
        
        # Auto-relaunch
        relaunch = self.settings.auto_relaunch
        self.relaunch_switch.set_active(relaunch.enabled)
        self.relaunch_delay_spin.set_value(relaunch.delay_minutes)
    
    def _save_settings(self) -> bool:
        """Save UI values to settings. Returns True if location changed."""
        location_changed = False
        
        # Location - save if verified
        if self._location_verified and self._verified_info:
            old_city = self.settings.location.city_name
            old_country = self.settings.location.country
            
            new_city = self._verified_info.get('city', '')
            new_country = self._verified_info.get('country', '')
            new_lat = self._verified_info.get('latitude', 0)
            new_lon = self._verified_info.get('longitude', 0)
            new_tz = self._verified_info.get('timezone', 'UTC')
            
            if old_city != new_city or old_country != new_country:
                location_changed = True
            
            # Save to app settings
            self.settings.location = LocationSettings(
                latitude=new_lat,
                longitude=new_lon,
                timezone=new_tz,
                city_name=new_city,
                country=new_country,
            )
            
            logger.info(f"Location saved: {new_city}, {new_country} ({new_lat}, {new_lon})")
        
        # Audio
        device_id = self.device_combo.get_active_id()
        self.settings.audio = AudioSettings(
            device_name=device_id if device_id else None,
            athan_file=self.file_entry.get_text(),
            fajr_enabled=self.prayer_switches['fajr'].get_active(),
            dhuhr_enabled=self.prayer_switches['dhuhr'].get_active(),
            asr_enabled=self.prayer_switches['asr'].get_active(),
            maghrib_enabled=self.prayer_switches['maghrib'].get_active(),
            isha_enabled=self.prayer_switches['isha'].get_active(),
        )
        
        # UI
        self.settings.ui = UISettings(
            use_24_hour=self.time_24h_switch.get_active(),
            minimize_to_tray=self.tray_switch.get_active(),
        )
        
        # Auto-relaunch
        self.settings.auto_relaunch = AutoRelaunchSettings(
            enabled=self.relaunch_switch.get_active(),
            delay_minutes=int(self.relaunch_delay_spin.get_value()),
        )
        
        # Persist to disk
        self.settings.save()
        logger.info("Settings saved to disk")
        return location_changed
    
    def do_response(self, response_id: int) -> None:
        """Handle dialog response."""
        if response_id == Gtk.ResponseType.APPLY:
            location_changed = self._save_settings()
            
            # Refresh main window if location changed
            if location_changed:
                loc = self.settings.location
                # Clear cache and fetch new times with coordinates
                if hasattr(self.parent_window, 'prayer_manager') and self.parent_window.prayer_manager:
                    self.parent_window.prayer_manager.cache.clear()
                    self.parent_window.prayer_manager.set_location(
                        loc.city_name, 
                        loc.country,
                        latitude=loc.latitude,
                        longitude=loc.longitude
                    )
                if hasattr(self.parent_window, 'refresh'):
                    self.parent_window.refresh()
                if hasattr(self.parent_window, '_schedule_next_athan'):
                    self.parent_window._schedule_next_athan()
