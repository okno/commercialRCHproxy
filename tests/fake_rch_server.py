"""Transport fixture server, not an implementation or emulator of RCH."""

from __future__ import annotations

import asyncio
from collections.abc import Callable


class FakeRCHServer:
    def __init__(
        self,
        *,
        response: bytes = b"",
        response_fragments: tuple[bytes, ...] = (),
        delay_sec: float = 0.0,
        server_first: bytes = b"",
        respond_per_chunk: Callable[[bytes], bytes] | None = None,
        hold_open_sec: float = 0.0,
        abort_after_read: bool = False,
    ) -> None:
        self.response = response
        self.response_fragments = response_fragments
        self.delay_sec = delay_sec
        self.server_first = server_first
        self.respond_per_chunk = respond_per_chunk
        self.hold_open_sec = hold_open_sec
        self.abort_after_read = abort_after_read
        self.received = bytearray()
        self.connections = 0
        self.server: asyncio.AbstractServer | None = None
        self.host = "127.0.0.1"
        self.port = 0

    async def start(self) -> None:
        self.server = await asyncio.start_server(self._handle, self.host, 0)
        self.port = int(self.server.sockets[0].getsockname()[1])

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self.connections += 1
        try:
            if self.server_first:
                writer.write(self.server_first)
                await writer.drain()
            while True:
                data = await reader.read(65536)
                if not data:
                    break
                self.received.extend(data)
                if self.abort_after_read:
                    writer.transport.abort()
                    return
                if self.respond_per_chunk is not None:
                    writer.write(self.respond_per_chunk(data))
                    await writer.drain()
            if self.delay_sec:
                await asyncio.sleep(self.delay_sec)
            if self.response_fragments:
                for fragment in self.response_fragments:
                    writer.write(fragment)
                    await writer.drain()
                    await asyncio.sleep(0.01)
            elif self.response:
                writer.write(self.response)
                await writer.drain()
            if self.hold_open_sec:
                await asyncio.sleep(self.hold_open_sec)
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except (ConnectionError, OSError, RuntimeError):
                pass

    async def close(self) -> None:
        if self.server is not None:
            self.server.close()
            await self.server.wait_closed()
