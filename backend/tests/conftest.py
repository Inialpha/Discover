from pathlib import Path
import pytest
from discover.config import Settings


@pytest.fixture
def settings():
    return Settings(qloo_api_key="secret-test-key", qloo_base_url="https://mock.invalid", qloo_timeout=5, qloo_retries=1,
                    llm_api_key=None, llm_base_url=None, llm_model=None, llm_timeout=5)


@pytest.fixture
def examples():
    return Path(__file__).resolve().parents[2] / "entity_examples"


# ---- persona-discovery fixtures --------------------------------------------------------------------------
from discover.personas.intake import ProductIntake
from discover.personas.refdata.records import (FX_PER_USD, GNI_PC_LCU, OFFICIAL_FX, QUINTILE_SHARES, RefRecord)
from discover.personas.refdata.store import ReferenceStore

NOW = "2099-01-01T00:00:00+00:00"  # far future => never "stale" relative to snapshots in tests that care


def rec(country, indicator, value, year=2024, source="test", fetched_at=None, as_of=None):
    from discover.personas.refdata.records import now_iso
    return RefRecord(country, indicator, year, value, source, fetched_at or now_iso(), as_of)


@pytest.fixture
def store():
    """SYNTHETIC reference data (not real statistics): complete quintiles for NGA, USA and JPN."""
    s = ReferenceStore(cache_path=None, snapshot_path=None)
    recs = [
        rec("NGA", GNI_PC_LCU, 1_800_000), rec("USA", GNI_PC_LCU, 90_000), rec("JPN", GNI_PC_LCU, 5_700_000),
        rec("KEN", GNI_PC_LCU, 200_000),
    ]
    shares = {"NGA": (7.5, 11.0, 15.0, 21.0, 45.5), "USA": (3.0, 8.0, 14.0, 22.0, 53.0), "JPN": (8.0, 13.0, 17.0, 23.0, 39.0)}
    for c, vals in shares.items():
        for q, v in zip(range(1, 6), vals):
            recs.append(rec(c, QUINTILE_SHARES[q], v, year=2021))
    for c, v in {"USD": 1.0, "NGN": 1500.0, "JPY": 150.0, "EUR": 0.9, "KES": 130.0}.items():
        recs.append(RefRecord(c, FX_PER_USD, None, v, "test", __import__("discover.personas.refdata.records", fromlist=["now_iso"]).now_iso(), "as-of"))
    s.put_many(recs)
    return s


@pytest.fixture
def make_intake():
    def _mk(**kw):
        base = dict(name="Test phone", description="A smartphone with a long battery life for everyday use.",
                    category="smartphone", price=40_000, currency="NGN", location="Lagos")
        base.update(kw)
        return ProductIntake(**base)
    return _mk
