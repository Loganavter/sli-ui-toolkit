# Button Component Architecture

## Overview

The Button component uses professional UI framework patterns (Flutter, Qt, MUI, WinUI3) instead of a monolithic design. The architecture solves the core problem: **adding a new state or variant should require changing only 1 file, not 4 files simultaneously**.

**Current Solution:**
- ✅ Add new state: 1 line in `TokenResolver`
- ✅ Add new variant: 1 line in `BUTTON_VARIANT_SCHEMA`
- ✅ Add new behavior: 1 capability class
- ✅ Add new content type: 1 primitive + 1 case in dispatcher

## Architecture Layers

### 1. State Machine (Flutter Pattern)

**Problem (was):** Scattered bool attributes (`_pressed`, `_hovered`, `_checked`)

**Solution:**
```python
# states/button_state.py
class ButtonState(Enum):
    HOVERED = auto()
    PRESSED = auto()
    CHECKED = auto()
    DISABLED = auto()
    SCROLLING = auto()
    FOCUSED = auto()

StateSet = frozenset[ButtonState]  # Immutable state collection
```

**Benefit:** Explicit state machine, type-safe, works with pattern matching.

### 2. Token Resolution (MUI Pattern)

**Problem (was):** Color resolution logic mixed with painter geometry

**Solution:**
```python
# tokens/resolver.py
class TokenResolver:
    def resolve_background(self, variant: str, states: StateSet) -> QColor:
        prefix = BUTTON_VARIANT_SCHEMA.get(variant, "button.toggle")
        if ButtonState.DISABLED in states:
            return QColor(self._tm.get_color(f"{prefix}.background.disabled"))
        if ButtonState.PRESSED in states:
            return QColor(self._tm.get_color(f"{prefix}.background.pressed"))
        # ... priority-based resolution
```

**Benefit:** Colors are separated from painter. Variants don't require painter changes.

### 3. Context Object (Qt Pattern)

**Problem (was):** 18 scattered parameters in `paint(*args, **kwargs)`

**Solution:**
```python
# painting/context.py
@dataclass(frozen=True)
class ButtonDrawContext:
    widget: QWidget
    painter: QPainter
    rect: QRectF
    states: StateSet
    variant: str
    corner_radius: int
    content: ButtonContent = None
    override_bg_color: QColor | None = None
    badge_text: str | None = None
    show_underline: bool = False
    # ... (11 fields total, was 18+ parameters)
```

**Benefit:** One immutable object instead of scattered parameters. Type-safe.

### 4. Primitive Decomposition (Qt Pattern)

**Problem (was):** 432-line monolithic painter with mixed concerns

**Solution:** Each primitive is a separate file with one responsibility:

```
painting/primitives/
  background.py      → draw_background_and_border()
  text.py           → draw_text_only()
  rows.py           → draw_rows() [multi-line support]
  icon.py           → draw_icon() [3 modes: standard, hover-value, scroll-value]
  icon_text.py      → draw_icon_and_text()
  badge.py          → draw_badge()
  edge.py           → draw_bottom_edge()
  underline.py      → draw_underline()
  strikethrough.py  → draw_strikethrough()
```

**Benefit:** Each file ~50-127 lines, clear responsibility. Easy to test and modify independently.

### 5. Painter as Orchestrator (Qt Pattern)

**Problem (was):** Painter did everything: state resolution, color picking, geometry, rendering

**Solution:**
```python
# painting/painter.py
class ButtonPainterV2:
    def paint(self, ctx: ButtonDrawContext) -> None:
        # Call primitives in order (layers):
        primitives.background.draw_background_and_border(ctx, self._resolver, self._tm)
        self._paint_content(ctx)  # dispatch by content type
        primitives.badge.draw_badge(ctx, self._tm)
        primitives.edge.draw_bottom_edge(ctx, self._tm)
        primitives.underline.draw_underline(ctx, self._tm)
        primitives.strikethrough.draw_strikethrough(ctx, self._tm)

    def _paint_content(self, ctx: ButtonDrawContext) -> None:
        match ctx.content:
            case RowsContent() as rows:
                primitives.rows.draw_rows(ctx, rows.rows, self._tm, compact=rows.compact)
            case TextContent() as text:
                primitives.text.draw_text_only(ctx, text.text, self._tm)
            case IconContent():
                primitives.icon.draw_icon(ctx, self._tm)
            case IconTextContent() as icon_text:
                primitives.icon_text.draw_icon_and_text(ctx, icon_text.text, self._tm)
```

**Benefit:** Painter is simple dispatcher, not monolith. Easy to add new primitives.

### 6. Capabilities (Headless UI / MUI Pattern)

**Problem (was):** Button class mixed event handling with rendering. Hard to test behavior independently.

**Solution:**
```python
# capabilities/base.py
class ButtonCapability(ABC):
    def attach(self, button: QWidget) -> None: pass
    def detach(self, button: QWidget) -> None: pass
    def is_enabled(self) -> bool: return True

# capabilities/scroll.py
class ScrollCapability(ButtonCapability):
    def handle_wheel_event(self, event) -> bool:
        # Pure scroll logic, isolated from button
        ...

# capabilities/long_press.py
class LongPressCapability(ButtonCapability):
    def on_press_start(self) -> None: ...
    def on_press_end(self) -> None: ...
    def was_long_pressed(self) -> bool: ...
```

**Button integration:**
```python
# button.py
class Button(QWidget):
    def wheelEvent(self, event: QWheelEvent):
        scroll_cap = self.get_capability(ScrollCapability)
        if scroll_cap and scroll_cap.handle_wheel_event(event):
            return
        return super().wheelEvent(event)

    def mousePressEvent(self, event: QMouseEvent):
        lp_cap = self.get_capability(LongPressCapability)
        if lp_cap:
            lp_cap.on_press_start()
        # ...
```

**Benefit:**
- Behaviors are independent, testable, composable
- Easy to add new behavior: just write new capability class
- CalendarDayButton can add TintCapability without overriding paintEvent

## File Structure

```
buttons/
  __init__.py
  button.py                    ← QWidget: event handlers + capability management
  button_group.py              ← Button group container
  config.py                    ← ButtonConfig, ButtonRow, content types
  _painter.py                  ← (Legacy fallback painter, ~432 lines)
  _dropdown_menu.py            ← Menu implementation

  states/
    __init__.py
    button_state.py            ← ButtonState enum + StateSet

  tokens/
    __init__.py
    schema.py                  ← BUTTON_VARIANT_SCHEMA (variant → token prefix mapping)
    resolver.py                ← TokenResolver: (variant, states) → QColor

  painting/
    __init__.py
    context.py                 ← ButtonDrawContext (immutable context object)
    painter.py                 ← ButtonPainterV2 (orchestrator + dispatcher)
    primitives/
      __init__.py
      background.py            ← Background + border rendering
      text.py                  ← Single-line text rendering
      rows.py                  ← Multi-line text with individual styling
      icon.py                  ← Icon with 3 modes (standard, hover-value, scroll-value)
      icon_text.py             ← Icon + text horizontal layout
      badge.py                 ← Badge number rendering
      edge.py                  ← Bottom decorative line
      underline.py             ← Custom underline with color/alpha
      strikethrough.py         ← Error indicator diagonal line

  capabilities/
    __init__.py
    base.py                    ← ButtonCapability abstract base
    scroll.py                  ← Scroll wheel handling + value popup
    long_press.py              ← Press-and-hold detection
    menu.py                    ← Dropdown menu lifecycle
    tint.py                    ← Dynamic color overlay (for CalendarDayButton)
```

## Extension Examples

### Add New State

```python
# 1. Add to states/button_state.py
class ButtonState(Enum):
    LOADING = auto()  # ← NEW

# 2. Add to tokens/resolver.py
def resolve_background(self, variant: str, states: StateSet) -> QColor:
    if ButtonState.LOADING in states:  # ← NEW
        return QColor(self._tm.get_color(f"{prefix}.background.loading"))
    # ... rest of logic

# Done! No other files changed.
```

### Add New Variant

```python
# 1. Add to tokens/schema.py
BUTTON_VARIANT_SCHEMA = {
    "default": "button.toggle",
    "accent": "button.default",
    "delete": "button.delete",
    "warning": "button.warning",  # ← NEW
}

# Done! Painter unchanged.
```

### Add New Content Type

```python
# 1. Create config.py
@dataclass
class ProgressContent:
    progress: float
    label: str = ""

# 2. Create painting/primitives/progress.py
def draw_progress(ctx: ButtonDrawContext, progress: float, tm: ThemeManager) -> None:
    # Implementation

# 3. Add to painter.py dispatcher
def _paint_content(self, ctx: ButtonDrawContext) -> None:
    match ctx.content:
        # ... existing cases
        case ProgressContent() as progress:  # ← NEW
            primitives.progress.draw_progress(ctx, progress.progress, self._tm)

# Done!
```

### Add New Capability

```python
# 1. Create capabilities/animation.py
class AnimationCapability(ButtonCapability):
    def attach(self, button: QWidget) -> None:
        self._timer = QTimer(button)
        self._timer.timeout.connect(self._on_animate)
        self._timer.start(16)  # ~60fps

    def detach(self, button: QWidget) -> None:
        self._timer.stop()

    def _on_animate(self):
        # Update animation state

# 2. Use it
button = Button(...)
anim = AnimationCapability()
button.attach_capability(anim)
```

## Design Patterns Used

| Pattern | From | Usage |
|---------|------|-------|
| **State Machine** | Flutter (MaterialState) | ButtonState + StateSet |
| **Token Resolution** | MUI (ThemeData) | TokenResolver maps variant+state→color |
| **Context Object** | Qt (QStyleOption) | ButtonDrawContext consolidates 18 params |
| **Primitive Decomposition** | Qt (CE_PushButton*) | Each primitive = separate file |
| **Orchestrator** | Qt (QStyle::drawControl) | ButtonPainterV2 dispatcher |
| **Composition** | MUI/Headless UI (slots) | Capabilities as independent behaviors |

## Key Metrics

| Metric | Value |
|--------|-------|
| Old painter monolith | 432 lines |
| New painter orchestrator | 79 lines |
| Average primitive size | 50-127 lines |
| State transitions | 6 states |
| Variants supported | 6+ (extensible) |
| Content types | 4 (extensible) |
| Capabilities | 5 (extensible) |
| Total new code | ~2700 lines, properly split |

## Integration

### Current State

- ✅ **ButtonPainterV2** enabled by default
- ✅ **Fallback** to old painter if exception occurs
- ✅ **Backwards compatible** - all old code works
- ✅ **CalendarWidget** uses new Button architecture
- ✅ **CalendarDayButton** inherits from Button, can add TintCapability

### Hybrid Rendering

```python
# button.py
def paintEvent(self, event):
    painter = QPainter(self)

    # Try new v2 painter (default)
    if self._use_painter_v2:
        try:
            ctx = ButtonDrawContext(...)
            self._painter_v2.paint(ctx)
            painter.end()
            return
        except Exception:
            painter.end()
            painter = QPainter(self)

    # Fallback to old painter for safety
    ButtonPainter.paint(...)
    painter.end()
```

**Benefit:** Zero risk migration. If v2 fails, automatically uses v1.

## Testing Strategy

### Unit Test Level
- Each primitive: `test_primitives/test_background.py`
- Each capability: `test_capabilities/test_scroll.py`
- TokenResolver: `test_tokens/test_resolver.py`

### Integration Level
- Button with capabilities: `test_button.py`
- CalendarWidget: `test_calendar_widget.py`

### Visual Level
- test_calendar.py (included in repo)

## Future Enhancements

1. **CalendarDayButton TintCapability** - replace paintEvent override
2. **Complete icon primitives** - finalize icon mode handling
3. **Animation capability** - smooth transitions between states
4. **Accessibility** - screen reader support via capabilities
5. **State persistence** - save/restore button state

## References

- Qt: [QStyle](https://doc.qt.io/qt-6/qstyle.html) (CE_* primitives, QStyleOption)
- Flutter: [Material Button](https://api.flutter.dev/flutter/material/TextButton-class.html) (MaterialState, ThemeData)
- MUI: [Button component](https://mui.com/material-ui/api/button/) (slots, token-based styling)
- WinUI3: [Visual State Manager](https://learn.microsoft.com/en-us/windows/winui/api/microsoft.ui.xaml.visualstatemanager)
