# 3DGS Viewer Studio Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax (- [ ]) for tracking.

**Goal:** Upgrade the Camera System result page into a local 3DGS roaming and presentation studio with standard, sphere, and overlay visualization modes, reproducible camera tours, and deterministic PNG/MP4 rendering.

**Architecture:** Keep the existing PySide6/Qt Widgets application and q3dviewer OpenGL renderer. Add pure viewer domain models for state and serialization, a deterministic camera timeline service, a shared Gaussian GPU-data owner, separate splat and sphere render passes, a session/adapter boundary for UI integration, and a GUI-thread render scheduler feeding a CPU encoder worker. The first delivery prioritizes high-quality interactive roaming and video presentation; editing/cleanup workflows remain outside this feature.

**Tech Stack:** Existing Python project conventions, Python 3.8-compatible syntax, PySide6 compatibility APIs, Qt Widgets, Fusion/QSS, NumPy, OpenGL 4.3 core profile, pytest, PyAV 12.3.0, and the existing Jetson GStreamer/H.264 path.

## Global Constraints

- Preserve the current six-page application shell, page indexes, existing signals, cancellation behavior, shutdown behavior, and GPU arbitration.
- Keep the viewer usable at 1600x900 and at the existing minimum window size of 1024x680.
- Use the existing dark Fusion/QSS visual language. Add clear focus states, keyboard shortcuts, 16 px minimum hit targets, and accessible labels.
- Do not modify the source PLY or duplicate the full Gaussian arrays for each display mode.
- Sphere radius is calculated from the original Gaussian center and scale as:
  sphere radius = sphere sigma multiplier multiplied by max(scale.x, scale.y, scale.z)
  with a default multiplier of 3.0. The current loader's scale expansion remains part of the effective source-scale contract.
- Standard, sphere, and overlay modes use one shared GPU allocation. Do not create one Qt or scene-graph mesh object per Gaussian.
- OpenGL work stays on the GUI/render thread. CPU encoding and file I/O stay on the worker side.
- Final rendering is frame-count-driven. A full encoder queue applies backpressure; frames are never silently dropped.
- Transparent background is supported for PNG stills/sequences only. MP4 output is opaque and uses the configured background.
- Project state is stored in a .splatview.json sidecar. Source identity uses file size and SHA-256. Saving is atomic and never replaces the source PLY.
- Do not add Qt, OpenCV, CUDA, Torch, or another graphics framework as a new dependency.
- Use tests before implementation for every behavior-bearing task. Use apply_patch for source edits and keep each task independently verifiable and committed.
- Avoid placeholder controls, fake progress, hidden fallback behavior, or unbounded frame queues.

## Current File Map

The implementation builds on the following existing boundaries:

- Result-page UI: src/camera_system_app/ui/pages/result_viewer.py
- UI signal bridge: src/camera_system_app/ui/viewer_bindings.py
- q3dviewer adapter: src/camera_system_app/infrastructure/adapters/q3dviewer_adapter.py
- OpenGL widget: 3DGSviewer/q3dviewer/q3dviewer/base_glwidget.py and glwidget.py
- Gaussian item and shaders: 3DGSviewer/q3dviewer/q3dviewer/custom_items/gaussian_item.py and shaders
- Existing experimental camera path: 3DGSviewer/q3dviewer/q3dviewer/tools/film_maker.py
- Existing Jetson encoder pipeline: multiwebcam/src/multiwebcam/recording/gstreamer.py
- Existing q3dviewer tests: tests/app_shell/test_q3dviewer_integration.py and test_q3dviewer_hardware.py

## Implementation Tasks

### Task 1: Add pure viewer state models and validation

Files:

- Add src/camera_system_app/domain/viewer.py
- Add tests/app_shell/test_viewer_models.py

Steps:

- [ ] Write failing tests for defaults, enum serialization, camera pose normalization, project round-trip, invalid dimensions/FPS, and rejection of transparent MP4.
- [ ] Run the focused model test file and confirm the new tests fail for the expected missing symbols.
- [ ] Implement DisplayMode with standard, sphere wireframe, sphere solid, and overlay values; SphereStyle; QualityPreset; and OutputKind.
- [ ] Implement CameraPose, CameraShot, CameraTimeline, DisplaySettings, AppearanceSettings, RenderSettings, and ViewerProject as typed dataclasses with JSON-safe conversion.
- [ ] Implement render-setting validation, including positive output dimensions, supported FPS, valid timeline duration, valid sphere multiplier, and the PNG-only transparency rule.
- [ ] Run the focused tests and the existing domain tests.
- [ ] Commit as feat: add 3dgs viewer state models.

Acceptance:

- Models have deterministic defaults and no Qt or OpenGL imports.
- A serialized project can be loaded back without changing values.
- Invalid render settings fail with typed, user-actionable errors.

### Task 2: Implement deterministic camera timeline math

Files:

- Add src/camera_system_app/application/viewer_timeline.py
- Add tests/app_shell/test_viewer_timeline.py

Steps:

- [ ] Write failing tests for interpolation endpoints, shortest-path quaternion interpolation, hold durations, exact frame counts, and monotonic easing.
- [ ] Run the focused tests and verify they fail before implementation.
- [ ] Implement interpolate_camera_pose, easing_value, sample_timeline, and timeline_frame_count using NumPy and pure Python only.
- [ ] Use quaternion slerp with normalized inputs and shortest-path correction. Use exact integer frame sampling so frame zero and the final frame are stable.
- [ ] Define behavior for an empty timeline and a single-shot timeline through typed validation rather than implicit guessing.
- [ ] Run focused timeline tests plus model tests.
- [ ] Commit as feat: add deterministic camera timeline.

Acceptance:

- Identical project settings produce identical sampled poses and frame counts.
- No timer, wall-clock, Qt, or renderer state affects the math.
- Camera position, target, and orientation remain finite and normalized.

### Task 3: Add safe sidecar project persistence

Files:

- Add src/camera_system_app/infrastructure/viewer_project_store.py
- Add tests/app_shell/test_viewer_project_store.py

Steps:

- [ ] Write failing tests for default sidecar naming, atomic save, load, missing sidecar, malformed JSON, and source size/hash mismatch.
- [ ] Run the focused tests and confirm the expected failures.
- [ ] Implement default_path, sha256_file, load, and save around ViewerProject.
- [ ] Store source path, source size, source SHA-256, version, display settings, appearance, camera, timeline, and render settings.
- [ ] Write to a same-directory temporary file, flush and close it, then publish with os.replace. Remove only the temporary file created by the operation on failure.
- [ ] Return typed results/errors so the UI can offer Load anyway, Reset, or Save As without exposing traceback text.
- [ ] Run persistence tests and a full non-GUI test subset.
- [ ] Commit as feat: persist 3dgs viewer projects safely.

Acceptance:

- The source PLY is never opened for writing.
- A sidecar for a changed source is detected instead of silently applied.
- Interrupted writes do not leave a partially published sidecar.

### Task 4: Create the shared Gaussian GPU-data owner and sphere-radius utility

Files:

- Add 3DGSviewer/q3dviewer/q3dviewer/utils/gaussian_sphere.py
- Add 3DGSviewer/q3dviewer/q3dviewer/custom_items/gaussian_gpu_data.py
- Modify 3DGSviewer/q3dviewer/q3dviewer/custom_items/gaussian_item.py
- Modify related custom_items package exports if needed
- Add tests/app_shell/test_q3dviewer_sphere.py

Steps:

- [ ] Write failing tests for circumscribed_sphere_radius on scalar and vector scales, invalid multipliers, and deterministic preview-index selection.
- [ ] Run the focused tests and confirm they fail for the expected missing utility/owner.
- [ ] Implement the radius utility using the effective Gaussian scale values without changing PLY data.
- [ ] Extract SSBO creation, upload, release, full-quality data, and preview-index handling into GaussianGpuData.
- [ ] Make GaussianItem own or reference one GaussianGpuData instance and preserve the existing public load, initialize_gl, release_gl, draw, and performance APIs.
- [ ] Ensure preview mode selects the same source rows deterministically and that full-quality mode restores all rows.
- [ ] Run sphere utility tests and existing q3dviewer integration tests.
- [ ] Commit as refactor: share gaussian gpu data.

Acceptance:

- Standard and future sphere passes can reference the same SSBO/data owner.
- No per-Gaussian Qt object or CPU-side transformed copy is introduced.
- Existing standard Gaussian loading and preview behavior remain green.

### Task 5: Add standard, sphere, and overlay render passes

Files:

- Add 3DGSviewer/q3dviewer/q3dviewer/custom_items/gaussian_splat_pass.py
- Add 3DGSviewer/q3dviewer/q3dviewer/custom_items/gaussian_sphere_pass.py
- Add 3DGSviewer/q3dviewer/q3dviewer/shaders/gau_sphere_vert.glsl
- Add 3DGSviewer/q3dviewer/q3dviewer/shaders/gau_sphere_frag.glsl
- Modify gaussian_item.py and its shader-loading path
- Add or extend tests/app_shell/test_q3dviewer_sphere.py

Steps:

- [ ] Write failing controller-level tests for the exact display-mode values, sphere style switching, radius multiplier changes, and mode changes without reloading the PLY.
- [ ] Run those tests and confirm failure before renderer implementation.
- [ ] Extract existing splat draw behavior into GaussianSplatPass without changing sorting, blending, SH/DC color handling, normal mode, or preview limits.
- [ ] Implement GaussianSpherePass around one screen-space quad per Gaussian. In the fragment shader, reconstruct the view ray, intersect the ray with the circumscribed sphere, discard misses, shade solid pixels with the Gaussian color, and calculate a stable wireframe shell from sphere coordinates.
- [ ] Support wireframe, solid, and overlay behavior. Overlay means standard splats remain visible while the sphere shell is rendered with configurable opacity and depth behavior.
- [ ] Add GaussianRenderController methods set_mode, set_quality, set_sphere_settings, and performance_metrics, with shared data and pass instances.
- [ ] Keep the default sphere presentation as a half-transparent wireframe overlay and expose multiplier, opacity, line width, and color mode as settings.
- [ ] Run focused renderer tests and existing integration/hardware tests where available.
- [ ] Commit as feat: add gaussian sphere display modes.

Acceptance:

- The UI can switch standard, sphere wireframe, sphere solid, and overlay without reloading data.
- Sphere geometry is visibly the original ellipsoid's circumscribed sphere, not an axis-aligned replacement mesh and not a modified Gaussian.
- The default sphere view remains readable on dense scenes and reports render metrics.

### Task 6: Add camera snapshots and sized render targets

Files:

- Add 3DGSviewer/q3dviewer/q3dviewer/render_target.py
- Modify base_glwidget.py
- Modify glwidget.py
- Add or extend tests/app_shell/test_q3dviewer_integration.py

Steps:

- [ ] Write failing tests for camera-state round-trip and render-target dimension validation.
- [ ] Run the focused tests and verify expected failures.
- [ ] Add get_camera_state and set_camera_state with position, target, orientation, FOV, and viewport-independent values.
- [ ] Extract the scene render sequence from paintGL into a reusable render_scene path.
- [ ] Implement RenderTarget around QOpenGLFramebufferObject with color/depth attachments and a readback method returning a well-defined RGBA array.
- [ ] Add render_to_array(width, height, camera_state, display_settings, appearance_settings) that renders at the requested output size while keeping the GUI-owned context.
- [ ] Emit or expose frame_rendered only after readback succeeds. Validate that output dimensions are positive and within the configured safety limit.
- [ ] Preserve interactive paintGL behavior, resize handling, context initialization, and shutdown.
- [ ] Run focused tests; run an opt-in Jetson hardware test when a display/context is available.
- [ ] Commit as feat: render q3dviewer frames to sized targets.

Acceptance:

- A still frame can be generated at a size different from the interactive viewport.
- Camera state can be saved and restored without accumulating transforms.
- The normal interactive path does not allocate a new FBO every paint event.

### Task 7: Connect a viewer session to the renderer adapter

Files:

- Add src/camera_system_app/application/viewer_session.py
- Modify src/camera_system_app/infrastructure/adapters/q3dviewer_adapter.py
- Add tests/app_shell/test_viewer_session.py
- Extend existing adapter/integration tests

Steps:

- [ ] Write failing tests for session defaults, display changes, camera changes, dirty-state tracking, and adapter protocol calls.
- [ ] Run focused tests and confirm failure before implementation.
- [ ] Implement ViewerSession as the single owner of the current ViewerProject and transient playback/render state.
- [ ] Add adapter methods for set_display_settings, set_appearance_settings, get_camera_state, set_camera_state, fit_scene, capture_frame, set_quality, and performance_metrics.
- [ ] Make display-setting changes update passes in place. Reload only when the source path changes.
- [ ] Preserve interactive quality/full-quality release behavior and existing GPU resource release paths.
- [ ] Run session, adapter, and q3dviewer integration tests.
- [ ] Commit as feat: connect viewer session to render adapter.

Acceptance:

- UI code does not reach into shader uniforms or OpenGL buffers directly.
- A session can be tested with a fake adapter.
- Source loading remains cancellable and compatible with the current application shell.

### Task 8: Build the studio toolbar and collapsible Inspector

Files:

- Add src/camera_system_app/ui/widgets/viewer_toolbar.py
- Add src/camera_system_app/ui/widgets/viewer_inspector.py
- Modify src/camera_system_app/ui/pages/result_viewer.py
- Modify src/camera_system_app/ui/widgets/__init__.py if present
- Add or extend tests/app_shell/test_viewer_ui.py

Steps:

- [ ] Write failing offscreen UI tests for required controls, signal emission, keyboard focus, collapsed sections, and minimum-width layout.
- [ ] Run the focused UI tests and confirm expected failures.
- [ ] Implement a compact top toolbar with Open, Reset, Fit, display-mode selector, quality selector, Play/Pause, Stop, Presentation, and Render actions.
- [ ] Implement an Inspector with View, Camera, Appearance, and Render sections. Keep advanced controls collapsed by default and make the right panel hideable.
- [ ] Add sphere controls for wireframe/solid/overlay, opacity, line width, and sigma multiplier with the confirmed default multiplier of 3.0.
- [ ] Add camera controls for Orbit/Fly selection, FOV, bookmarks, and reset/fit actions.
- [ ] Keep constructors free of file I/O, OpenGL calls, and playback timers. Expose signals and bind them from the page/controller.
- [ ] Run offscreen UI tests at 1600x900 and 1024x680 plus existing result-page tests.
- [ ] Commit as feat: add 3dgs studio shell and inspector.

Acceptance:

- The core high-frequency actions are available without opening a modal dialog.
- Controls are readable and usable at the current minimum window size.
- Existing Open/Load/Reset behavior and signals continue to work.

### Task 9: Integrate sessions, sidecars, and presentation mode

Files:

- Modify src/camera_system_app/ui/viewer_bindings.py
- Modify src/camera_system_app/ui/pages/result_viewer.py
- Modify the relevant main-window UI wiring
- Extend tests/app_shell/test_viewer_ui.py and integration tests

Steps:

- [ ] Write failing integration tests for opening a matching sidecar, rejecting a mismatched sidecar, saving, Save As, dirty-state indication, and reversible presentation mode.
- [ ] Run focused tests and confirm the expected failures.
- [ ] Implement open_project, save_project, save_project_as, set_presentation_mode, and settings-change bindings.
- [ ] When opening a source, load a matching sidecar automatically. If identity mismatches, show a warning and offer Load anyway or Reset; never silently apply stale camera/render settings.
- [ ] Make presentation mode hide or reduce chrome, preserve the current viewer state, and restore it with Escape or the toolbar action.
- [ ] Keep all source and sidecar I/O outside the OpenGL widget.
- [ ] Run focused application tests and the existing full shell tests.
- [ ] Commit as feat: persist viewer projects and presentation mode.

Acceptance:

- A saved project reopens with the same camera, display mode, timeline, and render settings when source identity matches.
- Presentation mode is reversible and does not lose unsaved settings.
- Stale projects are visible to the user before they affect the scene.

### Task 10: Add a model-backed Camera Director timeline and draft playback

Files:

- Add src/camera_system_app/ui/widgets/viewer_timeline.py
- Add src/camera_system_app/application/viewer_playback.py
- Modify result_viewer.py, viewer_bindings.py, and UI exports
- Add tests/app_shell/test_viewer_playback.py
- Extend viewer UI tests

Steps:

- [ ] Write failing tests for play, pause, stop, frame stepping, frame-range limits, and signal order.
- [ ] Run focused tests and verify expected failures.
- [ ] Implement ViewerPlayback as a QObject state machine with play, pause, stop, set_frame, current_frame, and is_playing. Use a QTimer only for interactive draft playback.
- [ ] Implement a timeline widget with shot/keyframe markers, duration/FPS labels, frame ruler, selected-shot editing, and add/duplicate/delete/reorder actions.
- [ ] Use the pure timeline sampler from Task 2 for every displayed frame. Do not interpolate in the widget.
- [ ] Bind playback to the adapter camera APIs and maintain the existing high-quality interactive preview policy.
- [ ] Add keyboard shortcuts for play/pause, frame stepping, and Escape presentation exit without stealing text-field focus.
- [ ] Run playback and offscreen UI tests.
- [ ] Commit as feat: add camera director timeline playback.

Acceptance:

- A saved timeline can be edited and previewed deterministically.
- Interactive playback is visibly separate from final rendering and is cancelable.
- A single frame can be selected and captured without starting playback.

### Task 11: Implement bounded PNG and MP4 encoder backends

Files:

- Add src/camera_system_app/infrastructure/viewer_encoder.py
- Add tests/app_shell/test_viewer_encoder.py
- Reuse or factor the existing multiwebcam GStreamer pipeline without changing its public behavior

Steps:

- [ ] Write failing tests for encoder lifecycle, frame-size validation, bounded sink backpressure, PNG output, and unsupported-backend errors.
- [ ] Run focused tests and confirm expected failures.
- [ ] Implement EncoderConfig, FrameEncoder, typed encoder errors, backend detection, and BoundedFrameSink.
- [ ] Implement PNG still/sequence output with explicit RGBA/RGB conversion and atomic final publication.
- [ ] Implement Jetson GStreamer H.264 output using the existing nvv4l2h264enc conventions where available.
- [ ] Implement PyAV H.264 as the controlled fallback using the already declared dependency.
- [ ] Ensure write blocks or returns a typed backpressure result when the queue is full; it must never discard a frame silently.
- [ ] Implement finish, abort, temporary-output cleanup, and recoverable error reporting.
- [ ] Run encoder tests without requiring a GPU; run backend-specific tests only when the dependency/device exists.
- [ ] Commit as feat: add viewer frame encoders.

Acceptance:

- PNG and MP4 paths have explicit lifecycle states and cleanup.
- Output frames have the requested size and frame rate.
- A canceled or failed render cannot be mistaken for a complete final file.

### Task 12: Add deterministic GUI-thread final rendering and render dialog

Files:

- Add src/camera_system_app/application/viewer_render_plan.py
- Add src/camera_system_app/ui/viewer_render_controller.py
- Add src/camera_system_app/ui/widgets/viewer_render_dialog.py
- Modify viewer_bindings.py and result_viewer.py
- Add tests/app_shell/test_viewer_render_controller.py

Steps:

- [ ] Write failing tests for RenderPlan frame count, endpoint poses, frozen settings, cancellation, backpressure, and final progress values.
- [ ] Run focused tests and confirm expected failures.
- [ ] Implement RenderPlan.from_project, frame_count, frame_pose, and validation. Freeze display, appearance, quality, camera, output size, FPS, and transparency at render start.
- [ ] Define a FinalRenderAdapter protocol with set_camera_state, set_display_settings, set_appearance_settings, and render_frame.
- [ ] Implement ViewerRenderController with start, cancel, is_running, progress, error, and finished signals.
- [ ] Schedule at most one render/readback per GUI event-loop turn. Enqueue the frame to BoundedFrameSink; if full, do not advance the frame index until capacity is available.
- [ ] Keep all OpenGL calls and readback on the GUI thread. Let the encoder worker own only CPU encoding and output I/O.
- [ ] Write to a temporary output and publish atomically only after all expected frames finish. On cancel/error, abort the encoder and remove only the controller's temporary output.
- [ ] Implement the render dialog with resolution, FPS, format, duration/frame count, quality, display mode, sphere settings, transparency rules, progress, ETA, cancel, and error summary.
- [ ] Disable conflicting scene controls while rendering, restore the previous interactive state after finish/cancel, and keep cancel responsive.
- [ ] Run controller tests with fakes and offscreen dialog tests. Run one real-output smoke test when a graphics context and encoder are available.
- [ ] Commit as feat: add deterministic viewer render controller.

Acceptance:

- The same timeline and settings always produce the same expected number of frames.
- No frames are dropped under encoder backpressure.
- Cancel leaves no partially published final output and returns the UI to a usable state.

### Task 13: Add presentation appearance and post-processing controls

Files:

- Add the required q3dviewer post-process pass and shader files under 3DGSviewer/q3dviewer/q3dviewer
- Modify render_target.py, base_glwidget.py, viewer.py, and viewer_inspector.py
- Add or extend renderer and UI tests

Steps:

- [ ] Write failing tests for default appearance settings, output-only post-processing, and preservation of debug-overlay exclusion.
- [ ] Run focused tests and verify expected failures.
- [ ] Implement exposure, tone mapping, contrast, saturation, vignette, and optional sharpening as a small output pass over the render target. Keep the first implementation numerically bounded and deterministic.
- [ ] Ensure camera guides, selection/debug overlays, Inspector chrome, and timeline chrome are excluded from final output unless explicitly requested by the render plan.
- [ ] Make interactive preview and final output share appearance settings but keep render snapshots immutable after start.
- [ ] Run pure appearance tests, renderer integration tests, and available hardware smoke tests.
- [ ] Commit as feat: add viewer appearance and presentation look.

Acceptance:

- The output can be tuned for a polished walkthrough without altering Gaussian source data.
- Final video/stills do not accidentally contain application chrome or debug guides.
- The appearance pass is disabled or bypassed when no post-processing is requested.

### Task 14: Complete application verification and documentation

Files:

- Modify tests/app_shell/test_q3dviewer_integration.py
- Modify tests/app_shell/test_q3dviewer_hardware.py when hardware coverage is needed
- Add/update viewer documentation and the user guide near the existing application docs
- Update README or feature documentation only where the project already documents user workflows

Steps:

- [ ] Add protocol tests for the full page-to-session-to-adapter path and regression tests for old result-page behavior.
- [ ] Run offscreen layout, signal, model, timeline, persistence, renderer-fake, encoder-fake, and render-controller test suites.
- [ ] Run static checks, diff checks, and the project test command used by CI.
- [ ] Run the opt-in Jetson hardware test with an actual OpenGL context and one small Gaussian asset when the environment provides it.
- [ ] Manually verify standard, sphere wireframe, sphere solid, overlay, Orbit, Fly, Fit, bookmarks, timeline preview, PNG still, PNG sequence, MP4, cancel, sidecar mismatch, restart, presentation mode, and recovery from encoder failure.
- [ ] Inspect a representative UI screenshot at 1600x900 and 1024x680 for clipping, unreadable controls, and accidental chrome in final output.
- [ ] Document the sphere formula, default 3.0 multiplier, render quality tradeoffs, output constraints, sidecar behavior, keyboard shortcuts, and Jetson encoder requirements.
- [ ] Run a final placeholder/TODO scan, review the diff for unrelated changes, check git status, and commit as docs: document 3dgs viewer studio workflow.

Acceptance:

- The feature is covered by deterministic tests plus hardware smoke coverage where possible.
- The documentation explains how to obtain a high-quality roaming video and how sphere mode relates to the original ellipsoid.
- No unrelated worktree changes are overwritten.

## Delivery Checkpoints

- After Task 5: the existing result page can switch between standard, sphere wireframe, sphere solid, and overlay modes while preserving the loaded scene.
- After Task 10: a saved Camera Director timeline can be edited and previewed with exact frame sampling.
- After Task 12: a small deterministic timeline can produce a complete PNG sequence and MP4, with progress, backpressure, and cancellation.
- After Task 13: presentation appearance controls affect both interactive preview and frozen final output.
- After Task 14: the complete feature passes the release verification gate.

## Execution Notes

The optional SuperSplat-like features that are not required for the first high-quality roaming/video release—selection, crop/box editing, cleanup tools, publishing, WebXR, SOG-specific workflows, and rich annotations—must remain a separate follow-up. They can reuse the shared GPU-data and session boundaries after the core output path is stable.

Plan completion rule: do not mark the feature complete until the final PNG/MP4 path, sphere mode, sidecar persistence, cancellation, and verification tasks all pass. 
