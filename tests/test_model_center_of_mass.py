"""Tests for de Leva whole-body centre-of-mass estimation."""

from __future__ import annotations

import numpy as np
import pytest
from numpy.testing import assert_allclose

from openbiomech.model.center_of_mass import (
    de_leva_com_fraction,
    de_leva_mass_fraction,
    whole_body_com,
)


def test_de_leva_hand_checked_values_and_whole_body_mass_sum():
    assert de_leva_mass_fraction("thigh", "male") == pytest.approx(0.1416)
    assert de_leva_mass_fraction("trunk", "female") == pytest.approx(0.4257)
    assert de_leva_com_fraction("upper_arm", "male") == pytest.approx(0.5772)
    assert de_leva_com_fraction("foot", "female") == pytest.approx(0.4014)

    singles = ("head", "trunk")
    paired = ("upper_arm", "forearm", "hand", "thigh", "shank", "foot")
    for sex in ("female", "male"):
        total = sum(de_leva_mass_fraction(name, sex) for name in singles)
        total += 2 * sum(de_leva_mass_fraction(name, sex) for name in paired)
        assert total == pytest.approx(1.0, abs=1e-4)


def test_whole_body_com_is_mass_weighted_and_renormalizes_missing_segments():
    proximal = np.zeros((2, 3), dtype=np.float64)
    distal = np.ones((2, 3), dtype=np.float64)
    missing = np.full((2, 3), np.nan, dtype=np.float64)
    segments = {
        "trunk": (proximal, distal),
        "thigh_l": (proximal, distal),
        "thigh_r": (proximal, distal),
    }
    result = whole_body_com(segments, "male")
    expected = (0.4346 * 0.5138 + 2 * 0.1416 * 0.4095) / (0.4346 + 2 * 0.1416)
    assert_allclose(result, expected)

    segments["trunk"] = (missing, missing)
    result_without_trunk = whole_body_com(segments, "male")
    assert_allclose(result_without_trunk, 0.4095)


def test_whole_body_com_rejects_invalid_shape_and_sex():
    endpoints = np.zeros((3, 3), dtype=np.float64)
    with pytest.raises(ValueError, match="sex"):
        whole_body_com({"trunk": (endpoints, endpoints)}, "other")
    with pytest.raises(ValueError, match="shape"):
        whole_body_com({"trunk": (np.zeros(3), np.zeros(3))}, "male")
