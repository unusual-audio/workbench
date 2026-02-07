import asyncio
from typing import Tuple

from workbench.instruments.ble import UT3X3BT


class UT333BT(UT3X3BT):

    async def fetch(self) -> Tuple[float, float]:
        temperature, humidity = None, None
        async for data in self:
            if data.hex().startswith("aabb100130"):
                temperature = float(data[5:].decode("ascii", errors="replace").strip().split()[0])
            elif data.hex().startswith("aabb100134"):
                humidity = float(data[5:].decode("ascii", errors="replace").strip().split("%RH")[0])
            else:
                print("Weird payload:", data[:5].hex(), data[5:])
            if temperature is not None and humidity is not None:
                break
        return temperature, humidity


if __name__ == "__main__":
    async def main():
        async with UT333BT.connect("743EB3A4-3784-A384-7EAD-6531496DA19B") as i:
            print(await i.fetch())


    asyncio.run(main())
