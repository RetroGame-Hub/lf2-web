"""Pair compatible OpenLF2 clients and forward their TCP streams."""
import argparse
import asyncio
import re

PROFILE = re.compile(rb"OpenLF2 TCP 1\n[0-9a-fA-F]{64}")
QUEUE_TIMEOUT = 115
MATCH_IDLE_TIMEOUT = 45
MAX_CONNECTIONS = 128
BUFFER_SIZE = 8192


class Relay:
    def __init__(self):
        self.waiting = {}
        self.connections = 0

    async def client(self, reader, writer):
        if self.connections >= MAX_CONNECTIONS:
            writer.close()
            return
        self.connections += 1
        profile = None
        waiting = None
        try:
            profile = await asyncio.wait_for(reader.readexactly(78), 8)
            if not PROFILE.fullmatch(profile):
                return
            peer = self.waiting.pop(profile, None)
            if peer and not peer[2].done() and not peer[0].at_eof():
                other_reader, other_writer, done = peer
                try:
                    await self.bridge(other_reader, other_writer, reader, writer)
                finally:
                    if not done.done():
                        done.set_result(None)
                return
            if peer and not peer[2].done():
                peer[2].set_result(None)
            waiting = asyncio.get_running_loop().create_future()
            self.waiting[profile] = (reader, writer, waiting)
            # The peer removes the ticket before sending roles. While queued, no
            # application bytes are expected and an EOF invalidates the ticket.
            for _ in range(QUEUE_TIMEOUT * 4):
                if reader.at_eof():
                    return
                if self.waiting.get(profile, (None, None, None))[2] is not waiting:
                    await waiting
                    return
                done, _ = await asyncio.wait({waiting}, timeout=0.25)
                if done:
                    return
        except (OSError, EOFError, TimeoutError):
            pass
        finally:
            if profile and waiting and self.waiting.get(profile, (None, None, None))[2] is waiting:
                del self.waiting[profile]
            self.connections -= 1
            writer.close()
            try:
                await asyncio.wait_for(writer.wait_closed(), 2)
            except (OSError, TimeoutError):
                pass

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
