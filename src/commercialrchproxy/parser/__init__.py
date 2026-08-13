"""Independent, filesystem-spool RCH parser process.

The package remains import-light so the watcher and diagnostics can operate
without importing the semantic parser or PDF renderer.  Runtime integrations
should import ``commercialrchproxy.parser.worker`` explicitly.
"""
