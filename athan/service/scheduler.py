"""
Athan Scheduler Module

Handles scheduling of Athan playback:
- Calculates prayer times daily
- Schedules timers for each prayer
- Handles system sleep/wake events
- Triggers Athan playback at correct times
"""

import logging
import threading
from datetime import datetime, timedelta
from typing import Optional, Callable, Dict, List
import time

from gi.repository import GLib

from ..calculation.prayer_times import (
    PrayerTimeCalculator, Prayer, PrayerTime, get_prayer_name
)
from ..config.settings import AppSettings

logger = logging.getLogger(__name__)


class AthanScheduler:
    """
    Manages Athan scheduling and timing.
    
    Features:
    - Efficient timer-based scheduling (no polling)
    - Automatic reschedule after system resume
    - Per-prayer enable/disable
    - Skip next Athan functionality
    - Accurate to the minute
    """
    
    # Main Athan prayers (excluding Sunrise)
    ATHAN_PRAYERS = [Prayer.FAJR, Prayer.DHUHR, Prayer.ASR, Prayer.MAGHRIB, Prayer.ISHA]
    
    def __init__(
        self,
        settings: AppSettings,
        on_athan_trigger: Callable[[Prayer, datetime], None],
        on_times_updated: Optional[Callable[[Dict[Prayer, datetime]], None]] = None
    ):
        """
        Initialize the scheduler.
        
        Args:
            settings: Application settings
            on_athan_trigger: Callback when Athan should play
            on_times_updated: Callback when prayer times are recalculated
        """
        self._settings = settings
        self._on_athan_trigger = on_athan_trigger
        self._on_times_updated = on_times_updated
        
        self._calculator: Optional[PrayerTimeCalculator] = None
        self._current_times: Dict[Prayer, datetime] = {}
        self._timer_ids: Dict[Prayer, int] = {}
        self._lock = threading.Lock()
        self._running = False
        
        # Daily recalculation timer
        self._daily_timer_id: Optional[int] = None
        
        # Monitor for system resume
        self._last_check_time = datetime.now()
        self._resume_check_timer_id: Optional[int] = None
        
        logger.info("AthanScheduler initialized")
    
    def start(self) -> bool:
        """
        Start the scheduler.
        
        Returns:
            True if started successfully
        """
        with self._lock:
            if self._running:
                return True
            
            # Check if location is configured
            if not self._settings.is_location_set():
                logger.warning("Location not configured, scheduler not started")
                return False
            
            # Create calculator
            self._create_calculator()
            
            # Calculate today's times
            self._calculate_and_schedule()
            
            # Set up daily recalculation at midnight
            self._schedule_daily_recalculation()
            
            # Start resume monitor
            self._start_resume_monitor()
            
            self._running = True
            logger.info("AthanScheduler started")
            return True
    
    def stop(self) -> None:
        """Stop the scheduler."""
        with self._lock:
            if not self._running:
                return
            
            # Cancel all timers
            for prayer, timer_id in self._timer_ids.items():
                GLib.source_remove(timer_id)
            self._timer_ids.clear()
            
            if self._daily_timer_id:
                GLib.source_remove(self._daily_timer_id)
                self._daily_timer_id = None
            
            if self._resume_check_timer_id:
                GLib.source_remove(self._resume_check_timer_id)
                self._resume_check_timer_id = None
            
            self._running = False
            logger.info("AthanScheduler stopped")
    
    def _create_calculator(self) -> None:
        """Create or update the prayer time calculator."""
        loc = self._settings.location
        calc = self._settings.calculation
        
        self._calculator = PrayerTimeCalculator(
            latitude=loc.latitude,
            longitude=loc.longitude,
            timezone=loc.timezone,
            settings=calc
        )
    
    def _calculate_and_schedule(self) -> None:
        """Calculate prayer times and schedule Athans."""
        if not self._calculator:
            return
        
        # Calculate today's times
        self._current_times = self._calculator.calculate_times()
        
        # Notify listeners
        if self._on_times_updated:
            try:
                self._on_times_updated(self._current_times)
            except Exception as e:
                logger.error(f"Error in times updated callback: {e}")
        
        # Schedule Athans
        self._schedule_athans()
        
        logger.info("Prayer times calculated and scheduled")
    
    def _schedule_athans(self) -> None:
        """Schedule Athan timers for today's prayers."""
        now = datetime.now(self._calculator.timezone)
        
        # Cancel existing timers
        for timer_id in self._timer_ids.values():
            try:
                GLib.source_remove(timer_id)
            except Exception:
                pass
        self._timer_ids.clear()
        
        scheduled_count = 0
        for prayer in self.ATHAN_PRAYERS:
            prayer_time = self._current_times.get(prayer)
            if not prayer_time:
                continue
            
            # Check if time is in the future
            if prayer_time <= now:
                continue
            
            # Check if Athan is enabled for this prayer
            if not self._settings.is_athan_enabled_for_prayer(prayer.value):
                logger.debug(f"Athan disabled for {prayer.value}")
                continue
            
            # Calculate delay in milliseconds
            delay = (prayer_time - now).total_seconds() * 1000
            
            # Schedule timer (GLib.timeout_add takes milliseconds)
            timer_id = GLib.timeout_add(
                int(delay),
                self._on_timer_trigger,
                prayer
            )
            self._timer_ids[prayer] = timer_id
            scheduled_count += 1
            
            logger.debug(f"Scheduled {prayer.value} in {delay/1000:.1f} seconds")
    
    def _on_timer_trigger(self, prayer: Prayer) -> bool:
        """
        Called when a prayer timer triggers.
        
        Returns:
            False to not repeat the timer
        """
        with self._lock:
            # Remove from timer list
            if prayer in self._timer_ids:
                del self._timer_ids[prayer]
            
            # Check if we should skip
            if self._settings.skip_next_athan:
                logger.info(f"Skipping Athan for {prayer.value} (skip flag set)")
                self._settings.skip_next_athan = False
                return False
            
            # Check if enabled
            if not self._settings.is_athan_enabled_for_prayer(prayer.value):
                logger.info(f"Athan disabled for {prayer.value}")
                return False
            
            # Trigger Athan
            prayer_time = self._current_times.get(prayer, datetime.now())
            logger.info(f"Triggering Athan for {prayer.value} at {prayer_time}")
            
            try:
                self._on_athan_trigger(prayer, prayer_time)
            except Exception as e:
                logger.error(f"Error triggering Athan: {e}")
        
        return False  # Don't repeat
    
    def _schedule_daily_recalculation(self) -> None:
        """Schedule recalculation at midnight."""
        now = datetime.now(self._calculator.timezone)
        tomorrow = now.replace(hour=0, minute=1, second=0, microsecond=0) + timedelta(days=1)
        
        delay = (tomorrow - now).total_seconds() * 1000
        
        self._daily_timer_id = GLib.timeout_add(
            int(delay),
            self._on_daily_recalculation
        )
        
        logger.debug(f"Daily recalculation scheduled in {delay/1000:.1f} seconds")
    
    def _on_daily_recalculation(self) -> bool:
        """Called at midnight to recalculate times."""
        logger.info("Daily prayer time recalculation")
        
        with self._lock:
            self._calculate_and_schedule()
            self._schedule_daily_recalculation()
        
        return False  # Don't repeat (we reschedule manually)
    
    def _start_resume_monitor(self) -> None:
        """Start monitoring for system resume."""
        # Check every 60 seconds if we've been asleep
        self._last_check_time = datetime.now()
        self._resume_check_timer_id = GLib.timeout_add_seconds(
            60,
            self._check_for_resume
        )
    
    def _check_for_resume(self) -> bool:
        """Check if system was suspended and reschedule if needed."""
        now = datetime.now()
        elapsed = (now - self._last_check_time).total_seconds()
        
        # If more than 2 minutes elapsed, system was likely suspended
        if elapsed > 120:
            logger.info(f"System resume detected (elapsed: {elapsed:.1f}s)")
            with self._lock:
                self._calculate_and_schedule()
        
        self._last_check_time = now
        return True  # Continue checking
    
    def recalculate(self) -> None:
        """Force recalculation of prayer times."""
        with self._lock:
            if self._calculator:
                self._create_calculator()  # Refresh calculator with new settings
                self._calculate_and_schedule()
    
    def get_current_times(self) -> Dict[Prayer, datetime]:
        """Get current prayer times."""
        with self._lock:
            return self._current_times.copy()
    
    def get_next_prayer(self) -> Optional[PrayerTime]:
        """Get the next prayer."""
        if not self._calculator:
            return None
        return self._calculator.get_next_prayer()
    
    def get_current_prayer(self) -> Optional[PrayerTime]:
        """Get the current prayer."""
        if not self._calculator:
            return None
        return self._calculator.get_current_prayer()
    
    def get_prayer_times_list(self) -> List[PrayerTime]:
        """Get prayer times as a list with current/next flags."""
        if not self._calculator:
            return []
        return self._calculator.get_prayer_times_list()
    
    def skip_next(self) -> None:
        """Skip the next Athan."""
        self._settings.skip_next_athan = True
        logger.info("Next Athan will be skipped")
    
    def unskip_next(self) -> None:
        """Cancel skip next Athan."""
        self._settings.skip_next_athan = False
        logger.info("Skip next Athan cancelled")
    
    @property
    def is_running(self) -> bool:
        """Check if scheduler is running."""
        return self._running
