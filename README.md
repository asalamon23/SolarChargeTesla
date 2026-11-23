# SolarCharge — Huawei FusionSolar × Tesla Model Y

A runnable local web dashboard and solar-surplus charging controller. **Defaults to simulation mode and never sends commands to Tesla without explicit configuration.**

## Run

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
python app.py
```

Open http://127.0.0.1:8080

## How the charging calculation works

The meter bridge supplies `solar_w` (PV generation) and `grid_w` (positive import, negative export). Because grid power already includes EV charging, available EV power is `current EV power - grid import - 450 W reserve`. The algorithm applies a 6–16 A three-phase range, starts only when 6 A is possible, uses 120 seconds of start hysteresis, 45 seconds to stop, and a 90-second command cooldown. Configure these values for your wiring, charger, inverter, and Tesla limits before live use. This is a proof-of-concept, not an electrical protection device.

## Huawei integration

1. Ask your Huawei installer/plant administrator for a FusionSolar Northbound API account or enable an authorized local meter/inverter integration such as a supported Modbus bridge. API availability, endpoint, permissions, and latency depend on the exact Huawei hardware and installation.
2. Implement a trusted HTTPS bridge returning JSON like `{"solar_w":6500,"grid_w":-4200}`. **Positive grid_w means import; negative means export.** Verify signs with a known household load and EV off.
3. Set `METER_BRIDGE_URL` and optionally `METER_BRIDGE_TOKEN`. Do not expose credentials in the browser.
4. The bridge must return recent readings. Production use should include timestamps and a watchdog; the example code only tracks the time of successful bridge responses.

## Tesla integration

1. Register an app at https://developer.tesla.com/ and obtain approved OAuth credentials. Request the required vehicle data and charging command permissions; consult current Tesla scope documentation.
2. Generate and register the virtual key, host the public key at the required `/.well-known/appspecific/com.tesla.3p.public-key.pem` path and pair it to the vehicle through Tesla's official flow.
3. Run Tesla's official Vehicle Command Proxy with TLS and private key securely stored on the server: https://github.com/teslamotors/vehicle-command .
4. Obtain a Tesla OAuth access token through the approved flow. For this prototype set `TESLA_PROXY_URL`, `TESLA_VIN`, and `TESLA_ACCESS_TOKEN` in your process environment. **Token refresh is not implemented**; use a secret manager and a token refresh service for unattended operation.
5. Test `charge_stop`, `set_charging_amps` and `charge_start` with the vehicle parked, plugged in, and supervised before enabling automation. Commands are sent to the vehicle, not directly to your third-party wallbox.

## Third-party charger and 3-phase limitations

The charger must be able to supply the requested current. This prototype assumes 3 phases at 230 V per phase: 6 A = 4.14 kW; 16 A = 11.04 kW. It does **not** switch phases. A compatible charger with phase-switching support requires a separate charger integration and interlock. Confirm charger make/model, maximum current, house main breaker rating, phase balancing and grid export rules with an electrician.

## Operational caveats

- This is a starter app with a functional dashboard and control loop, **not a production-ready unattended charging controller**.
- A live installation needs user authentication, HTTPS, CSRF protection, persisted configuration, robust token refresh, true charger telemetry, independent overload protection, error alerts and tested fail-safe behavior.
- Tesla may be asleep, offline, disconnected, charge-limited, or reject a command. The prototype uses optimistic charge-state tracking rather than reading back the actual vehicle state. This must be corrected before unattended use.
- If Tesla is charging at a different current than last commanded, the surplus calculation may be wrong. Production logic should use actual charging telemetry and meter timestamps.
- API quotas, billing and Huawei permissions may apply.
- Never use this app as the sole protection against electrical overload or grid import.

## Test readings

While in demo mode, simulate a sunny day:

```bash
curl -X POST http://127.0.0.1:8080/api/demo -H 'Content-Type: application/json' -d '{"solar_w":8500,"grid_w":-6500}'
```

To simulate a cloud:

```bash
curl -X POST http://127.0.0.1:8080/api/demo -H 'Content-Type: application/json' -d '{"solar_w":1000,"grid_w":200}'
```

Wait for the hysteresis period before checking changes. Do not expose the Flask server to the public internet.

## Confirmed installation: Schneider EVlink Home 11 kW (non-Smart)

This installation uses the **Tesla vehicle API**, not Schneider OCPP or charger networking. Schneider EVlink Home non-Smart does not expose the Smart model's OCPP/Wi-Fi/Ethernet interfaces. Keep `phases=3`, `min_amps=6`, `max_amps=16` unless your electrician verifies different limits. A three-phase 6 A threshold is approximately 4.14 kW; below this, pause instead of trying to request less than 6 A. Do not assume phase switching is possible. The Schneider anti-tripping accessory (if installed) is separate from solar optimization and must not be bypassed.

**Before real operation:** Confirm Huawei inverter/dongle and meter models and permitted access method; obtain authorized meter data with timestamps; implement actual Tesla charge-current/status readback; validate signed Tesla command proxy, OAuth refresh and command responses; secure the web interface; test meter sign and fail-safe behavior; and have a qualified electrician verify site load limits. The existing demo is not production-ready and must not be used unattended.
