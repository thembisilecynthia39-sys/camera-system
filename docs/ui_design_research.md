# MultiWebcam UI design research

## Product direction

The application is a professional capture workstation, not a consumer media app.
Its visual system should prioritize live video, recording safety, hardware status,
and predictable performance on Jetson. The recommended direction is a lightweight
industrial interpretation of Fluent rather than a literal Windows 11 clone.

## Current-state audit

Strengths:

- A semantic dark palette already exists.
- Recording, success, warning, and error have distinct roles.
- Video remains the largest visual element.
- Navigation and model workspaces use a consistent left-to-right structure.
- Compact window behavior and model viewport overlays are already supported.

Primary issues:

- Stock Qt Widgets, optional QFluentWidgets, and local style sheets produce subtly
  different geometry and interaction states.
- `theme.py` is token-like, but raw colors remain scattered through the stylesheet
  and view classes.
- Most regions use a border and rounded container, reducing hierarchy because every
  element has similar visual weight.
- The side rail mixes global navigation, page settings, status, and destructive
  operations in one narrow vertical flow.
- Navigation is text-heavy and numbered even though the numbers do not communicate
  workflow progress.
- Status is repeated inside tiles and the side panel, while no stable global status
  strip summarizes camera, recording, GPU, storage, and inference health.
- Buttons rely mainly on text. There is no coherent SVG icon system.
- Typography is close to a scale but not formally tokenized, and several local
  `setStyleSheet()` calls bypass the shared system.

## Technology assessment

| Option | Benefits | Costs for this project | Recommendation |
|---|---|---|---|
| Qt Widgets + QSS + custom components | Stable with current PyQt5 compatibility layer, integrates with camera labels and QOpenGLWidget, low migration risk | Requires discipline because QSS is less expressive than QML | Use now |
| PyQt-Fluent-Widgets | Ready-made navigation and Fluent controls | GPLv3 for non-commercial use, commercial licensing otherwise; current Jetson compatibility shim already falls back for unsupported APIs; mixing fallback and Fluent widgets creates inconsistency | Do not make it foundational |
| Qt Quick Controls Basic/Fusion | Better declarative layout, states, animation, and component reuse; Basic is Qt's maximum-performance Quick style | Requires a Qt/QML shell migration and careful QWidget/OpenGL integration | Evaluate after Qt 6 migration |
| Qt Quick Material/Universal/FluentWinUI3 | Polished built-in visual language | Qt documents higher resource use for Material/Universal; FluentWinUI3 is a modern Qt 6 path, not a natural fit for the current JetPack Qt 5 runtime | Future desktop option, not Jetson baseline |
| KDE Kirigami | Strong responsive/convergent page patterns on top of Qt Quick Controls | Adds a QML framework and KDE dependency; visual language is less appropriate for a dedicated capture appliance | Borrow layout ideas, not the dependency |
| Custom QStyle | Complete control and better native metrics than large QSS files | High implementation and maintenance cost | Only if QSS becomes a measured bottleneck |

## Patterns worth borrowing

### From Fluent

- Use one accent color for interaction, not decoration.
- Separate navigation, content, and contextual commands.
- Prefer command bars and compact icon buttons for frequent actions.
- Use elevation/surface contrast sparingly; not every group needs a border.
- Keep state transitions short and functional.

### From Kirigami

- Treat pages as responsive units that can collapse secondary information.
- Put page-specific actions next to the page rather than in global navigation.
- Use progressive disclosure: overview first, detailed settings on demand.
- Design desktop and narrow-window behavior from the same content priorities.

### From OBS and broadcast tools

- Make preview/program content dominant.
- Keep recording state, elapsed time, dropped frames, storage, and device health
  continuously visible.
- Use configurable workspaces/docks for advanced panels instead of permanently
  consuming preview space.
- Separate monitoring from configuration. Routine capture should require few controls.
- Preserve workspace layout and operator preferences between runs.

## Proposed visual system

### Tokens

- Spacing: `4, 8, 12, 16, 24, 32`.
- Radius: `6` for controls, `10` for cards, `12` for major panels.
- Control heights: `32` compact, `36` default, `44` primary/touch-friendly.
- Typography: `12` metadata, `14` body/control, `17` section, `22` page title.
- Borders: use only for interactive focus, separation that cannot be achieved with
  spacing, and critical state containers.
- Motion: 100–150 ms hover/state feedback; no geometry animation around live video.

### Component layer

Create project-owned components/factories rather than instantiating differently styled
widgets in each view:

- `AppButton`: primary, secondary, ghost, record, danger variants.
- `IconButton`: consistent 32/36 px target with tooltip and focus state.
- `NavItem`: SVG icon, label, active indicator, compact mode.
- `StatusBadge`: icon + text + semantic state; never color only.
- `PanelCard`: optional title and actions; borderless by default.
- `CommandBar`: primary task actions separated from settings.
- `EmptyState`: icon, title, corrective action.
- `Toast/InlineNotice`: operation feedback that does not block the viewport.

Use a single monochrome SVG icon family. Icons should inherit semantic color and be
available at 16, 20, and 24 px. Avoid emoji and platform-dependent glyphs.

## Recommended information architecture

1. Keep the left rail for the five workspaces only. Replace `01`–`05` with icons and
   labels; collapse to icons in narrow mode.
2. Add a stable top status strip over the content area:
   cameras online, capture paused/running, recording, storage remaining, inference,
   GPU load, and active warnings.
3. Move page controls into a contextual command bar or inspector:
   - video wall: layout, refresh, mirror;
   - recording: name, destination, record/stop;
   - guidance: angle and capture;
   - 3DGS: file, quality budget, reset view;
   - viewport overlay: orbit and coordinate-axis toggles.
4. Keep one visually dominant action per workspace. Record is red only while it is the
   primary available action; Stop becomes the dominant action while recording.
5. Move advanced camera parameters into the existing focus view or a collapsible
   inspector so routine monitoring remains quiet.

## Delivery plan

### Phase 1: consistency and hierarchy

- Formalize spacing, radius, typography, and state tokens.
- Remove raw colors and per-widget style sheets from views.
- Add the SVG icon pipeline and replace numbered navigation.
- Reduce nested borders and card density.
- Add the global status strip.

This phase stays entirely in Qt Widgets and has low runtime risk.

### Phase 2: operator workflow

- Introduce command bars and project-owned components.
- Persist selected workspace, panel widths, model overlay preferences, and camera-grid
  layout.
- Add non-blocking inline feedback and clear empty/error states.
- Add keyboard shortcuts for record, stop, snapshot, workspace switching, and fit model.

### Phase 3: measured modernization

- Profile the Widget UI after phases 1–2.
- When the Jetson base moves to Qt 6, prototype one non-critical screen in Qt Quick
  Controls Basic/Fusion.
- Migrate the shell only if frame pacing, OpenGL composition, startup time, and memory
  are no worse than the Widget implementation.

## References

- Qt Quick Controls styles: https://doc.qt.io/qt-6.8/qtquickcontrols-styles.html
- Qt Quick Controls customization: https://doc.qt.io/qt-6/qtquickcontrols-customize.html
- Qt Widget style sheets: https://doc.qt.io/qt-6/stylesheet.html
- KDE Kirigami: https://develop.kde.org/frameworks/kirigami/
- KDE status icon guidance: https://develop.kde.org/hig/icons/monochrome/status/
- Fluent 2 design principles: https://fluent2.microsoft.design/design-principles
- OBS interface overview: https://obsproject.com/kb/obs-studio-overview
- PyQt-Fluent-Widgets licensing and compatibility: https://github.com/zhiyiYo/PyQt-Fluent-Widgets
