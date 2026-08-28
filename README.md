
# zcharge

Simple module to limit charging capacity. This is my experiment coding in C++, jump straight using chatgpt, pretty fun.

## Fork changes

This is a fork of [lululoid/zcharge](https://github.com/lululoid/zcharge).

The fork mainly fixes charging-state handling on Qualcomm devices and removes
unnecessary polling overhead.

### Why these changes?

- **Main loop: 1s → 60s**
  - Polling battery state every second is unnecessary for a charge limiter.
  - The normal monitoring loop now runs once per minute.
  - The 1-second polling is retained only while confirming a charging
    switch transition.

- **USB presence via `usb/online`**
  - The original implementation relied on `battery/status` to determine
    whether the charger was still connected.
  - On Qualcomm devices, `input_suspend=1` makes the battery report
    `Discharging` even though USB is still physically connected.
  - The fork checks the actual USB power-supply state instead.

- **Charging detection via actual battery current**
  - `battery/status` is unreliable while charging is suspended.
  - `battery/current_now` is used to determine whether current is actually
    flowing into the battery.

- **Fixed recharge hysteresis**
  - The intended behaviour is:
    `50% → stop charging → 48% → resume charging`
  - Recharging no longer depends on the misleading `battery/status` state
    produced by `input_suspend`.

- **Temperature recovery cannot override the capacity limit**
  - Recovering from a thermal cooldown must not restart charging above
    `capacity_limit`.

- **Charging-switch verification rewritten**
  - The fork verifies the result using actual battery current instead of
    relying only on the software switch state.

- **Current units corrected in logging**
  - Android exposes `battery/current_now` in µA.
  - Logs therefore report the value as `µA` rather than `mA`.

### Build system

The repository contains a small helper build pipeline because the source is
also edited from Windows.

- `A1_make_configure_sqliteDB.py`
  - Creates a backup of `zcharge.db`.
  - Applies the intended default configuration.
  - Ensures the required SQLite configuration keys exist.

- `A2_make_magisk_module.py`
  - Collects the compiled binary and Magisk module files.
  - Creates the final `zcharge-magisk.zip`.

- `Makefile`
  - Builds `system/bin/zcharge`.
  - Links the bundled SQLite amalgamation.
  - Expects an Android ARM64 toolchain and the corresponding `libc++_shared.so`.

- `.github/workflows/`
  - The project is compiled through GitHub Actions instead of requiring a
    local Android NDK installation.
  - The workflow installs the Android NDK, builds the ARM64 binary, verifies
    the resulting ELF, and uploads the compiled binary as an artifact.

### Windows source sanitization

When the source is copied/edited from Windows, line endings and file encoding
can occasionally cause confusing compiler/parser failures.

The build workflow therefore treats the repository contents as source files
rather than assuming that a Windows copy/paste is already clean.

The helper scripts are intentionally kept separate from the C++ source so that
database configuration and Magisk packaging can be repeated without touching
the compiled code.

### Build flow

```text
zcharge.cpp
    │
    ▼
GitHub Actions
    │
    ├── Android NDK / ARM64 toolchain
    │
    ▼
make
    │
    ▼
system/bin/zcharge
    │
    ├── A1_make_configure_sqliteDB.py
    │
    └── A2_make_magisk_module.py
            │
            ▼
    zcharge-magisk.zip
````

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
