import numpy as np
from numpy.testing import assert_array_almost_equal

from workbench.utils import get_temperature_fit, correct_temperature_coefficient


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
