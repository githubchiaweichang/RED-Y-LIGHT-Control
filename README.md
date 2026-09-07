# RED.Y-LIGHT Control

A Python-based Bluetooth Low Energy (BLE) RGBW controller for the RED.Y-LIGHT.

This project reverse-engineers the BLE control interface of the RED.Y-LIGHT and provides a standalone desktop application for controlling its RGBW LED channels and hardware effect speed without relying on the original mobile application.

> **Project Status:** Experimental / Reverse-engineered

---

## Features

- Bluetooth Low Energy device discovery
- Automatic discovery of `RED.Y-LIGHT`
- Direct BLE GATT communication
- RGBW color control
- Visual color picker
- Independent R / G / B / W channel control
- Hardware effect speed control
- PC-side breathing animation
- Automatic BLE reconnection
- Fixed-size desktop interface
- Live BLE packet display
- Communication log

---

## Requirements

- Windows
- Python 3.12+
- Bluetooth Low Energy capable adapter
- RED.Y-LIGHT

### Python Dependencies

- `bleak`
- `Pillow`

Install the dependencies:

```bash
pip install bleak pillow
```

---

## Installation

Clone the repository:

```bash
git clone https://github.com/githubchiaweichang/RED-Y-LIGHT-Control.git
```

Enter the project directory:

```bash
cd RED-Y-LIGHT-Control
```

Install the required packages:

```bash
pip install -r requirements.txt
```

Run the controller:

```bash
python redy_rgbw_modern_ui.py
```

The application automatically searches for the BLE device named:

```text
RED.Y-LIGHT
```

The BLE address is not hard-coded because Windows may assign a different BLE address between connections.

---

# BLE Protocol

The RED.Y-LIGHT uses a custom Bluetooth Low Energy GATT interface.

## Device

Device name:

```text
RED.Y-LIGHT
```

Custom service:

```text
00010203-0405-0607-0809-0a0b0c0d1911
```

Write characteristic:

```text
00010203-0405-0607-0809-0a0b0c0d2b19
```

The protocol described below was determined through direct BLE experiments and observation of the physical LED behavior.

---

# RGBW Packet Format

The currently verified control packet is 10 bytes:

```text
01 01 00 00 00 R G B W B10
```

Byte layout:

| Byte | Field | Description |
|------|-------|-------------|
| B1 | `01` | RGBW control mode |
| B2 | `01` | Effect / mode related |
| B3 | `00` | Not fully characterized |
| B4 | `00` | Not fully characterized |
| B5 | `00` | Not fully characterized |
| B6 | `R` | Red channel |
| B7 | `G` | Green channel |
| B8 | `B` | Blue channel |
| B9 | `W` | White channel |
| B10 | `SPEED` | Effect speed |

RGBW channel values use the range:

```text
00 - FF
```

---

# RGBW Channels

The following channel mapping has been experimentally confirmed:

```text
B6 → Red
B7 → Green
B8 → Blue
B9 → White
```

### Red

```text
01 01 00 00 00 FF 00 00 00 00
```

### Green

```text
01 01 00 00 00 00 FF 00 00 00
```

### Blue

```text
01 01 00 00 00 00 00 FF 00 00
```

### White

```text
01 01 00 00 00 00 00 00 FF 00
```

### RGB

```text
01 01 00 00 00 FF FF FF 00 00
```

The white LED channel is independent from the RGB channels.

---

# Effect Speed

`B10` controls the hardware effect speed.

When:

```text
B10 = 00
```

the light produces a solid output rather than a hardware blinking effect.

The current application provides several speed presets:

| Preset | B10 |
|--------|-----|
| Solid | `00` |
| Slow | `20` |
| Medium | `80` |
| Fast | `FF` |

The exact relationship between the complete `00-FF` range and the physical blink frequency has not yet been fully characterized.

---

# PC Breathing Mode

The application includes a software-based breathing animation.

This mode is separate from the RED.Y-LIGHT's built-in hardware effects.

When breathing mode is enabled:

1. The PC generates RGB values continuously.
2. The RGB values are updated over time.
3. BLE packets are sent to the device.
4. `B10` remains `00`.
5. The device displays the generated RGB colors.

Conceptually:

```text
PC
 |
 | RGB animation
 v
RGB values
 |
 | BLE packet
 v
RED.Y-LIGHT
 |
 v
RGBW LEDs
```

This allows smooth color transitions without relying on the device's built-in effect timing.

---

# Connection Architecture

The application uses Python, Tkinter, asyncio, and Bleak.

```text
Tkinter UI
     |
     v
Application Logic
     |
     v
Async BLE Layer
     |
     v
Bleak
     |
     v
Windows Bluetooth
     |
     v
RED.Y-LIGHT
```

The device is discovered by name rather than by a fixed MAC address.

This is important because BLE addresses may change between scans or connections.

---

# Reconnection

The application supports BLE reconnection.

When the connection is lost:

1. The current connection is detected as unavailable.
2. The application searches for `RED.Y-LIGHT` again.
3. A new BLE connection is established.
4. The requested command is sent.

The application avoids unnecessarily sending duplicate commands.

---

# Reverse Engineering

The BLE protocol was discovered experimentally using direct communication with the device.

The investigation included:

- GATT service enumeration
- Characteristic discovery
- Characteristic property inspection
- Reading available characteristics
- Identifying writable characteristics
- Testing packet lengths
- Testing individual byte positions
- Testing RGB channel combinations
- Testing the independent white channel
- Testing effect speed
- Observing persistent LED behavior

The main experimentally verified packet structure is:

```text
01 01 00 00 00 R G B W B10
```

The RGBW channel mapping is:

```text
B6 → Red
B7 → Green
B8 → Blue
B9 → White
```

The effect speed field is:

```text
B10 → Effect speed
```

---

# Protocol Status

| Component | Status |
|-----------|--------|
| Device name | Confirmed |
| BLE write characteristic | Confirmed |
| 10-byte packet | Confirmed |
| B1 = `01` | Confirmed experimentally |
| B6 = Red | Confirmed |
| B7 = Green | Confirmed |
| B8 = Blue | Confirmed |
| B9 = White | Confirmed |
| B10 = Effect speed | Confirmed experimentally |
| B10 = `00` → solid output | Confirmed |
| B2 behavior | Partially characterized |
| B3 behavior | Under investigation |
| B4 behavior | Under investigation |
| B5 behavior | Under investigation |
| Exact B10 frequency curve | Under investigation |

The protocol should therefore be considered empirically derived rather than officially documented.

---

# Known Unknowns

Several packet fields have not yet been fully reverse-engineered.

In particular:

```text
B2
B3
B4
B5
```

may affect lighting modes, effects, or other device behavior.

Further experimentation is required before assigning definitive meanings to these fields.

---

# Limitations

This project currently targets the RED.Y-LIGHT device used during the reverse-engineering process.

Compatibility with the following is not guaranteed:

- Other RED.Y-LIGHT hardware revisions
- Different firmware versions
- Other products using similar BLE UUIDs
- Future firmware updates

The protocol may vary between hardware or firmware revisions.

---

# Disclaimer

This project is an independent reverse-engineering effort.

It is not affiliated with, endorsed by, or sponsored by RED.Y or the manufacturer of the RED.Y-LIGHT.

The protocol documentation is based on experimental observations and may be incomplete or inaccurate.

Use this software at your own risk.

---

# Contributing

Contributions are welcome.

Useful contributions include:

- Additional BLE protocol discoveries
- Reproducible packet experiments
- Support for additional hardware revisions
- Improved BLE reliability
- New lighting effects
- UI improvements
- Documentation improvements

When reporting a protocol discovery, please provide:

1. The complete BLE packet
2. The observed physical behavior
3. Whether the behavior is reproducible
4. Device firmware information, if available
5. Relevant BLE logs

This helps distinguish confirmed behavior from experimental results.

---

# License

This project is licensed under the MIT License.

See [`LICENSE`](LICENSE) for details.