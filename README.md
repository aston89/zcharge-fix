
# zcharge

Simple module to limit charging capacity. This is my experiment coding in C++, jump straight using chatgpt, pretty fun.


## Fork changes

This is a fork of [lululoid/zcharge](https://github.com/lululoid/zcharge).

### Why these changes?

- **Main loop: 1s → 60s**
  - Polling every second was pointless for a charge limiter and caused unnecessary
    wakeups / overhead.
  - 60 seconds is enough for capacity-based charging control.

- **USB detection via `usb/online`**
  - The original logic relied on `battery/status`.
  - On Qualcomm devices, disabling charging through `input_suspend` makes Android
    report `Discharging` even when the USB cable is still connected.
  - This made zcharge think the charger had been unplugged and prevented proper
    recharging.

- **`is_charging()` no longer uses `battery/status`**
  - Same problem: `battery/status` becomes misleading when `input_suspend=1`.
  - The actual battery current is a much better indication of whether charge is
    flowing.

- **Recharging logic fixed**
  - With the old logic, reaching the charge limit could leave charging suspended
    indefinitely because the device appeared to be "unplugged".
  - Now zcharge can correctly go:
    `50% → stop → 48% → resume`
    while the USB charger remains connected.

- **Temperature recovery cannot bypass the charge limit**
  - We don't want temperature control to accidentally restart charging above the
    configured capacity limit.
  - Temperature recovery can therefore only restart charging when
    `capacity < capacity_limit`.

- **Charging-switch verification rewritten**
  - The old code changed its internal switch state and then used that same state
    to decide whether the transition had succeeded.
  - That could make the check succeed/fail for the wrong reason.
  - The new code checks `battery/current_now` directly.

- **1-second checks kept only during switch transitions**
  - Turning charging on/off is something we actually want to verify quickly.
  - So the 1-second polling wasn't removed completely, just moved out of the normal
    monitoring loop.

- **Current logging fixed**
  - `current_now` is reported by the kernel in µA, while the original log labelled
    it as mA.
  - A value like `1500000` therefore means about `1.5 A`, not `1500 A`.

---

## Usage

```
Usage: zcharge [OPTIONS] [ARGS...]
Options:
  --print                                  Print configuration content
  --convert <old_config> <new_config>      Convert the old configuration file to the new database format.
  --enable [config_db]                     Enable zcharge with the specified database file (or default).
  --disable [config_db]                    Disable zcharge with the specified database file (or default).
  --reload                                 Tell service to reload the config.
  --update <key=value> [config_db]         Update the configuration value for the specified key. If [config_db] is omitted, uses default.
  -h, --help                               Show this help message and exit.

Example key-value pairs:
  charging_switch_path=/path/to/switch
  charging_switch_on=1
  charging_switch_off=0
  recharging_limit=75
  capacity_limit=85
  temperature_limit=410
```
