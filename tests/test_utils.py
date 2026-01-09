from datetime import datetime, timezone

import pytest
from math import isclose

import numpy as np
from numpy.testing import assert_array_almost_equal

from workbench.utils import get_temperature_fit, correct_temperature_coefficient
from workbench.utils.pt100 import r_to_c
from workbench.utils.solar import get_solar_irradiance, get_max_irradiance

PT100_IEC_60751_VECTORS = [
    (80.31, -50.0),
    (100.00, 0.0),
    (138.51, 100.0),
    (175.86, 200.0),
]

PT1000_IEC_60751_VECTORS = [
    (803.10, -50.0),
    (1000.00, 0.0),
    (1193.97, 50.0),
    (1385.10, 100.0),
    (1758.56, 200.0),
    (2470.92, 400.0),
]


@pytest.mark.parametrize("r_expected,t_expected", PT100_IEC_60751_VECTORS)
def test_pt100_reference_points(r_expected, t_expected):
    t = r_to_c(r_expected)
    assert np.isclose(t, t_expected, atol=0.1)


def test_pt100_reference_points_vector():
    t = r_to_c(np.array([80.31]))
    t_expected = np.array([-50.0])
    assert np.isclose(t, t_expected, atol=0.1)


@pytest.mark.parametrize("r_expected,t_expected", PT1000_IEC_60751_VECTORS)
def test_pt1000_reference_points(r_expected, t_expected):
    t = r_to_c(r_expected, r0=1000)
    assert np.isclose(t, t_expected, atol=0.1)


def test_pt1000_reference_points_vector():
    t = r_to_c(np.array([803.10]), r0=1000)
    t_expected = np.array([-50.0])
    assert np.isclose(t, t_expected, atol=0.1)


def test_get_temperature_fit():
    values = np.array([
        (10.000_000_1, 24.0),
        (10.000_000_2, 25.0),
        (10.000_000_3, 26.0),
    ], dtype=[
        ('voltage', 'float64'),
        ('temperature', 'float64'),
    ])
    x = np.linspace(22.0, 27.0, 6)
    temperature_fit = get_temperature_fit(x, values["voltage"], values["temperature"], 2)
    assert_array_almost_equal(temperature_fit, [
        9.999_999_9,
        10.000_000_0,
        10.000_000_1,
        10.000_000_2,
        10.000_000_3,
        10.000_000_4,
    ], decimal=8)
    assert True


def test_correct_temperature_coefficient():
    values = np.array([
        (0, 10.000_000_1, 24.0),
        (1, 10.000_000_2, 25.0),
        (2, 10.000_000_3, 26.0),
    ], dtype=[
        ('timestamp', 'datetime64[s]'),
        ('voltage', 'float64'),
        ('temperature', 'float64'),
    ])
    y_ = correct_temperature_coefficient(values["voltage"], values["temperature"], 23.0, 2)
    assert_array_almost_equal(y_, [
        10.000_000_0,
        10.000_000_0,
        10.000_000_0,
    ], decimal=8)
    assert True


def test_irradiance_at_night_is_zero():
    dt = datetime(2024, 6, 21, 0, 0, tzinfo=timezone.utc)  # midnight UTC
    lat = 50.0

    irradiance = get_solar_irradiance(dt, lat)

    assert irradiance >= 0
    assert irradiance < 1.0  # allow small numerical noise


def test_irradiance_positive_at_noon_summer():
    dt = datetime(2024, 6, 21, 12, 0, tzinfo=timezone.utc)  # summer solstice
    lat = 50.0

    irradiance = get_solar_irradiance(dt, lat)

    assert irradiance > 0


def test_noon_higher_than_morning():
    lat = 40.0
    morning = datetime(2024, 6, 21, 8, 0, tzinfo=timezone.utc)
    noon = datetime(2024, 6, 21, 12, 0, tzinfo=timezone.utc)

    irr_morning = get_solar_irradiance(morning, lat)
    irr_noon = get_solar_irradiance(noon, lat)

    assert irr_noon > irr_morning


def test_summer_higher_than_winter():
    lat = 45.0

    summer = datetime(2024, 6, 21, 12, 0, tzinfo=timezone.utc)
    winter = datetime(2024, 12, 21, 12, 0, tzinfo=timezone.utc)

    irr_summer = get_solar_irradiance(summer, lat)
    irr_winter = get_solar_irradiance(winter, lat)

    assert irr_summer > irr_winter


def test_polar_night_zero_irradiance():
    lat = 70.0  # Arctic Circle+
    dt = datetime(2024, 12, 21, 12, 0, tzinfo=timezone.utc)

    irradiance = get_solar_irradiance(dt, lat)

    assert irradiance >= 0
    assert irradiance < 1.0


def test_max_irradiance_non_negative():
    lat = 30.0
    day = 180

    max_irr = get_max_irradiance(lat, day)

    assert max_irr >= 0


def test_max_irradiance_seasonality():
    lat = 45.0

    summer_day = 172  # ~June 21
    winter_day = 355  # ~Dec 21

    max_summer = get_max_irradiance(lat, summer_day)
    max_winter = get_max_irradiance(lat, winter_day)

    assert max_summer > max_winter


def test_equator_low_seasonal_variation():
    lat = 0.0

    day_1 = 80  # March equinox
    day_2 = 263  # September equinox

    irr_1 = get_max_irradiance(lat, day_1)
    irr_2 = get_max_irradiance(lat, day_2)

    assert isclose(irr_1, irr_2, rel_tol=0.1)


def test_high_latitude_winter_near_zero():
    lat = 70.0
    winter_day = 355

    max_irr = get_max_irradiance(lat, winter_day)

    assert max_irr < 50.0
