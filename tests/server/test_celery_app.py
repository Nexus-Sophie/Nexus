from __future__ import annotations

import importlib

from src.server.config import get_settings


def _conf_value(conf, key: str):
    """Read Celery config from real Celery or the test stub."""
    if isinstance(conf, dict):
        return conf[key]
    return getattr(conf, key)


def test_celery_app_bounds_global_publish_retries_and_timeouts(monkeypatch) -> None:
    """Verify celery app bounds global publish retries and timeouts."""
    monkeypatch.setenv("NEXUS_CELERY_QUEUE", "test-agent-tasks")
    monkeypatch.setenv("NEXUS_CELERY_VISIBILITY_TIMEOUT_SECONDS", "123")
    monkeypatch.setenv("NEXUS_CELERY_TASK_PUBLISH_MAX_RETRIES", "3")
    monkeypatch.setenv("NEXUS_CELERY_BROKER_CONNECTION_TIMEOUT_SECONDS", "2.0")
    get_settings.cache_clear()

    import src.server.celery.app as celery_app_module

    celery_app_module = importlib.reload(celery_app_module)
    celery_app = celery_app_module.celery_app

    assert _conf_value(celery_app.conf, "task_publish_retry") is True
    assert _conf_value(celery_app.conf, "task_publish_retry_policy") == {
        "max_retries": 3,
        "interval_start": 0,
        "interval_step": 0.2,
        "interval_max": 0.2,
    }
    assert _conf_value(celery_app.conf, "broker_connection_timeout") == 2.0
    assert _conf_value(celery_app.conf, "redis_socket_connect_timeout") == 2.0
    assert _conf_value(celery_app.conf, "redis_socket_timeout") == 2.0
    assert _conf_value(celery_app.conf, "task_acks_late") is True
    assert _conf_value(celery_app.conf, "task_reject_on_worker_lost") is True
    assert _conf_value(celery_app.conf, "task_acks_on_failure_or_timeout") is True
    assert _conf_value(celery_app.conf, "broker_transport_options") == {
        "visibility_timeout": 123,
        "socket_connect_timeout": 2.0,
        "socket_timeout": 2.0,
    }
    assert _conf_value(celery_app.conf, "result_backend_transport_options") == {
        "visibility_timeout": 123,
        "retry_policy": {
            "timeout": 2.0,
        },
    }
    assert _conf_value(celery_app.conf, "visibility_timeout") == 123
    assert _conf_value(celery_app.conf, "task_default_queue") == "test-agent-tasks"
