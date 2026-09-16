"""Skeleton model definitions, lateralization, and side-specific color palettes.

Follows the color conventions established in vaila/sam3dinov3.py and
vaila/sam3dinov3_visualize.py:
- Left side: Green (0, 255, 0)
- Right side: Orange (255, 128, 0)
- Center / Midline / Cross-side: Light Blue (51, 153, 255)
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any

# Color definitions matching vaila/sam3dinov3.py & vaila/sam3dinov3_visualize.py
COLOR_LEFT_RGB: tuple[int, int, int] = (0, 255, 0)
COLOR_RIGHT_RGB: tuple[int, int, int] = (255, 128, 0)
COLOR_CENTER_RGB: tuple[int, int, int] = (51, 153, 255)

COLOR_LEFT_HEX: str = "#00ff00"
COLOR_RIGHT_HEX: str = "#ff8000"
COLOR_CENTER_HEX: str = "#3399ff"

SIDE_COLORS_RGB: dict[str, tuple[int, int, int]] = {
    "left": COLOR_LEFT_RGB,
    "right": COLOR_RIGHT_RGB,
    "center": COLOR_CENTER_RGB,
}

SIDE_COLORS_HEX: dict[str, str] = {
    "left": COLOR_LEFT_HEX,
    "right": COLOR_RIGHT_HEX,
    "center": COLOR_CENTER_HEX,
}


def get_marker_side(name: str) -> str:
    """Determine whether a marker / keypoint belongs to the left, right, or center of the body.

    Recognizes standard conventions across OpenPose, COCO, Halpe, SAM3D MHR-70,
    Sapiens2 Goliath-308, MediaPipe, FIFA, Vicon/Plug-in Gait, Helen Hayes, and Portuguese labels.
    """
    if not name or not isinstance(name, str):
        return "center"
    clean = name.strip()

    # 1. Explicit prefixes (English & Portuguese)
    if re.search(r"^(left[-_.]|l[-_.]|e[-_]|esq[-_]|esquerdo[-_]|esquerda[-_])", clean, re.I):
        return "left"
    if re.search(r"^(right[-_.]|r[-_.]|d[-_]|dir[-_]|direito[-_]|direita[-_])", clean, re.I):
        return "right"

    # 2. Explicit suffixes
    if re.search(r"[-_.](left|l|esq|esquerdo|esquerda)$", clean, re.I):
        return "left"
    if re.search(r"[-_.](right|r|dir|direito|direita)$", clean, re.I):
        return "right"

    # 3. Explicit infixes (e.g. of_l_eyebrow, of_r_eyebrow, corner_of_l_nostril)
    if re.search(r"[-_.](left|l|esq)[-_.]", clean, re.I):
        return "left"
    if re.search(r"[-_.](right|r|dir)[-_.]", clean, re.I):
        return "right"

    # 4. Standalone words
    if re.search(r"\b(left|esquerdo|esquerda)\b", clean, re.I):
        return "left"
    if re.search(r"\b(right|direito|direita)\b", clean, re.I):
        return "right"

    # 5. Mocap uppercase acronyms: LASI, RASI, LKNE, RKNE, LANK, RANK, etc.
    # Exclude non-lateral words: LIP, LOW, LEG, LUM, RIB, ROOT, REAR
    if re.match(r"^L[A-Z0-9]{2,5}$", clean) and not re.match(r"^(LIP|LOW|LEG|LUM)", clean, re.I):
        return "left"
    if re.match(r"^R[A-Z0-9]{2,5}$", clean) and not re.match(r"^(RIB|ROOT|REAR)", clean, re.I):
        return "right"

    return "center"


def get_bone_side(side_a: str, side_b: str) -> str:
    """Determine the side of a bone connection between two joint endpoints.

    If both endpoints are on the left side, the bone is 'left'.
    If both endpoints are on the right side, the bone is 'right'.
    If either endpoint is center, or they cross sides (e.g. left-shoulder to right-shoulder),
    the bone is 'center'.
    """
    if side_a == "left" and side_b == "left":
        return "left"
    if side_a == "right" and side_b == "right":
        return "right"
    return "center"


def get_side_color_rgb(side: str) -> tuple[int, int, int]:
    """Return the RGB tuple for a given side ('left', 'right', or 'center')."""
    return SIDE_COLORS_RGB.get(side, COLOR_CENTER_RGB)


def get_side_color_hex(side: str) -> str:
    """Return the hex color string for a given side ('left', 'right', or 'center')."""
    return SIDE_COLORS_HEX.get(side, COLOR_CENTER_HEX)


def classify_template_connections(
    template: dict[str, Any],
    trial_labels: Sequence[str] | None = None,
) -> list[dict[str, Any]]:
    """Classify all connections of a skeleton template into left, right, or center with colors."""
    keypoints = template.get("keypoints", [])
    connections = template.get("connections", [])
    results = []

    for conn in connections:
        if not isinstance(conn, (list, tuple)) or len(conn) < 2:
            continue
        a_str, b_str = str(conn[0]), str(conn[1])

        name_a = a_str
        if a_str.lower().startswith("p") and a_str[1:].isdigit():
            p_idx = int(a_str[1:]) - 1
            if p_idx < len(keypoints):
                name_a = keypoints[p_idx]
            elif trial_labels and p_idx < len(trial_labels):
                name_a = trial_labels[p_idx]

        name_b = b_str
        if b_str.lower().startswith("p") and b_str[1:].isdigit():
            p_idx = int(b_str[1:]) - 1
            if p_idx < len(keypoints):
                name_b = keypoints[p_idx]
            elif trial_labels and p_idx < len(trial_labels):
                name_b = trial_labels[p_idx]

        side_a = get_marker_side(name_a)
        side_b = get_marker_side(name_b)
        bone_side = get_bone_side(side_a, side_b)

        results.append(
            {
                "connection": [a_str, b_str],
                "name_a": name_a,
                "name_b": name_b,
                "side_a": side_a,
                "side_b": side_b,
                "side": bone_side,
                "color_rgb": get_side_color_rgb(bone_side),
                "color_hex": get_side_color_hex(bone_side),
            }
        )

    return results
