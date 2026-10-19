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

## Inventory-independent fallback

When the overview endpoint fails, the integration reads the COM-ID registry at
`/module/`. On the tested firmware this is a JavaScript-rendered form, so its
read-only backing JSON, `/module/module.php`, supplies the inputs. It scans numeric
`/data/<slot>/min.dat` files, not COM-ID paths. Every refresh retries the preferred
overview so recovery is automatic. In `const.py`, `FALLBACK_ENABLED` enables this
path; `SLOT_START=0`, `SLOT_END=15` (inclusive), and
`MISSING_SLOT_LIMIT=3` bound discovery. Only absent files count toward that stop,
and the scan always reaches the highest registered slot inside the configured
range, even after gaps. Registered slots outside that range remain unknown.
Missing, malformed, or stale channels remain unknown, not zero. Gateway sums
are unknown unless every registered channel has a fresh value. Unregistered
slots are not assigned invented identities or included in totals.

Existing configured entries reuse their gateway serial and registered COM-ID
spelling, including both prefixed `0X326ED5E0` and unprefixed `326ED5E0` IDs.
Entity unique-ID construction is unchanged. New installations can supply the
optional 14-digit serial number if the overview is dead, with explicit
confirmation that it matches the gateway label and any existing HA entry;
the registry does not attest that serial. Host reconfiguration still requires the preferred serial-bearing
overview to prevent accidentally switching gateway identities.

### Observed columns (BDG-256(P3), 2026-10-19)

After the date and minute: kW, DC V, AC V, A, Hz, °C, daily kWh,
an undocumented numeric telemetry index, diagnostic word, status word.
The parser converts kW/kWh to W/Wh. The numeric index retains the legacy
`rssi` field for compatibility; it is not confirmed RSSI and is disabled by
default. Do not interpret it as a boolean: a later sample was `0.347`.

Captured by read-only HTTP GET:

```text
slot 0: 2026-10-19 15:48 0.153837 29.62 246 0.1 59.97 30 0.58 1 0 8000
slot 1: 2026-10-19 15:48 0.001229 41.76 245.7 0 60.01 30 0.001 0 8B05 0
slot 5: 2026-10-19 15:48 0 0 0 0 0 -100 0 1 0 8000
night:  2026-10-19 01:13 0 0 0 0 0 -100 0 1 0 8000
```

The final word, not the diagnostic `8B05`, is used as the status, consistent
with the existing parser and the known `8000` night/idle samples. A producing
channel can still report `8000`, so that code never suppresses power or valid
nonzero voltage/frequency readings. Zero voltage/frequency at low light and
the temperature sentinel are missing readings. The exact meanings of the
penultimate diagnostic and numeric index remain unverified.

### Slot identity assumption, requiring owner confirmation

The registry explicitly labels Inverter1 through Inverter12, but the telemetry
files contain no COM-ID. We assume Inverter(N) maps to slot(N-1); ordering is
not independently proven. Do not rearrange the registry without validating it.

```text
0 326ED5E0    1 326ED5E1    2 326EFF30    3 326EFF31
4 3268C170    5 3268C171    6 3265F760    7 3265F761
8 326F0891    9 326F0890   10 326F2771   11 326F2770
```

Lifetime energy cannot be recovered from daily-resetting `min.dat` alone.
Fallback deliberately reports lifetime as unknown rather than publishing
daily energy under a non-resetting lifetime entity or fabricating a zero.
Restoring lifetime totals requires an independently verified historical source
or owner-approved baselines and persistence; neither is assumed here.

Read-only verification (no HA deployment):
```sh
python -m scripts.read_gateway http://GATEWAY SERIAL
```

## Support

Please include Home Assistant diagnostics and gateway model/firmware details in a [GitHub issue](https://github.com/FtlC-ian/ha-nep-local/issues). Diagnostics redact the configured host and device identifiers.

## License

MIT
