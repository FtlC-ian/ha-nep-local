"""Read-only slot verification: python -m scripts.read_gateway http://gateway SERIAL."""

import asyncio
import sys

from aiohttp import ClientSession

from custom_components.nep_local.client import NepGatewayClient
from custom_components.nep_local.models import InventoryModule


async def main():
    async with ClientSession() as session:
        client = NepGatewayClient(session, sys.argv[1])
        inventory = await client.fallback_inventory(sys.argv[2])
        records = await client.scan_slots({module.slot for module in inventory.modules})
        aggregate = await client.min_dat(InventoryModule("0", "", slot=0))
        print(
            f"gateway slot 0: {aggregate.timestamp.isoformat()} {aggregate.power_w:.3f} W {aggregate.energy_wh:.3f} Wh today"
        )
        print("slot COM-ID timestamp W Vdc Vac A Hz C today_Wh status index diagnostic")
        for module in inventory.modules:
            record = records.get(module.slot)
            if record is None:
                print(module.slot, module.raw_id, "missing")
                continue
            if not record.has_measurements:
                print(module.slot, module.raw_id, "unavailable (silent slot)")
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
        if all(module.slot in records for module in inventory.modules):
            power_sum = sum(
                records[module.slot].power_w for module in inventory.modules
            )
            today_sum = sum(
                records[module.slot].energy_wh for module in inventory.modules
            )
            print(f"raw channel sum: {power_sum:.3f} W {today_sum:.3f} Wh today")
            print(
                f"gateway minus channels: {aggregate.power_w - power_sum:.3f} W {aggregate.energy_wh - today_sum:.3f} Wh (non-atomic reads)"
            )
        print("Lifetime Wh: unavailable (not present in min.dat)")


if __name__ == "__main__":
    asyncio.run(main())
