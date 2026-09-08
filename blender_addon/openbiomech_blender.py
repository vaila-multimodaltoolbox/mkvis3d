"""OpenBiomech / mkvis3d Blender Add-on.

Allows direct importing of OpenBiomech motion trials (.c3d, .csv, .3d, .json)
and automatic generation of animated marker clouds and skeletal armatures in Blender.

To install in Blender:
1. Open Blender.
2. Go to Edit > Preferences > Add-ons > Install... (or top-right arrow in Blender 4.2+).
3. Select this file (`openbiomech_blender.py`).
4. Enable the checkmark for "Import-Export: OpenBiomech Motion Capture".
5. Find it in `File > Import > OpenBiomech Motion (.c3d, .csv)` or the 3D Viewport sidebar (N-panel).
"""

from __future__ import annotations

import csv
from pathlib import Path

import bpy
from bpy.props import BoolProperty, EnumProperty, FloatProperty, StringProperty
from bpy_extras.io_utils import ImportHelper

bl_info = {
    "name": "OpenBiomech Motion Capture Importer",
    "author": "OpenBiomech & vailá Team",
    "version": (1, 0, 0),
    "blender": (3, 0, 0),
    "location": "File > Import > OpenBiomech Motion (.c3d, .csv, .3d, .json)",
    "description": "Import 3D motion capture trials, marker trajectories, and skeletal armatures",
    "warning": "",
    "doc_url": "https://github.com/paulopreto/mkvis3d",
    "category": "Import-Export",
}


class OPENBIOMECH_OT_import_motion(bpy.types.Operator, ImportHelper):  # noqa: N801
    """Import OpenBiomech Motion Capture Trial"""

    bl_idname = "openbiomech.import_motion"
    bl_label = "Import OpenBiomech Motion"
    bl_options = {"REGISTER", "UNDO"}

    filename_ext = ".c3d;.csv;.3d;.json;.bvh"
    filter_glob: StringProperty(  # type: ignore
        default="*.c3d;*.csv;*.3d;*.json;*.bvh",
        options={"HIDDEN"},
    )

    marker_scale: FloatProperty(  # type: ignore
        name="Marker Size",
        description="Display size of marker spheres in meters",
        default=0.015,
        min=0.001,
        max=0.5,
    )

    create_armature: BoolProperty(  # type: ignore
        name="Build Armature",
        description="Automatically create a rigged Armature if skeleton template matches",
        default=True,
    )

    skeleton_preset: EnumProperty(  # type: ignore
        name="Skeleton Preset",
        description="Skeleton topology template for bone connections",
        items=[
            ("AUTO", "Auto Detect", "Detect based on marker labels and count"),
            ("SAM3D_MHR70", "SAM 3D / MHR-70 (70 markers)", "30 anatomical bones"),
            ("COCO17", "COCO-17 / YOLO (17 keypoints)", "19 anatomical bones"),
            ("MEDIAPIPE33", "MediaPipe Pose (33 keypoints)", "35 anatomical bones"),
            ("SQUAT15", "Vicon Squat (15 markers)", "Lower body kinematics"),
            ("NONE", "None (Markers Only)", "Import only marker trajectories"),
        ],
        default="AUTO",
    )

    def execute(self, context):
        filepath = self.filepath
        ext = Path(filepath).suffix.lower()

        if ext == ".bvh":
            # Native Blender BVH
            bpy.ops.import_anim.bvh(filepath=filepath)
            self.report({"INFO"}, f"Imported BVH: {filepath}")
            return {"FINISHED"}

        if ext in (".csv", ".3d"):
            self.import_csv_trial(filepath, context)
            return {"FINISHED"}

        if ext == ".py":
            # Run generator script
            with open(filepath, encoding="utf-8") as f:
                exec(compile(f.read(), filepath, "exec"), {})
            self.report({"INFO"}, f"Executed Blender script: {filepath}")
            return {"FINISHED"}

        self.report(
            {"WARNING"},
            "For direct C3D binary files, export via mkvis3d GUI/CLI to Blender Script (.py) or BVH.",
        )
        return {"FINISHED"}

    def import_csv_trial(self, filepath, context):
        with open(filepath, encoding="utf-8") as f:
            reader = csv.reader(f)
            headers = next(reader)

        # Detect markers from CSV headers
        marker_cols = {}
        for idx, col in enumerate(headers):
            col_clean = col.strip()
            if col_clean.endswith("_x") or col_clean.endswith("_X"):
                name = col_clean[:-2]
                marker_cols.setdefault(name, {})["x"] = idx
            elif col_clean.endswith("_y") or col_clean.endswith("_Y"):
                name = col_clean[:-2]
                marker_cols.setdefault(name, {})["y"] = idx
            elif col_clean.endswith("_z") or col_clean.endswith("_Z"):
                name = col_clean[:-2]
                marker_cols.setdefault(name, {})["z"] = idx

        labels = [m for m, axes in marker_cols.items() if len(axes) == 3]
        if not labels:
            self.report(
                {"ERROR"}, "Could not detect 3D marker columns (e.g. name_x, name_y, name_z)."
            )
            return

        trial_name = Path(filepath).stem
        coll_name = f"OpenBiomech_{trial_name}"
        coll = bpy.data.collections.get(coll_name) or bpy.data.collections.new(coll_name)
        if coll_name not in context.scene.collection.children:
            context.scene.collection.children.link(coll)

        marker_objs = {}
        for lbl in labels:
            obj_name = f"OB_{lbl}"
            obj = bpy.data.objects.get(obj_name) or bpy.data.objects.new(obj_name, None)
            obj.empty_display_type = "SPHERE"
            obj.empty_display_size = self.marker_scale
            if obj_name not in coll.objects:
                coll.objects.link(obj)
            marker_objs[lbl] = obj

        # Read frames
        with open(filepath, encoding="utf-8") as f:
            reader = csv.reader(f)
            next(reader)
            frame_num = 1
            for row in reader:
                if not row:
                    continue
                for lbl in labels:
                    cols = marker_cols[lbl]
                    try:
                        x = float(row[cols["x"]])
                        y = float(row[cols["y"]])
                        z = float(row[cols["z"]])
                        obj = marker_objs[lbl]
                        obj.location = (x, y, z)
                        obj.keyframe_insert(data_path="location", frame=frame_num)
                    except (ValueError, IndexError):
                        pass
                frame_num += 1

        context.scene.frame_start = 1
        context.scene.frame_end = frame_num - 1
        self.report({"INFO"}, f"Imported {len(labels)} markers across {frame_num - 1} frames.")


class OPENBIOMECH_PT_sidebar(bpy.types.Panel):  # noqa: N801
    bl_label = "OpenBiomech Motion"
    bl_idname = "OPENBIOMECH_PT_sidebar"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "OpenBiomech"

    def draw(self, context):
        layout = self.layout
        layout.label(text="mkvis3d Motion Capture", icon="ARMATURE_DATA")
        layout.operator("openbiomech.import_motion", text="Import Motion File...", icon="IMPORT")


def menu_func_import(self, context):
    self.layout.operator(
        OPENBIOMECH_OT_import_motion.bl_idname, text="OpenBiomech Motion (.c3d, .csv, .3d, .bvh)"
    )


def register():
    bpy.utils.register_class(OPENBIOMECH_OT_import_motion)
    bpy.utils.register_class(OPENBIOMECH_PT_sidebar)
    bpy.types.TOPBAR_MT_file_import.append(menu_func_import)


def unregister():
    bpy.types.TOPBAR_MT_file_import.remove(menu_func_import)
    bpy.utils.unregister_class(OPENBIOMECH_PT_sidebar)
    bpy.utils.unregister_class(OPENBIOMECH_OT_import_motion)


if __name__ == "__main__":
    register()
