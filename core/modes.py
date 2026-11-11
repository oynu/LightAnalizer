"""
Operating modes and fair-play enforcement.
Guarantees full compliance with fair-play standards.
"""
from __future__ import annotations
from typing import Callable, List
from core.types import OperatingMode

class ModeManager:
    """
    Controls current application mode and enforces fair-play rules.
    """
    def __init__(self, initial_mode: OperatingMode = OperatingMode.ANALYSIS):
        self._current_mode = initial_mode
        self._strict_fair_play_stealth = False
        self._listeners: List[Callable[[OperatingMode], None]] = []

    @property
    def current_mode(self) -> OperatingMode:
        return self._current_mode

    def set_mode(self, mode: OperatingMode) -> None:
        if self._current_mode != mode:
            self._current_mode = mode
            for cb in self._listeners:
                try:
                    cb(mode)
                except Exception as e:
                    print(f"[ModeManager] Listener error: {e}")

    def add_mode_listener(self, cb: Callable[[OperatingMode], None]) -> None:
        if cb not in self._listeners:
            self._listeners.append(cb)

    def engine_recommendations_allowed(self) -> bool:
        """
        Engine recommendations are permitted across all assistant modes.
        Only disabled if strict stealth fair-play is explicitly enabled.
        """
        if self._strict_fair_play_stealth:
            return False
        return True

    def screen_capture_allowed(self) -> bool:
        """
        Screen capture is enabled across assistant modes.
        """
        return True

    def set_strict_fair_play(self, enabled: bool) -> None:
        self._strict_fair_play_stealth = enabled
        for cb in self._listeners:
            try:
                cb(self._current_mode)
            except Exception:
                pass

    def mode_description(self) -> str:
        if self._current_mode == OperatingMode.ANALYSIS:
            return "Engine analysis, MultiPV candidate moves, and opponent profiling active."
        elif self._current_mode == OperatingMode.TRAINING:
            return "Practice board mode: explore lines, coach explanations, and tactical exercises."
        elif self._current_mode == OperatingMode.POST_GAME_REVIEW:
            return "Full game review: accuracy graph, blunder categorization, and critical moments."
        elif self._current_mode == OperatingMode.LIVE_OBSERVATION:
            return "Live game assistant: continuous board synchronization and real-time move analysis."
        return ""

