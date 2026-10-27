<p align="center">
  <img src="project/branding/platina-linux-logo.png" alt="Platina Linux — Xiaomi Mi 8 Lite headless Linux server" width="300" />
</p>

# Platina Linux for Xiaomi Mi 8 Lite

Turn a **Xiaomi Mi 8 Lite (platina, M1808D2TG, Snapdragon 660 / SDM660)** into
an ARM64 **headless Linux server** with Wi-Fi, USB networking and key-only SSH.
Built on postmarketOS and Alpine Linux, it boots directly from eMMC.

[![Source checks](https://github.com/Sukecz/platina-linux/actions/workflows/check.yml/badge.svg)](https://github.com/Sukecz/platina-linux/actions/workflows/check.yml)
[![License: GPL v2](https://img.shields.io/badge/License-GPL_v2-blue.svg)](LICENSE)
[![Device: Xiaomi Mi 8 Lite](https://img.shields.io/badge/device-Xiaomi_Mi_8_Lite-ff6900)](docs/HARDWARE.md)

**Integration: 0.8.1 · Development / early hardware testing · Source-only release**

The existing test phone runs 0.8.1 with a rear-camera MJPEG stream, optional
browser microphone listening, compact controls and digital zoom up to 10×.
Capture is OFF after startup. This is a tested existing-installation update,
not a fully qualified new installation image or a complete smartphone OS.

[Installation](docs/INSTALLATION.md) · [Build](docs/BUILDING.md)
· [Camera, audio and Home Assistant](docs/CAMERA.md)
· [Display](docs/DISPLAY.md) · [Shutdown](docs/SHUTDOWN.md)
· [Changelog](CHANGELOG.md) · [Releases](https://github.com/Sukecz/platina-linux/releases)

## Camera and compact controls

The main web panel contains **zoom, focus, JPEG quality, resolution and audio**.
Exposure, white balance, colors and orientation are in the **Advanced / Pokročilé**
dialog. Desktop and mobile layouts were checked without page scrolling.
The header shows actual FPS, resolution and a millisecond processing label
(frame age since the sensor timestamp, including waiting/processing).

- **Digital zoom 1–10×:** a centered crop in the shared image pipeline, so a web
  zoom change also appears in the Home Assistant image. Resolution stays fixed;
  digital zoom cannot add missing detail.
- **Six output sizes:** 12, 5.4, 3, 1.3, 0.75 and 0.33 MP. At 1× zoom they retain
  the full sensor field of view. JPEG quality ranges from 10 to 95.
- **Exposure and white balance:** automatic/manual modes, live sensor time/gain
  telemetry, manual focus and color controls. The capture target is fixed at
  30 FPS; observed output rates depend on scene, resolution and processing load.
- **Browser audio:** explicit microphone ON/OFF and volume control. Audio and
  MJPEG remain separate and are not precisely synchronized.
- **Home Assistant:** MQTT Discovery controls and a shared MJPEG/snapshot output.
  The current HA MJPEG camera **does not carry audio**. A unified A/V stream is
  deferred; no always-on transcoder or external server is required by this release.

Open `http://platina.local:8082/` on your own qualified installation.
The service has no user login: keep it on a trusted network or behind an
appropriate authenticated proxy/VPN. See the [camera guide](docs/CAMERA.md)
for source builds, credentials, startup policy and qualification limits.

## Feature status

Last reviewed **2026-10-27**, on the maintainer's Tianma Mi 8 Lite.
🟢 Verified · 🟠 Partial / awaiting qualification · 🔴 Unsupported / not working

| Feature | Status | Evidence and limits |
|---|:---:|---|
| Linux boot from eMMC, ARM64 Alpine and OpenRC | 🟢 | Normal starts and repeated restarts |
| Key-only SSH over Wi-Fi and USB networking | 🟢 | Administrator login; password/root SSH login disabled |
| Wi-Fi reconnect, USB recovery and mDNS | 🟢 | Tested recovery paths and local hostname |
| eMMC / ext4 and battery operation | 🟢 | Installed system and physically disconnected data USB operation |
| Separate charger operation | 🟢 | Short physical charging/operation tests |
| Battery / CPU / GPU thermal telemetry | 🟢 | Readings available; state-of-charge accuracy and low-battery policy need work |
| Tianma NT36672A display | 🟢 | Boot logo, brightness and ten off/on cycles tested |
| Full display power removal | 🟠 | VSP/VSN remain fixed always-on; full rail shutdown/power savings unproven |
| Power + Volume Up shutdown | 🟢 | Hold both 3 seconds, release both; physical battery shutdown tested |
| Staying off with USB/charger attached | 🔴 | Disconnect external power before shutdown; charger boot starts Linux again |
| Rear camera, web controls and HA MJPEG | 🟠 | Live 2008×2680 MJPEG/zoom/UI checked; color, exposure response and long-term qualification remain limited |
| Browser microphone | 🟠 | PCM playback/lifecycle checked; subjective quality and synchronized A/V not qualified |
| H.264 / shared video and audio in HA | 🔴 | Deferred; Venus is not a working hardware encoder path |
| Continuous 48–72-hour operation / sustained power balance | 🟠 | Qualification pending; short tests are not a soak test |
| Off-site VPN access | 🟠 | Local jump route checked; real off-site client test pending |
| CPU frequency scaling | 🟠 | No supported full DVFS claim |
| Bluetooth and SD card | 🟠 | Not functionally qualified |
| Touchscreen on this device | 🔴 | Controller initialization fails |
| Mobile calls/data and Android apps | 🔴 | Outside this headless integration |

## Build and installation boundaries

The tested camera installation uses **kernel 7.2.12-sdm660, r9 boot plus r11
sensor module**, with signed `platina-libcamera` **0.7.1-r31** and isolated Mesa
26.1.6. The checked-in kernel recipe is the **7.2.12-r12 development candidate**,
with device 5-r31 and the public source firmware recipe 2-r5. That combined kernel
and a new full 0.8.1 image have **not** passed a complete hardware installation test.
Camera packages are built/installed separately; `make images` does not yet add them.

No prebuilt APKs, boot/rootfs images, proprietary firmware or calibration data
are published. Provide your own administrator public key and matching firmware,
retain a verified recovery path, and qualify each new kernel/image on your device.
Initial installation erases Android user data. See [installation](docs/INSTALLATION.md)
and [building](docs/BUILDING.md) before any flash.

```sh
git clone https://github.com/Sukecz/platina-linux.git
cd platina-linux
make doctor
make check
```

To stay powered off, **disconnect USB/the charger**, hold **Power + Volume Up
for at least 3 seconds**, then release both. Attached power triggers a charger-mode
boot; this accepted limitation is not changed by the camera release.

Only **Mi 8 Lite / platina** and the tested **Tianma NT36672A** panel are qualified
here. Other Mi 8 models and BOE panel variants need their own integration/tests.
Integration versions are separate from kernel and Alpine package versions.

## Credits and license

Built on [postmarketOS](https://postmarketos.org/), [Alpine Linux](https://alpinelinux.org/),
[SDM660 mainline](https://github.com/sdm660-mainline/linux),
[libcamera](https://libcamera.org/), [Mesa](https://mesa3d.org/) and the
[community Mi 8 Lite port](https://github.com/macosmojave2-alt/postmarket-mi8lite-platina).
Xiaomi's published kernel sources provide device/panel reference data.
Original authors, SPDX declarations and upstream notices are retained.

Original integration contributions are **GPL-2.0-only** unless marked otherwise;
libcamera-derived code and helpers retain their LGPL terms. Firmware remains
proprietary and is not included. See [LICENSE](LICENSE), [NOTICE](NOTICE) and
[licensing](docs/LICENSING.md).
