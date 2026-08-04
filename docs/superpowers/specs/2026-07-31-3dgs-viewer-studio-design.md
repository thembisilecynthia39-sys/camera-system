# 3DGS Viewer Studio Design

## Objective

Upgrade the existing Camera System result page into a local, desktop-oriented
3DGS roaming and presentation workspace. The workspace should support smooth
interactive navigation, reproducible camera tours, high-quality still/video
rendering, and an explicit visualization mode that displays every Gaussian as
the circumscribed sphere of its original 3D ellipsoid.

The product direction is a lightweight local “Splat Studio” for the Jetson
workstation. It is not intended to become a general-purpose Gaussian cleanup
editor or a hosted publishing service.

## Context and constraints

- Target hardware is Jetson Orin Nano with JetPack 5.1.1, desktop OpenGL, and
  a GPU shared with camera capture and inference.
- The main application is a PySide6/Qt Widgets application using the Fusion
  style and the existing QSS design tokens.
- The primary window is designed at 1600×900 and must remain usable at
  1024×680. Mouse and keyboard are the required inputs; touch is not a release
  requirement.
- The existing result page is
  `src/camera_system_app/ui/pages/result_viewer.py`.
- The existing application adapter is
  `src/camera_system_app/infrastructure/adapters/q3dviewer_adapter.py`.
- Rendering is provided by `3DGSviewer/q3dviewer`, whose Gaussian path uses a
  validated CPU Gaussian array, an OpenGL SSBO, compute-shader preprocessing,
  view-depth sorting, and a premultiplied-alpha splat pass.
- PLY loading already expands the logarithmic scale fields into the
  `GaussianItem.scale` values. The current shader constructs the 3D covariance
  from those scales and renders a 3-sigma projected footprint.
- The current adapter deliberately uses a reduced-cost interactive preview
  while the camera is moving and restores full SH/depth-sorted rendering after
  interaction. This quality distinction is retained and made explicit in the
  new UI.
- `q3dviewer` already provides camera pose access, framebuffer capture, depth
  picking, and renderer performance counters. The standalone `film_maker.py`
  prototype already contains keyframe interpolation and video writing logic,
  while the multiwebcam package contains a Jetson GStreamer H.264 writer path.

## Product goals

### In scope

1. Make the result page a useful, low-glare 3D roaming workspace.
2. Provide standard Gaussian, sphere, and Gaussian-plus-sphere visualization
   modes without changing the source PLY.
3. Provide camera bookmarks and a frame-based camera Timeline.
4. Preview the tour interactively and render it deterministically to an image,
   PNG sequence, or MP4.
5. Expose quality, appearance, output, and performance state clearly.
6. Persist a reproducible viewer project beside a result without modifying the
   reconstruction artifact.
7. Keep capture/inference GPU arbitration, cancellation, and safe shutdown
   semantics intact.

### Out of scope for this design

- Gaussian selection, lasso/brush cleanup, deletion, crop, lock, and undoable
  per-Gaussian editing.
- Multi-splat merging and alignment as a general scene editor.
- Hosted publishing, accounts, social sharing, or a web viewer.
- Collision meshes, WebXR, and browser-specific SOG/LOD pipelines.

These may be separate future products. They are not prerequisites for a good
local roaming and video workflow.

## User workflows

### Inspect and roam

1. Open a completed local PLY from the result page or history.
2. Choose Orbit or Fly mode and navigate the scene.
3. Use frame/reset, standard view presets, grid/axis, and optional camera
   information to establish a reproducible view.
4. Switch between standard splats and the sphere visualization when inspecting
   the distribution and scale of individual Gaussians.

### Author a camera tour

1. Frame a view and add a named shot to the Timeline.
2. Move to the next view and add or update another shot.
3. Set hold time, transition duration, easing, FPS, total length, and loop
   behavior.
4. Play the tour in draft quality and scrub to any frame.

### Render a presentation

1. Select standard or sphere display mode and configure appearance.
2. Choose output resolution, FPS, format, and destination.
3. Start a final render. The UI shows frame progress, encoder status, elapsed
   time, and an estimated remaining duration.
4. Stop safely at a frame boundary if required. A successful render is renamed
   atomically; a cancelled or failed render is not presented as complete.

## UI design

### Page structure

The existing `03 结果查看` navigation item remains in place. The page keeps
the current dark operational surface but replaces the large source-information
card with a compact studio shell:

```text
┌──────────────────────────────────────────────────────────────────────┐
│  Open · Reset · Frame · Orbit/Fly · Display · Fullscreen · Render     │
├───────────────────────────────────────────────┬──────────────────────┤
│                                               │ Inspector            │
│                 3D Viewport                   │ View                 │
│                                               │ Camera               │
│                                               │ Appearance           │
│                                               │ Render               │
├───────────────────────────────────────────────┴──────────────────────┤
│  Timeline: play · stop · frame · keyframes · FPS · duration · loop    │
└──────────────────────────────────────────────────────────────────────┘
```

- The viewport owns the majority of the available space.
- The Inspector is collapsible and defaults to the View section.
- The Timeline is collapsible; it opens automatically after the first shot is
  added.
- Presentation mode hides the navigation rail, Inspector, and Timeline while
  keeping a minimal transport overlay. `Escape` always exits presentation mode.
- At 1024×680, the Inspector and Timeline become mutually exclusive overlays;
  they must not squeeze the viewport below its usable minimum.
- The page continues to follow the existing 16 px body text, 28 px title,
  semantic colors, visible keyboard focus, and dark/light token boundaries.

### Inspector sections

#### View

- Display mode: Standard, Sphere Wireframe, Sphere Solid, Standard + Sphere.
- Sphere radius multiplier, default `3.0σ`.
- Sphere style: wire color, opacity, solid shading, and color source.
- Render quality: Draft, Interactive, Final.
- Grid, axis, center marker, camera info, and bounding-box toggles.
- Background color and optional transparent background for PNG still/sequence
  output. MP4 output always uses an opaque background.

#### Camera

- Orbit/Fly mode.
- FOV and fly speed.
- Frame model, reset camera, and standard axis views.
- Current camera position, target, and FOV as editable numeric values.
- Named shot list with add, update, rename, duplicate, and delete actions.

#### Appearance

- Spherical-harmonics quality: DC, SH degree 1, 2, or 3 where available.
- Exposure and tonemapping controls.
- Global contrast/saturation/brightness controls only when supported by the
  render target.
- Optional vignette and sharpening are post-processing features and may be
  disabled automatically on Jetson when the render budget is exceeded.

#### Render

- Still or video output.
- Standard resolution presets: Current, 1280×720, 1920×1080, and Custom.
- FPS: 24, 25, 30, or 60.
- MP4/H.264 through the Jetson encoder, PNG sequence, and an explicit fallback
  when the hardware encoder is unavailable.
- Output path, estimated frame count, estimated memory, and final quality
  summary.

### Timeline

The Timeline is frame-based rather than wall-clock-timer-based. It provides:

- play/pause and stop;
- previous/next frame;
- previous/next shot;
- current frame and total frames;
- FPS and total length;
- add, update, duplicate, move, and delete shot;
- linear and smooth easing;
- per-shot hold frames;
- loop toggle;
- a visible “Draft preview” or “Final render” state.

The controls are model-backed and keyboard reachable. Timeline playback does not
silently start a final render.

## Display modes and sphere rendering

### Standard Gaussian mode

The current Gaussian path remains the reference rendering mode. It retains
view-dependent SH color, anti-aliased covariance projection, back-to-front
sorting, and the existing interaction preview budget.

### Circumscribed sphere definition

For a Gaussian with center `pw`, principal-axis scales `sx`, `sy`, and `sz`,
the default visualization sphere is:

```text
center = pw
radius = sphere_sigma_multiplier × max(sx, sy, sz)
```

The default multiplier is `3.0`, matching the current projected 3-sigma
footprint. Rotation does not change this radius because the enclosing sphere
depends on the largest principal semi-axis, not its orientation.

The PLY and the CPU Gaussian array remain unchanged. The radius is a derived
display value and is saved only in viewer project settings.

### GPU implementation

The sphere pass must not allocate one Qt object or one independent mesh per
Gaussian. The renderer will use a shared Gaussian GPU buffer and an instanced
sphere-impostor pass:

- one reusable screen-space quad used as a sphere impostor for every instance;
- one instance per Gaussian index;
- the vertex stage projects the center and the radius;
- the fragment stage performs a ray/sphere intersection and reconstructs a
  surface normal for solid shading;
- wireframe mode keeps only a configurable shell near the sphere boundary;
- depth testing is enabled for solid spheres;
- transparent sphere overlays use a controlled alpha and an explicit draw
  order so they do not corrupt the standard splat pass.

The implementation introduces a `GaussianGpuData` owner for the uploaded
SSBO, validated index buffers, and preview indices. A
`GaussianSplatPass` and a `GaussianSpherePass` consume that shared data, while
a `GaussianRenderController` selects one pass or both. This avoids duplicating
the largest model allocation and keeps the public adapter responsible for one
Gaussian display controller rather than two independently loaded models.

### Sphere quality behavior

- During interaction, sphere instances use the same preview index budget as the
  standard path unless the user explicitly selects “All spheres”.
- Final rendering defaults to all Gaussian instances and shows the expected
  cost before starting.
- DC color is the default sphere color source because it is stable and useful
  for technical inspection. Full SH color is available for presentation output.
- The viewport displays the active mode and instance count; it never silently
  presents a decimated final render as complete.

## Camera and Timeline data model

The viewer uses explicit serializable models outside page widget code.

```text
CameraPose
  world_transform
  target
  fov_degrees

CameraShot
  id
  name
  frame
  pose
  hold_frames
  easing

CameraTimeline
  fps
  total_frames
  loop
  shots[]

DisplaySettings
  mode
  sphere_sigma_multiplier
  sphere_style
  sphere_alpha
  sphere_color_source
  quality_preset
  overlays

RenderSettings
  output_kind
  width
  height
  fps
  codec
  output_path
  transparent_background
```

Project validation accepts `transparent_background` only for PNG stills and
PNG sequences. It rejects the combination with MP4 before a render session is
created.

Camera rotation is interpolated with a rotation-safe representation (SO(3)
exponential interpolation or quaternion slerp), not by independently blending
Euler angles. Position, target, FOV, and hold frames use deterministic frame
indices and easing.

Display and appearance settings are project-level render state in version 1;
camera shots own camera pose and timing only. A final render snapshots the
project-level settings at start so changing a panel during rendering cannot
change the output halfway through.

### Persistence

Version 1 stores viewer projects as a `.splatview.json` sidecar by default.
“Save As” may choose another path with the same extension and schema. The
project contains:

- a format version;
- the source PLY path relative to the project where possible;
- source file size and SHA-256 to detect a mismatched artifact;
- display settings;
- camera pose and Timeline;
- render settings;
- the last active panel and presentation preferences.

Saving a viewer project never overwrites the reconstruction PLY. A dirty
project prompts before loading another source or leaving the result page.

## Rendering and video pipeline

### Preview path

The existing visible `QOpenGLWidget` remains the interactive preview. Camera
movement enables reduced-cost rendering, and the end of interaction requests
one full-quality refresh. Timeline playback uses a draft quality setting unless
the user explicitly requests final playback.

### Final path

The first implementation keeps OpenGL operations on the GUI-owned context;
the CPU encoder is the only worker-thread stage. This avoids calling a
`QOpenGLWidget` context from a worker thread.

1. `FinalRenderController` validates the project and output settings.
2. A bounded frame scheduler advances an explicit frame index.
3. The renderer sets the exact `CameraPose`, display mode, quality, and output
   dimensions for that frame.
4. The scene is rendered into an output-size framebuffer object, independent
   of the visible viewport size.
5. Pixel data is copied while the GL context is current and placed into a
   bounded encoder queue.
6. `FrameEncoder` writes PNG frames or feeds the Jetson GStreamer H.264 path;
   PyAV is the fallback backend.
7. If the encoder queue is full, rendering pauses. Final output never drops
   frames to maintain the requested frame count.
8. The temporary output is atomically renamed only after all frames and the
   encoder trailer have been finalized.

The scheduler is frame-count-driven, not real-time-driven. A 30 FPS output may
take longer than 30 frames per second to produce on a large model; that is
reported as render progress rather than hidden behind a spinner.

### Render state arbitration

- Starting a final render requires the result page to own the render GPU
  resources, using the existing capture/review arbitration signal.
- Capture or inference is not silently interrupted. The UI explains the
  resource transition and disables conflicting actions until it completes.
- The active display mode, sphere settings, overlays, camera, and appearance
  settings are frozen for the render session.
- The user can cancel at a frame boundary. Temporary files and encoder state
  are cleaned up, and the cancelled output is not added to history.

## Error handling

- **Invalid or mismatched project:** show the source mismatch and offer to
  reopen the current PLY with default camera settings.
- **Sphere shader initialization failure:** retain the standard renderer,
  disable sphere modes, and show a persistent actionable error.
- **Insufficient GPU memory:** report the estimated allocation, offer Draft
  preview or a lower-detail preview, and never label a partial final render as
  complete.
- **Encoder unavailable:** offer PNG sequence output and show the missing
  encoder/backend diagnostic.
- **Disk full or write failure:** stop at the current frame, preserve the error
  message and remove only the temporary incomplete output.
- **Render cancellation:** stop after the current GPU/encoder boundary,
  release the queue and GL resources, and return to the editable Timeline.
- **No keyframes:** disable video render and explain that at least one shot is
  required; a still image remains available from the current camera.

All long operations expose status text, progress, and cancellation. No failure
is communicated by color alone.

## Architecture boundaries

### Application UI

`ResultViewerPage` owns layout, actions, accessible names, and visible state.
It does not perform PLY loading, OpenGL calls, encoding, or file persistence.

`ViewerBindings` remains the page/application signal boundary. It coordinates
the existing loader, adapter, project store, and render controller.

### Viewer domain/application services

Viewer state models, project serialization, camera Timeline operations, and
render job state live outside widgets. They expose pure operations that can be
unit tested without a GL context.

### q3dviewer rendering

The q3dviewer package owns camera math, shared Gaussian GPU data, standard
splat rendering, the sphere render pass, framebuffer rendering, and GPU
performance counters. It must not import Camera System page classes.

### Infrastructure

The application infrastructure owns PLY/project paths, SHA-256 checks,
Jetson encoder detection, temporary outputs, and final atomic publication.

## Verification plan

### Pure tests

- Sphere radius calculation for normal, non-uniform, and invalid scales.
- Display settings defaults and validation.
- Camera pose serialization round-trip.
- Rotation-safe Timeline interpolation and easing.
- Exact frame count for hold/transition/loop combinations.
- Project source hash mismatch detection.
- Render output path and temporary-file cleanup rules.

### Qt/application tests

- Inspector mode changes update the adapter without reloading the PLY.
- Sphere settings are disabled when the sphere shader is unavailable.
- Timeline actions follow keyboard focus order and preserve dirty state.
- Render progress, cancellation, encoder failure, and fallback states are
  exposed through the page and status bar.
- Presentation mode enters and exits with `Escape` and restores the previous
  panel state.

### Rendering tests

- Offscreen integration test for standard, wireframe sphere, solid sphere, and
  overlay modes when a GL context is available.
- Verify the sphere pass uses the expected center and `3σ` default radius.
- Verify output dimensions, frame count, and mode metadata for a deterministic
  fake encoder render.
- Verify the standard path continues to render after sphere mode is disabled.

### Jetson acceptance

Run on the production desktop session with representative small, medium, and
large PLYs:

- inspect standard and sphere modes at 1600×900 and 1024×680;
- switch modes during Orbit and Fly interaction;
- play a multi-shot Timeline without GPU resource crashes;
- render a short 24/30 FPS 1080p MP4 and a PNG sequence;
- verify no final frame drops, correct output dimensions, playable trailer, and
  atomic cleanup after cancellation;
- verify capture/inference can resume after the viewer and render session stop.

## Delivery phases

1. **Studio shell and display modes:** replace the result-page toolbar with the
   studio layout, add project state, implement standard/sphere/overlay modes,
   add full-screen presentation, and add still-image capture.
2. **Camera Director:** add named shots, deterministic Timeline models,
   playback, frame scrubbing, easing, hold frames, and project persistence.
3. **Final Renderer:** add output-size FBO rendering, PNG sequence output,
   Jetson H.264 encoding, PyAV fallback, progress, cancellation, and atomic
   publication.
4. **Presentation look:** add exposure, tonemapping, background/transparent
   output, stable appearance presets, and performance summaries.
5. **Optional extensions:** add 360° output, guided annotations, and richer
   post effects after the normal render path is reliable.

## References

- Existing architecture: `docs/development/ARCHITECTURE.md`
- Existing UI system: `docs/development/UI_DESIGN_SYSTEM.md`
- SuperSplat camera controls:
  https://developer.playcanvas.com/user-manual/supersplat/editor/camera-controls/
- SuperSplat Timeline:
  https://developer.playcanvas.com/user-manual/supersplat/editor/timeline/
- SuperSplat rendering:
  https://developer.playcanvas.com/user-manual/supersplat/editor/rendering/
- SuperSplat post effects:
  https://developer.playcanvas.com/user-manual/supersplat/studio/post-effects/
