from worker import WorkerSettings


def test_worker_settings_registers_expected_functions():
    func_names = [
        f.__name__ if hasattr(f, "__name__") else str(f)
        for f in WorkerSettings.functions
    ]
    assert any("process_webhook_events" in name for name in func_names)


def test_worker_settings_has_cron_jobs_configured():
    assert len(WorkerSettings.cron_jobs) >= 1
