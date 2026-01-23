"""
Prayer Times API Module

Uses:
- Nominatim (OpenStreetMap) for geocoding city/country to coordinates
- Aladhan.com for accurate prayer times based on coordinates
"""

import os
import json
import logging
from datetime import datetime, date, timedelta
from typing import Optional, Dict, List, Tuple
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError
from urllib.parse import urlencode, quote
import pytz

logger = logging.getLogger(__name__)

CACHE_DIR = os.path.expanduser("~/.cache/athan-app")
CACHE_FILE = os.path.join(CACHE_DIR, "prayer_times_cache.json")
ALADHAN_API_URL = "https://api.aladhan.com/v1"
NOMINATIM_API_URL = "https://nominatim.openstreetmap.org"


class GeocodingAPI:
    """
    Geocoding using Nominatim (OpenStreetMap).
    
    Converts city/country names to latitude/longitude coordinates.
    """
    
    @staticmethod
    def geocode(city: str, country: str) -> Optional[Dict]:
        """
        Get coordinates for a city/country.
        
        Args:
            city: City name
            country: Country name
            
        Returns:
            Dict with lat, lon, display_name or None if not found
        """
        try:
            query = f"{city}, {country}"
            params = urlencode({
                'q': query,
                'format': 'json',
                'limit': 1,
                'addressdetails': 1,
            })
            
            url = f"{NOMINATIM_API_URL}/search?{params}"
            
            req = Request(url, headers={
                'User-Agent': 'AthanApp/1.0 (Prayer Times Application)',
                'Accept-Language': 'en',
            })
            
            with urlopen(req, timeout=10) as response:
                data = json.loads(response.read().decode())
                
                if data and len(data) > 0:
                    result = data[0]
                    return {
                        'latitude': float(result.get('lat', 0)),
                        'longitude': float(result.get('lon', 0)),
                        'display_name': result.get('display_name', ''),
                        'city': city,
                        'country': country,
                        'address': result.get('address', {}),
                    }
            
            return None
            
        except HTTPError as e:
            logger.error(f"Geocoding HTTP error: {e.code}")
            return None
        except URLError as e:
            logger.error(f"Geocoding URL error: {e.reason}")
            return None
        except Exception as e:
            logger.error(f"Geocoding error: {e}")
            return None
    
    @staticmethod
    def get_timezone(latitude: float, longitude: float) -> str:
        """
        Estimate timezone from coordinates.
        
        Uses a simple longitude-based approximation.
        For production, consider using a timezone database.
        """
        # Simple approximation based on longitude
        # Each 15° of longitude = 1 hour offset
        offset_hours = round(longitude / 15)
        
        # Common timezone mappings
        tz_map = {
            -12: 'Pacific/Fiji',
            -11: 'Pacific/Midway',
            -10: 'Pacific/Honolulu',
            -9: 'America/Anchorage',
            -8: 'America/Los_Angeles',
            -7: 'America/Denver',
            -6: 'America/Chicago',
            -5: 'America/New_York',
            -4: 'America/Halifax',
            -3: 'America/Sao_Paulo',
            -2: 'Atlantic/South_Georgia',
            -1: 'Atlantic/Azores',
            0: 'Europe/London',
            1: 'Europe/Paris',
            2: 'Europe/Istanbul',
            3: 'Asia/Riyadh',
            4: 'Asia/Dubai',
            5: 'Asia/Karachi',
            6: 'Asia/Dhaka',
            7: 'Asia/Bangkok',
            8: 'Asia/Singapore',
            9: 'Asia/Tokyo',
            10: 'Australia/Sydney',
            11: 'Pacific/Noumea',
            12: 'Pacific/Auckland',
        }
        
        return tz_map.get(offset_hours, 'UTC')


class AladhanAPI:
    """
    Client for Aladhan.com Prayer Times API.
    
    Uses coordinates (from geocoding) to get accurate prayer times.
    """
    
    METHODS = {
        0: "Shia Ithna-Ansari",
        1: "University of Islamic Sciences, Karachi",
        2: "Islamic Society of North America (ISNA)",
        3: "Muslim World League",
        4: "Umm Al-Qura University, Makkah",
        5: "Egyptian General Authority of Survey",
        7: "Institute of Geophysics, University of Tehran",
        8: "Gulf Region",
        9: "Kuwait",
        10: "Qatar",
        11: "Majlis Ugama Islam Singapura",
        12: "Union Organization Islamic de France",
        13: "Diyanet İşleri Başkanlığı, Turkey",
        14: "Spiritual Administration of Muslims of Russia",
        15: "Moonsighting Committee Worldwide",
        16: "Dubai",
        17: "Jabatan Kemajuan Islam Malaysia (JAKIM)",
        18: "Tunisia",
        19: "Algeria",
        20: "ementerian Agama Republik Indonesia",
        21: "Morocco",
        22: "Comunidade Islamica de Lisboa",        
        23: "Ministry of Awqaf, Islamic Affairs and Holy Places, Jordan",        
    }
    
    def __init__(self, method: int = 2):
        """
        Initialize the API client.
        
        Args:
            method: Calculation method (default 2 = ISNA)
        """
        self.method = method
        self._ensure_cache_dir()
    
    def _ensure_cache_dir(self):
        """Ensure cache directory exists."""
        os.makedirs(CACHE_DIR, exist_ok=True)
    
    def _make_request(self, url: str) -> Optional[dict]:
        """Make HTTP request to API."""
        try:
            req = Request(url, headers={'User-Agent': 'AthanApp/1.0'})
            with urlopen(req, timeout=10) as response:
                data = json.loads(response.read().decode())
                if data.get('code') == 200:
                    return data.get('data')
                else:
                    logger.error(f"API error: {data.get('status')}")
                    return None
        except HTTPError as e:
            logger.error(f"HTTP error: {e.code}")
            return None
        except URLError as e:
            logger.error(f"URL error: {e.reason}")
            return None
        except Exception as e:
            logger.error(f"Request error: {e}")
            return None
    
    def get_times_by_coords(
        self,
        latitude: float,
        longitude: float,
        target_date: Optional[date] = None
    ) -> Optional[Dict[str, str]]:
        """
        Get prayer times for a specific date using coordinates.
        
        Args:
            latitude: Latitude
            longitude: Longitude
            target_date: Date (defaults to today)
            
        Returns:
            Dict of prayer name to time string, or None on error
        """
        if target_date is None:
            target_date = date.today()
        
        timestamp = int(datetime(
            target_date.year, target_date.month, target_date.day, 12, 0, 0
        ).timestamp())
        
        params = urlencode({
            'latitude': latitude,
            'longitude': longitude,
            'method': self.method,
        })
        
        url = f"{ALADHAN_API_URL}/timings/{timestamp}?{params}"
        data = self._make_request(url)
        
        if data and 'timings' in data:
            timings = data['timings']
            # Clean up times (remove timezone suffix)
            clean_timings = {}
            for prayer, time_str in timings.items():
                clean_time = time_str.split(' ')[0] if ' ' in time_str else time_str
                clean_timings[prayer] = clean_time
            return clean_timings
        
        return None
    
    def get_monthly_times(
        self,
        latitude: float,
        longitude: float,
        year: int,
        month: int
    ) -> Optional[List[Dict]]:
        """
        Get prayer times for a whole month.
        
        Args:
            latitude: Latitude
            longitude: Longitude
            year: Year
            month: Month (1-12)
            
        Returns:
            List of daily prayer times or None on error
        """
        params = urlencode({
            'latitude': latitude,
            'longitude': longitude,
            'method': self.method,
            'month': month,
            'year': year,
        })
        
        url = f"{ALADHAN_API_URL}/calendar/{year}/{month}?{params}"
        return self._make_request(url)
    
    def get_method_name(self) -> str:
        """Get the name of the current calculation method."""
        return self.METHODS.get(self.method, "Unknown")


class PrayerTimesCache:
    """
    Manages cached prayer times.
    """
    
    def __init__(self):
        self._cache: Dict = {}
        self._load_cache()
    
    def _load_cache(self):
        """Load cache from disk."""
        try:
            if os.path.exists(CACHE_FILE):
                with open(CACHE_FILE, 'r') as f:
                    self._cache = json.load(f)
        except Exception as e:
            logger.error(f"Error loading cache: {e}")
            self._cache = {}
    
    def _save_cache(self):
        """Save cache to disk."""
        try:
            os.makedirs(CACHE_DIR, exist_ok=True)
            with open(CACHE_FILE, 'w') as f:
                json.dump(self._cache, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving cache: {e}")
    
    def get_times_for_date(self, date_str: str) -> Optional[Dict]:
        """Get prayer times for a date (DD-MM-YYYY format)."""
        return self._cache.get('times', {}).get(date_str)
    
    def store_times(self, date_str: str, times: Dict[str, str]):
        """Store prayer times for a date."""
        if 'times' not in self._cache:
            self._cache['times'] = {}
        self._cache['times'][date_str] = times
        self._cache['last_updated'] = datetime.now().isoformat()
        self._save_cache()
    
    def store_monthly_times(self, monthly_data: List[Dict]):
        """Store monthly prayer times."""
        if 'times' not in self._cache:
            self._cache['times'] = {}
        
        for day_data in monthly_data:
            date_info = day_data.get('date', {})
            date_str = date_info.get('gregorian', {}).get('date')
            timings = day_data.get('timings', {})
            
            if date_str and timings:
                clean_timings = {}
                for prayer, time_str in timings.items():
                    clean_time = time_str.split(' ')[0] if ' ' in time_str else time_str
                    clean_timings[prayer] = clean_time
                self._cache['times'][date_str] = clean_timings
        
        self._cache['last_updated'] = datetime.now().isoformat()
        self._save_cache()
    
    def set_location(self, city: str, country: str, latitude: float, longitude: float, timezone: str):
        """Store location info."""
        self._cache['location'] = {
            'city': city,
            'country': country,
            'latitude': latitude,
            'longitude': longitude,
            'timezone': timezone,
        }
        self._save_cache()
    
    def get_location(self) -> Optional[Dict]:
        """Get cached location."""
        return self._cache.get('location')
    
    def needs_refresh(self) -> bool:
        """Check if cache needs refresh."""
        today = date.today()
        today_str = today.strftime('%d-%m-%Y')
        
        if not self.get_times_for_date(today_str):
            return True
        
        for i in range(7):
            future = today + timedelta(days=i)
            future_str = future.strftime('%d-%m-%Y')
            if not self.get_times_for_date(future_str):
                return True
        
        return False
    
    def clear(self):
        """Clear the cache."""
        self._cache = {}
        self._save_cache()


class PrayerTimesManager:
    """
    High-level manager for prayer times.
    
    Combines geocoding, API access, and caching.
    """
    
    def __init__(self, method: int = 2):
        self.api = AladhanAPI(method=method)
        self.cache = PrayerTimesCache()
    
    def validate_location(self, city: str, country: str) -> Tuple[bool, str, Optional[Dict]]:
        """
        Validate and geocode a city/country.
        
        Args:
            city: City name
            country: Country name
            
        Returns:
            Tuple of (success, message, location_info)
        """
        # Use geocoding to get coordinates
        geo_info = GeocodingAPI.geocode(city, country)
        
        if not geo_info:
            return False, f"Could not find '{city}, {country}'. Please check spelling.", None
        
        # Get timezone estimate
        timezone = GeocodingAPI.get_timezone(geo_info['latitude'], geo_info['longitude'])
        
        location_info = {
            'city': city,
            'country': country,
            'latitude': geo_info['latitude'],
            'longitude': geo_info['longitude'],
            'timezone': timezone,
            'display_name': geo_info['display_name'],
            'method_name': self.api.get_method_name(),
        }
        
        return True, f"Found: {geo_info['display_name']}", location_info
    
    def set_location(self, city: str, country: str, latitude: float = None, longitude: float = None) -> Tuple[bool, str, Optional[Dict]]:
        """
        Set location and fetch prayer times.
        
        Args:
            city: City name
            country: Country name
            latitude: Optional pre-verified latitude
            longitude: Optional pre-verified longitude
            
        Returns:
            Tuple of (success, message, location_info)
        """
        # If coordinates provided, use them; otherwise geocode
        if latitude is not None and longitude is not None:
            timezone = GeocodingAPI.get_timezone(latitude, longitude)
            location_info = {
                'city': city,
                'country': country,
                'latitude': latitude,
                'longitude': longitude,
                'timezone': timezone,
                'method_name': self.api.get_method_name(),
            }
        else:
            success, msg, location_info = self.validate_location(city, country)
            if not success:
                return False, msg, None
        
        # Store location
        self.cache.set_location(
            city, country,
            location_info['latitude'],
            location_info['longitude'],
            location_info['timezone']
        )
        
        # Fetch prayer times
        success = self._fetch_times(location_info['latitude'], location_info['longitude'])
        
        if success:
            return True, f"Location set to {city}, {country}", location_info
        else:
            return False, "Could not fetch prayer times. Check internet.", location_info
    
    def _fetch_times(self, latitude: float, longitude: float) -> bool:
        """Fetch current and next month's times."""
        today = date.today()
        
        # Fetch current month
        data = self.api.get_monthly_times(latitude, longitude, today.year, today.month)
        if data:
            self.cache.store_monthly_times(data)
        else:
            return False
        
        # Fetch next month
        next_month = today.replace(day=1) + timedelta(days=32)
        data = self.api.get_monthly_times(latitude, longitude, next_month.year, next_month.month)
        if data:
            self.cache.store_monthly_times(data)
        
        return True
    
    def refresh_if_needed(self) -> bool:
        """Refresh cache if needed."""
        if self.cache.needs_refresh():
            location = self.cache.get_location()
            if location:
                return self._fetch_times(location['latitude'], location['longitude'])
        return True
    
    def get_today_times(self) -> Optional[Dict[str, str]]:
        """Get today's prayer times."""
        today_str = date.today().strftime('%d-%m-%Y')
        times = self.cache.get_times_for_date(today_str)
        
        if times:
            main_prayers = ['Fajr', 'Sunrise', 'Dhuhr', 'Asr', 'Maghrib', 'Isha']
            return {p: times.get(p, '--:--') for p in main_prayers}
        
        return None
    
    def get_times_for_date(self, target_date: date) -> Optional[Dict[str, str]]:
        """Get prayer times for a specific date."""
        date_str = target_date.strftime('%d-%m-%Y')
        times = self.cache.get_times_for_date(date_str)
        
        if times:
            main_prayers = ['Fajr', 'Sunrise', 'Dhuhr', 'Asr', 'Maghrib', 'Isha']
            return {p: times.get(p, '--:--') for p in main_prayers}
        
        return None
    
    def get_next_prayer(self) -> Optional[Tuple[str, str, datetime]]:
        """
        Get the next upcoming prayer.
        
        Returns:
            Tuple of (prayer_name, time_str, datetime) or None
        """
        times = self.get_today_times()
        if not times:
            return None
        
        location = self.cache.get_location()
        if not location:
            return None
        
        try:
            tz = pytz.timezone(location['timezone'])
        except:
            tz = pytz.UTC
        
        now = datetime.now(tz)
        today = now.date()
        
        athan_prayers = ['Fajr', 'Dhuhr', 'Asr', 'Maghrib', 'Isha']
        
        for prayer in athan_prayers:
            time_str = times.get(prayer, '')
            if not time_str or time_str == '--:--':
                continue
            
            try:
                hour, minute = map(int, time_str.split(':'))
                prayer_dt = tz.localize(datetime(today.year, today.month, today.day, hour, minute))
                
                if prayer_dt > now:
                    return (prayer, time_str, prayer_dt)
            except:
                continue
        
        # If no prayer left today, return tomorrow's Fajr
        tomorrow = today + timedelta(days=1)
        tomorrow_times = self.get_times_for_date(tomorrow)
        if tomorrow_times:
            fajr_time = tomorrow_times.get('Fajr', '')
            if fajr_time and fajr_time != '--:--':
                try:
                    hour, minute = map(int, fajr_time.split(':'))
                    prayer_dt = tz.localize(datetime(tomorrow.year, tomorrow.month, tomorrow.day, hour, minute))
                    return ('Fajr', fajr_time, prayer_dt)
                except:
                    pass
        
        return None
    
    def get_current_prayer(self) -> Optional[str]:
        """Get the current prayer period."""
        times = self.get_today_times()
        if not times:
            return None
        
        location = self.cache.get_location()
        if not location:
            return None
        
        try:
            tz = pytz.timezone(location['timezone'])
        except:
            tz = pytz.UTC
        
        now = datetime.now(tz)
        today = now.date()
        
        prayers = ['Fajr', 'Dhuhr', 'Asr', 'Maghrib', 'Isha']
        current = None
        
        for prayer in prayers:
            time_str = times.get(prayer, '')
            if not time_str or time_str == '--:--':
                continue
            
            try:
                hour, minute = map(int, time_str.split(':'))
                prayer_dt = tz.localize(datetime(today.year, today.month, today.day, hour, minute))
                
                if prayer_dt <= now:
                    current = prayer
            except:
                continue
        
        return current
    
    def get_timezone(self) -> Optional[str]:
        """Get the timezone string."""
        location = self.cache.get_location()
        return location.get('timezone') if location else None
