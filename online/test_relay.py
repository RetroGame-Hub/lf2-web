import asyncio
import unittest
from unittest.mock import patch

import relay

PROFILE_A = b"OpenLF2 TCP 1\n" + b"a" * 64
PROFILE_B = b"OpenLF2 TCP 1\n" + b"b" * 64


class RelayTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.relay = relay.Relay()
        self.clients = []
        self.handlers = set()

        def accept(reader, writer):
            task = asyncio.create_task(self.relay.client(reader, writer))
            self.handlers.add(task)
            task.add_done_callback(self.handlers.discard)

        self.server = await asyncio.start_server(accept, "127.0.0.1", 0)
        self.port = self.server.sockets[0].getsockname()[1]

    async def asyncTearDown(self):
        self.server.close()
        for writer in self.clients:
            writer.close()
        await asyncio.gather(*(writer.wait_closed() for writer in self.clients), return_exceptions=True)
        await asyncio.wait_for(asyncio.gather(*self.handlers), 2)
        await asyncio.wait_for(self.server.wait_closed(), 2)

    @staticmethod
    async def read(reader, size):
        return await asyncio.wait_for(reader.readexactly(size), 2)

    async def send(self, data):
        reader, writer = await asyncio.open_connection("127.0.0.1", self.port)
        self.clients.append(writer)
        writer.write(data)
        await writer.drain()
        return reader, writer

    async def create_room(self):
        reader, writer = await self.send(b"C" + PROFILE_A)
        reply = await self.read(reader, 7)
        self.assertRegex(reply, rb"^R[0-9]{6}$")
        return reply[1:], reader, writer

    async def test_friend_room_is_separate_from_legacy_queue(self):
        code, host_in, _ = await self.create_room()
        first_in, _ = await self.send(PROFILE_A)
        second_in, _ = await self.send(PROFILE_A)
        quick_roles = {await self.read(first_in, 1), await self.read(second_in, 1)}
        self.assertEqual(quick_roles, {b"H", b"G"})
        guest_in, guest = await self.send(b"J" + PROFILE_A + code[:2])
        guest.write(code[2:])
        await guest.drain()
        # The host role is sent only after the complete six-digit code arrives.
        self.assertEqual(await self.read(host_in, 1), b"H")
        self.assertEqual(await self.read(guest_in, 1), b"G")

    async def test_room_has_one_guest_and_forwards_both_directions(self):
        code, host_in, host_out = await self.create_room()
        contenders = await asyncio.gather(
            self.send(b"J" + PROFILE_A + code),
            self.send(b"J" + PROFILE_A + code),
        )
        replies = {await self.read(reader, 1): (reader, writer) for reader, writer in contenders}
        self.assertEqual(set(replies), {b"G", b"N"})
        guest_in, guest_out = replies[b"G"]
        self.assertEqual(await self.read(host_in, 1), b"H")
        host_out.write(b"left")
        guest_out.write(b"right")
        await asyncio.gather(host_out.drain(), guest_out.drain())
        self.assertEqual(await self.read(guest_in, 4), b"left")
        self.assertEqual(await self.read(host_in, 5), b"right")

    async def test_wrong_version_leaves_room_available(self):
        code, host_in, _ = await self.create_room()
        wrong_in, _ = await self.send(b"J" + PROFILE_B + code)
        self.assertEqual(await self.read(wrong_in, 1), b"X")
        right_in, _ = await self.send(b"J" + PROFILE_A + code)
        self.assertEqual(await self.read(host_in, 1), b"H")
        self.assertEqual(await self.read(right_in, 1), b"G")

    async def test_host_cancel_invalidates_room(self):
        code, _, writer = await self.create_room()
        writer.close()
        await writer.wait_closed()

        async def wait_for_cleanup():
            while code in self.relay.rooms:
                await asyncio.sleep(0.01)
        await asyncio.wait_for(wait_for_cleanup(), 2)
        join_in, _ = await self.send(b"J" + PROFILE_A + code)
        self.assertEqual(await self.read(join_in, 1), b"N")

    async def test_room_expiration_is_reported_to_both_clients(self):
        with patch.object(relay, "ROOM_TIMEOUT", 0.05):
            code, host_in, _ = await self.create_room()
            self.assertEqual(await self.read(host_in, 1), b"T")
        join_in, _ = await self.send(b"J" + PROFILE_A + code)
        self.assertEqual(await self.read(join_in, 1), b"N")
