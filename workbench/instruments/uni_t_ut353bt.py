import asyncio

from workbench.instruments.ble import UNITUT3X3BT


class UNITUT353BT(UNITUT3X3BT):

    async def fetch(self) -> float:
        while True:
            async for data in self:
                if data.hex().startswith("aabb10013b"):
                    return float(data[5:].decode("ascii", errors="replace").strip().split("dBA")[0])


if __name__ == "__main__":
    async def main():
        async with UNITUT353BT.connect("AFB65A70-34DE-0163-C692-553F078E7BEE") as i:
            print(await i.fetch())


    asyncio.run(main())
