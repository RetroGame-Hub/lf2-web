"""Pair compatible OpenLF2 clients and forward their TCP streams."""
import argparse
import asyncio
import re
import secrets
from dataclasses import dataclass

PROFILE = re.compile(rb"OpenLF2 TCP 1\n[0-9a-fA-F]{64}")
QUEUE_TIMEOUT = 115
ROOM_TIMEOUT = 300
HANDSHAKE_TIMEOUT = 8
PROFILE_SIZE = 78
ROOM_CODE = re.compile(rb"[0-9]{6}")
MATCH_IDLE_TIMEOUT = 45
MAX_CONNECTIONS = 128
BUFFER_SIZE = 8192


@dataclass
class WaitingPeer:
    reader: asyncio.StreamReader
    writer: asyncio.StreamWriter
    profile: bytes
    deadline: float
    done: asyncio.Future
    claimed: bool = False

    def available(self):
        return not self.done.done() and not self.reader.at_eof()


class Relay:
    def __init__(self):
        self.waiting = {}
        self.rooms = {}
        self.connections = 0

    async def client(self, reader, writer):
        if self.connections >= MAX_CONNECTIONS:
            writer.close()
            return
        self.connections += 1
        try:
            command, profile, code = await asyncio.wait_for(self.read_request(reader), HANDSHAKE_TIMEOUT)
            if not PROFILE.fullmatch(profile):
                return
            if command == b"O":
                peer = self.waiting.get(profile)
                if self.is_joinable(peer):
                    await self.pair(self.waiting.pop(profile), reader, writer)
                else:
                    await self.wait(self.waiting, profile, reader, writer, profile, QUEUE_TIMEOUT)
            elif command == b"C":
                code = self.new_room_code()
                await self.wait(self.rooms, code, reader, writer, profile, ROOM_TIMEOUT, b"R" + code)
            elif command == b"J":
                peer = self.rooms.get(code)
                if not self.is_joinable(peer):
                    await self.reply(writer, b"N")
                elif peer.profile != profile:
                    await self.reply(writer, b"X")
                else:
                    await self.pair(self.rooms.pop(code), reader, writer)
        except (OSError, EOFError, TimeoutError):
            pass
        finally:
            self.connections -= 1
            writer.close()
            try:
                await asyncio.wait_for(writer.wait_closed(), 2)
            except (OSError, TimeoutError):
                pass

    @staticmethod
    async def read_request(reader):
        command = await reader.readexactly(1)
        if command == b"O":
            return command, command + await reader.readexactly(PROFILE_SIZE - 1), None
        if command in (b"C", b"J"):
            profile = await reader.readexactly(PROFILE_SIZE)
            if command == b"C":
                return command, profile, None
            code = await reader.readexactly(6)
            if ROOM_CODE.fullmatch(code):
                return command, profile, code
        return command, b"", None

    def new_room_code(self):
        while True:
            code = str(100000 + secrets.randbelow(900000)).encode("ascii")
            if code not in self.rooms:
                return code

    @staticmethod
    def is_joinable(peer):
        return (
            peer is not None
            and peer.available()
            and asyncio.get_running_loop().time() < peer.deadline
        )

    @staticmethod
    async def reply(writer, data):
        writer.write(data)
        await asyncio.wait_for(writer.drain(), HANDSHAKE_TIMEOUT)

    async def wait(self, queue, key, reader, writer, profile, timeout, confirmation=None):
        loop = asyncio.get_running_loop()
        peer = WaitingPeer(reader, writer, profile, loop.time() + timeout, loop.create_future())
        queue[key] = peer
        # Queue ownership moves to the guest when a match starts. Keep the host
        # socket open until the guest's forwarding loop finishes.
        try:
            if confirmation:
                # write() runs before the coroutine first yields, so R + code
                # always goes out before a guest can claim the room and get H.
                await self.reply(writer, confirmation)
            while queue.get(key) is peer:
                if not peer.available():
                    return
                remaining = peer.deadline - loop.time()
                if remaining <= 0:
                    if confirmation:
                        # Remove the room before yielding to a late joiner.
                        del queue[key]
                        await self.reply(writer, b"T")
                    return
                await asyncio.wait({peer.done}, timeout=min(0.25, remaining))
            # If another waiter replaced this one, its deadline already passed
            # or its connection closed. Only claimed peers need to stay open.
            if peer.claimed:
                await peer.done
        finally:
            if queue.get(key) is peer:
                del queue[key]

    async def pair(self, peer, reader, writer):
        peer.claimed = True
        try:
            await self.bridge(peer.reader, peer.writer, reader, writer)
        finally:
            if not peer.done.done():
                peer.done.set_result(None)

    @staticmethod
    async def bridge(host_in, host_out, guest_in, guest_out):
        async def forward(source, destination):
            while content := await asyncio.wait_for(source.read(BUFFER_SIZE), MATCH_IDLE_TIMEOUT):
                destination.write(content)
                await asyncio.wait_for(destination.drain(), MATCH_IDLE_TIMEOUT)

        host_out.write(b"H")
        guest_out.write(b"G")
        await asyncio.wait_for(asyncio.gather(host_out.drain(), guest_out.drain()), 8)
        tasks = {
            asyncio.create_task(forward(host_in, guest_out)),
            asyncio.create_task(forward(guest_in, host_out)),
        }
        try:
            await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)


async def serve(address, port):
    async with await asyncio.start_server(Relay().client, address, port, limit=BUFFER_SIZE) as server:
        print(f"OpenLF2 relay listening on {address}:{port}", flush=True)
        await server.serve_forever()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bind", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=12346)
    args = parser.parse_args()
    asyncio.run(serve(args.bind, args.port))
