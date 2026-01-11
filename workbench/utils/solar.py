from datetime import datetime
from math import radians, sin, cos


def get_solar_irradiance(dt: datetime, lat: float) -> float:
    """
    Calculate approximate clear-sky solar irradiance on a horizontal surface.
    - dt: datetime with timezone
    - lat: latitude in degrees
    Returns irradiance in W/m².
    """
    # Day of year
    day_of_year = dt.timetuple().tm_yday
    # Solar declination (radians)
    delta = radians(23.45 * sin(radians(360 * (284 + day_of_year) / 365)))
    # Latitude (radians)
    phi = radians(lat)
    # Decimal hour
    time_decimal = dt.hour + dt.minute / 60 + dt.second / 3600
    # Hour angle (radians)
    h = radians(15 * (time_decimal - 12))
    # Cosine of solar zenith angle
    cos_theta = sin(phi) * sin(delta) + cos(phi) * cos(delta) * cos(h)
    cos_theta = max(cos_theta, 0)  # No negative values before sunrise/after sunset
    # Solar constant (W/m²)
    I_sc = 1361
    # Irradiance on horizontal plane
    I = I_sc * cos_theta
    return I


def get_max_irradiance(lat: float, day_of_year: int):
    """
    Get maximum irradiance for a given latitude and day of the year.
    Returns irradiance in W/m².
    Tip: get the day of the year from `datetime.timetuple().tm_yday`.
    """
    # Solar declination (radians)
    delta = radians(23.45 * sin(radians(360 * (284 + day_of_year) / 365)))
    # Latitude (radians)
    phi = radians(lat)
    # Solar constant (W/m²)
    I_sc = 1361.0
    return I_sc * (sin(phi) * sin(delta) + cos(phi) * cos(delta))
