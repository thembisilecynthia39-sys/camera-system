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
- Increase the default and explicit history row height to 68 px.
- Reduce cell-widget vertical margins so status badges and actions receive their
  full size hints.
- Give status badges and primary actions a 36 px minimum height.
- Do not enforce a maximum height on text-bearing buttons.
- Continue using a fixed baseline row height instead of
  `resizeRowsToContents()`, because the latter does not reliably include
  `setCellWidget()` size hints on the JetPack Qt 5.12 compatibility stack.

### Timeout controls

- Add `FocusWheelSpinBox` and `FocusWheelDoubleSpinBox` shared widgets.
- When the widget does not have focus, `wheelEvent()` ignores the event. The
  surrounding scroll area can then continue scrolling.
- When the user left-clicks the control and it has focus, normal Qt wheel
  stepping remains available.
- Keyboard focus, direct typing, arrow buttons, ranges, suffixes, serialization,
  and validation remain unchanged.
- Apply the protected widgets only to timeout and polling fields. Other controls
  keep their existing behavior.

## Accessibility and responsive behavior

- Text-bearing row controls must be at least as tall as their Qt size hints.
- Status remains expressed by text and color.
- Primary row actions remain keyboard accessible and at least 36 px high.
- Timeout values remain editable by keyboard, arrow buttons, and focused wheel
  input.
- At 1024×680, the history table may scroll but must not compress row content.

## Verification

- A real `HistoryPage` test asserts that status badges and primary actions are
  not smaller than their size hints.
- Real wheel events prove unfocused timeout controls preserve values.
- A focused control test proves wheel stepping still works after selection.
- Existing history signal/action and settings serialization tests remain green.
- Offscreen screenshots at 1600×900 and 1024×680 are inspected.
- The root, Tx_Rx, and multiwebcam suites pass before publication.
