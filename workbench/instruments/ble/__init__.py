import asyncio
from asyncio import Queue, QueueEmpty
from typing import Self

from bleak import BleakClient, BleakScanner

from workbench.instruments import Instrument


class UNITUT3X3BT(Instrument):

    CHAR_WRITE = "0000ff01-0000-1000-8000-00805f9b34fb"
    CHAR_NOTIFY = "0000ff02-0000-1000-8000-00805f9b34fb"

    def __init__(self, address: str):
        self.client = BleakClient(address)
        self.queue = Queue()

    async def __aenter__(self) -> Self:
        await self.client.connect()
        await self.client.start_notify(self.CHAR_NOTIFY, lambda _, data: self.queue.put_nowait(data))
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.client.stop_notify(self.CHAR_NOTIFY)
        await self.client.disconnect()

    async def __aiter__(self):
        while True:
            try:
                self.queue.get_nowait()
            except QueueEmpty:
                break
        while True:
            await self.client.write_gatt_char(self.CHAR_WRITE, b"\x5e")
            try:
                yield self.queue.get_nowait()
            except QueueEmpty:
                await asyncio.sleep(0.001)

    @classmethod
    async def find(cls, name_or_address="UT333BT") -> Self:
        async with BleakScanner() as scanner:
            devices = await scanner.discover()
            for device in devices:
                if device.name == name_or_address or device.address == name_or_address:
                    return cls(address=device.address)
            raise RuntimeError("Device not found")

    @classmethod
    def connect(cls, address: str) -> Self:
        return cls(address)
