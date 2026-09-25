"""Synthetic broadcast cameras and rendered pitches for the soccer_field tests."""

from __future__ import annotations

import cv2
import numpy as np

from openbiomech.soccer_field.camera import Camera, in_view, project
from openbiomech.soccer_field.kiki49 import ground_lines, load_kiki49

WIDTH, HEIGHT = 1280, 720


def look_at(
    centre: tuple[float, float, float],
    target: tuple[float, float, float],
    f: float = 1400.0,
    width: int = WIDTH,
    height: int = HEIGHT,
    dist: np.ndarray | None = None,
) -> Camera:
    """Pinhole camera at ``centre`` looking at ``target`` (z up, image y down)."""
    C = np.asarray(centre, dtype=np.float64)
    z = np.asarray(target, dtype=np.float64) - C
    z /= np.linalg.norm(z)
    x = np.cross(z, [0.0, 0.0, 1.0])
    x /= np.linalg.norm(x)
    y = np.cross(z, x)
    R = np.vstack([x, y, z])
    K = np.array([[f, 0.0, width / 2.0], [0.0, f, height / 2.0], [0.0, 0.0, 1.0]])
    return Camera(K=K, R=R, t=-R @ C, dist=dist)


def left_camera() -> Camera:
    """Main-stand camera framing the left penalty box and goal."""
    return look_at((-25.0, -55.0, 22.0), (-40.0, 0.0, 0.0))


def render_pitch(cam: Camera, shift_px: float = 0.0) -> np.ndarray:
    """Green image with the painted markings of ``cam`` drawn in white
    (optionally misregistered by ``shift_px`` along both image axes)."""
    img = np.full((HEIGHT, WIDTH, 3), (40, 120, 40), dtype=np.uint8)
    for poly in ground_lines(0.1):
        uv, depth = project(poly, cam)
        uv = uv[depth > 0] + shift_px
        if len(uv) >= 2:
            cv2.polylines(img, [np.round(uv).astype(np.int32)], False, (255, 255, 255), 2)
    return img


def projected_kiki(cam: Camera) -> tuple[np.ndarray, np.ndarray]:
    """(uv (49, 2), in-view mask (49,)) of every kiki point."""
    uv, depth = project(load_kiki49().xyz, cam)
    return uv, in_view(uv, depth, WIDTH, HEIGHT)
