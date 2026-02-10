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
from ..calculation.prayer_times import (
    CalculationMethod, Madhab, HighLatitudeRule, Shafaq, CalculationSettings
)
from ..calculation.aladhan_api import AladhanAPI, PrayerTimesManager
from ..audio.player import AudioPlayer

logger = logging.getLogger(__name__)

# Constants
DEFAULT_ANGLE = 15.0  # Default angle for Fajr/Isha in degrees


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
            Gtk.Label(label="Location")
        )
        
        notebook.append_page(
            self._build_calculation_page(),
            Gtk.Label(label="Calculation")
        )
        
        notebook.append_page(
            self._build_audio_page(),
            Gtk.Label(label="Audio")
        )
        
        notebook.append_page(
            self._build_preferences_page(),
            Gtk.Label(label="Preferences")
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
    
    def _build_calculation_page(self) -> Gtk.Widget:
        """Build the calculation method settings page."""
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        page.get_style_context().add_class('settings-page')
        
        # Calculation Method section
        section_label = Gtk.Label(label="Calculation Method")
        section_label.get_style_context().add_class('section-label')
        section_label.set_xalign(0)
        page.pack_start(section_label, False, False, 0)
        
        method_row = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        method_row.get_style_context().add_class('settings-row')
        
        method_label = Gtk.Label(label="Prayer Time Calculation Method")
        method_label.get_style_context().add_class('settings-label')
        method_label.set_xalign(0)
        method_row.pack_start(method_label, False, False, 0)
        
        sublabel = Gtk.Label(label="Different regions use different calculation standards")
        sublabel.get_style_context().add_class('settings-sublabel')
        sublabel.set_xalign(0)
        sublabel.set_line_wrap(True)
        method_row.pack_start(sublabel, False, False, 0)
        
        self.method_combo = Gtk.ComboBoxText()
        # Add all calculation methods with descriptive names
        methods = [
            (CalculationMethod.ISNA, "ISNA - Islamic Society of North America"),
            (CalculationMethod.MWL, "MWL - Muslim World League"),
            (CalculationMethod.EGYPT, "Egyptian General Authority of Survey"),
            (CalculationMethod.KARACHI, "University of Islamic Sciences, Karachi"),
            (CalculationMethod.MAKKAH, "Umm al-Qura University, Makkah"),
            (CalculationMethod.DUBAI, "Dubai"),
            (CalculationMethod.KUWAIT, "Kuwait"),
            (CalculationMethod.QATAR, "Qatar"),
            (CalculationMethod.SINGAPORE, "Majlis Ugama Islam Singapura, Singapore"),
            (CalculationMethod.TEHRAN, "Institute of Geophysics, University of Tehran"),
            (CalculationMethod.TURKEY, "Diyanet İşleri Başkanlığı, Turkey"),
            (CalculationMethod.ALGERIA, "Algeria"),
            (CalculationMethod.FRANCE, "Union Organization Islamic de France"),
            (CalculationMethod.JAKIM, "Department of Islamic Development Malaysia"),
            (CalculationMethod.KEMENAG, "Indonesian Ministry of Religious Affairs"),
            (CalculationMethod.MOROCCO, "Morocco"),
            (CalculationMethod.TUNISIA, "Tunisia"),
            (CalculationMethod.JORDAN, "Ministry of Awqaf, Jordan"),
            (CalculationMethod.RUSSIA, "Spiritual Administration of Muslims of Russia"),
            (CalculationMethod.MOONSIGHTING, "Moonsighting Committee Worldwide"),
            (CalculationMethod.PORTUGAL, "Comunidade Islamica de Lisboa"),
        ]
        
        for method, description in methods:
            self.method_combo.append(method.value, description)
        
        method_row.pack_start(self.method_combo, False, False, 0)
        page.pack_start(method_row, False, False, 0)
        
        # Madhab (Asr calculation) section
        section_label = Gtk.Label(label="Asr Calculation")
        section_label.get_style_context().add_class('section-label')
        section_label.set_xalign(0)
        page.pack_start(section_label, False, False, 0)
        
        madhab_row = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        madhab_row.get_style_context().add_class('settings-row')
        
        madhab_label = Gtk.Label(label="Juristic Method (Madhab)")
        madhab_label.get_style_context().add_class('settings-label')
        madhab_label.set_xalign(0)
        madhab_row.pack_start(madhab_label, False, False, 0)
        
        sublabel = Gtk.Label(label="Shafi: Asr when shadow = object length\nHanafi: Asr when shadow = 2x object length")
        sublabel.get_style_context().add_class('settings-sublabel')
        sublabel.set_xalign(0)
        sublabel.set_line_wrap(True)
        madhab_row.pack_start(sublabel, False, False, 0)
        
        self.madhab_combo = Gtk.ComboBoxText()
        self.madhab_combo.append(Madhab.SHAFI.value, "Shafi, Maliki, Hanbali")
        self.madhab_combo.append(Madhab.HANAFI.value, "Hanafi")
        madhab_row.pack_start(self.madhab_combo, False, False, 0)
        
        page.pack_start(madhab_row, False, False, 0)
        
        # High Latitude Rule section
        section_label = Gtk.Label(label="High Latitude Adjustment")
        section_label.get_style_context().add_class('section-label')
        section_label.set_xalign(0)
        page.pack_start(section_label, False, False, 0)
        
        high_lat_row = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        high_lat_row.get_style_context().add_class('settings-row')
        
        high_lat_label = Gtk.Label(label="Adjustment for High Latitudes")
        high_lat_label.get_style_context().add_class('settings-label')
        high_lat_label.set_xalign(0)
        high_lat_row.pack_start(high_lat_label, False, False, 0)
        
        sublabel = Gtk.Label(label="Used for locations where normal calculations don't work")
        sublabel.get_style_context().add_class('settings-sublabel')
        sublabel.set_xalign(0)
        sublabel.set_line_wrap(True)
        high_lat_row.pack_start(sublabel, False, False, 0)
        
        self.high_lat_combo = Gtk.ComboBoxText()
        self.high_lat_combo.append(HighLatitudeRule.MIDDLE_OF_NIGHT.value, "Middle of the Night")
        self.high_lat_combo.append(HighLatitudeRule.SEVENTH_OF_NIGHT.value, "Seventh of the Night")
        self.high_lat_combo.append(HighLatitudeRule.TWILIGHT_ANGLE.value, "Twilight Angle")
        self.high_lat_combo.append(HighLatitudeRule.NONE.value, "None")
        high_lat_row.pack_start(self.high_lat_combo, False, False, 0)
        
        page.pack_start(high_lat_row, False, False, 0)
        
        # Custom Angles section
        section_label = Gtk.Label(label="Custom Angles (Optional)")
        section_label.get_style_context().add_class('section-label')
        section_label.set_xalign(0)
        page.pack_start(section_label, False, False, 0)
        
        angles_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        angles_box.get_style_context().add_class('settings-row')
        
        sublabel = Gtk.Label(label="Override default angles from calculation method")
        sublabel.get_style_context().add_class('settings-sublabel')
        sublabel.set_xalign(0)
        sublabel.set_line_wrap(True)
        angles_box.pack_start(sublabel, False, False, 0)
        
        # Fajr angle
        fajr_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        fajr_label = Gtk.Label(label="Fajr Angle (degrees)")
        fajr_label.get_style_context().add_class('settings-label')
        fajr_label.set_xalign(0)
        fajr_row.pack_start(fajr_label, True, True, 0)
        
        self.fajr_angle_spin = Gtk.SpinButton.new_with_range(10.0, 25.0, 0.1)
        self.fajr_angle_spin.set_digits(1)
        self.fajr_angle_spin.set_valign(Gtk.Align.CENTER)
        self.fajr_angle_spin.set_tooltip_text("Custom Fajr angle in degrees (10-25)")
        fajr_label.set_mnemonic_widget(self.fajr_angle_spin)
        fajr_row.pack_end(self.fajr_angle_spin, False, False, 0)
        
        self.fajr_angle_check = Gtk.CheckButton(label="Use custom")
        self.fajr_angle_check.set_valign(Gtk.Align.CENTER)
        self.fajr_angle_check.connect('toggled', lambda c: self.fajr_angle_spin.set_sensitive(c.get_active()))
        fajr_row.pack_end(self.fajr_angle_check, False, False, 0)
        
        angles_box.pack_start(fajr_row, False, False, 0)
        
        # Isha angle
        isha_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        isha_label = Gtk.Label(label="Isha Angle (degrees)")
        isha_label.get_style_context().add_class('settings-label')
        isha_label.set_xalign(0)
        isha_row.pack_start(isha_label, True, True, 0)
        
        self.isha_angle_spin = Gtk.SpinButton.new_with_range(10.0, 25.0, 0.1)
        self.isha_angle_spin.set_digits(1)
        self.isha_angle_spin.set_valign(Gtk.Align.CENTER)
        self.isha_angle_spin.set_tooltip_text("Custom Isha angle in degrees (10-25)")
        isha_label.set_mnemonic_widget(self.isha_angle_spin)
        isha_row.pack_end(self.isha_angle_spin, False, False, 0)
        
        self.isha_angle_check = Gtk.CheckButton(label="Use custom")
        self.isha_angle_check.set_valign(Gtk.Align.CENTER)
        self.isha_angle_check.connect('toggled', lambda c: self.isha_angle_spin.set_sensitive(c.get_active()))
        isha_row.pack_end(self.isha_angle_check, False, False, 0)
        
        angles_box.pack_start(isha_row, False, False, 0)
        
        page.pack_start(angles_box, False, False, 0)
        
        # Time Adjustments section
        section_label = Gtk.Label(label="Time Adjustments (Minutes)")
        section_label.get_style_context().add_class('section-label')
        section_label.set_xalign(0)
        page.pack_start(section_label, False, False, 0)
        
        adjustments_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        adjustments_box.get_style_context().add_class('settings-row')
        
        sublabel = Gtk.Label(label="Fine-tune prayer times by adding or subtracting minutes")
        sublabel.get_style_context().add_class('settings-sublabel')
        sublabel.set_xalign(0)
        sublabel.set_line_wrap(True)
        adjustments_box.pack_start(sublabel, False, False, 0)
        
        self.adjustment_spins = {}
        for prayer in ['Fajr', 'Sunrise', 'Dhuhr', 'Asr', 'Maghrib', 'Isha']:
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            
            label = Gtk.Label(label=f"{prayer} adjustment")
            label.get_style_context().add_class('settings-label')
            label.set_xalign(0)
            label.set_width_chars(10)
            row.pack_start(label, False, False, 0)
            
            spin = Gtk.SpinButton.new_with_range(-30, 30, 1)
            spin.set_valign(Gtk.Align.CENTER)
            spin.set_width_chars(5)
            spin.set_tooltip_text(f"Adjust {prayer} time by minutes (-30 to +30)")
            label.set_mnemonic_widget(spin)
            row.pack_end(spin, False, False, 0)
            
            self.adjustment_spins[prayer.lower()] = spin
            adjustments_box.pack_start(row, False, False, 0)
        
        page.pack_start(adjustments_box, False, False, 0)
        
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
        
        # Calculation settings
        calc = self.settings.calculation
        self.method_combo.set_active_id(calc.method.value)
        self.madhab_combo.set_active_id(calc.madhab.value)
        self.high_lat_combo.set_active_id(calc.high_latitude_rule.value)
        
        # Custom angles
        if calc.fajr_angle is not None:
            self.fajr_angle_check.set_active(True)
            self.fajr_angle_spin.set_value(calc.fajr_angle)
            self.fajr_angle_spin.set_sensitive(True)
        else:
            self.fajr_angle_check.set_active(False)
            self.fajr_angle_spin.set_value(DEFAULT_ANGLE)
            self.fajr_angle_spin.set_sensitive(False)
        
        if calc.isha_angle is not None:
            self.isha_angle_check.set_active(True)
            self.isha_angle_spin.set_value(calc.isha_angle)
            self.isha_angle_spin.set_sensitive(True)
        else:
            self.isha_angle_check.set_active(False)
            self.isha_angle_spin.set_value(DEFAULT_ANGLE)
            self.isha_angle_spin.set_sensitive(False)
        
        # Time adjustments
        self.adjustment_spins['fajr'].set_value(calc.fajr_adjustment)
        self.adjustment_spins['sunrise'].set_value(calc.sunrise_adjustment)
        self.adjustment_spins['dhuhr'].set_value(calc.dhuhr_adjustment)
        self.adjustment_spins['asr'].set_value(calc.asr_adjustment)
        self.adjustment_spins['maghrib'].set_value(calc.maghrib_adjustment)
        self.adjustment_spins['isha'].set_value(calc.isha_adjustment)
        
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
        """Save UI values to settings. Returns True if location or calculation changed."""
        location_changed = False
        calculation_changed = False
        
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
        
        # Calculation settings
        old_calc = self.settings.calculation
        new_method = CalculationMethod(self.method_combo.get_active_id())
        new_madhab = Madhab(self.madhab_combo.get_active_id())
        new_high_lat = HighLatitudeRule(self.high_lat_combo.get_active_id())
        
        # Check if calculation settings changed
        if (old_calc.method != new_method or 
            old_calc.madhab != new_madhab or 
            old_calc.high_latitude_rule != new_high_lat):
            calculation_changed = True
        
        # Custom angles
        fajr_angle = self.fajr_angle_spin.get_value() if self.fajr_angle_check.get_active() else None
        isha_angle = self.isha_angle_spin.get_value() if self.isha_angle_check.get_active() else None
        
        if old_calc.fajr_angle != fajr_angle or old_calc.isha_angle != isha_angle:
            calculation_changed = True
        
        # Time adjustments
        adjustments = {
            'fajr': int(self.adjustment_spins['fajr'].get_value()),
            'sunrise': int(self.adjustment_spins['sunrise'].get_value()),
            'dhuhr': int(self.adjustment_spins['dhuhr'].get_value()),
            'asr': int(self.adjustment_spins['asr'].get_value()),
            'maghrib': int(self.adjustment_spins['maghrib'].get_value()),
            'isha': int(self.adjustment_spins['isha'].get_value()),
        }
        
        if (old_calc.fajr_adjustment != adjustments['fajr'] or
            old_calc.sunrise_adjustment != adjustments['sunrise'] or
            old_calc.dhuhr_adjustment != adjustments['dhuhr'] or
            old_calc.asr_adjustment != adjustments['asr'] or
            old_calc.maghrib_adjustment != adjustments['maghrib'] or
            old_calc.isha_adjustment != adjustments['isha']):
            calculation_changed = True
        
        # Save calculation settings
        self.settings.calculation = CalculationSettings(
            method=new_method,
            madhab=new_madhab,
            high_latitude_rule=new_high_lat,
            polar_circle_resolution=old_calc.polar_circle_resolution,
            shafaq=old_calc.shafaq,
            fajr_angle=fajr_angle,
            isha_angle=isha_angle,
            fajr_adjustment=adjustments['fajr'],
            sunrise_adjustment=adjustments['sunrise'],
            dhuhr_adjustment=adjustments['dhuhr'],
            asr_adjustment=adjustments['asr'],
            maghrib_adjustment=adjustments['maghrib'],
            isha_adjustment=adjustments['isha'],
        )
        
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
        return location_changed or calculation_changed
    
    def do_response(self, response_id: int) -> None:
        """Handle dialog response."""
        if response_id == Gtk.ResponseType.APPLY:
            settings_changed = self._save_settings()
            
            # Refresh main window if location or calculation changed
            if settings_changed:
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
