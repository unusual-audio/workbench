import numpy as np
from si_prefix import split, prefix

def si_format(value, precision=1, format_str="{value} {prefix}", rel=False):
    svalue, expof10 = split(value, precision)
    value_format = ("%%+.%df" if rel else "%%.%df") % precision
    value_str = value_format % svalue
    return format_str.format(value=value_str, prefix=prefix(expof10).strip())


def format_voltage(x: float, precision=1, unit="V", rel=False):
    return si_format(x, precision=precision, rel=rel) + unit


def format_timedelta(duration: np.timedelta64) -> str:
    dt = duration / np.timedelta64(1, 's')
    return f"{dt // 86400:.0f} days, {(dt % 86400) // 3600:.0f} hours, {(dt % 3600) // 60:.0f} minutes"


def get_temperature_fit(x: np.array, y: np.array, temperature: np.array, degree) -> np.poly1d:
    coefficients = np.polyfit(temperature, y, degree)
    polynomial = np.poly1d(coefficients)
    return polynomial(x)


def correct_temperature_coefficient(
        y: np.array, temperatures: np.array, reference_temperature: float, degree: int) -> np.array:
    coefficients = np.polyfit(temperatures, y, degree)
    correction = np.polyval(coefficients, temperatures) - np.polyval(coefficients, reference_temperature)
    return np.array(np.poly1d(y - correction))


def get_type_a_uncertainty(y: np.array) -> float:
    population_standard_deviation = y.std(ddof=1)
    standard_error_of_mean = population_standard_deviation / np.sqrt(len(y))
    return standard_error_of_mean


def get_type_b_uncertainties(type_b_expanded_uncertainties: np.array, k: int = 2) -> np.array:
    return type_b_expanded_uncertainties / k


def get_type_b_uncertainty(type_b_expanded_uncertainties: np.array, k: int = 2) -> np.array:
    type_b_uncertainties = get_type_b_uncertainties(type_b_expanded_uncertainties, k)
    return np.sqrt((1 / len(type_b_uncertainties)) * (type_b_uncertainties ** 2).sum())


def get_expanded_uncertainties(type_a_uncertainty: float, type_b_uncertainties: np.array, k=2) -> float:
    return propagate_uncertainties(type_a_uncertainty, type_b_uncertainties) * k


def get_expanded_uncertainty(type_a_uncertainty: float, type_b_uncertainty: float, k=2) -> float:
    return propagate_uncertainties(type_a_uncertainty, type_b_uncertainty) * k


def propagate_uncertainties(*u):
    return np.sqrt(sum(i ** 2 for i in u))


def dbu_to_vrms(x):
    return 10 ** (x / 20) * (600 * 1e-3) ** 0.5


def vrms_to_vpp(x):
    return x * 2 * 2 ** 0.5


def vrms_to_dbu(x):
    return 20 * np.log10(x / (600 * 1e-3) ** 0.5)


def vpp_to_vrms(x):
    return x / (2 * 2 ** 0.5)


def dbu_to_vpp(x):
    return vrms_to_vpp(dbu_to_vrms(x))


def vpp_to_dbu(x):
    return vrms_to_dbu(vpp_to_vrms(x))
