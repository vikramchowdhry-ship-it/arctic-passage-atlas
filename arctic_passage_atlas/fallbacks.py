from __future__ import annotations

from dataclasses import dataclass
from html import escape
from math import cos, radians, sqrt
from pathlib import Path
from typing import Any, Literal

from .config import ProjectConfig

Mode = Literal["demo", "live"]

WIDTH = 1200
HEIGHT = 675
LEFT = 80
TOP = 70
MAP_WIDTH = 1040
MAP_HEIGHT = 520
MAX_TOTAL_FEATURES = 1500
ICE_COLORS = ["#c9f5ff", "#7bdff2", "#4bb6dc", "#267ca8", "#8b9ef5", "#b77de8"]


@dataclass(frozen=True)
class FeatureGroup:
    features: list[dict[str, Any]]
    color: str
    label: str
    radius_property: str | None = None


def _plot_bounds(bbox: tuple[float, float, float, float]) -> tuple[float, float, float, float]:
    """Fit a local equirectangular view into the frame without distorting distance ratios."""
    west, south, east, north = bbox
    centre_latitude = (south + north) / 2
    physical_width = (east - west) * cos(radians(centre_latitude))
    physical_height = north - south
    aspect = physical_width / physical_height
    frame_aspect = MAP_WIDTH / MAP_HEIGHT
    if aspect >= frame_aspect:
        width = float(MAP_WIDTH)
        height = width / aspect
    else:
        height = float(MAP_HEIGHT)
        width = height * aspect
    return LEFT + (MAP_WIDTH - width) / 2, TOP + (MAP_HEIGHT - height) / 2, width, height


def _point(coordinates: list[float], bbox: tuple[float, float, float, float]) -> tuple[float, float]:
    west, south, east, north = bbox
    plot_left, plot_top, plot_width, plot_height = _plot_bounds(bbox)
    longitude, latitude = float(coordinates[0]), float(coordinates[1])
    x = plot_left + ((longitude - west) / (east - west)) * plot_width
    y = plot_top + ((north - latitude) / (north - south)) * plot_height
    return x, y


def _line(coordinates: list[list[float]], bbox: tuple[float, float, float, float]) -> str:
    return " ".join(f"{x:.1f},{y:.1f}" for x, y in (_point(item, bbox) for item in coordinates))


def _point_radius(feature: dict[str, Any], property_name: str | None) -> float:
    if not property_name:
        return 8
    raw_value = (feature.get("properties") or {}).get(property_name, 1)
    try:
        value = max(0.0, float(raw_value or 0))
    except (TypeError, ValueError):
        value = 1
    return min(18, max(6, 5 + sqrt(value) * 3))


def _geometry(
    feature: dict[str, Any],
    bbox: tuple[float, float, float, float],
    color: str,
    radius_property: str | None = None,
) -> str:
    geometry = feature.get("geometry") or {}
    kind = geometry.get("type")
    coordinates = geometry.get("coordinates")
    if not coordinates:
        return ""
    if kind == "Point":
        x, y = _point(coordinates, bbox)
        radius = _point_radius(feature, radius_property)
        return (
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{radius:.1f}" '
            f'fill="{color}" stroke="#ffffff" stroke-width="2"/>'
        )
    if kind == "LineString":
        return f'<polyline points="{_line(coordinates, bbox)}" fill="none" stroke="{color}" stroke-width="5"/>'
    if kind == "MultiLineString":
        return "".join(
            f'<polyline points="{_line(line, bbox)}" fill="none" stroke="{color}" stroke-width="5"/>'
            for line in coordinates
        )
    if kind == "Polygon":
        paths = []
        for ring in coordinates:
            points = [_point(item, bbox) for item in ring]
            if points:
                paths.append("M " + " L ".join(f"{x:.1f} {y:.1f}" for x, y in points) + " Z")
        return f'<path d="{" ".join(paths)}" fill="{color}" fill-opacity=".34" stroke="{color}" stroke-width="2" fill-rule="evenodd"/>'
    if kind == "MultiPolygon":
        return "".join(
            _geometry(
                {**feature, "geometry": {"type": "Polygon", "coordinates": polygon}},
                bbox,
                color,
                radius_property,
            )
            for polygon in coordinates
        )
    return ""


def _cap_groups(groups: list[FeatureGroup]) -> list[FeatureGroup]:
    """Share a fixed SVG feature budget across groups so each remains represented."""
    selected: list[FeatureGroup] = []
    remaining = MAX_TOTAL_FEATURES
    for index, group in enumerate(groups):
        groups_left = len(groups) - index
        allowance = remaining // groups_left if groups_left else 0
        features = group.features[:allowance]
        selected.append(FeatureGroup(features, group.color, group.label, group.radius_property))
        remaining -= len(features)
    return selected


def _legend(groups: list[FeatureGroup]) -> str:
    entries = []
    for index, group in enumerate(groups):
        x = 82 + (index % 4) * 245
        y = 620 + (index // 4) * 22
        entries.append(
            f'<circle cx="{x}" cy="{y - 5}" r="6" fill="{group.color}"/>'
            f'<text x="{x + 12}" y="{y}" fill="#d9edf7" font-family="system-ui,sans-serif" '
            f'font-size="15">{escape(group.label)}</text>'
        )
    return "".join(entries)


def _render(
    config: ProjectConfig,
    name: str,
    title: str,
    groups: list[FeatureGroup],
    mode: Mode,
) -> Path:
    if mode not in {"demo", "live"}:
        raise ValueError("mode must be 'demo' or 'live'")
    total_count = sum(len(group.features) for group in groups)
    rendered_groups = _cap_groups(groups)
    rendered_count = sum(len(group.features) for group in rendered_groups)
    shapes = "".join(
        _geometry(feature, config.bbox, group.color, group.radius_property)
        for group in rendered_groups
        for feature in group.features
    )
    label = "DEMONSTRATION FIXTURE · not an observation" if mode == "demo" else "PROVIDER-BACKED OUTPUT"
    plot_left, plot_top, plot_width, plot_height = _plot_bounds(config.bbox)
    west, south, east, north = config.bbox
    count_label = f"{rendered_count} of {total_count}" if rendered_count < total_count else str(total_count)
    path = config.root / "site" / "assets" / f"fallback-{name}.svg"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"""<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}" role="img" aria-labelledby="t d">
<title id="t">{escape(title)} static fallback</title><desc id="d">{escape(label)}. {count_label} mapped features shown. AOI outline only; no basemap.</desc>
<rect width="{WIDTH}" height="{HEIGHT}" fill="#071521"/>
<rect x="{plot_left:.1f}" y="{plot_top:.1f}" width="{plot_width:.1f}" height="{plot_height:.1f}" fill="#0c2232" stroke="#83f3c7" stroke-width="2" stroke-dasharray="10 8"/>
{shapes}
<text x="80" y="42" fill="#d9edf7" font-family="system-ui,sans-serif" font-size="28" font-weight="700">{escape(title)}</text>
<text x="{plot_left:.1f}" y="{plot_top - 10:.1f}" fill="#8ba9b9" font-family="system-ui,sans-serif" font-size="14">{west:.2f}°, {north:.2f}°</text>
<text x="{plot_left + plot_width:.1f}" y="{plot_top + plot_height + 20:.1f}" text-anchor="end" fill="#8ba9b9" font-family="system-ui,sans-serif" font-size="14">{east:.2f}°, {south:.2f}°</text>
<text x="1120" y="42" text-anchor="end" fill="#8ba9b9" font-family="system-ui,sans-serif" font-size="14">AOI outline only · no basemap</text>
{_legend(rendered_groups)}
<text x="80" y="665" fill="#8ba9b9" font-family="system-ui,sans-serif" font-size="14">{escape(label)} · {count_label} mapped features shown</text>
</svg>""",
        encoding="utf-8",
        newline="\n",
    )
    return path


def _ice_groups(features: list[dict[str, Any]]) -> list[FeatureGroup]:
    by_period: dict[str, list[dict[str, Any]]] = {}
    for feature in features:
        period = str((feature.get("properties") or {}).get("period") or "period unavailable")
        by_period.setdefault(period, []).append(feature)
    return [
        FeatureGroup(items, ICE_COLORS[index % len(ICE_COLORS)], period)
        for index, (period, items) in enumerate(sorted(by_period.items()))
    ]


def write_fallbacks(
    config: ProjectConfig,
    changes: list[dict[str, Any]],
    ice: list[dict[str, Any]],
    gaps: list[dict[str, Any]],
    sar: list[dict[str, Any]],
    mode: Mode,
) -> list[Path]:
    """Render bounded offline SVGs from the same features published to the interactive maps."""
    if mode not in {"demo", "live"}:
        raise ValueError("mode must be 'demo' or 'live'")
    ice_groups = _ice_groups(ice) or [FeatureGroup([], ICE_COLORS[0], "ice extent")]
    return [
        _render(
            config,
            "change",
            "Surface-change candidates",
            [FeatureGroup(changes, "#ffb454", "change candidate")],
            mode,
        ),
        _render(config, "ice", "Seasonal ice classification", ice_groups, mode),
        _render(
            config,
            "vessels",
            "AIS gaps and SAR cells",
            [
                FeatureGroup(gaps, "#ff6b7a", "AIS gap"),
                FeatureGroup(sar, "#ffb454", "SAR detections", "detections"),
            ],
            mode,
        ),
    ]
