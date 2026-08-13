"""Command-line entry point for the independent parser service."""

from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
import threading
from pathlib import Path

from commercialrchproxy import __version__
from commercialrchproxy.config import DEFAULT_CONFIG_PATH, Config, ConfigError
from commercialrchproxy.logging.structured import configure_logging, event, shutdown_logging
from commercialrchproxy.parser.watcher import SpoolWatcher
from commercialrchproxy.parser.worker import ProcessResult, process_job, run_once


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Parse completed commercialRCHproxy RAW spool jobs")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--once", action="store_true", help="scan once and exit")
    parser.add_argument("--job", type=Path, help="process one ready job directory")
    parser.add_argument("--force", action="store_true", help="regenerate parser-owned output for --job")
    parser.add_argument("--poll-interval", type=float, help="override configured polling fallback seconds")
    return parser


def _log_results(logger: logging.Logger, results: list[ProcessResult]) -> None:
    for result in results:
        event(
            logger,
            "parser_job",
            "Parser spool job result",
            status=result.status,
            job=result.job_dir,
            documents=result.document_count,
            error=result.error,
        )


def cli(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logger: logging.Logger | None = None
    try:
        config = Config.load(args.config)
        os.umask(0o027)
        logger = configure_logging(config.log_dir, config.log_level, component="parser")
        if args.force and args.job is None:
            build_parser().error("--force requires --job")
        if args.job is not None:
            result = process_job(config, args.job, force=args.force)
            _log_results(logger, [result])
            return 0 if result.status in {"parsed", "already_parsed"} else 1
        if args.once:
            results = run_once(config)
            _log_results(logger, results)
            failed = any(
                result.status in {"retry_pending", "parse_failed", "claim_error", "failure_state_error"}
                for result in results
            )
            return 1 if failed else 0

        interval = config.parser_poll_interval_sec if args.poll_interval is None else args.poll_interval
        if interval <= 0:
            build_parser().error("--poll-interval must be positive")
        stop = threading.Event()

        def request_stop(_signum: int, _frame: object) -> None:
            stop.set()

        signal.signal(signal.SIGTERM, request_stop)
        signal.signal(signal.SIGINT, request_stop)
        with SpoolWatcher(config.output_dir, enabled=config.parser_use_inotify, logger=logger) as watcher:
            event(logger, "parser_watcher", "Parser watcher initialized", mode=watcher.mode)
            while not stop.is_set():
                _log_results(logger, run_once(config))
                watcher.wait(interval, stop)
        return 0
    except (ConfigError, RuntimeError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130
    finally:
        if logger is not None:
            shutdown_logging(logger)


main = cli


if __name__ == "__main__":
    raise SystemExit(cli())
