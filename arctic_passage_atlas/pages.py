"""Keep the site header, footer and stylesheet links identical on every page.

Pages carry marker comments; ``apply_chrome`` rewrites whatever is between them. A page that still has
the original unmarked header or footer is migrated on first run, and its per-page source line (the
second span of the old footer) is kept as that page's legal line.
"""

from __future__ import annotations

import html
import re
from pathlib import Path

from .config import ProjectConfig

# (path relative to site/, nav label)
PAGES: list[tuple[str, str]] = [
    ("index.html", "Home"),
    ("live.html", "Live"),
    ("route.html", "Route"),
    ("layers/change.html", "Change"),
    ("layers/ice.html", "Ice"),
    ("layers/vessels.html", "Vessels"),
    ("methodology.html", "Method"),
    ("sources.html", "Sources"),
    ("about.html", "About"),
    ("defence.html", "Defence"),
    ("contact.html", "Contact"),
]

# Pages shown in the top navigation. Sources and About live in the footer to keep the header short.
NAV = {"index.html", "live.html", "route.html", "layers/change.html", "layers/ice.html", "layers/vessels.html", "methodology.html", "contact.html"}

BRAND_MARK = (
    '<svg class="brand-mark" viewBox="0 0 32 32" aria-hidden="true" focusable="false">'
    '<circle cx="16" cy="16" r="14.5" fill="#0b1e2b" stroke="#24465b"/>'
    '<path d="M5 21 C10 11 14 23 19 14 S25 9 27 11" fill="none" stroke="#7bdff2" stroke-width="2.2" '
    'stroke-linecap="round"/><circle cx="19" cy="14" r="2.3" fill="#ffb454"/></svg>'
)
PAGE_LEGAL = {
    "layers/change.html": "Source: USGS Landsat 8 Collection 2 Level 2 via Google Earth Engine; water masked with ESA WorldCover. Candidates are not confirmed construction.",
    "layers/ice.html": "Source: Copernicus Sentinel-1 GRD via Google Earth Engine. Reference: NOAA CDR OISST V2.1 ice band. Not an operational ice chart.",
    "layers/vessels.html": "Source: Global Fishing Watch (CC BY-NC 4.0, non-commercial). Not for navigation, enforcement or claims about an individual vessel's conduct.",
    "route.html": "Planning estimate from shortest-water paths on a coarse coastline, with model and Environment Canada forecasts. Not for navigation; ice, depth, currents and charts are not modelled.",
    "defence.html": "Environmental planning context only. Not for targeting, tracking, surveillance or navigation. No accreditation or clearance is claimed.",
    "contact.html": "Open-source method maintained by Maheep Chowdhary. Enquiries about the method, adoption and collaboration; not a paid service.",
    "live.html": "Live feeds: Environment and Climate Change Canada (Open Government Licence – Canada), NASA GIBS and NSIDC. Context only, not project results.",
}
DEFAULT_LEGAL = "Method prototype. Not an operational navigation, enforcement or surveillance system."
HEADER_RE = re.compile(r"<!-- chrome:header -->.*?<!-- /chrome:header -->|<header class=\"site-header\">.*?</header>", re.DOTALL)
FOOTER_RE = re.compile(r"<!-- chrome:footer -->.*?<!-- /chrome:footer -->|<footer class=\"site-footer\">.*?</footer>", re.DOTALL)
LEGAL_RE = re.compile(r'<p class="footer-legal">(.*?)</p>', re.DOTALL)


def header(prefix: str, current: str) -> str:
    current_attr = ' aria-current="page"'
    links = "".join(
        f'<a{current_attr if path == current else ""} href="{prefix}{path}">{label}</a>'
        for path, label in PAGES
        if path in NAV
    )
    return (
        "<!-- chrome:header -->"
        '<header class="site-header"><nav class="nav" aria-label="Primary">'
        f'<a class="brand" href="{prefix}index.html">{BRAND_MARK}'
        '<span class="brand-text">Arctic Passage Atlas<small>Open geospatial method</small></span></a>'
        '<button class="nav-toggle" type="button" aria-expanded="false" aria-controls="nav-links">Menu</button>'
        f'<div class="nav-links" id="nav-links">{links}</div></nav></header>'
        "<!-- /chrome:header -->"
    )


def footer(prefix: str, legal: str) -> str:
    def link(path: str, label: str) -> str:
        return f'<a href="{prefix}{path}">{label}</a>'

    return (
        "<!-- chrome:footer -->"
        '<footer class="site-footer pro"><div class="wrap"><div class="footer-grid">'
        "<div><strong>Arctic Passage Atlas</strong>"
        '<p style="margin:.5rem 0 0;max-width:34ch">An open-source method for observing Arctic surface, '
        "sea-ice and vessel-event change from public data. By Maheep Chowdhary.</p></div>"
        f'<div><h4>Project</h4>{link("index.html", "Overview")}{link("live.html", "Live conditions")}'
        f'{link("methodology.html", "Method and limits")}{link("sources.html", "Sources and licences")}</div>'
        f'<div><h4>Layers</h4>{link("layers/change.html", "Surface change")}'
        f'{link("layers/ice.html", "Sea ice")}{link("layers/vessels.html", "Vessel events")}</div>'
        f'<div><h4>Company</h4>{link("contact.html", "Contact and support")}{link("defence.html", "Defence and security")}{link("about.html", "About the author")}'
        f'{link("sources.html#licences", "Licences")}{link("route.html", "Route planner")}</div>'
        f'</div><p class="footer-legal">{legal}</p></div></footer>'
        "<!-- /chrome:footer -->"
    )


def _legal_from(old_footer: str) -> str:
    marked = LEGAL_RE.search(old_footer)
    if marked:
        return marked.group(1)
    spans = re.findall(r"<span[^>]*>(.*?)</span>", old_footer, re.DOTALL)
    texts = [" ".join(re.sub(r"<[^>]+>", "", s).split()) for s in spans]
    extra = [t for t in texts[1:] if t]
    return html.escape(" · ".join(extra) if extra else DEFAULT_LEGAL, quote=False)


DESCRIPTIONS = {
    "about.html": "About Arctic Passage Atlas and its author: an open-source geospatial methodology project by Maheep Chowdhary.",
    "methodology.html": "How Arctic Passage Atlas screens surface change, classifies sea ice and handles vessel events, with limits and reproducibility boundaries stated.",
    "layers/change.html": "Landsat surface-change candidates over the Cambridge Bay study area: method, limits and data.",
    "layers/ice.html": "Sentinel-1 sea-ice classification over the study area: threshold method, sensitivity and limitations.",
    "layers/vessels.html": "AIS gap events and SAR detection cells from Global Fishing Watch: what they show, what they do not, and provider caveats.",
}
FAVICON = (
    "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E"
    "%3Ccircle cx='16' cy='16' r='15' fill='%230b1e2b' stroke='%2324465b'/%3E"
    "%3Cpath d='M5 21C10 11 14 23 19 14S25 9 27 11' fill='none' stroke='%237bdff2' stroke-width='2.4' "
    "stroke-linecap='round'/%3E%3Ccircle cx='19' cy='14' r='2.4' fill='%23ffb454'/%3E%3C/svg%3E"
)


def _ensure_head_and_scripts(text: str, prefix: str, path: str) -> str:
    """Add favicon, social-card metadata and the shared UI script once."""
    if 'name="description"' not in text and path in DESCRIPTIONS:
        text = text.replace("</head>", f'    <meta name="description" content="{DESCRIPTIONS[path]}" />\n  </head>', 1)
    if 'rel="icon"' not in text:
        text = text.replace("</head>", f'    <link rel="icon" href="{FAVICON}" />\n  </head>', 1)
    if 'property="og:title"' not in text:
        title = re.search(r"<title>(.*?)</title>", text, re.DOTALL)
        desc = re.search(r'<meta\s+name="description"\s+content="(.*?)"', text, re.DOTALL)
        if title and desc:
            tags = (
                f'    <meta property="og:site_name" content="Arctic Passage Atlas" />\n'
                f'    <meta property="og:type" content="website" />\n'
                f'    <meta property="og:title" content="{title.group(1).strip()}" />\n'
                f'    <meta property="og:description" content="{" ".join(desc.group(1).split())}" />\n'
                f'    <meta name="twitter:card" content="summary" />\n'
            )
            text = text.replace("</head>", tags + "  </head>", 1)
    if "assets/ui.js" not in text:
        text = text.replace("</body>", f'    <script src="{prefix}assets/ui.js" defer></script>\n  </body>', 1)
    return text


def apply_chrome(config: ProjectConfig) -> list[Path]:
    site = config.root / "site"
    changed: list[Path] = []
    for path, _label in PAGES:
        target = site / path
        if not target.exists():
            continue
        prefix = "../" * path.count("/")
        text = original = target.read_text(encoding="utf-8")
        old_footer = FOOTER_RE.search(text)
        legal = PAGE_LEGAL.get(path) or (_legal_from(old_footer.group(0)) if old_footer else DEFAULT_LEGAL)
        new_header, new_footer = header(prefix, path), footer(prefix, legal)
        text = HEADER_RE.sub(lambda _m, h=new_header: h, text, count=1)
        text = FOOTER_RE.sub(lambda _m, f=new_footer: f, text, count=1)
        if "assets/pro.css" not in text:
            pro = f'<link rel="stylesheet" href="{prefix}assets/pro.css" />'
            text = re.sub(
                r'(<link rel="stylesheet" href="[^"]*assets/site\.css" />)',
                lambda m, extra=pro: m.group(1) + extra, text, count=1,
            )
        text = _ensure_head_and_scripts(text, prefix, path)
        if text != original:
            target.write_text(text, encoding="utf-8", newline="\n")
            changed.append(target)
    return changed
