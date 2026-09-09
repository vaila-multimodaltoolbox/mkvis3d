"""Tests for Blender integration and interchange export (openbiomech/blender_io.py)."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest

from openbiomech.blender_io import export_blender_script, export_bvh, generate_blender_python_script
from openbiomech.cli import main
from openbiomech.trial_io import load_trial

FIXTURE_C3D = Path(__file__).parent.parent / "data" / "rec3d_20260826_121305_m.c3d"
TEMPLATE_PATH = Path(__file__).parent.parent / "skeleton_templates" / "sam3dinov3_mhr70.json"


def test_generate_blender_python_script():
    trial = load_trial(FIXTURE_C3D)
    template = json.loads(TEMPLATE_PATH.read_text(encoding="utf-8"))
    script = generate_blender_python_script(trial, name="test_rec3d", skeleton_template=template)

    assert "import bpy" in script
    assert "OpenBiomech_test_rec3d" in script
    assert "scene.render.fps = 100" in script
    assert "scene.frame_end = 631" in script
    assert 'f"OB_{label}"' in script
    assert '"p1"' in script
    assert "setup_openbiomech_scene()" in script
    assert "Bone_" in script


def test_export_blender_script(tmp_path):
    trial = load_trial(FIXTURE_C3D)
    template = json.loads(TEMPLATE_PATH.read_text(encoding="utf-8"))
    out_file = tmp_path / "rec3d_blender.py"
    res = export_blender_script(trial, out_file, skeleton_template=template)

    assert res.exists()
    content = res.read_text(encoding="utf-8")
    assert "setup_openbiomech_scene()" in content


def test_export_bvh(tmp_path):
    trial = load_trial(FIXTURE_C3D)
    out_bvh = tmp_path / "rec3d.bvh"
    res = export_bvh(trial, out_bvh)

    assert res.exists()
    content = res.read_text(encoding="utf-8")
    assert "HIERARCHY" in content
    assert "ROOT p1" in content
    assert "ROOT p70" in content
    assert "MOTION" in content
    assert "Frames: 631" in content


def test_export_bvh_converts_isb_axes_to_bvh_up_axes(tmp_path):
    """ISB trials are X=ML, Y=AP/forward, Z=up; BVH files are X=right, Y=up,
    Z=forward. A raw pass-through would put the subject's vertical axis into
    BVH's forward channel, so the exported motion opens on its side / facing
    the wrong way in Blender."""
    from openbiomech.marker_trial import MarkerTrial

    trial = MarkerTrial(
        labels=("p1",),
        rate_hz=100.0,
        xyz=np.array([[[1.0, 2.0, 3.0]]]),  # ML=1, AP/forward=2, up=3
        residuals=np.zeros((1, 1)),
    )
    out_bvh = tmp_path / "single_point.bvh"
    export_bvh(trial, out_bvh)

    motion_line = out_bvh.read_text(encoding="utf-8").splitlines()[-1]
    x, y, z = (float(v) for v in motion_line.split())
    assert (x, y, z) == pytest.approx((1.0, 3.0, -2.0))


def test_export_bvh_matches_golden_vaila_bvh_axes(tmp_path):
    """`data/rec3d_20260826_121305.bvh` is the same trial exported by vailá's
    own (already Blender-correct) BVH writer. Our export must reproduce its
    axis convention on marker p1's first frame, not just be internally
    consistent."""

    def first_motion_xyz(path: Path) -> tuple[float, float, float]:
        line = next(
            ln
            for ln in path.read_text(encoding="utf-8").splitlines()
            if ln and ln[0] in "-0123456789"
        )
        x, y, z = (float(v) for v in line.split()[:3])
        return x, y, z

    golden_bvh = FIXTURE_C3D.with_name("rec3d_20260826_121305.bvh")
    golden_p1 = first_motion_xyz(golden_bvh)

    trial = load_trial(FIXTURE_C3D)
    out_bvh = tmp_path / "axis_check.bvh"
    export_bvh(trial, out_bvh)
    our_p1 = first_motion_xyz(out_bvh)

    assert our_p1 == pytest.approx(golden_p1, abs=1e-4)


@pytest.mark.skipif(
    not shutil.which("blender"), reason="Blender executable not installed in system"
)
def test_blender_headless_execution(tmp_path):
    """Run Blender in background mode to verify generated script execution."""
    trial = load_trial(FIXTURE_C3D)
    template = json.loads(TEMPLATE_PATH.read_text(encoding="utf-8"))
    out_file = tmp_path / "blender_test.py"
    export_blender_script(trial, out_file, skeleton_template=template)

    cmd = ["blender", "--background", "--python", str(out_file)]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0
    assert "[OpenBiomech] Import complete!" in proc.stdout


@pytest.mark.skipif(
    not shutil.which("blender"), reason="Blender executable not installed in system"
)
def test_blender_native_bvh_import(tmp_path):
    """Run Blender in background mode to verify native BVH import."""
    trial = load_trial(FIXTURE_C3D)
    out_bvh = tmp_path / "mocap.bvh"
    export_bvh(trial, out_bvh)

    expr = f"import bpy; bpy.ops.import_anim.bvh(filepath=r'{out_bvh}'); print('BVH_OK')"
    cmd = ["blender", "--background", "--python-expr", expr]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0
    assert "BVH_OK" in proc.stdout


def test_cli_blender_command(tmp_path):
    out_py = tmp_path / "cli_blender.py"
    rc = main(
        ["blender", str(FIXTURE_C3D), "--output", str(out_py), "--skeleton", "sam3dinov3_mhr70"]
    )
    assert rc == 0
    assert out_py.exists()
    assert "OpenBiomech" in out_py.read_text()


def test_cli_bvh_command(tmp_path):
    out_bvh = tmp_path / "cli_mocap.bvh"
    rc = main(["bvh", str(FIXTURE_C3D), "--output", str(out_bvh)])
    assert rc == 0
    assert out_bvh.exists()
    assert "HIERARCHY" in out_bvh.read_text()
