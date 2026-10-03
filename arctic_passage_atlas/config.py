from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

POLARISATIONS = ("HH", "HV", "VV", "VH")


class ConfigError(ValueError):
    """Raised when a project configuration is incomplete or inconsistent."""


@dataclass(frozen=True)
class ProjectConfig:
    source: Path
    data: dict[str, Any]

    @property
    def root(self) -> Path:
        return self.source.parent.parent

    @property
    def bbox(self) -> tuple[float, float, float, float]:
        values = self.data["aoi"]["bbox"]
        return tuple(float(value) for value in values)  # type: ignore[return-value]

    @property
    def geometry(self) -> dict[str, Any]:
        west, south, east, north = self.bbox
        return {
            "type": "Polygon",
            "coordinates": [[[west, south], [east, south], [east, north], [west, north], [west, south]]],
        }

    @property
    def slug(self) -> str:
        return str(self.data["project"]["slug"])


def load_config(path: str | Path) -> ProjectConfig:
    source = Path(path).resolve()
    if not source.exists():
        raise ConfigError(f"Configuration not found: {source}")
    data = json.loads(source.read_text(encoding="utf-8"))
    _validate(data)
    return ProjectConfig(source=source, data=data)


def _validate(data: dict[str, Any]) -> None:
    required = {"project", "aoi", "change", "ice", "vessels", "site"}
    missing = required.difference(data)
    if missing:
        raise ConfigError(f"Missing top-level configuration sections: {sorted(missing)}")

    bbox = data["aoi"].get("bbox")
    if not isinstance(bbox, list) or len(bbox) != 4:
        raise ConfigError("aoi.bbox must be [west, south, east, north]")
    west, south, east, north = map(float, bbox)
    if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
        raise ConfigError("aoi.bbox is outside valid longitude/latitude bounds")

    for key in ("before", "after"):
        dates = data["change"].get(key)
        if not isinstance(dates, list) or len(dates) != 2 or dates[0] >= dates[1]:
            raise ConfigError(f"change.{key} must contain an ordered [start, end] pair")

    thresholds = data["ice"].get("thresholds_db")
    if not isinstance(thresholds, dict) or not thresholds:
        raise ConfigError("ice.thresholds_db must map polarisation (HH, HV, VV, VH) to a dB threshold or null")
    for polarisation, value in thresholds.items():
        if polarisation not in POLARISATIONS:
            raise ConfigError(f"ice.thresholds_db has unknown polarisation {polarisation!r}")
        if value is not None and not -40 <= float(value) <= 5:
            raise ConfigError(f"ice.thresholds_db[{polarisation}] is outside a plausible Sentinel-1 dB range")
    expected_water_fraction = data["ice"].get("water_mask_expected_fraction")
    if (
        not isinstance(expected_water_fraction, list)
        or len(expected_water_fraction) != 2
        or not 0 <= float(expected_water_fraction[0]) < float(expected_water_fraction[1]) <= 1
    ):
        raise ConfigError("ice.water_mask_expected_fraction must be an ordered [low, high] pair within 0..1")
    if int(data["change"].get("minimum_candidate_pixels", 1)) < 1:
        raise ConfigError("change.minimum_candidate_pixels must be at least 1")

    if int(data["vessels"].get("minimum_gap_minutes", 0)) < 720:
        raise ConfigError("minimum_gap_minutes must be at least 720 (12 hours)")



def ice_threshold(data: dict[str, Any], polarisation: str) -> float:
    """Return the configured dB threshold for one polarisation.

    A threshold is only meaningful for the band it was chosen on, so a missing value is an error
    rather than a fallback to another polarisation.
    """
    value = data["ice"]["thresholds_db"].get(polarisation)
    if value is None:
        raise ConfigError(
            f"No ice threshold is configured for {polarisation}. Inspect the backscatter percentiles "
            "in ice_summary.json, choose a value, and record how in docs/METHODOLOGY.md."
        )
    return float(value)


def usable_acquisitions(data: dict[str, Any], candidates: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Restrict acquisition candidates to polarisations that have a configured threshold."""
    thresholds = data["ice"]["thresholds_db"]
    return [pair for pair in candidates if thresholds.get(pair[1]) is not None]
