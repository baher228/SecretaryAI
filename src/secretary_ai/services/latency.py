from __future__ import annotations

from dataclasses import dataclass, field
from time import monotonic
from typing import Any


@dataclass(slots=True)
class CallLatencyTimeline:
    call_id: str
    created_mono: float = field(default_factory=monotonic)
    call_answered_mono: float | None = None
    first_user_speech_mono: float | None = None
    first_assistant_audio_mono: float | None = None
    first_assistant_turn_complete_mono: float | None = None
    last_barge_in_mono: float | None = None
    last_barge_in_stop_mono: float | None = None
    barge_in_count: int = 0
    stream_interrupt_count: int = 0

    def mark_answered(self) -> None:
        if self.call_answered_mono is None:
            self.call_answered_mono = monotonic()

    def mark_first_user_speech(self) -> None:
        if self.first_user_speech_mono is None:
            self.first_user_speech_mono = monotonic()

    def mark_first_assistant_audio(self) -> None:
        if self.first_assistant_audio_mono is None:
            self.first_assistant_audio_mono = monotonic()

    def mark_first_turn_complete(self) -> None:
        if self.first_assistant_turn_complete_mono is None:
            self.first_assistant_turn_complete_mono = monotonic()

    def mark_barge_in(self) -> None:
        self.barge_in_count += 1
        self.last_barge_in_mono = monotonic()

    def mark_interrupt_stop(self) -> None:
        self.stream_interrupt_count += 1
        self.last_barge_in_stop_mono = monotonic()

    @staticmethod
    def _delta_ms(start: float | None, end: float | None) -> int | None:
        if start is None or end is None:
            return None
        return max(0, int((end - start) * 1000))

    def to_metrics(self) -> dict[str, Any]:
        answered_ms = self._delta_ms(self.created_mono, self.call_answered_mono)
        first_response_ms = self._delta_ms(self.first_user_speech_mono, self.first_assistant_audio_mono)
        barge_in_stop_ms = self._delta_ms(self.last_barge_in_mono, self.last_barge_in_stop_mono)
        return {
            "call_id": self.call_id,
            "call_answer_ms": answered_ms,
            "first_response_ms": first_response_ms,
            "barge_in_stop_ms": barge_in_stop_ms,
            "barge_in_count": self.barge_in_count,
            "stream_interrupt_count": self.stream_interrupt_count,
            "kpi_thresholds_ms": {
                "call_answer_max": 2000,
                "first_response_max": 1500,
                "barge_in_stop_max": 300,
            },
            "kpi_ok": {
                "call_answer": answered_ms is not None and answered_ms <= 2000,
                "first_response": first_response_ms is not None and first_response_ms <= 1500,
                "barge_in_stop": barge_in_stop_ms is not None and barge_in_stop_ms <= 300,
            },
        }


class LatencyTracker:
    def __init__(self) -> None:
        self._timelines: dict[str, CallLatencyTimeline] = {}

    def ensure(self, call_id: str) -> CallLatencyTimeline:
        timeline = self._timelines.get(call_id)
        if timeline is None:
            timeline = CallLatencyTimeline(call_id=call_id)
            self._timelines[call_id] = timeline
        return timeline

    def mark_answered(self, call_id: str) -> CallLatencyTimeline:
        timeline = self.ensure(call_id)
        timeline.mark_answered()
        return timeline

    def mark_first_user_speech(self, call_id: str) -> CallLatencyTimeline:
        timeline = self.ensure(call_id)
        timeline.mark_first_user_speech()
        return timeline

    def mark_first_assistant_audio(self, call_id: str) -> CallLatencyTimeline:
        timeline = self.ensure(call_id)
        timeline.mark_first_assistant_audio()
        return timeline

    def mark_first_turn_complete(self, call_id: str) -> CallLatencyTimeline:
        timeline = self.ensure(call_id)
        timeline.mark_first_turn_complete()
        return timeline

    def mark_barge_in(self, call_id: str) -> CallLatencyTimeline:
        timeline = self.ensure(call_id)
        timeline.mark_barge_in()
        return timeline

    def mark_interrupt_stop(self, call_id: str) -> CallLatencyTimeline:
        timeline = self.ensure(call_id)
        timeline.mark_interrupt_stop()
        return timeline

    def metrics(self, call_id: str) -> dict[str, Any]:
        timeline = self._timelines.get(call_id)
        if timeline is None:
            return {
                "call_id": call_id,
                "detail": "No latency timeline for this call.",
            }
        return timeline.to_metrics()

    def all_metrics(self) -> list[dict[str, Any]]:
        return [timeline.to_metrics() for timeline in self._timelines.values()]
