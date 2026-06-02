# SLI UI Toolkit Demo Application

A showcase of all main widget families in the `sli-ui-toolkit` PyQt6 library, with light and dark theme support.

## What's Included

The demo displays:

- **Buttons**: All 7 variants (default, accent, delete, primary, surface, ghost, subtle), states, and features
- **Inputs**: ComboBox, LineEdit, SpinBox, Slider, Switch, CheckBox, RadioButton, and variants
- **Composites**: Dialogs (DialogActionBar, ScrollableDialogPage, SidebarDialogShell)
- **Misc**: Labels, LoadingSpinner, ToastNotification, Tooltips

## Running

### From repository root:
```bash
python -m demo
```

### Or use as a module:
```bash
python -m demo.main
```

## Features

- **Theme Toggle**: Button in header switches between light and dark themes
- **Responsive**: Widgets are scrollable on smaller screens
- **Self-Documenting**: Each widget family is organized in its own page with minimal examples

## Structure

```
demo/
├── main.py              # Entry point and QApplication setup
├── app.py               # MainWindow with tabs and theme toggle
├── config.py            # Light and dark palettes
└── pages/
    ├── base_page.py     # BasePageWidget for reusable page construction
    ├── buttons_page.py  # Button showcase
    ├── inputs_page.py   # Input widgets showcase
    ├── composites_page.py # Dialogs showcase
    └── misc_page.py     # Labels, spinners, toasts, tooltips
```

## Requirements

- Python 3.10+
- PyQt6 >= 6.6
- sli-ui-toolkit (installed in editable mode)

## Development

Each page is a self-contained `BasePageWidget` subclass. To add a new widget showcase:

1. Create a new page in `pages/my_page.py`:
```python
from demo.pages.base_page import BasePageWidget
from sli_ui_toolkit.widgets import MyWidget

class MyPage(BasePageWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        
        section = self.add_section("My Widget")
        my_widget = MyWidget()
        section.addWidget(my_widget)
```

2. Register in `app.py`:
```python
from .pages.my_page import MyPage

# In MainWindow.__init__:
self._tabs.addTab(MyPage(), "My Tab")
```

The `add_section(title)` and `add_row(*widgets)` helpers handle layout automatically.
