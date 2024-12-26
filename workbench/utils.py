import math

import numpy as np


def get_temperature_fit(x, y, temperature_difference, degree):
    coefficients = np.polyfit(temperature_difference, y, degree)
    polynomial = np.poly1d(coefficients)
    return polynomial(x)


def correct_temperature_coefficient(y, temperatures, reference_temperature, degree):
    coefficients = np.polyfit(temperatures, y, degree)
    correction = np.polyval(coefficients, temperatures) - np.polyval(coefficients, reference_temperature)
    return y - correction


def get_type_a_uncertainty(y: np.array) -> float:
    population_standard_deviation = y.std(ddof=1)
    standard_error_of_mean = population_standard_deviation / np.sqrt(len(y))
    return standard_error_of_mean


def get_type_b_uncertainties(type_b_expanded_uncertainties: np.array, k: int = 2) -> np.array:
    return type_b_expanded_uncertainties / k


def get_type_b_uncertainty(type_b_expanded_uncertainties: np.array, k: int = 2) -> np.array:
    type_b_uncertainties = get_type_b_uncertainties(type_b_expanded_uncertainties, k)
    return np.sqrt((1 / len(type_b_uncertainties)) * (type_b_uncertainties ** 2).sum())


def get_total_uncertainties(type_a_uncertainty: float, type_b_uncertainties: np.array, k=2) -> float:
    return np.sqrt(type_a_uncertainty ** 2 + type_b_uncertainties ** 2) * k


def get_total_uncertainty(type_a_uncertainty: float, type_b_uncertainties: np.array, k=2) -> float:
    type_b_uncertainty = np.sqrt((1 / len(type_b_uncertainties)) * (type_b_uncertainties ** 2).sum())
    return np.sqrt(type_a_uncertainty ** 2 + type_b_uncertainty ** 2) * k


def propagate_uncertainties(*u):
    return np.sqrt(sum(i ** 2 for i in u))


def dbu_to_vrms(x):
    return 10 ** (x / 20) * (600 * 1e-3) ** 0.5


def vrms_to_vpp(x):
    return x * 2 * 2 ** 0.5


def vrms_to_dbu(x):
    return 20 * math.log10(x / (600 * 1e-3) ** 0.5)


def vpp_to_vrms(x):
    return x / (2 * 2 ** 0.5)


def dbu_to_vpp(x):
    return vrms_to_vpp(dbu_to_vrms(x))


def vpp_to_dbu(x):
    return vrms_to_dbu(vpp_to_vrms(x))
