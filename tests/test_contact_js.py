"""The enquiry form composes a mailto: link; check it under Node (skipped without Node)."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = r"""
globalThis.window = { ATLAS_SITE: {} };
globalThis.document = { addEventListener() {} };
const { buildMessage } = require(process.argv[1]);
const data = new Map(Object.entries({ topic: 'Reuse and licensing', company: 'Acme & Sons', name: ' Ada ', email: 'ada@acme.test',
  message: 'Can we use it?\nLine two & <tags> "quotes"' }));
const m = buildMessage({ contactEmail: 'maintainer@example.test' }, data);
const query = new URLSearchParams(m.href.split('?')[1]);
console.log(JSON.stringify({ to: m.href.split('?')[0], subject: query.get('subject'), body: query.get('body') }));
"""


@pytest.mark.skipif(shutil.which("node") is None, reason="Node is not installed")
def test_mailto_carries_every_field_and_survives_special_characters():
    out = subprocess.run(["node", "-e", SCRIPT, str(ROOT / "site" / "assets" / "contact.js")], check=True, capture_output=True, text=True, encoding="utf-8")
    r = json.loads(out.stdout)
    assert r["to"] == "mailto:maintainer@example.test"
    assert r["subject"] == "[Arctic Passage Atlas] Reuse and licensing \u2014 Acme & Sons"
    for expected in ("Name: Ada", "Organisation: Acme & Sons", "Reply-to email: ada@acme.test", "Timeframe: not stated",
                     'Line two & <tags> "quotes"'):
        assert expected in r["body"]


def test_shipped_contact_email_is_the_maintainers_not_a_placeholder():
    import re

    text = (ROOT / "site" / "assets" / "site-config.js").read_text(encoding="utf-8")
    m = re.search(r'contactEmail:\s*"([^"]*)"', text)
    assert m and m.group(1) == "maheep512@gmail.com"
