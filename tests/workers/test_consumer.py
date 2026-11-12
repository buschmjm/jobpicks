"""Tests for queue consumer loop behavior."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from workers import consumer


def test_run_consumer_exits_when_poll_false_and_queue_empty() -> None:
    session = MagicMock()
    session.__enter__ = MagicMock(return_value=session)
    session.__exit__ = MagicMock(return_value=False)
    with (
        patch.object(consumer, "SessionLocal", return_value=session),
        patch.object(consumer, "requeue_stale_running", return_value=0),
        patch(
            "api.services.application_packet_service.application_packet_service.recover_stale_generating",
            return_value=0,
        ),
        patch.object(consumer, "process_one", return_value=False),
    ):
        consumer.run_consumer(poll=False)


def test_run_consumer_sleeps_when_poll_true_and_queue_empty() -> None:
    session = MagicMock()
    session.__enter__ = MagicMock(return_value=session)
    session.__exit__ = MagicMock(return_value=False)
    with (
        patch.object(consumer, "SessionLocal", return_value=session),
        patch.object(consumer, "requeue_stale_running", return_value=0),
        patch(
            "api.services.application_packet_service.application_packet_service.recover_stale_generating",
            return_value=0,
        ),
        patch.object(consumer, "process_one", return_value=False),
    ):
        with patch.object(consumer.time, "sleep", side_effect=KeyboardInterrupt):
            with pytest.raises(KeyboardInterrupt):
                consumer.run_consumer(poll=True, idle_sleep_seconds=0.5)
