from __future__ import annotations

import argparse
import asyncio
import os
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .config import load_config
from .earth_engine import initialize_earth_engine
from .ice_inventory import inventory_ice
from .pipeline import run_demo, run_live
from .verify import verify_project
from .vessels import capture_gfw_event_fixture

DEFAULT_CONFIG = "configs/cambridge-bay.json"


class PreviewHandler(SimpleHTTPRequestHandler):
    """Local preview handler that does not retain stale generated artifacts."""

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store, max-age=0")
        super().end_headers()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="arctic-atlas", description="Arctic Passage Atlas pipeline")
    parser.add_argument("--config", default=DEFAULT_CONFIG, help="JSON project configuration")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo", help="Generate visibly labelled synthetic fixtures and site data")
    live = sub.add_parser("live", help="Generate authenticated provider-backed outputs")
    live.add_argument("--parts", nargs="+", choices=["change", "ice", "vessels"], default=["change", "ice", "vessels"])
    sub.add_parser("ice-grid", help="Download the newest NSIDC sea-ice concentration and resample it for the Route page")
    sub.add_parser("route-grid", help="Rebuild the land/water grid used by the Route page (downloads Natural Earth land)")
    sub.add_parser("pages", help="Re-apply the shared header, footer and stylesheet links to every site page")
    sub.add_parser("live-feeds", help="Refresh third-party live-feed snapshots shown on the Live conditions page")
    sub.add_parser("ice-inventory", help="Write Sentinel-1 calibration evidence without classifying ice")
    fixture = sub.add_parser("gfw-fixture", help="Capture one redacted GFW gap-event schema fixture")
    fixture.add_argument(
        "--output",
        default="tests/fixtures/gfw_event_sample.json",
        help="Sanitized fixture destination, relative to the project root",
    )
    fixture.add_argument("--replace", action="store_true", help="Replace an existing sanitized fixture")
    sub.add_parser("verify", help="Validate processed data and public-site completeness")
    serve = sub.add_parser("serve", help="Serve the static site locally")
    serve.add_argument("--port", type=int, default=8000)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = Path.cwd() / config_path
    config = load_config(config_path)

    if args.command == "demo":
        outputs = run_demo(config)
        print(f"Generated {len(outputs)} outputs in demo mode.")
        return 0
    if args.command == "live":
        outputs = run_live(config, args.parts)
        print(f"Generated {len(outputs)} outputs in live mode.")
        return 0
    if args.command == "ice-grid":
        from .ice_grid import build_ice_grids

        for path in build_ice_grids(config):
            print(f"Wrote {path.relative_to(config.root)}")
        return 0
    if args.command == "route-grid":
        from .route_grid import build_route_grid, build_world_grid

        for path in [*build_route_grid(config), *build_world_grid(config)]:
            print(f"Wrote {path.relative_to(config.root)}")
        return 0
    if args.command == "pages":
        from .pages import apply_chrome

        changed = apply_chrome(config)
        print(f"Updated {len(changed)} page(s).")
        return 0
    if args.command == "live-feeds":
        from .live_feeds import refresh_live_feeds

        for path in refresh_live_feeds(config):
            print(f"Wrote {path.relative_to(config.root)}")
        return 0
    if args.command == "ice-inventory":
        outputs = inventory_ice(config, initialize_earth_engine())
        print(f"Generated {len(outputs)} calibration inventory output.")
        return 0
    if args.command == "gfw-fixture":
        output = Path(args.output)
        if not output.is_absolute():
            output = config.root / output
        fixture = asyncio.run(capture_gfw_event_fixture(config, output, args.replace))
        print(f"Wrote redacted GFW schema fixture: {fixture}")
        return 0
    if args.command == "verify":
        for message in verify_project(config):
            print(f"PASS {message}")
        return 0
    if args.command == "serve":
        site = config.root / "site"
        handler = partial(PreviewHandler, directory=str(site))
        server = ThreadingHTTPServer(("127.0.0.1", args.port), handler)
        print(f"Serving {site} at http://127.0.0.1:{args.port}")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
        return 0
    return os.EX_USAGE

