from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from commercialrchproxy.metrics import Metrics
from commercialrchproxy.proxy.server import ProxyServer
from commercialrchproxy.proxy.streams import _half_close
from commercialrchproxy.storage.spool import RawSpoolStorage
from tests.fake_rch_server import FakeRCHServer
from tests.support import load_manifest, make_config, null_logger, unused_port, wait_for_manifests


async def _proxy(tmp_path: Path, fake: FakeRCHServer, **overrides: object):
    config = make_config(tmp_path, fake.port, unused_port(), **overrides)
    proxy = ProxyServer(config, RawSpoolStorage(config), null_logger(), Metrics())
    await proxy.start()
    return config, proxy


@pytest.mark.asyncio
async def test_opaque_error_looking_response_is_forwarded_not_interpreted(tmp_path: Path) -> None:
    opaque = b"ERR:999\x00\x15"
    fake = FakeRCHServer(response=opaque)
    await fake.start()
    config, proxy = await _proxy(tmp_path, fake)
    try:
        reader, writer = await asyncio.open_connection(config.listen_ip, config.listen_port)
        writer.write(b"opaque-request")
        await writer.drain()
        writer.write_eof()
        assert await reader.read() == opaque
        writer.close()
        await writer.wait_closed()
        manifests = await wait_for_manifests(config.output_dir, 1)
    finally:
        await proxy.close()
        await fake.close()
    manifest = load_manifest(manifests[0])
    assert "protocol_status" not in manifest
    assert "application_success" not in manifest
    assert "rch_error_code" not in manifest


@pytest.mark.asyncio
async def test_printer_reset_is_propagated_without_synthetic_payload(tmp_path: Path) -> None:
    fake = FakeRCHServer(abort_after_read=True)
    await fake.start()
    config, proxy = await _proxy(tmp_path, fake, response_timeout_sec=0.2)
    try:
        reader, writer = await asyncio.open_connection(config.listen_ip, config.listen_port)
        writer.write(b"request-before-reset")
        await writer.drain()
        writer.write_eof()
        try:
            reply = await asyncio.wait_for(reader.read(), 1.0)
        except (ConnectionError, OSError):
            reply = b""
        assert reply == b""
        writer.close()
        try:
            await writer.wait_closed()
        except (ConnectionError, OSError):
            pass
    finally:
        await proxy.close()
        await fake.close()
    assert bytes(fake.received) == b"request-before-reset"


@pytest.mark.asyncio
async def test_nonclosing_printer_tail_is_bounded_and_not_called_success(tmp_path: Path) -> None:
    fake = FakeRCHServer(hold_open_sec=1.0)
    await fake.start()
    config, proxy = await _proxy(tmp_path, fake, response_timeout_sec=0.12)
    started = asyncio.get_running_loop().time()
    try:
        reader, writer = await asyncio.open_connection(config.listen_ip, config.listen_port)
        writer.write(b"request-with-no-response")
        await writer.drain()
        writer.write_eof()
        assert await asyncio.wait_for(reader.read(), 0.8) == b""
        elapsed = asyncio.get_running_loop().time() - started
        writer.close()
        await writer.wait_closed()
        manifests = await wait_for_manifests(config.output_dir, 1)
    finally:
        await proxy.close()
        await fake.close()
    assert elapsed < 0.8
    manifest = load_manifest(manifests[0])
    assert "application_success" not in manifest
    assert "tail_timeout" in str(manifest["close_reason"])
    assert "incomplete" in str(manifest["close_reason"])
    assert manifest["bytes_read_from_client"] == len(b"request-with-no-response")
    assert manifest["bytes_local_write_drain_to_printer"] == len(b"request-with-no-response")
    assert manifest["bytes_arrived_at_printer"] is None
    assert manifest["bytes_arrived_at_client"] is None
    assert manifest["delivery_evidence"] == "UNCONFIRMED_WITHOUT_PCAP"


@pytest.mark.asyncio
async def test_tail_timeout_is_recorded_even_after_response_bytes_arrive(tmp_path: Path) -> None:
    response = b"opaque-response-before-stall"
    fake = FakeRCHServer(response=response, hold_open_sec=1.0)
    await fake.start()
    config, proxy = await _proxy(
        tmp_path,
        fake,
        response_timeout_sec=0.12,
        job_idle_timeout_ms=30,
    )
    try:
        reader, writer = await asyncio.open_connection(config.listen_ip, config.listen_port)
        writer.write(b"request")
        await writer.drain()
        writer.write_eof()
        assert await reader.readexactly(len(response)) == response
        assert await asyncio.wait_for(reader.read(), 0.8) == b""
        writer.close()
        await writer.wait_closed()
        manifests = await wait_for_manifests(config.output_dir, 1)
    finally:
        await proxy.close()
        await fake.close()
    manifest = load_manifest(manifests[0])
    assert "tail_timeout" in manifest["close_reason"]
    assert "incomplete" in manifest["close_reason"]
    assert "application_success" not in manifest


@pytest.mark.asyncio
async def test_failed_fin_propagation_is_not_reported_as_clean_half_close() -> None:
    class BrokenHalfCloseWriter:
        def can_write_eof(self) -> bool:
            return True

        def write_eof(self) -> None:
            raise ConnectionResetError("fixture reset during FIN propagation")

        async def drain(self) -> None:
            return None

    error = await _half_close(BrokenHalfCloseWriter())  # type: ignore[arg-type]
    assert error == "ConnectionResetError: fixture reset during FIN propagation"
