"""Every env var the deployments set must keep binding to its worker setting.

compose and k8s configure workers through these exact names and defaults;
renaming or re-defaulting one silently changes production behaviour.
"""

import pytest

import uvo_workers.crz as crz
import uvo_workers.dedup as dedup
import uvo_workers.ingestor as ingestor
import uvo_workers.itms as itms
import uvo_workers.ted as ted
import uvo_workers.vestnik as vestnik

_SHARED = {"HEALTH_PORT": ("health_port", "9100", 9100)}
_STREAM = {
    "STREAM_MAXLEN_APPROX": ("stream_maxlen_approx", "123", 123),
    "STREAM_HIGH_WATER": ("stream_high_water", "45", 45),
}
_OVERLAP = {"CHECKPOINT_OVERLAP_SECONDS": ("checkpoint_overlap_seconds", "77", 77)}

# worker -> (settings class, default health port, {ENV_NAME: (field, raw, expected)})
CASES = {
    "vestnik": (
        vestnik.VestnikSettings,
        8091,
        {
            **_SHARED,
            **_STREAM,
            "VESTNIK_INTERVAL_SECONDS": ("vestnik_interval_seconds", "11", 11),
            "VESTNIK_MODE": ("vestnik_mode", "historical", "historical"),
        },
    ),
    "crz": (
        crz.CrzSettings,
        8092,
        {
            **_SHARED,
            **_STREAM,
            **_OVERLAP,
            "CRZ_INTERVAL_SECONDS": ("crz_interval_seconds", "12", 12),
        },
    ),
    "ted": (
        ted.TedSettings,
        8093,
        {
            **_SHARED,
            **_STREAM,
            **_OVERLAP,
            "TED_INTERVAL_SECONDS": ("ted_interval_seconds", "13", 13),
        },
    ),
    "itms": (
        itms.ItmsSettings,
        8094,
        {
            **_SHARED,
            **_STREAM,
            "ITMS_INTERVAL_SECONDS": ("itms_interval_seconds", "14", 14),
            "ITMS_CACHE_BACKEND": ("itms_cache_backend", "memory", "memory"),
            "ITMS_CACHE_TTL_SECONDS": ("itms_cache_ttl_seconds", "15", 15),
        },
    ),
    "ingestor": (
        ingestor.IngestorSettings,
        8095,
        {
            **_SHARED,
            "INGESTOR_BATCH_SIZE": ("ingestor_batch_size", "16", 16),
            "INGESTOR_MAX_DELIVERIES": ("ingestor_max_deliveries", "17", 17),
            "INGESTOR_RECLAIM_INTERVAL_SECONDS": (
                "ingestor_reclaim_interval_seconds",
                "1.5",
                1.5,
            ),
            "INGESTOR_RECLAIM_MIN_IDLE_MS": ("ingestor_reclaim_min_idle_ms", "18", 18),
            "INGESTOR_MAINTENANCE_INTERVAL_SECONDS": (
                "ingestor_maintenance_interval_seconds",
                "2.5",
                2.5,
            ),
        },
    ),
    "dedup": (
        dedup.DedupWorkerSettings,
        8096,
        {
            **_SHARED,
            "DEDUP_INTERVAL_SECONDS": ("dedup_interval_seconds", "19", 19),
            "DEDUP_DEBOUNCE_SECONDS": ("dedup_debounce_seconds", "20", 20),
            "DEDUP_WINDOW_DAYS": ("dedup_window_days", "21", 21),
            "DEDUP_LOCK_TTL_SECONDS": ("dedup_lock_ttl_seconds", "22", 22),
        },
    ),
}

_DEFAULTS = {
    "vestnik": {"vestnik_interval_seconds": 3600, "vestnik_mode": "recent"},
    "crz": {"crz_interval_seconds": 3600, "checkpoint_overlap_seconds": 86_400},
    "ted": {"ted_interval_seconds": 3600, "checkpoint_overlap_seconds": 86_400},
    "itms": {
        "itms_interval_seconds": 3600,
        "itms_cache_backend": "redis",
        "itms_cache_ttl_seconds": 86_400,
    },
    "ingestor": {
        "ingestor_batch_size": 100,
        "ingestor_max_deliveries": 5,
        "ingestor_reclaim_interval_seconds": 30.0,
        "ingestor_reclaim_min_idle_ms": 60_000,
        "ingestor_maintenance_interval_seconds": 30.0,
    },
    "dedup": {
        "dedup_interval_seconds": 3600,
        "dedup_debounce_seconds": 5,
        "dedup_window_days": 30,
        "dedup_lock_ttl_seconds": 1800,
    },
}

_ALL_ENV_NAMES = {name for _, _, cases in CASES.values() for name in cases}


def _clear_env(monkeypatch):
    for name in _ALL_ENV_NAMES:
        monkeypatch.delenv(name, raising=False)


@pytest.mark.parametrize("worker", CASES)
def test_env_names_bind(worker, monkeypatch):
    cls, _, env_cases = CASES[worker]
    _clear_env(monkeypatch)
    for env_name, (_, raw, _) in env_cases.items():
        monkeypatch.setenv(env_name, raw)
    settings = cls(_env_file=None)
    for env_name, (field, _, expected) in env_cases.items():
        assert getattr(settings, field) == expected, env_name


@pytest.mark.parametrize("worker", CASES)
def test_defaults_unchanged(worker, monkeypatch):
    cls, health_port, _ = CASES[worker]
    _clear_env(monkeypatch)
    settings = cls(_env_file=None)
    assert settings.health_port == health_port
    for field, expected in _DEFAULTS[worker].items():
        assert getattr(settings, field) == expected, field
    if worker in {"vestnik", "crz", "ted", "itms"}:
        assert settings.stream_maxlen_approx == 1_000_000
        assert settings.stream_high_water == 50_000
