# Session Handoff: Browser Video Auto-Compress (mp4v → *_compress.mp4)

- **Status:** Completed
- **Current State:**
  - MPEG-4 Part 2 (`mp4v`) overlays fail in HTML5 video; H.264 works.
  - `openbiomech/video_compat.py` probes codecs and re-encodes via ffmpeg (NVENC when available) to `{stem}_compress.mp4` beside the source.
  - GUI: Load Video uses host zenity dialog (`/api/pick_and_ensure_video`); companion/`--video` use `/api/ensure_browser_video`; file-picker uploads use authenticated `/api/transcode_upload`.
  - Auth bug fixed: session token from `location.hash`, not `boot.token`.
  - Debug instrumentation removed after user confirmation.
  - Tests: `tests/test_video_compat.py` (3).
- **What Worked:** Auto-compress + sibling `_compress.mp4` + load playable URL.
- **Failed Approaches:** Suggest-only ffmpeg message; blob playback of mp4v.
- **Open Questions & Next Steps:** None for this bug.
