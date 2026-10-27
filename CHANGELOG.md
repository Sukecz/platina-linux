# Changelog

## 0.8.1 — 2026-10-27, compact camera release

- Restore the millisecond processing label in the compact live header. Its value
  is frame age at status-read time, not isolated JPEG time or browser latency.
- Signed camera userspace 0.7.1-r31 and integration 0.8.1 were checked on the
  existing phone; boot and settings were preserved. Publish source, not binaries.
- Includes the camera/audio/control features below, plus build recipes, regression
  tests, source attribution and updated installation/qualification documentation.

## 0.8.0 — compact controls and 10× zoom

- Digital zoom 1–10× in the shared web/HA JPEG pipeline.
- Keep zoom, focus, JPEG, resolution and audio in the compact main panel. Put
  exposure, white balance, colors and rotation in a tabbed Advanced dialog.
- Remove the target-FPS slider and fix the capture target at 30; actual output
  rates remain dependent on scene, resolution and processing capacity.
- Remove verbose audio hints. Desktop/mobile page and dialog geometry were
  checked without scrolling; live browser checked 10× MJPEG at 2008×2680.

## 0.7.0 — shared digital zoom

- Centered GPU input crop before debayering/scaling, with a CPU ARGB fallback.
- Live web/API/MQTT control and settings migration; output dimensions unchanged.
- Zoom applies to snapshots and the same MJPEG used by Home Assistant.

## 0.6.0 — exposure controls

- Expose auto/manual sensor time and analogue gain through Simple IPA, web/API
  and MQTT. Report actual sensor metadata separately from requested settings.
- Bound requests to configured sensor limits and preserve complete older configs.
- Broader physical exposure-response and image-quality qualification is pending.

## 0.5.0 — optional browser microphone

- Explicit ON/OFF mono PCM16 48 kHz browser listening and local volume control.
- Single-listener lifecycle, mixer restore and cleanup on disconnect/page exit.
- Audio is separate from MJPEG; no synchronized A/V or audio in the HA camera.

## 0.4.1 — JPEG range

- Extend JPEG quality to 10–95. Lower quality reduced bytes in short tests;
  it did not establish a meaningful overall FPS improvement.

## 0.4.0 — camera and Home Assistant

- IMX363 rear camera with DW9714 focus, full-field GPU MJPEG and six output sizes.
- OFF-by-default OpenRC controls, explicit capture ON/OFF, live settings and
  MQTT Discovery for Home Assistant. Image requests do not start capture.
- Existing installation boot/restart and HA image/control paths were tested.
- H.264/Venus development is not a working encoding feature and remains deferred.


## 0.3.1 — fresh-image integration

- New local images include versioned boot and shutdown screens, display helpers,
  the headless boot hook and the enabled OpenRC shutdown-button service.
- Image audits verify decoded screens, file hashes, permissions and service links.
- Exported boot images automatically receive module indexes matching the actual
  initramfs contents; the final boot/rootfs pair is audited before build success.
- A full local image passed offline audits. The existing installation was updated
  in place to 0.3.1: screen preview, normal restart, runtime checksums, SSH and
  service autostart passed. The new full installation image was not flashed.

## 0.3.0 — verified shutdown buttons and screen

- Hold Power + Volume Up for three seconds and release both for orderly shutdown.
- Show the Platina logo, release version and Power off screen during shutdown.
- Preview, button handling and shutdown on battery were physically verified.
- Disconnect USB/the charger first to remain powered off. Attached power triggers
  a charger-mode boot and starts Linux again; this remains an accepted limitation.
- No experimental PMIC trigger changes are included in new images.

## 0.2.0 — verified integrated display

- Kernel 7.2.12-r1 integrates the Platina Tianma NT36672A panel and device tree.
- RAM boot, normal eMMC boot, logo, brightness and ten display off/on cycles passed
  physical testing. VSP/VSN full rail shutdown and power savings remain unproven.
- Display on/off/brightness/status, timed images and host-side image preparation.

## 0.1.1 — historical integration

- Headless postmarketOS from eMMC with key-only SSH over Wi-Fi or USB networking.
- NetworkManager reconnect and OpenRC autostart; corrected initramfs indexes.
- Seven-second boot logo using a temporary LCD helper, now superseded on the
  tested Tianma phone by the integrated driver.

The integration version is separate from the kernel and distribution versions.
