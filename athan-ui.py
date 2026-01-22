#!/usr/bin/env python3
"""
Athan App - Prayer Times Application

A simple, integrated prayer times application with:
- Prayer times from Aladhan.com API
- System tray indicator with countdown
- Athan playback at prayer times
- Auto-relaunch when closed
"""

import os
import sys
import logging
import signal
import subprocess

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib, Gio

# Add package to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from athan import __app_name__, __version__, __app_id__
from athan.config.settings import get_settings
from athan.calculation.aladhan_api import PrayerTimesManager
from athan.ui.main_window import MainWindow
from athan.ui.indicator import AthanIndicator
from athan.utils.helpers import setup_logging, get_data_dir

# Import AppIndicator for cleanup
try:
    gi.require_version('AyatanaAppIndicator3', '0.1')
    from gi.repository import AyatanaAppIndicator3 as AppIndicator
except ImportError:
    gi.require_version('AppIndicator3', '0.1')
    from gi.repository import AppIndicator3 as AppIndicator

logger = logging.getLogger(__name__)


class AthanApplication(Gtk.Application):
    """
    Main GTK Application class.
    
    Manages:
    - Main window
    - System tray indicator
    - Prayer time scheduling
    - Auto-relaunch on quit
    """
    
    def __init__(self):
        super().__init__(
            application_id=__app_id__,
            flags=Gio.ApplicationFlags.FLAGS_NONE
        )
        
        self.window = None
        self.indicator = None
        self.settings = get_settings()
        self.prayer_manager = PrayerTimesManager()
        self._force_quit = False
        self._quit_complete = False
        
        self.connect('activate', self.on_activate)
        self.connect('shutdown', self.on_shutdown)
    
    def on_activate(self, app):
        """Handle application activation."""
        if self.window is None:
            # Try to load prayer times
            loc = self.settings.location
            if loc.city_name and loc.country:
                self.prayer_manager.set_location(loc.city_name, loc.country)
            
            # Create main window
            self.window = MainWindow(self)
            
            # Create indicator
            self.indicator = AthanIndicator(
                prayer_manager=self.prayer_manager,
                on_show_window=self._show_window,
                on_quit=self._quit_app,
                on_stop=self._stop_athan,
                on_skip_toggle=self._toggle_skip,
            )
        
        # Show window
        self.window.show_all()
        self.window.present()
    
    def on_shutdown(self, app):
        """Handle application shutdown."""
        logger.info("Application shutting down")
        
        # If force quit, skip cleanup to avoid blocking
        if hasattr(self, '_force_quit') and self._force_quit:
            logger.info("Force quit - skipping cleanup")
            return
        
        # Do minimal cleanup quickly without blocking
        try:
            # Stop any playing audio first (non-blocking, don't wait)
            if self.window and hasattr(self.window, 'player'):
                try:
                    # Just signal stop, don't wait
                    self.window.player.stop()
                except Exception:
                    pass
            
            # Minimal cleanup - don't wait for anything
            # Cleanup indicator quickly
            if self.indicator:
                try:
                    # Just remove timer, don't wait
                    if hasattr(self.indicator, '_update_timer_id') and self.indicator._update_timer_id:
                        try:
                            GLib.source_remove(self.indicator._update_timer_id)
                        except:
                            pass
                except Exception:
                    pass
            
            # Cleanup window timers quickly
            if self.window:
                try:
                    # Just remove timers, don't wait
                    if hasattr(self.window, '_countdown_timer_id') and self.window._countdown_timer_id:
                        try:
                            GLib.source_remove(self.window._countdown_timer_id)
                        except:
                            pass
                    if hasattr(self.window, '_athan_timer_id') and self.window._athan_timer_id:
                        try:
                            GLib.source_remove(self.window._athan_timer_id)
                        except:
                            pass
                except Exception:
                    pass
            
            # Schedule relaunch if enabled (non-blocking, in background thread)
            if self.settings.auto_relaunch.enabled:
                delay = self.settings.auto_relaunch.delay_minutes
                try:
                    # Schedule in background thread to avoid blocking
                    import threading
                    def schedule():
                        try:
                            self._schedule_relaunch(delay)
                        except:
                            pass
                    thread = threading.Thread(target=schedule, daemon=True)
                    thread.start()
                except Exception:
                    pass
        except Exception as e:
            logger.error(f"Error during shutdown: {e}", exc_info=True)
    
    def _show_window(self):
        """Show the main window."""
        if self.window:
            self.window.show_all()
            self.window.present()
    
    def _quit_app(self):
        """Quit the application."""
        
        # Set flag for shutdown handler (if it ever gets called)
        self._force_quit = True
        
        # Use immediate force exit - normal quit() is clearly blocking
        # Schedule a delayed force exit in case something needs to finish
        import threading
        import time
        import os
        
        def force_quit_immediately():
            try:
                time.sleep(0.1)  # Very short delay to let menu close
            except Exception:
                pass  # Ignore any errors - we're about to exit anyway
            finally:
                # Always exit, even if there was an error
                try:
                    os._exit(0)
                except Exception:
                    pass  # If os._exit fails, there's nothing we can do
        
        # Start force quit thread immediately
        force_thread = threading.Thread(target=force_quit_immediately, daemon=True)
        force_thread.start()
        
        # Also try to quit via GTK - but don't wait for it
        try:
            # Schedule quit in next event loop iteration
            def do_quit_now():
                try:
                    self.quit()
                except:
                    pass
                return False
            
            GLib.idle_add(do_quit_now, priority=GLib.PRIORITY_HIGH)
        except:
            pass
        
        # Return immediately - force thread will kill us in 100ms
        return
    
    def _stop_athan(self):
        """Stop playing Athan."""
        if self.window:
            self.window.player.stop()
    
    def _toggle_skip(self) -> bool:
        """Toggle skip next Athan."""
        if self.window:
            self.window._skip_next_athan = not self.window._skip_next_athan
            self.window._update_skip_button()
            # Update indicator
            if self.indicator:
                self.indicator.update_skip_state(self.window._skip_next_athan)
            return self.window._skip_next_athan
        return False
    
    def _schedule_relaunch(self, delay_minutes: int):
        """Schedule app relaunch after delay."""
        logger.info(f"Scheduling relaunch in {delay_minutes} minutes")
        
        # Use 'at' command or systemd timer for reliable scheduling
        # For simplicity, we'll create a background process
        script_path = os.path.abspath(__file__)
        
        # Create a simple relaunch script
        relaunch_cmd = f'''
        sleep {delay_minutes * 60}
        exec {sys.executable} "{script_path}"
        '''
        
        try:
            subprocess.Popen(
                ['bash', '-c', relaunch_cmd],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True
            )
            logger.info(f"Relaunch scheduled")
        except Exception as e:
            logger.error(f"Failed to schedule relaunch: {e}")
    
    def _get_icon_path(self) -> str:
        """Get the application icon path."""
        locations = [
            '/usr/share/icons/hicolor/scalable/apps/athan-app.svg',
            os.path.join(os.path.dirname(__file__), 'data', 'icons', 'athan-app.svg'),
        ]
        
        for path in locations:
            if os.path.exists(path):
                return path
        
        return 'appointment-soon'


def main():
    """Main entry point."""
    # Set up logging
    log_file = os.path.join(get_data_dir(), 'logs', 'athan.log')
    os.makedirs(os.path.dirname(log_file), exist_ok=True)
    setup_logging('athan', logging.INFO, log_file)
    
    logger.info(f"Starting {__app_name__} v{__version__}")
    
    # Create and run application
    app = AthanApplication()
    
    # Handle signals
    GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGINT, app.quit)
    GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGTERM, app.quit)
    
    return app.run(sys.argv)


if __name__ == '__main__':
    sys.exit(main())
