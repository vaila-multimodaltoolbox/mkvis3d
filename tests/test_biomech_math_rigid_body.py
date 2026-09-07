"""Synthetic ground-truth test for Kabsch rigid-body registration."""

from __future__ import annotations

import numpy as np
import pytest

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


def test_kabsch_accepts_a_coplanar_marker_cluster():
    """A planar cluster is a well-posed rigid fit, not a degenerate one.

    This asserts the opposite of what the scaffold originally did. The guard
    was inherited from vailá's `umeyama_alignment`, which estimates a *scale*
    and so genuinely needs rank-3 points; a rigid fit does not. The old
    behaviour rejected every flat technical cluster — including the standard
    three-marker cluster README.md §3.2 describes.
    """
    rng = np.random.default_rng(1)
    n = 8
    source = np.zeros((n, 3))
    source[:, 0] = rng.normal(size=n)
    source[:, 1] = rng.normal(size=n)
    # z stays exactly 0 -> perfectly planar, but not collinear.
    R_true = np.array([[0.0, 0.0, 1.0], [0.0, 1.0, 0.0], [-1.0, 0.0, 0.0]])
    t_true = np.array([1.0, 2.0, 3.0])
    target = source @ R_true.T + t_true

    result = kabsch(source, target)

    assert not result.degenerate
    assert result.R is not None
    assert result.t is not None
    assert np.allclose(result.R, R_true, atol=1e-9)
    assert np.allclose(result.t, t_true, atol=1e-9)
    assert result.max_residual < 1e-9


def test_kabsch_requires_minimum_points():
    source = np.zeros((2, 3))
    target = np.zeros((2, 3))

    result = kabsch(source, target, min_points=3)

    assert result.degenerate
    assert result.reason is not None
    assert "need >= 3" in result.reason


def test_kabsch_flags_collinear_source_as_degenerate():
    """Markers strung along one line leave the rotation about that line free."""
    direction = np.array([1.0, 2.0, -0.5])
    source = np.outer(np.linspace(-1.0, 1.0, 6), direction)
    target = source.copy()

    result = kabsch(source, target)

    assert result.degenerate
    assert result.reason is not None
    assert "collinear" in result.reason


def test_kabsch_rejects_a_reflection():
    """A mirrored target must yield a proper rotation, never det(R) = -1."""
    rng = np.random.default_rng(5)
    source = rng.normal(size=(10, 3))
    target = source * np.array([1.0, 1.0, -1.0])  # reflect through the xy-plane

    result = kabsch(source, target)

    assert not result.degenerate
    assert result.R is not None
    assert np.isclose(np.linalg.det(result.R), 1.0, atol=1e-12)
    # A reflection is not a rigid motion, so the fit cannot be exact.
    assert result.rms_residual > 1e-6


def test_kabsch_recovers_a_180_degree_rotation():
    """The trace-based branch of quaternion conversion is worst-conditioned here."""
    rng = np.random.default_rng(6)
    source = rng.normal(size=(12, 3))
    R_true = np.diag([1.0, -1.0, -1.0])  # 180° about x, det = +1
    target = source @ R_true.T

    result = kabsch(source, target)

    assert not result.degenerate
    assert result.R is not None
    assert np.allclose(result.R, R_true, atol=1e-9)
    assert result.max_residual < 1e-9


def test_kabsch_is_exact_for_the_minimum_three_points():
    rng = np.random.default_rng(12)
    source = rng.normal(size=(3, 3))
    R_true = np.array([[0.0, -1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, 1.0]])
    t_true = np.array([0.3, -0.7, 2.0])
    target = source @ R_true.T + t_true

    result = kabsch(source, target)

    assert not result.degenerate
    assert result.R is not None
    assert result.t is not None
    assert result.n_points == 3
    assert np.allclose(result.R, R_true, atol=1e-9)
    assert np.allclose(result.t, t_true, atol=1e-9)


def test_kabsch_rejects_mismatched_shapes():
    with pytest.raises(ValueError, match=r"\(N, 3\)"):
        kabsch(np.zeros((5, 3)), np.zeros((4, 3)))
    with pytest.raises(ValueError, match=r"\(N, 3\)"):
        kabsch(np.zeros((5, 2)), np.zeros((5, 2)))
