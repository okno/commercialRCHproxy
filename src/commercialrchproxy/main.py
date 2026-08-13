"""Backward-compatible alias for the independent dumper entry point."""

from commercialrchproxy.dumper.main import cli

if __name__ == "__main__":
    raise SystemExit(cli())
