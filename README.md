# zcharge

Simple Magisk module to limit battery charging capacity.

This repository is a fork of [lululoid/zcharge](https://github.com/lululoid/zcharge), with a number of bugfixes and behavioral changes made to make the limiter reliable on Qualcomm devices, especially when charging is suspended through `input_suspend`.

The original project is a C++ charging-limiter experiment. This fork keeps the original architecture, SQLite configuration and notification system, but changes the charging-state logic substantially.

## Fork changes

This is a fork of **lululoid/zcharge**.

### Why these changes?

The original logic mixed together:

* battery charge state
* USB connection state
* `battery/status`
* battery current
* charging switch state

On Qualcomm devices this becomes problematic because suspending charging through:

```text
/sys/class/qcom-battery/input_suspend
```

can make Android report:

```text
battery/status = Discharging
```

even while the USB charger is physically connected.

That means `battery/status` cannot reliably be used to decide whether the charger is connected or whether zcharge should resume charging.

This fork therefore simplifies the controller and makes `input_suspend` the actual charging switch.

---

## 1. Main monitoring loop reduced from 1 second to 60 seconds

The original limiter polled continuously every second.

This was unnecessary for capacity-based charging control and caused needless wakeups.

The normal monitoring loop now runs every:

```text
60 seconds
```

This is more than sufficient for a battery capacity limiter.

The fast polling behavior has **not** been completely removed: short 1-second checks are still used when verifying an actual charging-switch transition.

---

## 2. USB detection removed from the charging controller

The fork originally experimented with `usb/online` as an additional charger-presence signal.

That logic has now been removed from the limiter entirely.

zCharge does **not** need to determine:

> "Is the USB charger physically connected?"

The Android/Qualcomm power stack already knows whether the device can charge.

The limiter only needs to control:

```text
/sys/class/qcom-battery/input_suspend
```

Therefore the charging logic no longer depends on:

```text
/sys/class/power_supply/usb/online
```

or:

```text
/sys/class/power_supply/battery/status
```

This also means a USB disconnect/reconnect cannot be used as the state machine for deciding whether charging should resume.

---

## 3. `battery/status` is no longer used to determine charging state

On the target Qualcomm setup, when:

```text
input_suspend = 1
```

Android may report:

```text
battery/status = Discharging
```

even though:

```text
USB = connected
```

That behavior makes `battery/status` unsuitable as the primary charging-state signal.

The fork therefore does not use it to drive the limiter.

---

## 4. `input_suspend` is now the source of truth

The charging controller operates directly on:

```text
/sys/class/qcom-battery/input_suspend
```

with:

```text
0 = charging allowed
1 = charging suspended
```

The controller therefore behaves as:

```text
battery >= capacity_limit
        +
input_suspend = 0
        ↓
input_suspend = 1
```

and:

```text
battery < recharging_limit
        +
input_suspend = 1
        ↓
input_suspend = 0
```

With the default configuration:

```text
capacity_limit  = 50
recharging_limit = 48
```

the state machine is:

```text
50% → STOP
49% → STOP
48% → STOP
47% → RESUME
```

This hysteresis prevents rapid on/off switching around the limit.

Importantly, this logic is independent of USB presence.

A charger can remain physically connected while:

```text
input_suspend = 1
```

and zCharge will keep charging suspended until the battery falls below the recharging threshold.

---

## 5. Recharging no longer requires a "charger plugged" state

The original implementation maintained an internal charger-plugged state and used battery/USB state to decide whether charging could restart.

This fork removes that dependency.

The actual switch state is read directly from:

```text
/sys/class/qcom-battery/input_suspend
```

before the capacity decision is made.

This means zCharge can correctly perform:

```text
50%
 ↓
input_suspend = 1
 ↓
charging stops
 ↓
battery falls below 48%
 ↓
input_suspend = 0
 ↓
charging resumes
```

without requiring a new USB connection event.

---

## 6. Charging-switch verification was rewritten

The original implementation used battery current as part of the logic deciding whether the charging switch transition had succeeded.

That introduced unnecessary coupling between:

```text
input_suspend
```

and:

```text
battery/current_now
```

The fork now verifies the transition by reading the actual switch value again.

The sequence is:

```text
write input_suspend
        ↓
wait briefly
        ↓
read input_suspend again
        ↓
confirm requested value
```

`battery/current_now` is still logged for diagnostics, but it is no longer the authority for deciding whether the switch itself changed successfully.

This is important because the Qualcomm charging stack may take a moment to propagate the new state through the power-supply interfaces.

---

## 7. Fast polling is kept only during switch transitions

The normal control loop runs every 60 seconds.

When zCharge actually changes:

```text
input_suspend 0 → 1
```

or:

```text
input_suspend 1 → 0
```

it briefly checks the switch state once per second.

This gives fast confirmation without constantly polling the whole charging subsystem every second.

---

## 8. Temperature controller is decoupled from USB state

The temperature controller also works independently from charger presence.

It monitors:

```text
/sys/class/power_supply/battery/temp
```

and can suspend charging if the configured temperature limit is exceeded.

Temperature recovery is only allowed to re-enable charging while:

```text
capacity < capacity_limit
```

so temperature recovery cannot accidentally bypass the capacity limit.

The current default configuration intentionally uses:

```text
temperature_limit = 800
```

which corresponds to:

```text
80.0°C
```

The phone/kernel charging stack remains responsible for normal thermal charging management.

The zCharge temperature limit is therefore effectively a high-temperature fallback rather than the primary thermal controller.

---

## 9. Current units fixed

Android exposes:

```text
battery/current_now
```

in **microamps (µA)**.

Therefore:

```text
1500000
```

means approximately:

```text
1.5 A
```

and not:

```text
1500 A
```

The fork corrected the log messages accordingly.

---

## 10. Configuration is stored in SQLite

zCharge uses:

```text
/data/adb/zcharge/zcharge.db
```

The default configuration used by this fork is:

```text
enabled                 = 1
capacity_limit          = 50
recharging_limit        = 48
temperature_limit       = 800
charging_switch_path    = /sys/class/qcom-battery/input_suspend
charging_switch_on      = 0
charging_switch_off     = 1
```

The database can be inspected with:

```sh
zcharge --print
```

---

# Usage

```text
Usage: zcharge [OPTIONS] [ARGS...]

Options:

  --print
      Print configuration content

  --convert <old_config> <new_config>
      Convert the old configuration file to the SQLite database format

  --enable [config_db]
      Enable zcharge with the specified database file (or the default)

  --disable [config_db]
      Disable zcharge with the specified database file (or the default)

  --reload
      Tell the running zcharge service to reload the configuration

  --update <key=value> [config_db]
      Update a configuration value

  -h, --help
      Show this help message
```

## Examples

Show current configuration:

```sh
su -c 'zcharge --print'
```

Set the charge limit:

```sh
su -c 'zcharge --update capacity_limit=50'
```

Set the recharge threshold:

```sh
su -c 'zcharge --update recharging_limit=48'
```

Set the high-temperature fallback limit:

```sh
su -c 'zcharge --update temperature_limit=800'
```

Reload the running service after changing the configuration:

```sh
su -c 'zcharge --reload'
```

Enable the limiter:

```sh
su -c 'zcharge --enable'
```

Disable the limiter:

```sh
su -c 'zcharge --disable'
```

---

# Important paths

Main executable:

```text
/system/bin/zcharge
```

Configuration database:

```text
/data/adb/zcharge/zcharge.db
```

PID file:

```text
/data/adb/zcharge/zcharge.pid
```

Log:

```text
/data/adb/zcharge/zcharge.log
```

Charging switch used by this fork:

```text
/sys/class/qcom-battery/input_suspend
```

Battery capacity:

```text
/sys/class/power_supply/battery/capacity
```

Battery temperature:

```text
/sys/class/power_supply/battery/temp
```

Battery current:

```text
/sys/class/power_supply/battery/current_now
```

---

# Repository tools

The repository also contains two small Python utilities.

## `A1_make_configure_sqliteDB.py`

This script prepares the repository SQLite configuration database.

It:

1. creates a backup of the existing `zcharge.db`
2. displays the configuration currently stored in the database
3. inserts missing configuration keys
4. updates existing keys
5. writes the resulting configuration back to SQLite
6. displays the final configuration

The script is intended to make preparation of the database reproducible and avoids manually editing the SQLite file.

The default configuration written by the script should match the configuration expected by this fork:

```text
enabled                 = 1
capacity_limit          = 50
recharging_limit        = 48
temperature_limit       = 800
charging_switch_path    = /sys/class/qcom-battery/input_suspend
charging_switch_on      = 0
charging_switch_off     = 1
```

A backup is created as:

```text
zcharge.db.backup
```

---

## `A2_make_magisk_module.py`

This script packages the repository into:

```text
zcharge-magisk.zip
```

It collects the required Magisk module files, `system/`, `META-INF/`, the SQLite database and other module files into a temporary staging directory and creates the final flashable ZIP.

This avoids manually creating the Magisk package from Windows Explorer and helps prevent accidental omissions or path/layout errors.

---

# Build

The project contains a Makefile and the SQLite amalgamation required for building the binary.

The GitHub Actions workflow builds the project using:

```text
Android NDK 26.3.11579264
```

and the Android AArch64 compiler:

```text
aarch64-linux-android24-clang++
```

The resulting binary is:

```text
ELF 64-bit
ARM aarch64
```

The workflow also checks the SQLite include path explicitly before compiling.

---

# Why this fork exists

The main reason for this fork is not to add another charging feature.

It is to make the existing limiter behave like a simple state machine instead of trying to reconstruct the entire Android charging subsystem.

The intended logic is:

```text
                    battery capacity
                           │
              ┌────────────┴────────────┐
              │                         │
           >= 50%                    < 48%
              │                         │
              ▼                         ▼
      input_suspend = 1         input_suspend = 0
              │                         │
              ▼                         ▼
       charging suspended         charging allowed
```

USB connection state and Android's human-readable charging status are intentionally outside that decision.

That makes the limiter much less sensitive to Qualcomm/Android power-supply state reporting quirks.

---

# Disclaimer

This module writes directly to a kernel charging-control interface:

```text
/sys/class/qcom-battery/input_suspend
```

Behavior depends on the device kernel and power-management implementation.

This fork was developed and tested primarily around a Qualcomm-based device where the above interface is available.

Do not assume that the same charging-switch path exists on other devices.
