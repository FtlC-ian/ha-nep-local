# NEP Local

NEP Local is a Home Assistant custom integration for the local web interface of Northern Electric Power BDG-256 gateways. It discovers every logical PV input reported by the gateway and reads production data without a cloud account.

This project is early alpha software tested against one gateway. Gateway firmware variants may expose different local response formats.

## Installation

1. In HACS, add `FtlC-ian/ha-nep-local` as a custom integration repository.
2. Install **NEP Local** and restart Home Assistant.
3. Go to **Settings → Devices & services → Add integration**, search for **NEP Local**, and enter the gateway's local IP address or hostname.

The integration creates one gateway device and groups logical input channels under their physical microinverter when the gateway's `M_ID` scheme makes that pairing unambiguous. Newly reported channels are added automatically. Channels are retained at night and when they report zero production.

## Data behavior

- Power is reported in watts.
- Daily and lifetime energy are reported in watt-hours.
- Daily energy is a resetting total; lifetime energy is a non-resetting total.
- NEP status `8000` means low light. It is a valid response and does not make a device unavailable.
- Missing or invalid telemetry is not converted to zero.
- The gateway's `-100 °C` unavailable-temperature sentinel is not published as a temperature.

## Support

Please include Home Assistant diagnostics and gateway model/firmware details in a [GitHub issue](https://github.com/FtlC-ian/ha-nep-local/issues). Diagnostics redact the configured host and device identifiers.

## License

MIT
