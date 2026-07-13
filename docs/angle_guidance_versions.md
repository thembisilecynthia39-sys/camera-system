# YOLO11 Angle Capture Guidance Versions

Last updated: 2026-06-26

## Goal

Guide the operator to capture one object at the required reconstruction angles:

```text
0, 45, 90, 135, 180, 225, 270, 315
```

`360` is treated as the loop-complete return to `0`, not a ninth required angle.

YOLO11 is responsible for detecting the target object and giving object-region evidence. The first production versions do not ask YOLO11 to infer the physical angle. The operator rotates the object to the prompted angle and confirms capture in the GUI.

## Version Plan

### V1: Guided Manual Angles With YOLO Target Gate

Implemented behavior:

- GUI prompts the next angle in the 8-angle sequence.
- User manually rotates the object and clicks `Capture Photo`.
- YOLO/subprocess detection must find the target object before capture is accepted.
- If YOLO does not detect the object, the GUI can fall back to a lightweight center-object contour detector so plain boxes can still be captured.
- When YOLO returns multiple detections, the selector prefers the detection closest to the image center over a higher-confidence object near the edge.
- Quality scoring checks blur, exposure, texture, object position and cross-camera timestamp spread.
- Accepted captures advance to the next missing angle.
- After `315`, the guide shows the loop as complete with `360 deg complete`.
- Duplicate captures at the same angle are blocked unless the new readiness score is meaningfully better.
- Quality thresholds are tuned for inexpensive USB2.0 webcams: the system tolerates moderate blur, lower ORB feature counts and wider timestamp spread as long as the target is detected and frames are not severely unusable.

This version uses YOLO when possible, but supports a contour fallback for plain boxes and other untrained calibration objects.

Important Jetson note: the current local `multiwebcam.toml` uses `target_class_ids = [0]`, which means the TensorRT YOLO path is filtered to COCO class `0` (`person`). A plain cardboard/plastic box will usually not pass that filter. For a real box detector, train/export a custom YOLO model or remove/change the class filter if the target class exists in the model.

The current local `multiwebcam.toml` no longer sets `target_class_ids`, so YOLO can report any class it knows. This is intentional because the target can be a box, book, cup, rabbit-shaped object or another small central object. The capture guide treats the central object as the target instead of requiring one fixed class.

Current USB2.0-friendly thresholds:

- Blur is only hard-blocked below very low sharpness.
- Low texture is only hard-blocked when ORB features are extremely sparse.
- Timestamp spread is tolerated up to a wider range before becoming a hard failure.
- One weak camera marks the capture as warning instead of immediately making the whole set bad.
- Minimum readiness for capture is `50%` when the target is detected.

### V2: Better Operator Feedback

Planned behavior:

- Show clearer per-camera target status: found/not found, confidence, centeredness.
- Convert generic quality reasons into actionable text such as move object left, improve light, wait for focus, reduce glare.
- Highlight the camera that is blocking readiness.
- Persist a compact capture checklist in the GUI so the user can see all 8 angles at once.

### V3: Retake And Review Workflow

Planned behavior:

- Add a review panel for saved angles.
- Allow selecting an angle and replacing it with a better capture.
- Rank completed angles by readiness and recommend the weakest retake after the full loop is complete.
- Keep `360` as a completion/closure cue.

### V4: Optional Automatic Angle Evidence

Possible future behavior:

- Use a turntable encoder, AprilTag/ArUco marker, or a dedicated orientation classifier to estimate angle.
- Compare estimated angle against the GUI-selected expected angle.
- Warn when the object appears to be at the wrong angle.

This should not be part of V1 because normal YOLO object detection does not know the object's rotation angle.

## Current Runbook

Start the GUI:

```bash
cd /home/lab/3DGS/Multcamera/multiwebcam
./.venv/bin/python -m multiwebcam
```

Use the grid view:

1. Watch the `Guide`, `Now`, `Next`, and `Done` labels.
2. Rotate the object to the prompted angle.
3. Wait until YOLO finds the target and `Now` is acceptable.
4. Click `Capture Photo`.
5. Continue until `Next: 360 deg complete`.
