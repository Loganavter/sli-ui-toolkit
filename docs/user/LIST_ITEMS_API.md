# List Items API

`sli_ui_toolkit.ui.widgets.list_items` — row widgets meant to be dropped into
a host-owned list/flyout, not a generic list container itself.

| Widget | Description |
|--------|-------------|
| `EditableListItem` | Row with inline-editable text, an optional checkbox, and a delete button. |

Both import from `sli_ui_toolkit.widgets`.

`EditableListItem` is a `Button` subclass (regions/layers-based row, see
[BUTTON_API.md](BUTTON_API.md)):

```python
from sli_ui_toolkit.widgets import EditableListItem

row = EditableListItem(
    decrement_rating=lambda path: ...,
)
```

`get_rating`/`increment_rating`/`decrement_rating`/`create_rating_gesture`/
`on_update_drop_indicator`/`on_clear_drop_indicator` are host-supplied hooks
(all default to `None`); the row has no built-in rating persistence of its
own.

`EditableListItem(text="", *, enabled=True, placeholder="", checkbox_tooltip="", delete_icon="delete", delete_tooltip="", parent=None)`
pairs a leading checkbox, an inline-editable `CustomLineEdit`, and a
trailing delete `Button` (28×28, `variant="surface"`). It has one signal —
`delete_clicked` — plus plain getters for the other two rows' state:

```python
from sli_ui_toolkit.widgets import EditableListItem

item = EditableListItem("Preset A", placeholder="Unnamed preset", delete_tooltip="Remove")
item.delete_clicked.connect(lambda: remove_preset(item))

item.get_text()             # stripped text from the line edit
item.is_enabled_checked()   # checkbox state
item.get_value_data()       # {"value": ..., "enabled": ...} convenience dict
```

The line edit (`item.input_field`) and checkbox (`item.checkbox`) are plain
public attributes — connect to their own signals directly (e.g.
`item.input_field.textChanged`) if you need live updates instead of reading
`get_text()` on demand.

See also [API_CATALOG.md](API_CATALOG.md) for the full widget index.
