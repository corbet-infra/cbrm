"""The panel's VNC console: a Proxmox noVNC websocket. A local TCP port is bridged to that websocket
so a normal VNC client (vncdotool) can capture the screen and send keys."""
from __future__ import annotations

import asyncio
import atexit
import concurrent.futures
import ssl
import threading
import time

import websockets
from vncdotool import api as vnc

from .errors import PanelError

# vncdotool runs one Twisted reactor per process and cannot restart it: stop it once, at exit, so
# long-running servers (API, MCP) can open many console sessions. It must run BEFORE the interpreter
# joins non-daemon threads (the reactor thread is one), which plain atexit does not: use the hook
# concurrent.futures uses, and atexit only where it is missing.
_register = getattr(threading, "_register_atexit", atexit.register)
_register(vnc.shutdown)


class Console:
    """Use as a context manager: `with Console(host, port, ticket) as c: c.capture("out.png")`."""

    #: hard limit for one console operation; a VM changing resolution while it boots can stall a VNC client
    DEADLINE = 60

    def __init__(self, host: str, port: int, password: str):
        self.url, self.password = f"wss://{host}:{port}/websockify", password
        self._loop = asyncio.new_event_loop()
        self._server = None
        self._thread = threading.Thread(target=self._loop.run_forever, daemon=True)
        self.client = None

    async def _connect(self):
        """The panel starts the console proxy on demand: right after the session is handed out its port may
        still refuse connections, so retry for a while."""
        for attempt in range(20):
            try:
                return await websockets.connect(self.url, subprotocols=["binary"], ssl=ssl.create_default_context(),
                                                max_size=None)
            except (ConnectionRefusedError, OSError):
                if attempt == 19:
                    raise
                await asyncio.sleep(1)

    async def _bridge(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        async with await self._connect() as ws:
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

    def __enter__(self) -> Console:
        try:
            return self._open()
        except BaseException:
            self._stop()
            raise

    def _open(self) -> Console:
        self._thread.start()
        self._server = asyncio.run_coroutine_threadsafe(
            asyncio.start_server(self._bridge, "127.0.0.1", 0), self._loop).result(10)
        port = self._server.sockets[0].getsockname()[1]
        self.client = self._bounded(lambda: vnc.connect(f"127.0.0.1::{port}", password=self.password, timeout=30))
        return self

    def _bounded(self, fn, seconds: float | None = None):
        """Run one console operation with a hard deadline; a stalled VNC session raises instead of hanging."""
        pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        try:
            return pool.submit(fn).result(timeout=seconds or self.DEADLINE)
        except concurrent.futures.TimeoutError:
            raise PanelError(f"the console did not answer within {seconds or self.DEADLINE} s") from None
        finally:
            pool.shutdown(wait=False)

    def __exit__(self, *exc) -> None:
        try:
            if self.client:
                self.client.disconnect()
        finally:
            self._stop()

    def _stop(self) -> None:
        if self._thread.is_alive():
            if getattr(self, "_server", None) is not None:
                asyncio.run_coroutine_threadsafe(self._close(), self._loop).result(10)
            self._loop.call_soon_threadsafe(self._loop.stop)
            self._thread.join(5)
        if not self._loop.is_running():
            self._loop.close()

    async def _close(self) -> None:
        self._server.close()
        tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    def capture(self, path: str) -> str:
        self._bounded(lambda: self.client.captureScreen(path))
        return path

    def png(self) -> bytes:
        import io

        def grab():
            self.client.refreshScreen()
            buf = io.BytesIO()
            self.client.screen.save(buf, "PNG")
            return buf.getvalue()
        return self._bounded(grab)

    def type(self, text: str) -> None:
        self._bounded(lambda: [self.client.keyPress(ch) for ch in text])

    def keys(self, *names: str, repeat: int = 1, interval: float = 1.0) -> None:
        """Press the keys (vncdotool names: enter, ctrl-c, alt-f2, f1, ...), `repeat` times, `interval` s apart:
        e.g. Enter every second while a VM boots catches its boot menu without guessing the moment."""
        for i in range(repeat):
            if i:
                time.sleep(interval)
            self._bounded(lambda: [self.client.keyPress(n) for n in names])
