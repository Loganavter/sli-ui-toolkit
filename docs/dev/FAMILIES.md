# Widget-family inspection catalog

Every widget family inspected by `sli_ui_toolkit.ui.inspector` is listed
here. Families self-describe via a co-located `inspect_spec` class attribute
(`ui/inspector/spec.py`); config auto-derives from the `__init__` signature,
state is curated, token families are static hints overridden by live capture.

| Family | Widget class(es) | File | Extras |
|---|---|---|---|
| Button | `Button` (+ all subclasses) | `ui/widgets/buttons/button.py` | regions, layers |
| Label | `Label` | `ui/widgets/atomic/text_labels.py` | |
| DropZoneLabel | `DropZoneLabel` | `ui/widgets/atomic/drop_zone_label.py` | |
| Switch | `Switch` | `ui/widgets/atomic/switch.py` | |
| Slider | `Slider` (incl. `ValueSlider` subclasses) | `ui/widgets/atomic/slider.py` | |
| SpinBox | `SpinBox` | `ui/widgets/atomic/spinbox.py` | |
| DoubleSpinBox | `DoubleSpinBox` | `ui/widgets/atomic/spinbox.py` | |
| CustomLineEdit | `CustomLineEdit` (incl. `TimeLineEdit`) | `ui/widgets/atomic/custom_line_edit.py` | |
| CheckBox | `CheckBox` | `ui/widgets/atomic/checkbox.py` | |
| RadioButton | `RadioButton` | `ui/widgets/atomic/radio.py` | |
| ComboBox | `ComboBox` | `ui/widgets/comboboxes/combo_box.py` | |
| ScrollableComboBox | `ScrollableComboBox` | `ui/widgets/comboboxes/scrollable_combobox.py` | |
| IconListWidget | `IconListWidget` (sidebar nav) | `ui/widgets/composite/sidebar_nav_list.py` | |
| ListPanel | `ListPanel` | `ui/widgets/composite/list_panel.py` | |
| AdaptiveTabStrip | `AdaptiveTabStrip` | `ui/widgets/composite/adaptive_tab_strip/widget.py` | |
| BaseFlyout | `BaseFlyout` | `ui/widgets/composite/base_flyout/widget.py` | |
| SimpleOptionsFlyout | `SimpleOptionsFlyout` | `ui/widgets/composite/simple_options_flyout.py` | |
| IconActionFlyout | `IconActionFlyout` | `ui/widgets/composite/icon_action_flyout.py` | |
| IndexedToggleFlyout | `IndexedToggleFlyout` | `ui/widgets/composite/indexed_toggle_flyout.py` | |
| TimelineWidget | `TimelineWidget` | `ui/widgets/composite/timeline_widget/widget.py` | |
| LoadingSpinner | `LoadingSpinner` | `ui/widgets/atomic/loading_spinner.py` | |
| CustomGroupWidget | `CustomGroupWidget` | `ui/widgets/atomic/custom_group_widget.py` | |
| ToastNotification | `ToastNotification` | `ui/widgets/composite/toast.py` | |

App-side families (registered by the host app the same way): RatingListItem,
ScrollValueButton, UnifiedListPicker, GlassHUD, InfoHUD, ZoomIndicator,
SettingsDialog.

## Adding a widget family

1. Give the class an `inspect_spec` attribute in its own file:
   `from sli_ui_toolkit.ui.inspector.spec import InspectSpec, SpecField`
   then    `inspect_spec = InspectSpec(family=..., state=(SpecField(...), ...),
   token_family=(...), regions=..., layers=..., docs=...)`. Config is auto-derived —
   declare `config` only when the constructor leaks internals. Auto-derivation
   walks the MRO for the nearest `__init__` that declares named kwargs, so a
   thin subclass forwarding `*args, **kwargs` still shows its base
   constructor's parameters.
2. `docs=` points at the family's docs file (repo-relative, e.g.
   `docs/user/BUTTON_API.md`). The inspector renders it in the read-only
   **Docs** section (markdown document view) and shows a `docs` row in the
   Object section; the Code section's top row gets a Docs button that
   switches to it. Host apps can read the reference back via
   `sli_ui_toolkit.ui.inspector.spec.docs_for(widget)` (or
   `WidgetInspection.docs`) to build their own help entries.
3. Add a row to the table above.
4. Subclasses inherit via the MRO; widgets without a spec fall back to the
   duck-typed registry and then the generic QWidget inspection.
