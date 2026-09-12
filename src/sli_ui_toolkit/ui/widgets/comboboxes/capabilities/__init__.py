"""ComboBox capabilities — composable ComboBox-specific behavior modules.

Mirrors ``buttons/capabilities/``: each capability encapsulates one piece of
ComboBox-only gesture/interaction logic and is attached via the inherited
``Button.attach_capability()`` (``ComboBox`` is a ``Button`` subclass).
Unlike ``buttons/capabilities``, these are ComboBox-specific (not meant for
reuse on a plain ``Button``) and are attached by ``ComboBox`` itself, not by
app code.
"""

from .gear_drag import GearDragCapability

__all__ = [
    "GearDragCapability",
]
