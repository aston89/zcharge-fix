# zcharge-fix

A bug-fix fork of [lululoid/zcharge](https://github.com/lululoid/zcharge), a small Android/Qualcomm charging limiter written in C++.

The original project already provides the core idea: limit battery charging to a configured capacity and control charging through a kernel charging-switch interface.

This fork focuses on fixing the charging-state logic on Qualcomm devices and reducing unnecessary background polling.

> **Target:** Qualcomm / Android devices using `/sys/class/qcom-battery/input_suspend`.

---

## What changed

### 1. Main polling loop: 1 second → 60 seconds

The original implementation runs its main monitoring loop once every second.

For a charging-capacity limiter this is unnecessarily aggressive: battery percentage does not need to be polled every second, and constantly waking a background process is pointless overhead.

The fork changes the normal monitoring interval to:

```cpp
constexpr int MAIN_LOOP_INTERVAL_SECONDS = 60;
```

Normal battery/USB monitoring therefore happens once per minute.

The 1-second interval is **not completely removed**: it is still used while confirming an actual charging-switch transition.

This gives us:

```text
normal monitoring
        ↓
      every 60 s

charging ON/OFF transition
        ↓
   verify every 1 s
```

The idea is simple: sleep most of the time, react quickly only when a charging state is actively being changed.

---

### 2. USB presence is now detected from `usb/online`

The original logic inferred charger presence from:

```text
/sys/class/power_supply/battery/status
```

This is problematic on Qualcomm devices when charging is suspended through:

```text
/sys/class/qcom-battery/input_suspend
```

With:

```text
input_suspend = 1
```

the battery can report:

```text
Discharging
```

even though the USB cable is still physically connected and the USB power source is still present.

That confused the original state machine.

The fork therefore reads:

```text
/sys/class/power_supply/usb/online
```

instead.

Conceptually:

```text
USB cable physically present
        ↓
usb/online = 1
```

is now the definition of **charger present**.

This is independent of whether charging is currently suspended.

---

### 3. `battery/status` is no longer used to decide whether current is flowing

The original implementation combined the Android battery status with the charging-switch state to determine whether charging was actually occurring.

That becomes unreliable once `input_suspend` is involved.

The fork instead uses the actual battery current:

```text
/sys/class/power_supply/battery/current_now
```

The relevant distinction is:

```text
current_now < 0
    ↓
current is flowing into the battery
    ↓
charging

current_now >= 0
    ↓
battery is not being charged
```

This makes the charging decision based on the electrical state reported by the power-supply driver rather than on the higher-level `battery/status` string.

---

### 4. Recharging hysteresis was fixed

The intended behaviour of the limiter is:

```text
50%
 ↓
stop charging
 ↓
battery falls
 ↓
48%
 ↓
resume charging
```

The original state machine could fail here because after `input_suspend` was enabled the battery could report `Discharging`, causing the software to interpret the situation as if the charger had disappeared.

The fork separates:

```text
"Is a USB charger connected?"
```

from:

```text
"Is the battery currently being charged?"
```

so the system can remain:

```text
usb/online = 1
input_suspend = 1
battery/status = Discharging
```

while correctly understanding that the charger is still connected and charging can later be resumed.

---

### 5. Capacity recovery no longer depends on `battery/status`

Once charging has been suspended, the battery may legitimately report `Discharging`.

Therefore the recharge condition is based on:

```text
USB charger present
+
capacity below recharging_limit
+
charging switch currently OFF
```

rather than requiring Android to report `Charging`.

This allows the intended hysteresis loop to work even while `input_suspend=1`.

---

### 6. Temperature recovery cannot bypass the capacity limit

The original logic had two independent controllers:

```text
capacity controller
temperature controller
```

That creates a possible interaction where the temperature controller can decide to re-enable charging after a thermal cooldown even though the battery is already at the configured capacity limit.

The fork prevents that.

Temperature-based recovery is allowed only when:

```text
capacity < capacity_limit
```

In other words:

```text
temperature recovered
        +
battery still below charge limit
        ↓
charging may resume
```

but:

```text
temperature recovered
        +
battery already at/above capacity limit
        ↓
charging stays suspended
```

---

### 7. Charging-switch confirmation was rewritten

The kernel switch used by this fork is:

```text
/sys/class/qcom-battery/input_suspend
```

with:

```text
0 = charging enabled
1 = charging suspended
```

After changing that value, the program does not blindly assume that the hardware state has already followed the write.

The transition is verified using actual battery current.

That is important because:

```text
software switch state
```

and:

```text
actual current flow
```

are not necessarily updated at exactly the same instant.

The fork therefore treats the actual current as the useful confirmation signal.

---

### 8. Current logging units were corrected

Android exposes:

```text
battery/current_now
```

in microamps (`µA`).

Therefore:

```text
1503000
```

means approximately:

```text
1.503 A
```

and not:

```text
1503 A
```

The fork corrected the log messages accordingly.

---

## Default configuration

The included database is configured for the following defaults:

```text
enabled = 1
capacity_limit = 50
recharging_limit = 48

temperature_limit = 800

charging_switch_path = /sys/class/qcom-battery/input_suspend
charging_switch_on = 0
charging_switch_off = 1
```

### Capacity limits

The normal charging cycle is:

```text
battery reaches 50%
        ↓
charging suspended

battery falls below 48%
        ↓
charging resumed
```

The two values intentionally provide hysteresis so that charging does not repeatedly toggle around one exact percentage.

### Temperature limit

The fork leaves temperature protection effectively to the Android/kernel charging stack rather than using zcharge as the primary thermal controller.

For this reason the bundled configuration uses:

```text
temperature_limit = 800
```

which corresponds to 80.0°C in zcharge's own unit convention and effectively keeps zcharge from becoming the active low-temperature thermal limiter.

The intention is to avoid duplicating or fighting the device's native Qualcomm/Android thermal charging management.

---

## Qualcomm charging switch

This fork is specifically built around:

```text
/sys/class/qcom-battery/input_suspend
```

The bundled configuration uses:

```text
charging_switch_on = 0
charging_switch_off = 1
```

Therefore:

```text
0 → allow charging
1 → suspend battery charging
```

The exact semantics are device/kernel dependent, so the module should not be assumed to work unchanged on unrelated hardware.

---

## Repository structure

The repository contains both the original project components and the additional tooling used by this fork.

```text
zcharge-fix/
│
├── .github/
│   └── workflows/
│       └── build.yml
│
├── MAGISK_MODULE/
│   ├── readme.md
│   └── zcharge-magisk-module.zip
│
├── META-INF/
│   └── com/google/android/
│
├── sqlite-amalgamation/
│   ├── sqlite3.c
│   ├── sqlite3.h
│   └── ...
│
├── system/
│   └── bin/
│       ├── zcharge
│       └── zcharge.cpp
│
├── A1_make_configure_sqliteDB.py
├── A2_make_magisk_module.py
├── Makefile
├── README.md
├── build.sh
├── customize.sh
├── module.prop
├── service.sh
├── tools.sh
└── zcharge.db
```

---

## Source code

The main program is:

```text
system/bin/zcharge.cpp
```

The compiled executable is:

```text
system/bin/zcharge
```

SQLite is bundled directly into the repository using the SQLite amalgamation:

```text
sqlite-amalgamation/libsqlite3.a
```

The Makefile links that static SQLite library into the executable.

---

## Build system

The original project includes a shell build script and Makefile.

The repository Makefile:

* builds `system/bin/zcharge`
* links the bundled SQLite amalgamation
* links Android `liblog`
* expects an Android ARM64 toolchain
* verifies that the required `libc++_shared.so` is available.

The original `build.sh` also handles version/versionCode updates and packaging through `7za`.

For this fork, compilation is performed through GitHub Actions so a local Android NDK installation is not required.

---

## GitHub Actions build

The workflow is:

```text
.github/workflows/build.yml
```

It currently:

1. checks out the repository
2. installs Java 17
3. installs the required host build tools
4. installs Android NDK 26.3.11579264
5. prepares the ARM64 Android toolchain
6. provides the required `libc++_shared.so`
7. invokes `make` using the Android ARM64 compiler
8. adds the SQLite include path
9. verifies the resulting ELF
10. uploads the compiled binary as a GitHub Actions artifact.

The compiler target is:

```text
aarch64-linux-android24
```

and the resulting executable is verified as:

```text
ELF 64-bit
ARM aarch64
PIE executable
```

---

## Windows / source-file handling

Part of the reason for keeping the build pipeline explicit is that the source tree is also edited and maintained from Windows.

When source files are copied or modified through Windows tooling, line endings and file representation can occasionally introduce confusing build failures.

The practical approach used in this project is:

```text
edit / copy source
        ↓
keep the repository as the source of truth
        ↓
compile on a clean Linux runner
```

The GitHub Actions runner therefore provides a reproducible Linux build environment instead of relying on whatever compiler/runtime happens to be installed on the Windows machine.

This is also why the build process is kept separate from the Magisk packaging step.

---

## SQLite configuration helper

`A1_make_configure_sqliteDB.py` prepares the bundled:

```text
zcharge.db
```

The script:

* checks that the database exists
* creates a backup as `zcharge.db.backup`
* prints the existing configuration
* updates the expected configuration keys
* inserts a key if it does not already exist
* commits the SQLite transaction
* prints the resulting configuration.

The current defaults applied by the script are:

```text
enabled = 1
capacity_limit = 50
recharging_limit = 48
temperature_limit = 800
charging_switch_path = /sys/class/qcom-battery/input_suspend
charging_switch_on = 0
charging_switch_off = 1
```

This lets the database be rebuilt/configured without manually editing SQLite data.

---

## Magisk packaging helper

`A2_make_magisk_module.py` builds:

```text
zcharge-magisk.zip
```

The script creates a temporary staging directory, copies the module files and `system/` tree into it, creates the ZIP, and removes the staging directory afterwards.

The packaged components include:

```text
module.prop
customize.sh
service.sh
tools.sh
zcharge.db
system/
META-INF/
```

Missing optional files are skipped rather than causing the entire packaging operation to fail.

---

## Runtime service

`service.sh` starts the zcharge executable through Magisk's service mechanism and redirects its output into the zcharge log environment. It also starts a filtered `logcat` stream for the `zcharge` tag.

The runtime files are stored under:

```text
/data/adb/zcharge/
```

including:

```text
/data/adb/zcharge/zcharge.db
/data/adb/zcharge/zcharge.log
/data/adb/zcharge/zcharge.pid
```

---

## Runtime configuration

The zcharge binary provides the following command-line operations:

```text
zcharge [OPTIONS] [ARGS...]

Options:

  --print
      Print configuration.

  --convert <old_config> <new_config>
      Convert an old configuration file to the SQLite format.

  --enable [config_db]
      Enable zcharge and start the service.

  --disable [config_db]
      Disable zcharge.

  --reload
      Tell the running zcharge process to reload its configuration.

  --update <key=value> [config_db]
      Update a configuration value.

  -h, --help
      Show help.
```

The command set comes from the upstream zcharge interface and remains available in this fork.

---

## Example commands

Print the active configuration:

```sh
su -c '/data/adb/modules/zcharge/system/bin/zcharge --print'
```

Reload configuration after changing the database:

```sh
su -c '/data/adb/modules/zcharge/system/bin/zcharge --reload'
```

Update a configuration value:

```sh
su -c '/data/adb/modules/zcharge/system/bin/zcharge --update capacity_limit=50'
```

Disable zcharge:

```sh
su -c '/data/adb/modules/zcharge/system/bin/zcharge --disable'
```

Enable zcharge:

```sh
su -c '/data/adb/modules/zcharge/system/bin/zcharge --enable'
```

---

## Useful runtime checks

USB charger presence:

```sh
su -c 'cat /sys/class/power_supply/usb/online'
```

USB current:

```sh
su -c 'cat /sys/class/power_supply/usb/current_now'
```

Battery current:

```sh
su -c 'cat /sys/class/power_supply/battery/current_now'
```

Battery temperature:

```sh
su -c 'cat /sys/class/power_supply/battery/temp'
```

Battery status:

```sh
su -c 'cat /sys/class/power_supply/battery/status'
```

Charging switch:

```sh
su -c 'cat /sys/class/qcom-battery/input_suspend'
```

Running zcharge process:

```sh
su -c 'pgrep -af zcharge'
```

Recent zcharge log:

```sh
su -c 'tail -30 /data/adb/zcharge/zcharge.log'
```

---

## Expected charging states

With a charger physically connected and normal charging:

```text
usb/online       = 1
input_suspend    = 0
battery/status   = Charging
battery/current  < 0
```

After reaching the configured capacity limit:

```text
usb/online       = 1
input_suspend    = 1
battery/status   = Discharging
battery/current  >= 0
```

The important point is that the second state does **not** mean that the USB charger was unplugged.

It means:

```text
USB still connected
        +
charging intentionally suspended
```

This distinction is the main reason for the charging-state rewrite in this fork.

---

## Current flow example

A typical charging measurement may look like:

```text
usb/current_now     = 1503000
battery/current_now = -1253069
```

which is approximately:

```text
USB input       ≈ 1.50 A
battery charge  ≈ 1.25 A
```

The remaining input power is consumed by the phone itself and by conversion losses, so the two current readings are not expected to be identical.

---

## Scope of this fork

This fork does **not** attempt to redesign Android's entire charging stack.

The goal is narrower:

```text
keep the original zcharge concept
            +
fix Qualcomm charging-state behaviour
            +
remove pointless 1 Hz polling
            +
keep charging-limit hysteresis reliable
```

The device's own charging, thermal and power-management systems remain responsible for their normal hardware protections.

---

## Prebuilt module

A prebuilt Magisk package is also kept under:

```text
MAGISK_MODULE/
```

for convenience.

For development, the preferred path is to build the current source rather than assuming that the prebuilt ZIP corresponds to the latest commit.

---

## Credits

Original project:

**lululoid/zcharge**

This repository is a fork containing device-specific fixes and build/configuration tooling.

Original project description:

> Simple module to limit charging capacity.

The upstream project was written as a small C++ experiment and uses SQLite for persistent configuration. The fork keeps that architecture while changing the parts that proved unreliable on the target Qualcomm environment.

---

## Disclaimer

This module writes directly to kernel power-supply interfaces and is intended for rooted Android devices.

The exact behaviour of:

```text
/sys/class/qcom-battery/input_suspend
```

depends on the device kernel and vendor charging implementation.

Do not assume that the same switch semantics or power-supply paths exist on unrelated devices.

Always verify the relevant `/sys/class/power_supply/` and Qualcomm charging interfaces on the target device before deploying the module.

---

## License / upstream history

This repository is derived from the upstream:

```text
https://github.com/lululoid/zcharge
```

See the upstream project and repository history for the original implementation and licensing information.

```
```
