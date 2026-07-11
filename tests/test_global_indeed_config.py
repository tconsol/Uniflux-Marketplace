from app.services.indeed_scheduler_service import GLOBAL_INDEED_CONFIG


def test_global_indeed_defaults():
    assert GLOBAL_INDEED_CONFIG.location == "United States"
    assert GLOBAL_INDEED_CONFIG.interval_minutes == 30
    assert len(GLOBAL_INDEED_CONFIG.keywords) == 14
