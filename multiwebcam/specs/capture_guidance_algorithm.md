# Capture Guidance Algorithm Research

## Goal

The grid GUI should use the lower-right status space to guide an operator through a fixed 360-degree still-image capture sequence. The operator captures the object/scene at nominal angles:

`0, 45, 90, 135, 180, 225, 270, 315`

`360` is equivalent to `0` for coverage. It can be shown as the loop-complete target, but it should not count as a ninth required viewpoint unless the capture procedure intentionally needs a duplicate closure frame.

The UI needs two answers in real time:

1. `Can I capture now?`
2. `Which angle should I capture next?`

## Existing Evidence

The project already computes lightweight live quality in `src/multiwebcam/quality/metrics.py`:

- sharpness: variance of Laplacian on grayscale frames
- brightness and clipping percentages
- ORB feature count
- cross-camera timestamp spread

`src/multiwebcam/ui/views/grid_view.py` already displays a global quality label through `GridView.update_quality()`, and `src/multiwebcam/snapshot.py` already persists per-shot quality into `captures/capture_001/quality.csv`.

This means the capture guide can be built as an extension of the current quality path instead of a separate OpenCV display.

## Recommended Algorithm

Use a rule-based multi-score first. It is transparent, fast enough for live Qt polling, and matches the current code style.

## Decision

The selected first implementation is:

`sparse-reconstruction-inspired heuristic guidance`

That means:

- use sparse-reconstruction capture requirements as the design target
- do not run online SfM in the Qt polling loop
- expose a live percentage that estimates reconstruction readiness and angle coverage
- keep an optional offline validation hook open for later COLMAP-based checking

### Why this wins here

| Option | Reconstruction fidelity | Runtime cost | UI latency | Engineering risk | Fit for this repo |
| --- | --- | --- | --- | --- | --- |
| Run COLMAP sparse matching after every shot | Highest | High | Poor | High | Poor |
| Learned Next-Best-View / trained predictor | Potentially high | Medium to high | Medium | High | Poor |
| Rule-based online score from blur, features, overlap, angle bins | Medium to high | Low | Good | Low | Best |

The core reason is that the GUI needs a continuously updating percentage and a next-angle suggestion. Online SfM is more accurate, but too slow and too brittle for that interaction loop. A lightweight heuristic is weaker as a reconstruction oracle, but strong enough as an operator aid.

### 1. Per-frame quality score

Convert each existing `FrameQuality` to a normalized score:

```text
sharpness_score = clamp((sharpness - 40) / (160 - 40), 0, 1)
brightness_score = triangular score, best near 120-160 gray mean
clipping_score = 1 - clamp((underexposed_pct + overexposed_pct) / 10, 0, 1)
feature_score = clamp(feature_count / 700, 0, 1)
```

Recommended weighted frame score:

```text
frame_score =
    0.30 * sharpness_score +
    0.25 * brightness_score +
    0.25 * feature_score +
    0.20 * clipping_score
```

### 2. Multi-camera capture readiness

Aggregate all active cameras conservatively:

```text
camera_score = 0.70 * median(frame_scores) + 0.30 * min(frame_scores)
sync_score = clamp(1 - timestamp_spread_ms / 150, 0, 1)
capture_readiness = 100 * (0.85 * camera_score + 0.15 * sync_score)
```

Suggested labels:

- `>= 80`: Ready
- `60-79`: Usable, but warn
- `< 60`: Do not capture

### 3. Angle coverage score

Keep a capture state for the eight required angle bins. Each accepted still set stores:

- target angle
- frame id
- readiness score
- per-camera quality metrics
- optional feature-overlap score with neighboring accepted angles

Coverage percentage:

```text
angle_coverage = accepted_bins / 8
quality_coverage = average(best_score_per_bin) / 100
progress_percent = 100 * (0.65 * angle_coverage + 0.35 * quality_coverage)
```

This makes the dynamic percentage meaningful: it rises when the operator covers more angles, but poor captures still hold the score down.

### 4. Next-angle suggestion

Use missing-bin first:

```text
if any required angle is missing:
    suggest nearest missing angle in capture order
else:
    suggest the accepted angle with the lowest score for retake
```

For the first implementation, do not try to estimate physical camera angle from the live image. The user can select or confirm the current angle. This is much more reliable than inferring angle from image content without a marker, IMU, turntable encoder, or already reconstructed geometry.

### 5. Optional overlap/redundancy check

After at least two angles are captured, compare the current candidate frame against the nearest accepted angle using ORB descriptors and brute-force Hamming matching. Use this only as a warning:

```text
if good_matches_to_previous_angle is very low:
    warn "low overlap; rotate less or improve texture"
if good_matches_to_same_angle is very high:
    warn "duplicate view; move to next angle"
```

This should not replace the explicit angle bins. It is a quality guard, not a robust pose estimator.

## Final Chosen Scoring Model

The first production version should use exactly three live outputs:

### A. `capture_readiness`

This answers: `should the operator capture now?`

Inputs:

- normalized sharpness
- normalized exposure / clipping
- normalized feature count
- sync score across cameras

Output:

- `0-100`
- label: `READY`, `BORDERLINE`, or `WAIT`

### B. `coverage_progress`

This answers: `how complete is the 8-angle loop?`

Inputs:

- accepted angle bins out of 8
- best readiness retained for each bin

Output:

- `0-100`
- can drive the lower-right dynamic percentage directly

### C. `matchability_warning`

This answers: `is this likely to match neighboring views in sparse reconstruction?`

Inputs:

- ORB match count / inlier ratio against nearest captured angle
- duplicate similarity against same-angle retakes

Output:

- warning text only, not the main percentage

Reason for keeping this separate: overlap evidence is useful, but noisier than blur or feature count. It should influence operator guidance without destabilizing the main progress percentage.

## Alternatives Considered

### Full SfM/COLMAP feedback

Running feature extraction/matching or incremental reconstruction after each shot gives stronger evidence, but it is too slow and brittle for a live lower-right GUI percentage. It is better as an optional post-capture validation step.

### Learned Next-Best-View

Next-Best-View methods optimize view utility for reconstruction, but most require a partial 3D model, depth observations, a simulator, a trained model, or robotic pose control. That is not the right first implementation for this webcam GUI.

### Automatic angle estimation from images

Without AprilTags/ArUco markers, a turntable encoder, IMU, or known camera poses, estimating the exact object rotation angle from normal RGB frames is unreliable. It can become a future feature if the capture setup adds a printed marker or hardware angle signal.

## GUI Mapping

Use the bottom-right status area for a compact guidance panel:

```text
Capture Guide: 38%
Next: 135 deg
Now: 82% READY
Done: 0 45 90
Retake: 90 deg soft
```

The existing `Quality: --` label can become a small widget with:

- progress percentage
- current readiness percentage
- next recommended angle
- warning reason

The `Capture Photo` button should either use the selected angle or prompt/step through the expected angle before saving.

## Suggested Implementation Steps

1. Add normalized scores to `FrameQuality` / `CaptureSetQuality` without removing the existing textual summaries.
2. Add a small `capture_guidance.py` module that owns angle bins, progress percentage, next-angle selection, and retake selection.
3. Extend snapshot metadata with `angle_deg`, `readiness_score`, and `progress_percent`.
4. Replace the lower-right quality label with a compact guide widget in `GridView`.
5. Add tests for score normalization, angle-bin progress, next-angle suggestion, and retake selection.

## References

- COLMAP FAQ: feature choice depends on overlap, texture, and illumination consistency; SIFT is robust for moderate/high overlap and sufficient texture, while learned features can help under harder view or lighting changes. https://colmap.github.io/faq.html
- Nerfstudio custom data guide: self-captured data should be overlapping and non-blurry; Polycam capture guidance also emphasizes many viewpoints, good lighting, slow motion, and reduced blur. https://docs.nerf.studio/quickstart/custom_dataset.html
- OpenCV ORB documentation: ORB detects stable keypoints and computes oriented BRIEF descriptors; it is already aligned with the project's lightweight feature-count metric. https://docs.opencv.org/4.x/db/d95/classcv_1_1ORB.html
- Next-Best-View literature frames the problem as choosing views that maximize reconstruction utility, but these methods are heavier than the current webcam GUI needs. Example: Bag of Views, an appearance-based NBV approach. https://arxiv.org/abs/2307.05832
