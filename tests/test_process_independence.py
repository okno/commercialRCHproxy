from __future__ import annotations

import asyncio
import subprocess
import sys
from pathlib import Path

import pytest

from commercialrchproxy.metrics import Metrics
from commercialrchproxy.parser.worker import run_once
from commercialrchproxy.proxy.server import ProxyServer
from commercialrchproxy.storage.spool import RawSpoolStorage
from commercialrchproxy.tools.inspect_stream import load_archive_directory
from tests.fake_rch_server import FakeRCHServer
from tests.support import make_config, null_logger, unused_port, wait_for_manifests

FIXTURES = Path(__file__).parent / "fixtures"


def _fixture(name: str) -> bytes:
    return bytes.fromhex((FIXTURES / name).read_text(encoding="ascii"))


@pytest.mark.asyncio
async def test_dumper_publishes_with_parser_absent_then_backlog_is_parsed_once(tmp_path: Path) -> None:
    request = _fixture("rch_synthetic_management.request.hex")
    response = _fixture("rch_synthetic_management.response.hex")
    fake = FakeRCHServer(response=response)
    await fake.start()
    config = make_config(
        tmp_path,
        printer_port=fake.port,
        listen_port=unused_port(),
        save_clean_txt=True,
        save_pdf=True,
        timezone="Europe/Rome",
    )
    proxy = ProxyServer(config, RawSpoolStorage(config), null_logger(), Metrics())
    await proxy.start()
    try:
        reader, writer = await asyncio.open_connection(config.listen_ip, config.listen_port)
        for offset in range(0, len(request), 7):
            writer.write(request[offset : offset + 7])
            await writer.drain()
        writer.write_eof()
        assert await asyncio.wait_for(reader.read(), 2.0) == response
        writer.close()
        await writer.wait_closed()
        manifests = await wait_for_manifests(config.output_dir, 1)
    finally:
        await proxy.close()
        await fake.close()

    assert bytes(fake.received) == request
    assert len(manifests) == 1
    job_dir = manifests[0].parent
    assert not (job_dir / "PHARSED").exists()
    inspected = load_archive_directory(config.output_dir)
    assert len(inspected) == 1
    assert inspected[0].request == request
    assert inspected[0].response == response

    first = run_once(config)
    second = run_once(config)

    assert [(result.status, result.document_count) for result in first] == [("parsed", 1)]
    assert [result.status for result in second] == ["already_parsed"]
    assert len(list((job_dir / "PHARSED").glob("*.txt"))) == 1
    assert len(list((job_dir / "PHARSED").glob("*.pdf"))) == 1


def test_dumper_and_parser_import_graphs_are_process_independent() -> None:
    dumper = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; import commercialrchproxy.dumper.main; "
                "assert not any(n.startswith('commercialrchproxy.parser') for n in sys.modules)"
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    parser = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; import commercialrchproxy.parser.worker; "
                "assert not any(n.startswith('commercialrchproxy.proxy') for n in sys.modules)"
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert dumper.returncode == 0, dumper.stderr
    assert parser.returncode == 0, parser.stderr
