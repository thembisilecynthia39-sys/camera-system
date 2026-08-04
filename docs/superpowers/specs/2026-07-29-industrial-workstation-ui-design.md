# Industrial Workstation UI Design

## Objective

Redesign the unified Qt Widgets shell as a task-focused industrial workstation
for Jetson Orin Nano without replacing the verified Qt 5.12/PyQt5 compatibility
stack. The interface must make the capture-to-result workflow obvious, expose
system state continuously, and remain usable at both 1600×900 and the existing
1024×680 minimum window size.

## Context

- Platform: Jetson Orin Nano, JetPack 5.1.1 desktop.
- Shape and geometry: rectangular desktop window, primary 1600×900, minimum
  1024×680.
- Viewing distance: approximately 60 cm.
- Locale: Simplified Chinese; no RTL requirement.
- Input: keyboard and mouse. Touch is not a release requirement.
- Design system: existing Qt Fusion/QWidget application with QSS.
- Content priority: capture, transfer/reconstruction, result viewing, task
  history, settings, diagnostics.

The application is an embedded Linux workstation but has a GPU and desktop
input. Desktop layout and typography rules apply. Runtime-heavy gradients,
blur, decorative animation, and a QML migration are out of scope.

## Chosen direction

Use an “industrial workstation console” direction:

- a stable navy navigation rail;
- light, high-legibility document surfaces for transfer, history, settings,
  and diagnostics;
- low-glare dark operational surfaces for live capture and 3D viewing;
- one primary action per task group;
- explicit workflow numbering and persistent status text;
- semantic status treatment using symbol, text, and colour together.

This direction preserves hardware compatibility while fixing hierarchy,
wayfinding, empty states, and cognitive load. A visual-only reskin would leave
the workflow problems intact. Migrating to QML would add unacceptable Qt
version and OpenGL integration risk.

## Token architecture

Implement tokens in three layers in `camera_system_app.ui.design_tokens`.
QSS consumes semantic and component tokens through named formatting rather than
embedding unrelated raw values throughout the stylesheet.

### Primitive layer

- Spacing: 4, 8, 12, 16, 20, 24, 32 px.
- Radius: 6, 10, 14 px.
- Type scale: 13, 16, 19, 23, 28 px, based on a compact 1.2 ratio.
- Navy: `#07131D`, `#0B1B27`, `#12263A`, `#193853`.
- Neutral light: `#F4F7FA`, `#FFFFFF`, `#D7E0EA`, `#5E6D82`,
  `#142033`.
- Interactive blue: `#0B70C9`, hover `#085EAA`, focus `#58A6FF`.
- Operational teal: `#16B8A6`.
- Status: success `#0F766E`, warning `#9A5B00`, danger `#B42318`.

### Semantic layer

- Light: background, surface, surface-subtle, text, text-muted, border,
  interactive, focus, success, warning, danger.
- Dark: background, surface, surface-raised, text, text-muted, border,
  interactive, focus, success, warning, danger.
- Interactive blue is used only for controls and selection.
- Operational teal is used for active workflow progress and completion, not
  decorative backgrounds.

### Component layer

Define named values for:

- navigation rail and selected navigation item;
- primary, secondary, ghost, disabled, and focus button states;
- content cards and section cards;
- status banners for info, success, warning, and danger;
- metric cards;
- empty states;
- workflow stage cards;
- tables, inputs, progress bars, and status bar.

## Shared components

### PageHeader

Add an optional eyebrow such as `工作流 01` or `系统`. It appears above the
page title and provides orientation without increasing navigation depth.

### StatusBanner

Support `info`, `success`, `warning`, and `danger`. Each variant owns a symbol,
plain-language label, accessible name, and semantic property. Changing status
must refresh the style without recreating the widget.

### EmptyState

Provide a centred symbol, title, description, and optional action button.
Descriptions explain the next useful action, not merely that data is absent.
The component must work on light and dark surfaces.

### MetricCard

Provide a compact label, value, and semantic status property. Diagnostics use
three cards for passed, warning, and failed checks.

### WorkflowStage

Represent upload, reconstruction, and download with a stage number, title,
status text, and progress bar. States are pending, active, completed, warning,
and failed. Colour is always paired with text and a symbol.

### Content cards

Extend the base page card helper to support an optional title and description.
Card content remains independent of business logic.

## Navigation and global shell

- Preserve six stack indexes so existing bindings remain valid.
- Prefix visible navigation labels with `01` through `06`.
- Mark the first three as the main capture workflow through their labels and
  page eyebrows; mark the remaining pages as workspace/system support.
- Keep the brand block and add a compact local workstation status at the
  bottom of the rail.
- Status bar text remains persistent and changes between operational dark mode
  and document light mode.
- All navigation items retain at least a 48 px target and a visible selected
  indicator.

## Page designs

### Capture workspace

- Preserve the edge-to-edge dark camera host and zero outer margins.
- Keep the persistent runtime banner.
- Replace the plain placeholder with a dark EmptyState titled
  `等待摄像头画面`.
- Add an action that navigates to diagnostics when capture cannot start.
- Do not add a fake rescan operation the adapter does not support.

### Transfer and reconstruction

- Separate task identity and endpoint metadata from progress.
- Present upload, reconstruction, and download as three horizontal workflow
  stages at 1600 px; allow them to remain readable at the minimum width.
- Place manual image selection as a secondary action.
- Place the current task action as the single primary action.
- Busy, failed, cancelled, retryable, and completed states continue to use the
  current application state machine.

### Result viewer

- Preserve the dark low-glare surface.
- Convert the path/source block into a compact toolbar card.
- Keep select, load/reload, and reset actions in logical Tab order.
- Replace the plain empty label with a dark EmptyState titled
  `尚未加载 Gaussian 结果`.
- Viewer content continues to own the majority of the page.

### History

- Keep the existing task table and compact row actions.
- Replace a blank zero-row table with an EmptyState explaining how tasks are
  created.
- Switch to the table when at least one job exists.
- Preserve retry, open result, detail, and directory actions.

### Settings

- Keep save behaviour and field names unchanged.
- Place connection, storage paths, timeouts, and logging in labelled section
  cards inside a scroll area.
- Keep the primary Save action visible below the scroll area.
- Use field labels and helper text that tolerate longer Chinese strings.

### Diagnostics and logs

- Add passed, warning, and failed MetricCards.
- Update metrics from `DiagnosticReport`.
- Keep the model-backed table required for JetPack stability.
- Put the diagnostics table and log viewer in a vertical splitter so operators
  can allocate space.
- Keep refresh actions together at the top and label the log source clearly.

## Responsive behaviour

- Primary design: 1600×900.
- Minimum: 1024×680.
- Page outer margins reduce from 28 px to 20 px where necessary.
- Transfer stages use equal stretch factors and minimum widths; text wraps.
- Settings scrolls vertically instead of shrinking controls below usable size.
- Tables retain horizontal header policies and may scroll rather than clipping
  essential action columns.
- No fixed-width user-visible strings.

## Accessibility

- Body text is 16 px and page titles are 28 px.
- Normal text contrast is at least 4.5:1; component boundaries and focus
  indicators are at least 3:1.
- Buttons are at least 40 px high; primary workflow targets are 44–48 px.
- Every control is reachable by keyboard in visual order.
- Focus uses a 2 px semantic ring.
- Status never relies on colour alone.
- Widgets expose accessible names for navigation, empty-state actions,
  workflow stages, metrics, tables, logs, and primary actions.
- Layouts must tolerate large system font settings without fixed-height text
  containers.

## Behaviour boundaries

The redesign must not:

- change reconstruction state transitions;
- initialize hardware from a page constructor;
- perform network or file work on the UI thread;
- replace the model-backed diagnostics table with `QTableWidgetItem`;
- change capture, transfer, or viewer cancellation semantics;
- add Qt, OpenCV, or graphics dependencies.

## Verification

1. Widget tests cover component states, metric updates, workflow stage updates,
   empty-state transitions, navigation mapping, and keyboard-visible actions.
2. Existing application, reconstruction, history, settings, capture, and viewer
   tests remain green.
3. The complete root, Tx_Rx, and multiwebcam suites pass.
4. Offscreen screenshots are generated for all six pages at 1600×900 and
   1024×680 and inspected for clipping, hierarchy, empty states, and contrast.
5. The Qt shell starts and closes repeatedly without native crashes.
6. Jetson diagnostics report no core failure.
7. The final branch is pushed to GitHub and a draft pull request contains the
   complete commit series and validation evidence.

