"""
AC-2: run-history instrumentation for exit-condition metrics.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_local_get_run_stats_counts_consecutive_daily_runs(monkeypatch, tmp_path):
    """Three daily runs on consecutive days should produce a 3-day streak."""
    from hedwig.models import EvolutionCycleType, EvolutionLog
    from hedwig.storage import local as local_storage

    monkeypatch.setenv("HEDWIG_DB_PATH", str(tmp_path / "hedwig.db"))

    start = datetime(2026, 4, 10, 6, 0, 0, tzinfo=timezone.utc)
    for cycle_number in range(3):
        assert local_storage.save_evolution_log(
            EvolutionLog(
                cycle_type=EvolutionCycleType.DAILY,
                cycle_number=cycle_number,
                criteria_version_before=cycle_number,
                criteria_version_after=cycle_number + 1,
                timestamp=start + timedelta(days=cycle_number),
            )
        )

    stats = local_storage.get_run_stats()

    assert stats["consecutive_daily_runs"] >= 3
    assert stats["total_daily_cycles"] == 3
    assert stats["total_weekly_cycles"] == 0
    assert stats["last_daily_at"] == "2026-04-12T06:00:00+00:00"
    assert stats["last_weekly_at"] is None
