"""Read-only slot verification: python -m scripts.read_gateway http://gateway SERIAL."""

import asyncio
import sys

from aiohttp import ClientSession

from custom_components.nep_local.client import NepGatewayClient


async def main():
    async with ClientSession() as session:
        client = NepGatewayClient(session, sys.argv[1])
        inventory = await client.fallback_inventory(sys.argv[2])
        records = await client.scan_slots()
        print("slot COM-ID timestamp W Vdc Vac A Hz C today_Wh status flag diagnostic")
        for module in inventory.modules:
            record = records.get(module.slot)
            if record is None:
                print(module.slot, module.raw_id, "missing")
                continue
            print(
                module.slot,
                module.raw_id,
                record.timestamp.isoformat(),
                f"{record.power_w:.3f}",
                record.voltage_dc_v,
                record.voltage_ac_v,
                record.current_a,
                record.frequency_hz,
                record.temperature_c,
                record.energy_wh,
                record.status_code,
                record.rssi,
                record.diagnostic_code,
            )
        print("Lifetime Wh: unavailable (not present in min.dat)")


if __name__ == "__main__":
    asyncio.run(main())
