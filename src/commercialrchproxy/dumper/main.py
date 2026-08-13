"""Independent dumper service entry point."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import signal
import sys
from pathlib import Path

from commercialrchproxy import __version__
from commercialrchproxy.config import Config, ConfigError
from commercialrchproxy.health import format_health, health_report, local_ip_assigned
from commercialrchproxy.logging.structured import configure_logging, event, shutdown_logging
from commercialrchproxy.metrics import Metrics
from commercialrchproxy.proxy.server import BindError, ProxyServer
from commercialrchproxy.storage.spool import RawSpoolStorage


def _argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Full-duplex relay and immutable RAW spool dumper")
    parser.add_argument("--config", type=Path, help="shared configuration file path")
    parser.add_argument("--version", action="version", version=__version__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--check-config", action="store_true", help="validate config and local bind IP")
    group.add_argument("--healthcheck", action="store_true", help="non-invasive dumper health report")
    parser.add_argument("--json", action="store_true", help="machine-readable diagnostic output")
    return parser


async def run_dumper(config: Config) -> None:
    os.umask(0o027)
    logger = configure_logging(config.log_dir, config.log_level, component="dumper")
    try:
        storage = RawSpoolStorage(config)
        metrics = Metrics()
        server = ProxyServer(config, storage, logger, metrics)
        await server.start()

        stopping = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, stopping.set)
            except (NotImplementedError, RuntimeError):
                pass

        serve_task = asyncio.create_task(server.serve_forever(), name="dumper-listener")
        stop_task = asyncio.create_task(stopping.wait(), name="dumper-signal-wait")
        try:
            done, _ = await asyncio.wait({serve_task, stop_task}, return_when=asyncio.FIRST_COMPLETED)
            if serve_task in done and not serve_task.cancelled():
                exception = serve_task.exception()
                if exception is not None:
                    raise exception
        finally:
            stop_task.cancel()
            serve_task.cancel()
            await asyncio.gather(stop_task, serve_task, return_exceptions=True)
            await server.close()
            event(logger, "metrics", "Final dumper counter snapshot", **metrics.snapshot())
    finally:
        shutdown_logging(logger)


def cli(argv: list[str] | None = None) -> int:
    args = _argument_parser().parse_args(argv)
    try:
        config = Config.load(args.config)
        if args.check_config:
            assigned, error = local_ip_assigned(config.listen_ip)
            result = {
                "component": "dumper",
                "valid": assigned,
                "listen_ip_assigned": assigned,
                "spool_root": str(config.output_dir),
                "error": error,
                "printer_probe": "not_performed",
            }
            human = "Configuration: OK" if assigned else f"ERROR: {error}"
            print(json.dumps(result, indent=2) if args.json else human)
            return 0 if assigned else 2
        if args.healthcheck:
            report = health_report(config)
            report["component"] = "dumper"
            print(json.dumps(report, ensure_ascii=False, indent=2) if args.json else format_health(report))
            return 0 if report["proxy"]["ip_assigned"] and report["jobs_directory"]["ok"] else 2
        asyncio.run(run_dumper(config))
        return 0
    except (ConfigError, BindError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(cli())
