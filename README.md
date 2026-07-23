# NEP Local

NEP Local is a Home Assistant custom integration for the local web interface of Northern Electric Power BDG-256 gateways. It discovers every logical PV input reported by the gateway and reads production data without a cloud account.

This project is early alpha software tested against one gateway. Gateway firmware variants may expose different local response formats.

## Installation

1. In HACS, add `FtlC-ian/ha-nep-local` as a custom integration repository.
2. Install **NEP Local** and restart Home Assistant.
3. Go to **Settings → Devices & services → Add integration**, search for **NEP Local**, and enter the gateway's local IP address or hostname.

The integration creates one gateway device and groups logical input channels under their physical microinverter when the gateway's `M_ID` scheme makes that pairing unambiguous. Newly reported channels are added automatically. Channels are retained at night and when they report zero production.

Power, DC voltage, current, energy, and status remain per input channel. AC voltage, grid frequency, and temperature are published once per physical inverter because both inputs share the same AC connection and enclosure.

## Data behavior

- Power is reported in watts.
- Daily and lifetime energy are reported in watt-hours.
- Daily energy is a resetting total; lifetime energy is a non-resetting total.
- NEP status `8000` means low light. It is a valid response and does not make a device unavailable.
- NEP status `0010` is the documented bit-4 "frequency over" fault. It can appear
  briefly while an inverter synchronizes at sunrise, but remains a fault rather
  than a standby state. The exact code is available as the status sensor's
  `raw_status` attribute.
- Missing or invalid telemetry is not converted to zero.
- Rich `min.dat` telemetry older than 15 minutes is treated as unavailable.
- Fresh `min.dat` daily energy backs up the live daily-energy value; lifetime energy remains live-endpoint only.
- The gateway's `-100 °C` unavailable-temperature sentinel is not published as a temperature.

## Support

Please include Home Assistant diagnostics and gateway model/firmware details in a [GitHub issue](https://github.com/FtlC-ian/ha-nep-local/issues). Diagnostics redact the configured host and device identifiers.

## License

MIT
