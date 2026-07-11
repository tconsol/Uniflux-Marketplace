from datetime import datetime
from app.services.jobs_service import _job_identity_query
from app.models.scraped_job import ScrapedJob


def _job(**kw):
    base = dict(org_id="GLOBAL", source_site="indeed", scraped_at=datetime.utcnow())
    base.update(kw)
    return ScrapedJob(**base)


def test_identity_uses_external_id_without_org():
    q = _job_identity_query(_job(external_id="abc123"))
    assert q == {"source_site": "indeed", "external_id": "abc123"}


def test_identity_fallback_without_org():
    q = _job_identity_query(_job(title="Dev", company_name="Acme", url="http://x"))
    assert "org_id" not in q
    assert q["source_site"] == "indeed"
    assert q["title"] == "Dev"
