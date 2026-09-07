"""Synthetic ground-truth test for Kabsch rigid-body registration."""

from __future__ import annotations

import numpy as np

from openbiomech.biomech_math import kabsch


def _random_rotation(rng: np.random.Generator) -> np.ndarray:
    """A uniformly random proper rotation matrix via QR decomposition."""
    a = rng.normal(size=(3, 3))
    q, r = np.linalg.qr(a)
    # Fix sign so det(q) == +1 (QR can hand back a reflection).
    q *= np.sign(np.diag(r))
    if np.linalg.det(q) < 0:
        q[:, 0] *= -1
    return q


def test_kabsch_recovers_known_rotation_and_translation():
    rng = np.random.default_rng(0)
    source = rng.normal(size=(12, 3))  # non-planar random cloud
    R_true = _random_rotation(rng)
    t_true = rng.normal(size=3) * 5.0
    target = source @ R_true.T + t_true

    result = kabsch(source, target)

    assert not result.degenerate
    assert result.R is not None
    assert result.t is not None
    assert np.allclose(result.R, R_true, atol=1e-9)
    assert np.allclose(result.t, t_true, atol=1e-9)
    assert np.isclose(np.linalg.det(result.R), 1.0, atol=1e-12)
    assert result.max_residual < 1e-9


def test_kabsch_flags_planar_source_as_degenerate():
    rng = np.random.default_rng(1)
    n = 8
    source = np.zeros((n, 3))
    source[:, 0] = rng.normal(size=n)
    source[:, 1] = rng.normal(size=n)
    # z stays exactly 0 -> perfectly planar.
    target = source.copy()

    result = kabsch(source, target)

    assert result.degenerate
    assert result.reason is not None


def test_kabsch_requires_minimum_points():
    source = np.zeros((2, 3))
    target = np.zeros((2, 3))

    result = kabsch(source, target, min_points=3)

    assert result.degenerate
    assert result.reason is not None
    assert "need >= 3" in result.reason
