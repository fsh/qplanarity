# Changelog

## 1.4.2 - 2021-02-19
- Fixed a bug with moving multiple nodes.
- Moved autocenter/autofit from toolbar to options and set its default
  to False.
- Exposed background color options.
- Implemented auto-save in case of crash.
- Changed some defaults.

## 1.4.1 - 2021-02-19
- Added an About dialog.

## 1.4.0 - 2021-02-19
- Rewrote line intersect detection again. Now much faster overall, and
  instant when loading previous state.
- Node solve status is checked dynamically.
- Victory condition is checked dynamically.
- Cleaned up some parts of the code.
- Changed default colors.

## 1.3.0 - 2021-02-14
- Graph selection algorithm moved to options.
- New game window is now much more sane.

## 1.2.2 - 2021-02-14
- Swapped functionality of left and right mouse button when
  interacting with background.

## 1.2.0 - 2021-02-10
- Added manual zoom (using mouse wheel).
- Added manual pan (dragging background).
- Added ability to select and move multiple nodes at once.

## 1.1.2 - 2021-02-10
- Rewrote internal line intersect detection.
- Now much faster when starting a new game with many nodes, though
  possibly slower when resuming a solved or near-solved game.

## 1.1.1 - 2021-02-09
- Fixed a bug in intersect detection under high zoom.

## 1.1.0 - 2021-02-08
- First version with a changelog.
- Added an option dialog for customizing color and size.
