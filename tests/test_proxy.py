from __future__ import annotations

import asyncio
import hashlib
import threading
from pathlib import Path

import pytest

from commercialrchproxy.capture.jobs import RCH_TO_CLIENT
from commercialrchproxy.metrics import Metrics
from commercialrchproxy.proxy import session as session_module
from commercialrchproxy.proxy.server import ProxyServer
from commercialrchproxy.proxy.streams import PumpResult
from commercialrchproxy.storage.files import JobStorage
from tests.fake_rch_server import FakeRCHServer
from tests.support import load_manifest, make_config, null_logger, unused_port, wait_for_manifests


async def _start_proxy(tmp_path: Path, fake: FakeRCHServer, **overrides: object):
    config = make_config(tmp_path, fake.port, unused_port(), **overrides)
    server = ProxyServer(config, JobStorage(config), null_logger(), Metrics())
    await server.start()
    return config, server


@pytest.mark.asyncio
async def test_full_duplex_arbitrary_binary_integrity_and_fragmented_response(tmp_path: Path) -> None:
    response_parts = (b"\x06first", b"\x00second", bytes((255, 251, 1)))
    fake = FakeRCHServer(response_fragments=response_parts)
    await fake.start()
    config, proxy = await _start_proxy(tmp_path, fake)
    payload = bytes(range(256)) * 257 + b"tail"
    try:
        reader, writer = await asyncio.open_connection(config.listen_ip, config.listen_port)
        for index in range(0, len(payload), 997):
            writer.write(payload[index : index + 997])
            await writer.drain()
        writer.write_eof()
        received = await asyncio.wait_for(reader.read(), 2.0)
        writer.close()
        await writer.wait_closed()
        manifests = await wait_for_manifests(config.output_dir, 1)
    finally:
        await proxy.close()
        await fake.close()

    assert bytes(fake.received) == payload
    assert hashlib.sha256(fake.received).digest() == hashlib.sha256(payload).digest()
    assert received == b"".join(response_parts)
    assert manifests
    manifest = load_manifest(manifests[0])
    directory = manifests[0].parent
    assert (directory / str(manifest["files"]["raw"])).read_bytes() == payload
    assert (directory / str(manifest["files"]["response_raw"])).read_bytes() == received
    assert manifest["telnet_iac_candidate_bytes_observed"] is True
    assert manifest["telnet_negotiation_confirmed"] is False
    assert manifest["framing_confirmed"] is False
    assert manifest["bytes_read_from_client"] == len(payload)
    assert manifest["bytes_local_write_drain_to_printer"] == len(payload)
    assert manifest["bytes_arrived_at_printer"] is None
    assert manifest["bytes_read_from_printer"] == len(received)
    assert manifest["bytes_local_write_drain_to_client"] == len(received)
    assert manifest["bytes_arrived_at_client"] is None
    assert manifest["delivery_evidence"] == "UNCONFIRMED_WITHOUT_PCAP"


@pytest.mark.asyncio
async def test_delayed_reverse_channel_survives_client_half_close(tmp_path: Path) -> None:
    fake = FakeRCHServer(response=b"delayed-status", delay_sec=0.15)
    await fake.start()
    config, proxy = await _start_proxy(tmp_path, fake, response_timeout_sec=0.6)
    try:
        reader, writer = await asyncio.open_connection(config.listen_ip, config.listen_port)
        writer.write(b"request")
        await writer.drain()
        writer.write_eof()
        assert await asyncio.wait_for(reader.readexactly(len(b"delayed-status")), 1.0) == b"delayed-status"
        writer.close()
        await writer.wait_closed()
        manifests = await wait_for_manifests(config.output_dir, 1)
    finally:
        await proxy.close()
        await fake.close()
    assert bytes(fake.received) == b"request"
    assert len(manifests) == 1


@pytest.mark.asyncio
async def test_server_first_bytes_are_relayed_without_telnet_handling(tmp_path: Path) -> None:
    banner = bytes((255, 253, 1)) + b"RCH-like-server-first"
    fake = FakeRCHServer(server_first=banner)
    await fake.start()
    config, proxy = await _start_proxy(tmp_path, fake)
    try:
        reader, writer = await asyncio.open_connection(config.listen_ip, config.listen_port)
        assert await asyncio.wait_for(reader.readexactly(len(banner)), 1.0) == banner
        writer.write_eof()
        await reader.read()
        writer.close()
        await writer.wait_closed()
    finally:
        await proxy.close()
        await fake.close()


@pytest.mark.asyncio
async def test_configured_device_endpoint_has_only_one_upstream_session_at_a_time(tmp_path: Path) -> None:
    fake = FakeRCHServer()
    await fake.start()
    config, proxy = await _start_proxy(tmp_path, fake)
    first_reader = first_writer = second_reader = second_writer = None
    try:
        first_reader, first_writer = await asyncio.open_connection(config.listen_ip, config.listen_port)
        for _ in range(50):
            if fake.connections == 1:
                break
            await asyncio.sleep(0.01)
        assert fake.connections == 1

        second_reader, second_writer = await asyncio.open_connection(config.listen_ip, config.listen_port)
        await asyncio.sleep(0.05)
        assert fake.connections == 1

        first_writer.write_eof()
        await first_reader.read()
        first_writer.close()
        await first_writer.wait_closed()
        for _ in range(50):
            if fake.connections == 2:
                break
            await asyncio.sleep(0.01)
        assert fake.connections == 2

        second_writer.write_eof()
        await second_reader.read()
        second_writer.close()
        await second_writer.wait_closed()
    finally:
        for writer in (first_writer, second_writer):
            if writer is not None and not writer.is_closing():
                writer.close()
                await writer.wait_closed()
        await proxy.close()
        await fake.close()


@pytest.mark.asyncio
async def test_persistent_connection_can_archive_multiple_idle_fallback_jobs(tmp_path: Path) -> None:
    fake = FakeRCHServer(respond_per_chunk=lambda data: b"R:" + data)
    await fake.start()
    config, proxy = await _start_proxy(tmp_path, fake, job_idle_timeout_ms=40, response_timeout_sec=0.4)
    try:
        reader, writer = await asyncio.open_connection(config.listen_ip, config.listen_port)
        writer.write(b"job-one")
        await writer.drain()
        assert await reader.readexactly(9) == b"R:job-one"
        await asyncio.sleep(0.10)
        writer.write(b"job-two")
        await writer.drain()
        assert await reader.readexactly(9) == b"R:job-two"
        await asyncio.sleep(0.10)
        writer.write_eof()
        await reader.read()
        writer.close()
        await writer.wait_closed()
        manifests = await wait_for_manifests(config.output_dir, 2)
    finally:
        await proxy.close()
        await fake.close()
    assert bytes(fake.received) == b"job-onejob-two"
    raw_payloads = []
    for manifest_path in manifests:
        manifest = load_manifest(manifest_path)
        raw_payloads.append((manifest_path.parent / str(manifest["files"]["raw"])).read_bytes())
        assert manifest["job_boundary_source"] == "fallback_inactivity"
        assert float(manifest["job_boundary_confidence"]) <= 0.2
    assert sorted(raw_payloads) == [b"job-one", b"job-two"]


@pytest.mark.asyncio
async def test_printer_offline_produces_no_false_positive_reply(tmp_path: Path) -> None:
    unused = unused_port()
    config = make_config(tmp_path, unused, unused_port(), connection_timeout_sec=0.1)
    proxy = ProxyServer(config, JobStorage(config), null_logger(), Metrics())
    await proxy.start()
    try:
        reader, writer = await asyncio.open_connection(config.listen_ip, config.listen_port)
        writer.write(b"must-not-be-acknowledged")
        await writer.drain()
        assert await asyncio.wait_for(reader.read(), 1.0) == b""
        writer.close()
        await writer.wait_closed()
    finally:
        await proxy.close()
    assert not list(config.output_dir.rglob("*.json"))


@pytest.mark.asyncio
async def test_reverse_copy_failure_cancels_opposite_direction_without_tail_wait(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = FakeRCHServer()
    await fake.start()
    cancelled = asyncio.Event()

    async def controlled_pump(*_args: object, direction: str, **_kwargs: object) -> PumpResult:
        if direction == RCH_TO_CLIENT:
            await asyncio.sleep(0.02)
            return PumpResult(direction, 0, "transport_error", "synthetic fixture transport failure")
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled.set()
            return PumpResult(direction, 0, "cancelled", "cancelled after opposite pump failure")

    monkeypatch.setattr(session_module, "pump", controlled_pump)
    config, proxy = await _start_proxy(tmp_path, fake, response_timeout_sec=1.0)
    started = asyncio.get_running_loop().time()
    try:
        reader, writer = await asyncio.open_connection(config.listen_ip, config.listen_port)
        assert await asyncio.wait_for(reader.read(), 0.5) == b""
        assert asyncio.get_running_loop().time() - started < 0.5
        await asyncio.wait_for(cancelled.wait(), 0.5)
        writer.close()
        await writer.wait_closed()
    finally:
        await proxy.close()
        await fake.close()


@pytest.mark.asyncio
async def test_slow_archive_does_not_hold_transport_or_device_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = FakeRCHServer()
    await fake.start()
    config = make_config(tmp_path, fake.port, unused_port(), response_timeout_sec=0.5)
    storage = JobStorage(config)
    archive_started = threading.Event()
    archive_release = threading.Event()
    original_archive = storage.archive

    def slow_archive(job: object):
        archive_started.set()
        if not archive_release.wait(2.0):
            raise TimeoutError("test did not release archive")
        return original_archive(job)  # type: ignore[arg-type]

    monkeypatch.setattr(storage, "archive", slow_archive)
    proxy = ProxyServer(config, storage, null_logger(), Metrics())
    await proxy.start()
    first_writer = second_writer = None
    try:
        first_reader, first_writer = await asyncio.open_connection(config.listen_ip, config.listen_port)
        first_writer.write(b"archive-me")
        await first_writer.drain()
        first_writer.write_eof()
        assert await asyncio.wait_for(asyncio.to_thread(archive_started.wait, 1.0), 1.2)
        assert await asyncio.wait_for(first_reader.read(), 0.3) == b""

        _second_reader, second_writer = await asyncio.open_connection(config.listen_ip, config.listen_port)
        for _ in range(50):
            if fake.connections == 2:
                break
            await asyncio.sleep(0.01)
        assert fake.connections == 2
    finally:
        archive_release.set()
        for writer in (first_writer, second_writer):
            if writer is not None and not writer.is_closing():
                writer.close()
                await writer.wait_closed()
        await proxy.close()
        await fake.close()
