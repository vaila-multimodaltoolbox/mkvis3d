"""6DoF rigid-body optimal registration (Kabsch algorithm).

Adapted from `/home/preto/data/vaila/vaila/mesh_alignment.py:umeyama_alignment`
(+ `apply_similarity_transform`), with the scale term fixed to `s = 1.0`:
Visual3D-style cluster/segment tracking (README.md §3.2) is a *rigid*
registration, not a similarity transform, so no scale factor is estimated.

Reflection-rejection (`det(R) == +1`) and the near-planar/collinear
degeneracy guard are kept from the source implementation.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class KabschResult:
    """Result of fitting a rigid transform source -> target.

    `degenerate` is True when the source point set is too small or too
    close to planar/collinear for a numerically stable rotation estimate —
    callers must skip a degenerate result rather than trust R/t.
    """

    degenerate: bool
    reason: str | None = None
    R: np.ndarray | None = None
    t: np.ndarray | None = None
    n_points: int = 0
    mean_residual: float = float("inf")
    rms_residual: float = float("inf")
    max_residual: float = float("inf")


def kabsch(
    source: np.ndarray,
    target: np.ndarray,
    *,
    min_points: int = 3,
    planarity_ratio_threshold: float = 1e-3,
) -> KabschResult:
    """Fit a rigid transform (R, t) mapping source points onto target points:
    target_i ~= R @ source_i + t, in the closed-form least-squares sense of
    Kabsch (1976) / Umeyama (1991) with s fixed to 1.

    Args:
        source: (N, 3) array, N >= min_points.
        target: (N, 3) array, same N and row correspondence as source.
        min_points: minimum number of point correspondences required.
        planarity_ratio_threshold: minimum allowed ratio of the smallest to
            largest singular value of the centered source points; below
            this, the source set is treated as too close to planar/collinear
            for a numerically stable rotation and the result is degenerate.

    Returns:
        KabschResult. Check `.degenerate` before using `.R`/`.t`.
    """
    source = np.asarray(source, dtype=np.float64)
    target = np.asarray(target, dtype=np.float64)
    if source.shape != target.shape or source.ndim != 2 or source.shape[1] != 3:
        raise ValueError(
            f"source and target must both be (N, 3) arrays of the same shape, "
            f"got {source.shape} and {target.shape}"
        )
    n = source.shape[0]
    if n < min_points:
        return KabschResult(
            degenerate=True,
            reason=f"only {n} valid point correspondences, need >= {min_points}",
            n_points=n,
        )

    mu_src = source.mean(axis=0)
    mu_tgt = target.mean(axis=0)
    src_c = source - mu_src
    tgt_c = target - mu_tgt

    singular_values = np.linalg.svd(src_c, compute_uv=False)
    if (
        singular_values[0] <= 0
        or (singular_values[-1] / singular_values[0]) < planarity_ratio_threshold
    ):
        ratio = 0.0 if singular_values[0] <= 0 else singular_values[-1] / singular_values[0]
        return KabschResult(
            degenerate=True,
            reason=(
                f"source points are near-planar/collinear "
                f"(smallest/largest singular value ratio {ratio:.2e} < "
                f"{planarity_ratio_threshold:.2e})"
            ),
            n_points=n,
        )

    # H = sum_i (x_i - c_x)(y_i - c_y)^T, per README.md §3.2 — equal (up to
    # the 1/n scale, which cancels in the SVD) to covariance = tgt_c.T @ src_c.
    covariance = (tgt_c.T @ src_c) / n
    U, _D, Vt = np.linalg.svd(covariance)
    d = np.eye(3)
    if np.linalg.det(U) * np.linalg.det(Vt) < 0:
        d[2, 2] = -1.0
    R = U @ d @ Vt
    t = mu_tgt - R @ mu_src

    aligned = source @ R.T + t
    residuals = np.linalg.norm(aligned - target, axis=1)
    return KabschResult(
        degenerate=False,
        R=R,
        t=t,
        n_points=n,
        mean_residual=float(residuals.mean()),
        rms_residual=float(np.sqrt((residuals**2).mean())),
        max_residual=float(residuals.max()),
    )
