# NEP Local

NEP Local is a Home Assistant custom integration for the local web interface of Northern Electric Power BDG-256 gateways. It discovers every logical PV input reported by the gateway and reads production data without a cloud account.

This project is early alpha software tested against one gateway. Gateway firmware variants may expose different local response formats.

## What's new in 0.2.0

- Falls back to per-slot `/data/<n>/min.dat` when the gateway's `/nep/status` inventory and `/total` endpoints stop working.
- Treats slot 0 as the gateway aggregate and unwired spare inverters as unavailable.
- Reports lifetime energy as unknown in fallback mode because `min.dat` holds only daily totals.

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
path; channel `SLOT_START=1`, `SLOT_END=15` (inclusive), and
`MISSING_SLOT_LIMIT=3` bound discovery. Only absent files count toward that stop,
and the scan always reaches the highest registered slot, even after gaps.
The end extends beyond SLOT_END when needed to include registered channels.
Missing, malformed, stale, or silent channels are unavailable, not fabricated
zeroes. The gateway's silent template has zero electrical readings and the
-100 °C sentinel; a responding channel with valid voltage or temperature can
still legitimately report 0 W. Slot 0 is fetched separately as the gateway
aggregate and supplies power/today energy whenever fresh. If unavailable, the
gateway uses a complete sum of reporting channels, otherwise unknown.
Diagnostics cross-check slot 0 against all fresh raw channel records (including
silent-slot zero templates), with sums, deltas, and reporting-channel count.
Reads are not atomic; independently updated records can differ even within
the same minute. Diagnostic timestamps accompany the cross-check values.
Unregistered slots are never assigned invented identities or included in sums.

Existing configured entries reuse their gateway serial and registered COM-ID
spelling, including both prefixed `0X12340000` and unprefixed `12340000` IDs.
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
with the existing parser and the known `8000` night/idle samples. The producing
gateway aggregate can report `8000`, so that code never suppresses power or valid
nonzero voltage/frequency readings. Zero voltage/frequency at low light and
the temperature sentinel are missing readings. The exact meanings of the
penultimate diagnostic and numeric index remain unverified.

### Verified PLC slot identity

Registry Inverter(N) is PLC index/data slot N. Slot 0 is the gateway aggregate,
not an inverter. The owner's PLC_ID dump confirms index 0 = FFFFFFFF (all),
followed by the same twelve COM-IDs in the registry. Live HTTP evidence at
2026-10-19 16:24 independently confirms it: slot 0 power 30.255 W equals
slots 2 + 4 + 9 (12.993 + 2.026 + 15.236 W), and slot 0 daily energy 611 Wh
equals all channels (1 + 112 + 0 + 42 + 444 + 12 Wh). Slots 1..12 respond;
slot 13 is missing. Matching AC frequency and temperature pair slots (1,2),
(3,4), and (9,10), consistent with their dual-input physical COM-ID pairs.

The identifiers below are neutral placeholders; slot relationships are preserved.

```text
0 GATEWAY
1 12340000    2 12340001    3 12340010    4 12340011
5 12340020    6 12340021    7 12340030    8 12340031
9 12340040   10 12340041   11 12340050   12 12340051
```

The owner confirmed slots 5..8 and 11..12 are unwired spares. Their silent
templates remain unavailable, not 0 W sensors.

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
