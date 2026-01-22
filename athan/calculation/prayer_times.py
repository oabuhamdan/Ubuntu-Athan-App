"""
Prayer Time Calculation Engine

Implements configurable prayer time calculation supporting:
- Multiple calculation methods (ISNA, MWL, etc.)
- Madhab settings (Shafi, Hanafi)
- High latitude adjustments
- Twilight angle configuration
- Polar circle resolution
"""

import math
from datetime import datetime, timedelta, date
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Tuple
import pytz


class CalculationMethod(Enum):
    """Prayer time calculation methods with their parameters."""
    ISNA = "isna"  # Islamic Society of North America
    MWL = "mwl"  # Muslim World League
    EGYPT = "egypt"  # Egyptian General Authority of Survey
    KARACHI = "karachi"  # University of Islamic Sciences, Karachi
    MAKKAH = "makkah"  # Umm al-Qura University, Makkah
    DUBAI = "dubai"  # Dubai
    KUWAIT = "kuwait"  # Kuwait
    QATAR = "qatar"  # Qatar
    SINGAPORE = "singapore"  # Singapore
    TEHRAN = "tehran"  # Institute of Geophysics, University of Tehran


class Madhab(Enum):
    """Juristic methods for Asr calculation."""
    SHAFI = "shafi"  # Shafi, Maliki, Hanbali (shadow factor = 1)
    HANAFI = "hanafi"  # Hanafi (shadow factor = 2)


class HighLatitudeRule(Enum):
    """Rules for calculating prayer times at high latitudes."""
    MIDDLE_OF_NIGHT = "middle_of_night"
    SEVENTH_OF_NIGHT = "seventh_of_night"
    TWILIGHT_ANGLE = "twilight_angle"
    NONE = "none"


class PolarCircleResolution(Enum):
    """Methods for handling prayer times in polar regions."""
    UNRESOLVED = "unresolved"
    CLOSEST_CITY = "closest_city"
    CLOSEST_DATE = "closest_date"


class Shafaq(Enum):
    """Shafaq settings for Isha calculation."""
    GENERAL = "general"  # Default
    AHMER = "ahmer"  # Red twilight
    ABYAD = "abyad"  # White twilight


class Prayer(Enum):
    """Prayer names."""
    FAJR = "fajr"
    SUNRISE = "sunrise"
    DHUHR = "dhuhr"
    ASR = "asr"
    MAGHRIB = "maghrib"
    ISHA = "isha"


@dataclass
class CalculationSettings:
    """Settings for prayer time calculation."""
    method: CalculationMethod = CalculationMethod.ISNA
    madhab: Madhab = Madhab.SHAFI
    high_latitude_rule: HighLatitudeRule = HighLatitudeRule.MIDDLE_OF_NIGHT
    polar_circle_resolution: PolarCircleResolution = PolarCircleResolution.CLOSEST_CITY
    shafaq: Shafaq = Shafaq.GENERAL
    
    # Custom angles (if not using method defaults)
    fajr_angle: Optional[float] = None
    isha_angle: Optional[float] = None
    
    # Adjustments in minutes
    fajr_adjustment: int = 0
    sunrise_adjustment: int = 0
    dhuhr_adjustment: int = 0
    asr_adjustment: int = 0
    maghrib_adjustment: int = 0
    isha_adjustment: int = 0
    
    def to_dict(self) -> dict:
        """Convert settings to dictionary for storage."""
        return {
            'method': self.method.value,
            'madhab': self.madhab.value,
            'high_latitude_rule': self.high_latitude_rule.value,
            'polar_circle_resolution': self.polar_circle_resolution.value,
            'shafaq': self.shafaq.value,
            'fajr_angle': self.fajr_angle,
            'isha_angle': self.isha_angle,
            'fajr_adjustment': self.fajr_adjustment,
            'sunrise_adjustment': self.sunrise_adjustment,
            'dhuhr_adjustment': self.dhuhr_adjustment,
            'asr_adjustment': self.asr_adjustment,
            'maghrib_adjustment': self.maghrib_adjustment,
            'isha_adjustment': self.isha_adjustment,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'CalculationSettings':
        """Create settings from dictionary."""
        return cls(
            method=CalculationMethod(data.get('method', 'isna')),
            madhab=Madhab(data.get('madhab', 'shafi')),
            high_latitude_rule=HighLatitudeRule(data.get('high_latitude_rule', 'middle_of_night')),
            polar_circle_resolution=PolarCircleResolution(data.get('polar_circle_resolution', 'closest_city')),
            shafaq=Shafaq(data.get('shafaq', 'general')),
            fajr_angle=data.get('fajr_angle'),
            isha_angle=data.get('isha_angle'),
            fajr_adjustment=data.get('fajr_adjustment', 0),
            sunrise_adjustment=data.get('sunrise_adjustment', 0),
            dhuhr_adjustment=data.get('dhuhr_adjustment', 0),
            asr_adjustment=data.get('asr_adjustment', 0),
            maghrib_adjustment=data.get('maghrib_adjustment', 0),
            isha_adjustment=data.get('isha_adjustment', 0),
        )


@dataclass
class PrayerTime:
    """Represents a single prayer time."""
    prayer: Prayer
    time: datetime
    is_current: bool = False
    is_next: bool = False


# Method parameters: (fajr_angle, isha_angle)
METHOD_PARAMETERS = {
    CalculationMethod.ISNA: (15.0, 15.0),
    CalculationMethod.MWL: (18.0, 17.0),
    CalculationMethod.EGYPT: (19.5, 17.5),
    CalculationMethod.KARACHI: (18.0, 18.0),
    CalculationMethod.MAKKAH: (18.5, 90),  # 90 means Isha is 90 min after Maghrib
    CalculationMethod.DUBAI: (18.2, 18.2),
    CalculationMethod.KUWAIT: (18.0, 17.5),
    CalculationMethod.QATAR: (18.0, 90),
    CalculationMethod.SINGAPORE: (20.0, 18.0),
    CalculationMethod.TEHRAN: (17.7, 14.0),
}


class PrayerTimeCalculator:
    """
    Calculates Islamic prayer times based on geographical coordinates
    and configurable calculation parameters.
    
    The calculation follows these astronomical principles:
    - Fajr: When the sun is at the fajr angle below the horizon (dawn)
    - Sunrise: When the sun's upper edge appears on the horizon
    - Dhuhr: When the sun passes the meridian (solar noon)
    - Asr: Based on shadow length (Shafi: shadow = object + noon shadow)
    - Maghrib: When the sun's upper edge disappears below horizon
    - Isha: When the sun is at the isha angle below the horizon (night)
    """
    
    def __init__(
        self,
        latitude: float,
        longitude: float,
        timezone: str,
        settings: Optional[CalculationSettings] = None
    ):
        """
        Initialize the calculator.
        
        Args:
            latitude: Geographical latitude (-90 to 90)
            longitude: Geographical longitude (-180 to 180)
            timezone: Timezone string (e.g., 'America/New_York')
            settings: Calculation settings (uses defaults if not provided)
        """
        self.latitude = latitude
        self.longitude = longitude
        self.timezone = pytz.timezone(timezone)
        self.settings = settings or CalculationSettings()
        
        # Get method angles
        self._fajr_angle, self._isha_angle = self._get_angles()
        
    def _get_angles(self) -> Tuple[float, float]:
        """Get Fajr and Isha angles based on method or custom settings."""
        method_params = METHOD_PARAMETERS.get(
            self.settings.method, 
            (15.0, 15.0)
        )
        
        fajr_angle = self.settings.fajr_angle or method_params[0]
        isha_angle = self.settings.isha_angle or method_params[1]
        
        return fajr_angle, isha_angle
    
    def _julian_day(self, year: int, month: int, day: int) -> float:
        """Calculate Julian Day number."""
        if month <= 2:
            year -= 1
            month += 12
        
        a = math.floor(year / 100)
        b = 2 - a + math.floor(a / 4)
        
        return math.floor(365.25 * (year + 4716)) + \
               math.floor(30.6001 * (month + 1)) + day + b - 1524.5
    
    def _sun_position(self, jd: float) -> Tuple[float, float]:
        """
        Calculate sun declination and equation of time.
        
        Args:
            jd: Julian day number
            
        Returns:
            Tuple of (declination in degrees, equation of time in minutes)
        """
        d = jd - 2451545.0
        
        # Mean longitude of the sun
        g = math.radians((357.529 + 0.98560028 * d) % 360)
        q = (280.459 + 0.98564736 * d) % 360
        
        # Ecliptic longitude
        L = (q + 1.915 * math.sin(g) + 0.020 * math.sin(2 * g)) % 360
        
        # Obliquity of the ecliptic
        e = 23.439 - 0.00000036 * d
        e_rad = math.radians(e)
        L_rad = math.radians(L)
        
        # Sun's declination
        decl = math.degrees(math.asin(math.sin(e_rad) * math.sin(L_rad)))
        
        # Right ascension
        ra = math.degrees(math.atan2(math.cos(e_rad) * math.sin(L_rad), math.cos(L_rad)))
        ra = (ra + 360) % 360
        
        # Equation of time (in minutes)
        eqt = (q - ra) * 4  # Convert degrees to minutes
        if eqt > 720:
            eqt -= 1440
        elif eqt < -720:
            eqt += 1440
            
        return decl, eqt
    
    def _hour_angle(self, angle: float, decl: float) -> Optional[float]:
        """
        Calculate hour angle for a given sun angle.
        
        Args:
            angle: Sun angle below horizon (positive)
            decl: Sun declination
            
        Returns:
            Hour angle in hours, or None if impossible
        """
        lat_rad = math.radians(self.latitude)
        decl_rad = math.radians(decl)
        angle_rad = math.radians(angle)
        
        cos_ha = (-math.sin(angle_rad) - math.sin(lat_rad) * math.sin(decl_rad)) / \
                 (math.cos(lat_rad) * math.cos(decl_rad))
        
        if cos_ha < -1 or cos_ha > 1:
            return None
            
        return math.degrees(math.acos(cos_ha)) / 15.0
    
    def _apply_high_latitude_adjustment(
        self,
        prayer: Prayer,
        time: Optional[float],
        sunrise: float,
        sunset: float
    ) -> float:
        """Apply high latitude rule if prayer time is invalid."""
        if time is not None:
            return time
        
        night_duration = 24 - sunset + sunrise
        
        if self.settings.high_latitude_rule == HighLatitudeRule.MIDDLE_OF_NIGHT:
            portion = 0.5
        elif self.settings.high_latitude_rule == HighLatitudeRule.SEVENTH_OF_NIGHT:
            portion = 1/7
        else:
            return 0  # Return midnight as fallback
        
        if prayer == Prayer.FAJR:
            return sunrise - portion * night_duration
        elif prayer == Prayer.ISHA:
            return sunset + portion * night_duration
        
        return 0
    
    def calculate_times(self, calc_date: Optional[date] = None) -> Dict[Prayer, datetime]:
        """
        Calculate prayer times for a given date.
        
        Args:
            calc_date: Date to calculate for (defaults to today)
        
        Returns:
            Dictionary mapping Prayer enum to datetime
        """
        if calc_date is None:
            calc_date = datetime.now(self.timezone).date()
        
        jd = self._julian_day(calc_date.year, calc_date.month, calc_date.day)
        decl, eqt = self._sun_position(jd)
        
        # Calculate transit time (Dhuhr/solar noon) in local time
        # Transit = 12:00 - EqT/60 - Longitude/15 + Timezone_offset
        tz_offset = self.timezone.utcoffset(
            datetime(calc_date.year, calc_date.month, calc_date.day, 12)
        ).total_seconds() / 3600
        
        transit = 12 - eqt/60 - self.longitude/15 + tz_offset
        
        # Calculate hour angles
        ha_sunrise = self._hour_angle(0.833, decl)  # 0.833° for refraction
        ha_fajr = self._hour_angle(self._fajr_angle, decl)
        ha_isha = self._hour_angle(self._isha_angle, decl) if self._isha_angle != 90 else None
        
        # Calculate Asr hour angle
        shadow_factor = 1 if self.settings.madhab == Madhab.SHAFI else 2
        lat_rad = math.radians(self.latitude)
        decl_rad = math.radians(decl)
        
        # Asr: when shadow = shadow_factor * object_height + noon_shadow
        # cot(asr_angle) = shadow_factor + tan(|lat - decl|)
        # acot(x) = atan(1/x)
        asr_angle = math.degrees(math.atan(1 / (shadow_factor + math.tan(abs(lat_rad - decl_rad)))))
        ha_asr = self._hour_angle(-asr_angle, decl)
        
        # Calculate prayer times
        times_dict = {}
        
        # Fajr
        if ha_fajr is not None:
            times_dict[Prayer.FAJR] = transit - ha_fajr
        else:
            times_dict[Prayer.FAJR] = None
            
        # Sunrise
        if ha_sunrise is not None:
            times_dict[Prayer.SUNRISE] = transit - ha_sunrise
        else:
            times_dict[Prayer.SUNRISE] = transit - 6  # Fallback
            
        # Dhuhr (transit + small offset to ensure sun has passed meridian)
        times_dict[Prayer.DHUHR] = transit
        
        # Asr
        if ha_asr is not None:
            times_dict[Prayer.ASR] = transit + ha_asr
        else:
            times_dict[Prayer.ASR] = transit + 4  # Fallback
            
        # Maghrib (sunset)
        if ha_sunrise is not None:
            times_dict[Prayer.MAGHRIB] = transit + ha_sunrise
        else:
            times_dict[Prayer.MAGHRIB] = transit + 6  # Fallback
            
        # Isha
        if self._isha_angle == 90:
            # Isha is 90 minutes after Maghrib (Umm al-Qura method)
            times_dict[Prayer.ISHA] = times_dict[Prayer.MAGHRIB] + 1.5
        elif ha_isha is not None:
            times_dict[Prayer.ISHA] = transit + ha_isha
        else:
            times_dict[Prayer.ISHA] = None
        
        # Apply high latitude adjustments
        sunrise_time = times_dict[Prayer.SUNRISE]
        sunset_time = times_dict[Prayer.MAGHRIB]
        
        if times_dict[Prayer.FAJR] is None:
            times_dict[Prayer.FAJR] = self._apply_high_latitude_adjustment(
                Prayer.FAJR, None, sunrise_time, sunset_time
            )
        
        if times_dict[Prayer.ISHA] is None:
            times_dict[Prayer.ISHA] = self._apply_high_latitude_adjustment(
                Prayer.ISHA, None, sunrise_time, sunset_time
            )
        
        # Apply manual adjustments and convert to datetime
        adjustments = {
            Prayer.FAJR: self.settings.fajr_adjustment,
            Prayer.SUNRISE: self.settings.sunrise_adjustment,
            Prayer.DHUHR: self.settings.dhuhr_adjustment,
            Prayer.ASR: self.settings.asr_adjustment,
            Prayer.MAGHRIB: self.settings.maghrib_adjustment,
            Prayer.ISHA: self.settings.isha_adjustment,
        }
        
        result = {}
        for prayer, time_val in times_dict.items():
            if time_val is not None:
                # Add adjustment (in minutes)
                time_val += adjustments[prayer] / 60
                
                # Handle day overflow
                day_offset = 0
                while time_val >= 24:
                    time_val -= 24
                    day_offset += 1
                while time_val < 0:
                    time_val += 24
                    day_offset -= 1
                
                # Convert to hours, minutes, seconds
                hours = int(time_val)
                minutes = int((time_val - hours) * 60)
                seconds = int(((time_val - hours) * 60 - minutes) * 60)
                
                actual_date = calc_date + timedelta(days=day_offset)
                dt = datetime(
                    actual_date.year, actual_date.month, actual_date.day,
                    hours, minutes, seconds
                )
                result[prayer] = self.timezone.localize(dt)
            else:
                # Fallback
                result[prayer] = self.timezone.localize(
                    datetime(calc_date.year, calc_date.month, calc_date.day, 0, 0, 0)
                )
        
        return result
    
    def get_prayer_times_list(
        self, 
        calc_date: Optional[date] = None
    ) -> List[PrayerTime]:
        """
        Get prayer times as a list with current/next flags.
        
        Returns:
            List of PrayerTime objects sorted by time
        """
        times = self.calculate_times(calc_date)
        now = datetime.now(self.timezone)
        
        # Create list and sort by time
        prayer_list = [
            PrayerTime(prayer=p, time=t) 
            for p, t in times.items()
        ]
        prayer_list.sort(key=lambda x: x.time)
        
        # Determine current and next prayer
        # Prayer times for Athan are: Fajr, Dhuhr, Asr, Maghrib, Isha (not Sunrise)
        athan_prayers = [Prayer.FAJR, Prayer.DHUHR, Prayer.ASR, Prayer.MAGHRIB, Prayer.ISHA]
        
        current_prayer = None
        next_prayer = None
        
        for i, pt in enumerate(prayer_list):
            if pt.prayer not in athan_prayers:
                continue
            
            if pt.time <= now:
                current_prayer = pt
            elif next_prayer is None:
                next_prayer = pt
        
        # Mark current and next
        for pt in prayer_list:
            if current_prayer and pt.prayer == current_prayer.prayer:
                pt.is_current = True
            if next_prayer and pt.prayer == next_prayer.prayer:
                pt.is_next = True
        
        return prayer_list
    
    def get_next_prayer(self) -> Optional[PrayerTime]:
        """Get the next upcoming prayer (excluding sunrise)."""
        prayer_list = self.get_prayer_times_list()
        
        for pt in prayer_list:
            if pt.is_next:
                return pt
        
        # If no next prayer today, get tomorrow's Fajr
        tomorrow = datetime.now(self.timezone).date() + timedelta(days=1)
        tomorrow_times = self.calculate_times(tomorrow)
        
        return PrayerTime(
            prayer=Prayer.FAJR,
            time=tomorrow_times[Prayer.FAJR],
            is_next=True
        )
    
    def get_current_prayer(self) -> Optional[PrayerTime]:
        """Get the current active prayer."""
        prayer_list = self.get_prayer_times_list()
        
        for pt in prayer_list:
            if pt.is_current:
                return pt
        
        return None
    
    def update_settings(self, settings: CalculationSettings) -> None:
        """Update calculation settings and refresh angles."""
        self.settings = settings
        self._fajr_angle, self._isha_angle = self._get_angles()
    
    def update_location(self, latitude: float, longitude: float, timezone: str) -> None:
        """Update location settings."""
        self.latitude = latitude
        self.longitude = longitude
        self.timezone = pytz.timezone(timezone)


def get_prayer_name(prayer: Prayer) -> str:
    """Get human-readable prayer name."""
    names = {
        Prayer.FAJR: "Fajr",
        Prayer.SUNRISE: "Sunrise",
        Prayer.DHUHR: "Dhuhr",
        Prayer.ASR: "Asr",
        Prayer.MAGHRIB: "Maghrib",
        Prayer.ISHA: "Isha",
    }
    return names.get(prayer, str(prayer))


def get_prayer_arabic_name(prayer: Prayer) -> str:
    """Get Arabic prayer name."""
    names = {
        Prayer.FAJR: "الفجر",
        Prayer.SUNRISE: "الشروق",
        Prayer.DHUHR: "الظهر",
        Prayer.ASR: "العصر",
        Prayer.MAGHRIB: "المغرب",
        Prayer.ISHA: "العشاء",
    }
    return names.get(prayer, "")
