"""The panel's VNC console: a Proxmox noVNC websocket. A local TCP port is bridged to that websocket
so a normal VNC client (vncdotool) can capture the screen and send keys."""
from __future__ import annotations

import asyncio
import atexit
import ssl
import threading

import websockets
from vncdotool import api as vnc

# vncdotool runs one Twisted reactor per process and cannot restart it: stop it once, at exit,
# so long-running servers (API, MCP) can open many console sessions.
atexit.register(vnc.shutdown)


class Console:
    """Use as a context manager: `with Console(host, port, ticket) as c: c.capture("out.png")`."""

    def __init__(self, host: str, port: int, password: str):
        self.url, self.password = f"wss://{host}:{port}/websockify", password
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop.run_forever, daemon=True)
        self.client = None

    async def _bridge(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        async with websockets.connect(self.url, subprotocols=["binary"], ssl=ssl.create_default_context(),
                                      max_size=None) as ws:
            async def up():
                while data := await reader.read(65536):
                    await ws.send(data)
            async def down():
                async for msg in ws:
                    writer.write(msg if isinstance(msg, bytes) else msg.encode())
                    await writer.drain()
            await asyncio.wait([asyncio.ensure_future(up()), asyncio.ensure_future(down())],
                               return_when=asyncio.FIRST_COMPLETED)
        writer.close()

    def __enter__(self) -> "Console":
        self._thread.start()
        self._server = asyncio.run_coroutine_threadsafe(
            asyncio.start_server(self._bridge, "127.0.0.1", 0), self._loop).result(10)
        port = self._server.sockets[0].getsockname()[1]
        self.client = vnc.connect(f"127.0.0.1::{port}", password=self.password, timeout=30)
        return self

    def __exit__(self, *exc) -> None:
        try:
            if self.client:
                self.client.disconnect()
        finally:
            asyncio.run_coroutine_threadsafe(self._close(), self._loop).result(10)
            self._loop.call_soon_threadsafe(self._loop.stop)
            self._thread.join(5)

    async def _close(self) -> None:
        self._server.close()
        tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    def capture(self, path: str) -> str:
        self.client.captureScreen(path)
        return path

    def png(self) -> bytes:
        import io
        self.client.refreshScreen()
        buf = io.BytesIO()
        self.client.screen.save(buf, "PNG")
        return buf.getvalue()

    def type(self, text: str) -> None:
        for ch in text:
            self.client.keyPress(ch)

    def keys(self, *names: str) -> None:
        for name in names:  # vncdotool key names: enter, ctrl-c, alt-f2, f1, ...
            self.client.keyPress(name)
