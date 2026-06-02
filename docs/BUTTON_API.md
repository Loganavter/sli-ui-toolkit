# Button Component API Reference

## Quick Start

### Basic Button

```python
from sli_ui_toolkit.ui.widgets.buttons import Button

# Icon button
btn = Button(icon='settings', size=(36, 36))

# Text button
btn = Button(text='Click me', size=(100, 40))

# Icon + text
btn = Button(icon='play', text='Start', size=(100, 40))
```

### Button with Features

```python
# Toggle button
btn = Button(icon='eye_open', toggle=True, size=(36, 36))
btn.toggled.connect(on_toggled)  # Emitted when toggled

# Scrollable button (value 0-10)
btn = Button(icon='volume', scrollable=(0, 10), size=(36, 36))
btn.valueChanged.connect(on_value_changed)  # Emitted on scroll

# Long-press detection
btn = Button(icon='delete', long_press=True, long_press_ms=600)
btn.longPressed.connect(on_long_press)

# Menu button
menu_items = [
    ('Copy', copy_action),
    ('Paste', paste_action),
    ('Delete', delete_action),
]
btn = Button(icon='menu', menu=menu_items)
btn.menuTriggered.connect(on_menu_item)

# Multi-row text button
rows = [
    ButtonRow(text='Title', size=14, weight='bold'),
    ButtonRow(text='Subtitle', size=11),
]
btn = Button(rows=rows, toggle=True, size=(60, 50))
```

## Constructor Parameters

```python
Button(
    icon: Any = None,
    text: str = "",
    rows: list[ButtonRow] | None = None,
    toggle: bool = False,
    scrollable: tuple[int, int] | None = None,  # (min, max)
    long_press: bool = False,
    long_press_ms: int = 600,
    badge: int | None = None,
    show_underline: bool = False,
    menu: list[tuple[str, Any]] | None = None,
    size: tuple[int, int] = (36, 36),
    icon_size: int = 22,
    corner_radius: int | None = None,
    variant: str = "default",
    density: str = "normal",
    config: ButtonConfig | None = None,
    parent: QWidget | None = None,
)
```

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `icon` | `Any` | `None` | Icon name or tuple of (unchecked, checked) |
| `text` | `str` | `""` | Single-line text content |
| `rows` | `list[ButtonRow]` | `None` | Multi-line text with individual styling |
| `toggle` | `bool` | `False` | Toggleable button (on/off state) |
| `scrollable` | `(int, int)` | `None` | Enable scroll wheel: (min, max) values |
| `long_press` | `bool` | `False` | Detect press-and-hold |
| `long_press_ms` | `int` | `600` | Time (ms) before long-press triggers |
| `badge` | `int` | `None` | Number badge (top-right corner) |
| `show_underline` | `bool` | `False` | Show underline decoration |
| `menu` | `list[tuple]` | `None` | Dropdown menu items: [(label, action), ...] |
| `size` | `(int, int)` | `(36, 36)` | Fixed size (width, height) |
| `icon_size` | `int` | `22` | Icon pixel size |
| `corner_radius` | `int` | `None` | Corner radius (auto-calculated if None) |
| `variant` | `str` | `"default"` | Color variant: "default", "accent", "delete", etc. |
| `density` | `str` | `"normal"` | Visual density: "normal", "compact" |
| `config` | `ButtonConfig` | `None` | Use ButtonConfig dataclass instead of params |
| `parent` | `QWidget` | `None` | Parent widget |

## Signals

```python
button = Button(...)

# Emitted when clicked (left button)
button.clicked.connect(on_clicked)

# Emitted on left button press
button.pressed.connect(on_pressed)

# Emitted on left button release
button.released.connect(on_released)

# Emitted when toggled (toggle=True only)
button.toggled.connect(lambda checked: print(f"Toggled: {checked}"))

# Emitted when scroll wheel moves (scrollable=(min,max) only)
button.valueChanged.connect(lambda value: print(f"Value: {value}"))

# Emitted after long press timeout (long_press=True only)
button.longPressed.connect(on_long_press)

# Emitted on right click
button.rightClicked.connect(on_right_click)

# Emitted on middle click
button.middleClicked.connect(on_middle_click)

# Emitted when menu item selected (menu=items only)
button.menuTriggered.connect(on_menu_item)

# Emitted immediately after clicked (useful for rapid click detection)
button.shortClicked.connect(on_short_click)
```

## Properties & Methods

### State Management

```python
# Toggle state
button.setChecked(True)          # Set toggle state (if toggle=True)
is_checked = button.isChecked()  # Get toggle state

# Scroll value
button.setValue(5)               # Set value (if scrollable=(...) is set)
value = button.getValue()        # Get current value
button.set_value = 5             # Alias for setValue()
value = button.get_value()       # Alias for getValue()

# Set scroll range
button.setRange(0, 20)           # Change min/max (if scrollable=(...))
```

### Visual Properties

```python
# Badge (number indicator)
button.setBadge(5)               # Show "5" badge
button.setBadge(None)            # Hide badge

# Text content
button.setText("New text")
button.getText()

# Rows (multi-line)
rows = [
    ButtonRow(text='Line 1', size=14, weight='bold'),
    ButtonRow(text='Line 2', size=11),
]
button.setRows(rows, compact=False)  # compact=True centers block vertically

# Icon
button.setIcon('new_icon_name')

# Colors
button.set_color(QColor('red'))           # Override text/icon color
button.set_override_bg_color(QColor('blue'))  # Override background

# Underline
button.setShowUnderline(True)
button.setShowUnderline(False)

# Strike-through (error indicator)
button.set_show_strike_through(True)

# Variant
button.setVariant('accent')
variant = button.getVariant()

# Size & spacing
button.setIconSize(QSize(24, 24))
button.setIconSizePx(24)
button.setCornerRadiusPx(8)

# Density
button.setDensity('compact')
density = button.getDensity()

# Footer mode (visual hint)
button.set_footer_mode(True)
```

### Capability Management

```python
from sli_ui_toolkit.ui.widgets.buttons.capabilities import (
    ScrollCapability, LongPressCapability, MenuCapability, TintCapability
)

# Attach a capability
scroll_cap = ScrollCapability()
button.attach_capability(scroll_cap)

# Get attached capability
scroll_cap = button.get_capability(ScrollCapability)
if scroll_cap:
    # ... use capability

# Detach capability
button.detach_capability(ScrollCapability)
```

### Menu Management

```python
# Set/update menu items
menu_items = [('Item 1', action1), ('Item 2', action2)]
button.set_menu_items(menu_items)

# Show menu programmatically
button.show_menu()
```

### Painter Control

```python
# Use new ButtonPainterV2 (default: True)
button.use_painter_v2(True)   # Use new painter
button.use_painter_v2(False)  # Use legacy painter
```

## ButtonRow API

```python
from sli_ui_toolkit.ui.widgets.buttons import ButtonRow

row = ButtonRow(
    text='Row text',
    size=12,                                    # Font pixel size
    weight='normal',                            # 'normal' or 'bold'
    color=QColor('blue'),                       # Text color (optional)
    ratio=0.5,                                  # Height fraction of button
    h_align=Qt.AlignmentFlag.AlignHCenter,     # Horizontal alignment
)
```

## ButtonConfig API

```python
from sli_ui_toolkit.ui.widgets.buttons import ButtonConfig

config = ButtonConfig(
    icon='settings',
    text='Settings',
    rows=None,
    toggle=False,
    scrollable=None,
    long_press=False,
    long_press_ms=600,
    badge=None,
    show_underline=False,
    menu=None,
    size=(36, 36),
    icon_size=22,
    corner_radius=None,
    variant='default',
    density='normal',
)

# Use config instead of parameters
button = Button(config=config)
```

## Variants

Predefined color schemes (use `setVariant()` or `variant=` param):

```python
# Available variants
"default"    # Standard appearance
"accent"     # Highlighted/primary color
"delete"     # Destructive action (red)
"ghost"      # Minimal, outlined style
"subtle"     # Muted, secondary style
"primary"    # Bold, attention-getting
```

## Density

Visual spacing/sizing (use `setDensity()` or `density=` param):

```python
"normal"     # Default spacing and size
"compact"    # Reduced spacing (for tight layouts)
```

## Examples

### Toggle with Badge

```python
btn = Button(
    icon=('eye_open', 'eye_closed'),
    toggle=True,
    badge=3,
    size=(40, 40),
)
btn.toggled.connect(lambda checked: print(f"Visible: {checked}"))
```

### Scrollable Button

```python
btn = Button(
    icon='volume',
    scrollable=(0, 100),
    size=(36, 36),
)
btn.valueChanged.connect(lambda vol: print(f"Volume: {vol}%"))

# Use scroll wheel to change value
# Or set programmatically:
btn.setValue(50)
```

### Menu Button

```python
def on_copy():
    print("Copied!")

def on_paste():
    print("Pasted!")

btn = Button(
    icon='edit',
    menu=[
        ('Copy', on_copy),
        ('Paste', on_paste),
        ('Delete', lambda: print("Deleted!")),
    ],
)
btn.menuTriggered.connect(lambda action: action())
```

### Multi-row Calendar Button

```python
from sli_ui_toolkit.ui.widgets.buttons import Button, ButtonRow

btn = Button(
    rows=[
        ButtonRow(text='25', size=16, weight='bold'),
        ButtonRow(text='Mon', size=10),
    ],
    toggle=True,
    size=(50, 70),
    corner_radius=4,
    variant='ghost',
)
btn.toggled.connect(lambda checked: print(f"Date selected: {checked}"))
```

### Custom Styling

```python
btn = Button(
    text='Custom',
    size=(100, 40),
    variant='accent',
)

# Override colors
btn.set_color(QColor('white'))                    # Text color
btn.set_override_bg_color(QColor('#0066cc'))      # Background

# Add underline
btn.setShowUnderline(True)

# Add error indicator
btn.set_show_strike_through(True)
```

### Long-Press Action

```python
btn = Button(
    icon='delete',
    long_press=True,
    long_press_ms=800,
    size=(36, 36),
)

def on_delete():
    print("Deleted!")

btn.clicked.connect(lambda: print("Short click"))
btn.longPressed.connect(on_delete)
```

## Backwards Compatibility

Old code still works:

```python
# These still work from button.py attributes
_lp_timer = btn._lp_timer               # Returns LongPressCapability's timer
_scroll_end_timer = btn._scroll_end_timer  # Returns ScrollCapability's timer

# Old methods delegate to capabilities
btn._show_scroll_popup(5)
btn._hide_scroll_popup()
```

## Integration with CalendarDayButton

```python
from sli_ui_toolkit.ui.widgets.composite.calendar_widget.day_button import CalendarDayButton

day_btn = CalendarDayButton()
day_btn.set_date(QDate(2026, 6, 1))
day_btn.set_weekend(True, QColor(100, 150, 255))  # Light blue
day_btn.set_data(True, QColor(0, 200, 0))        # Has data, green

# New painter architecture handles rendering
```

## Performance Notes

- ✅ ButtonPainterV2 uses efficient primitives (no full redraws)
- ✅ Immutable ButtonDrawContext allows compiler optimizations
- ✅ Capabilities attach/detach cleanly (no memory leaks)
- ✅ Hybrid fallback ensures no rendering failures

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Button not responding to scroll | Check `scrollable=(min, max)` param |
| Menu not showing | Verify `menu=[(label, action), ...]` param |
| Long press not triggering | Increase `long_press_ms` (default 600) |
| Colors not applying | Use `set_override_bg_color()` or variant |
| Underline not visible | Call `setShowUnderline(True)` |

## See Also

- [Button Architecture](BUTTON_ARCHITECTURE.md) - Technical design details
