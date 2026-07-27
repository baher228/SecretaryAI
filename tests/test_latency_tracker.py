from secretary_ai.services.latency import LatencyTracker


def test_latency_tracker_emits_kpi_metrics() -> None:
    tracker = LatencyTracker()
    call_id = "tg-latency-1"
    tracker.mark_answered(call_id)
    tracker.mark_first_user_speech(call_id)
    tracker.mark_first_assistant_audio(call_id)
    tracker.mark_barge_in(call_id)
    tracker.mark_interrupt_stop(call_id)

    metrics = tracker.metrics(call_id)
    assert metrics["call_id"] == call_id
    assert metrics["call_answer_ms"] is not None
    assert metrics["first_response_ms"] is not None
    assert metrics["barge_in_stop_ms"] is not None
    assert metrics["barge_in_count"] == 1
    assert metrics["stream_interrupt_count"] == 1
    assert set(metrics["kpi_ok"].keys()) == {"call_answer", "first_response", "barge_in_stop"}
