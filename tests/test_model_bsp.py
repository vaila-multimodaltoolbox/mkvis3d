"""Tests for `openbiomech/model/bsp.py` (Dumas et al. 2007 BSP)."""

from __future__ import annotations

import pytest

from openbiomech.model.bsp import com_fraction_from_proximal, mass_fraction


def test_mass_fraction_hand_checked_values():
    # Dumas et al. 2007a Table 2, transcribed from Dumas & Wojtusch 2018.
    assert mass_fraction("thigh", "male") == pytest.approx(0.123)
    assert mass_fraction("thigh", "female") == pytest.approx(0.146)
    assert mass_fraction("head", "male") == pytest.approx(0.067)
    assert mass_fraction("foot", "female") == pytest.approx(0.010)


def test_mass_fraction_not_de_leva():
    # de Leva (1996) thigh male mass fraction is 0.1416 -- a distinct,
    # commonly-confused dataset. Dumas 2007 must NOT match it.
    assert mass_fraction("thigh", "male") != pytest.approx(0.1416)


def test_com_fraction_from_proximal_hand_checked_values():
    # Dumas Length_percent Y-component: thigh male -42.9 -> |*|/100 = 0.429.
    assert com_fraction_from_proximal("thigh", "male") == pytest.approx(0.429)
    # Shank female -40.4 -> 0.404.
    assert com_fraction_from_proximal("shank", "female") == pytest.approx(0.404)
    # Head female 55.9 (positive, unlike the limb segments) -> 0.559.
    assert com_fraction_from_proximal("head", "female") == pytest.approx(0.559)


def test_com_fraction_from_proximal_is_bounded_fraction():
    for segment in (
        "head",
        "torso",
        "pelvis",
        "upper_arm",
        "forearm",
        "hand",
        "thigh",
        "shank",
        "foot",
    ):
        for sex in ("male", "female"):
            f = com_fraction_from_proximal(segment, sex)
            assert 0.0 <= f <= 1.0


def test_unknown_segment_raises():
    with pytest.raises(ValueError, match="unknown segment"):
        mass_fraction("elbow", "male")
    with pytest.raises(ValueError, match="unknown segment"):
        com_fraction_from_proximal("elbow", "male")


def test_unknown_sex_raises():
    with pytest.raises(ValueError, match="unknown sex"):
        mass_fraction("thigh", "other")
    with pytest.raises(ValueError, match="unknown sex"):
        com_fraction_from_proximal("thigh", "other")


def test_torso_mass_fraction_is_combined_thorax_abdomen():
    # torso = thorax (0.304 male) + abdomen (0.029 male), per Dumas et al.
    # 2007a Table 2's own combined "Torso" row -- checked against the
    # separate thorax+abdomen figures rather than re-summing them here,
    # since only the combined figure is exposed by this module.
    assert mass_fraction("torso", "male") == pytest.approx(0.333)
    assert mass_fraction("torso", "female") == pytest.approx(0.304)


def test_whole_body_mass_fraction_sanity_sum_male():
    # Whole-body BSP consistency check (well-known property: fractions sum
    # close to 1.0). Segments here are single (head, torso, pelvis) or
    # paired (upper_arm, forearm, hand, thigh, shank, foot) -- paired ones
    # counted twice. torso is the combined thorax+abdomen figure, so no
    # double-counting against separate thorax/abdomen entries (those are
    # not exposed by this module).
    single = ["head", "torso", "pelvis"]
    paired = ["upper_arm", "forearm", "hand", "thigh", "shank", "foot"]
    total = sum(mass_fraction(s, "male") for s in single) + 2 * sum(
        mass_fraction(s, "male") for s in paired
    )
    assert total == pytest.approx(1.0, abs=0.02)
