from pathlib import Path

from gridlens.common.regions import load_regions

REPO = Path(__file__).resolve().parents[1]


def test_python_regions_match_dbt_seed():
    """Ingestion and dbt must agree on what a region is."""
    pkg = (REPO / "src/gridlens/common/regions.csv").read_text(encoding="utf-8").strip()
    seed = (REPO / "dbt/seeds/regions.csv").read_text(encoding="utf-8").strip()
    assert pkg == seed


def test_regions_load():
    regions = load_regions()
    assert len({r.code for r in regions}) == len(regions)
    assert all(-90 <= r.latitude <= 90 and -180 <= r.longitude <= 180 for r in regions)
