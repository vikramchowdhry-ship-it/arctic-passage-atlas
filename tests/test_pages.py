from pathlib import Path

from arctic_passage_atlas.config import load_config
from arctic_passage_atlas.pages import NAV, PAGES, apply_chrome

ROOT = Path(__file__).resolve().parents[1]


def test_every_page_links_every_other_page_and_is_idempotent():
    config = load_config(ROOT / "configs" / "cambridge-bay.json")
    apply_chrome(config)  # normalise first
    snapshot = {p: (ROOT / "site" / p).read_text(encoding="utf-8") for p, _ in PAGES}
    for path, text in snapshot.items():
        prefix = "../" * path.count("/")
        for target, _label in PAGES:
            assert f'href="{prefix}{target}"' in text, f"{path} does not link to {target}"
        assert text.count("<!-- chrome:header -->") == 1 and text.count("<!-- chrome:footer -->") == 1
        if path in NAV:
            assert 'aria-current="page"' in text
    assert apply_chrome(config) == []  # nothing left to change on a second run


def test_route_and_live_pages_carry_a_notice_and_not_the_demo_banner():
    for page, marker in (("live.html", "LIVE THIRD-PARTY FEEDS"), ("route.html", "NOT FOR NAVIGATION")):
        text = (ROOT / "site" / page).read_text(encoding="utf-8")
        assert marker in text and "demo-banner" not in text
