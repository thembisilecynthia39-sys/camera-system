# History Table and Settings Input Safety Design

## Objective

Fix two desktop interaction defects without changing reconstruction or settings
data semantics:

1. History status badges and primary row actions must not clip Chinese text.
2. Timeout spin boxes must not change while the user scrolls the settings page.

## Root causes

The history table uses a fixed 58 px row, a status-container vertical margin of
20 px, and a primary-button maximum height of 32 px. Under the current Qt 5.12
style, the status label receives about 21 px even though its size hint is about
30 px. Larger fonts or DPI scaling leave even less usable space.

Qt spin boxes consume wheel events while hovered by default, including when the
control is not focused. This makes normal vertical page scrolling mutate upload,
request, polling, reconstruction, and download timeout values.

## Chosen design

### History rows

- Keep the model, columns, status mapping, menus, signals, and table interaction
  unchanged.
- Replace nested status-label cell widgets with native `QTableWidgetItem`
  status cells. Each cell contains a symbol and complete Chinese label, such as
  `✕ 失败` or `○ 待上传`, and uses semantic foreground/background colors.
- Native table items own their text layout, selection, accessibility, and
  clipping behavior; rounded nested badge borders are removed.
- Keep row action widgets, but derive each populated row height from the real
  action widget size hint plus vertical clearance.
- Do not enforce a maximum height on text-bearing buttons.
- Keep all six columns visible at the 1024×680 minimum window width.

### Timeout controls

- Add `SafeSpinBox` and `SafeDoubleSpinBox` shared widgets.
- Wheel events never change these configuration values, regardless of whether
  Qt delivers the event to the spin box or its embedded line editor.
- The user must click/select a field and then type a value or use its visible
  up/down buttons.
- Keyboard focus, direct typing, arrow buttons, ranges, suffixes, serialization,
  and validation remain unchanged.
- Apply the protected widgets only to timeout and polling fields. Other controls
  keep their existing behavior.

## Accessibility and responsive behavior

- Text-bearing row controls must be at least as tall as their Qt size hints.
- Status remains expressed by text and color.
- Primary row actions remain keyboard accessible and at least 36 px high.
- Timeout values remain editable by keyboard and visible arrow buttons.
- At 1024×680, the history table may scroll but must not compress row content.

## Verification

- A real `HistoryPage` test asserts that status cells are native items with
  complete symbol-and-text labels and no nested status widget.
- Real wheel events sent to both the spin box and its embedded line editor prove
  timeout values never change.
- Click selection followed by direct keyboard input proves intentional editing
  remains available.
- Existing history signal/action and settings serialization tests remain green.
- Offscreen screenshots at 1600×900 and 1024×680 are inspected.
- The root, Tx_Rx, and multiwebcam suites pass before publication.
