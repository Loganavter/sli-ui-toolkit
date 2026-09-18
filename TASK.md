# Worker context — task-toolkit-debugflags-followup-2026-09-06 (supervisor copy)

Title: Toolkit debug-flags FOLLOW-UP (out of scope) — inspector/text_view/tab-bar/marquee/realign/context-menu ungated clusters
Base: private/main 813ee12 (your branch origin/private-main-base).
Type: docs/code-hygiene. Priority P2.

Background: waves WS-NAV / WS-FLYOUT / WS-MISC already converted nav/button/flyout/misc
clusters to env-gated streams. Convention contract: docs/dev/LOGGING.md
("Unique-prefix env-gated streams" recipe: `_xxx_debug_enabled()` /
`_xxx_debug()` over core.debug_flags.any_flag, call-time check, unique
bracketed prefix, OFF by default even under host --debug; canonical SLI_*
names first, documented at use site + LOGGING.md stream table).

Known ungated sites on this base (verify, then convert):
1. src/sli_ui_toolkit/ui/inspector/tree.py — raw
   logging.getLogger("sli_ui_toolkit.inspector.tree").isEnabledFor(DEBUG) gates
2. src/sli_ui_toolkit/ui/widgets/composite/text_view/canvas.py — legacy strict
   os.getenv("SLI_TEXTVIEW_DEBUG") == "1" (LOGGING.md: migrate to any_flag
   when touched) + diagnostic _canvas_logger.warning calls
3. src/sli_ui_toolkit/ui/widgets/overlays/marquee_band_gesture.py —
   _dbg = logging.getLogger("ImproveImgSLI.flyout")  # TEMP debug (host-tree leak)
4. src/sli_ui_toolkit/ui/widgets/composite/adaptive_tab_strip/tab_bar.py:332 —
   ungated _log.debug("[TAB-BAR] ...")
5. src/sli_ui_toolkit/ui/managers/realign.py +
   src/sli_ui_toolkit/ui/widgets/composite/context_menu/ — audit for ungated
   logging; convert if found, else report clean with grep evidence.

AGENTS.md hard rules apply: CHANGELOG.md Unreleased entry mandatory (same
commit, NO version bump); mypy 0 errors; stdlib logging only, never print().
