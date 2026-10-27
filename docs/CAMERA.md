# Camera, browser audio and Home Assistant

Platina Linux **0.8.1** provides a headless rear-camera service on the tested
Xiaomi Mi 8 Lite with an IMX363 sensor and DW9714 focus actuator. It runs with
the display dark. This is development software, qualified on one device.

## What is available

- Live MJPEG and snapshots, using an isolated Freedreno GPU software ISP.
- Six output sizes: 12, 5.4, 3, 1.3, 0.75 and 0.33 megapixels. At 1× zoom,
  changing output resolution retains the full sensor field of view.
- Centered digital zoom **1–10×**, applied before the shared JPEG output.
  A zoom change in the web UI therefore also changes the Home Assistant image.
  Output dimensions stay constant; digital enlargement cannot restore detail.
- Manual focus and JPEG quality 10–95. The capture target is fixed at 30 FPS;
  actual delivered FPS depend on resolution, scene and processing capacity.
- Automatic/manual exposure, requested exposure time 100–100000 microseconds
  and analogue gain 1–8×. The sensor clamps time/gain to its configured limits.
  Actual exposure time and gain are reported separately from requested values.
- Automatic/manual white balance, gamma, contrast, saturation and rotation.
- Optional live browser microphone listening, mono PCM16 at 48 kHz, with local
  volume control. Audio is a separate stream and is not synchronized with MJPEG.

## Compact web UI

Open `http://platina.local:8082/`, or use your phone's own network address.
The main panel contains zoom, focus, JPEG quality, resolution and audio controls.
The **Advanced / Pokročilé** dialog has tabs for exposure, white balance, and
colors/orientation. Values apply live; Save and Restore saved include advanced
settings. Existing complete settings files are migrated without resetting them.

The header shows actual FPS, dimensions and the restored processing-time label.
That millisecond value is **frame age since the sensor timestamp at status-read
time**, including waiting/processing; it is not an isolated JPEG encode time or
an end-to-end browser latency measurement. The compact layout and dialogs were
checked without page scrolling at desktop, phone and landscape viewport sizes.

Camera capture is **OFF after each service/system startup**. Loading the page,
snapshot or MJPEG URL does not enable capture. Stop releases capture and focus,
removes the last frame, and lets the sensor/lens suspend. Audio also requires an
explicit action, allows one listener and stops when the page is hidden/closed.
It does not record sound to disk.

The service listens on all interfaces and has no account/password login. Use a
trusted network or an authenticated proxy/VPN; do not expose its port directly
to the Internet. The short-lived audio ticket is an activation mechanism,
not user authentication.

## Home Assistant

Configure MQTT locally on the phone in `/etc/platina-camera/mqtt.json`, owned by
root with mode `0600`. Supply your own broker credentials; no maintainer settings
are included. The expected JSON keys are `host`, optional `port`, `username`,
`password`, `topic`, `device_id` and `web_url`. Use a unique device ID and topic.
The optional `py3-paho-mqtt` dependency is installed by the camera package.

MQTT Discovery publishes camera enable/disable, image settings, digital zoom,
actual FPS and exposure telemetry. Commands retained by the broker are ignored
so they cannot restart capture after a reconnect. MQTT setting changes are
saved automatically; the web UI retains its explicit Save action. The legacy
target-FPS setting is normalized to 30 and has no web slider.

Add Home Assistant's **MJPEG IP Camera** integration using your own phone's URLs:

- MJPEG: `http://platina.local:8082/stream.mjpg`
- Still image: `http://platina.local:8082/snapshot.jpg`

The HA host must resolve that name, or you can use the phone's own reserved
address. Both URLs use the same already-processed image, including zoom. They
return HTTP 503 while capture is OFF. Use the discovered camera switch to enable
capture explicitly. No dashboard, HA token or broker password is bundled.

**The existing HA MJPEG camera has no audio.** Browser PCM listening does not
add an audio track to that entity. A shared H.264/AAC or WebRTC path would require
additional encoding, timing and playback work. It is deferred in this release;
there is no continuously running transcoder or dependency on an external server.

## Source build and installation boundary

The camera packages are separate from the base image recipe. After preparing
your own candidate environment as described in [BUILDING.md](BUILDING.md):

```sh
python3 scripts/build-camera-userspace.py --component mesa --lax
python3 scripts/build-camera-userspace.py --component userspace --lax
```

This builds isolated Mesa/Freedreno 26.1.6 and `platina-libcamera` 0.7.1-r31.
The latter includes the camera consumer, HTTP/MQTT controller, UI, OpenRC service
and the active libcamera patches. Neither command connects to a phone. These
packages are not automatically installed by `make images`.

Before any installation, qualify a matching camera-enabled kernel and modules,
the IMX363/CCI/CAMSS media graph and DW9714 actuator on your own device. A
display-only kernel is insufficient. The source kernel candidate is 7.2.12-r12;
the tested installation instead uses the separately tested r9 boot and r11 sensor
module runtime combination. **The combined r12 kernel and a new full 0.8.1 image
have not passed a complete hardware installation test.** Do not replace a
working boot/modules set merely to install the camera userspace.

Install only your own signed camera/Mesa packages with your matching APK public
key, preserving existing configuration and rollback packages. On a qualified
installation the service can be enabled/started with:

```sh
sudo rc-update add platina-camera default
sudo rc-service platina-camera start
```

Starting this service exposes controls and MQTT; capture remains OFF. Review
logs in `/var/log/platina-camera.log` and enable capture through the web or MQTT.
The service currently runs as root for device/mixer access; privilege reduction
has not been qualified. Generic building steps are not permission to flash
another device or reuse another phone's calibration/firmware/configuration.

## Validation and remaining limits

The existing phone received signed 0.7.1-r31 userspace and integration 0.8.1.
Runtime files matched the built package; its existing boot and system boot ID
were preserved. Zoom 10× and decoded 2008×2680 MJPEG were exercised through the
live browser. Compact controls, advanced tabs, save/restore, MQTT Discovery and
the exposure control interface were checked. The 0.8.1 header change was tested
with synthetic frame metadata while keeping the phone's capture OFF.

Browser audio data/lifecycle and short audio/video coexistence tests passed.
These do not establish subjective microphone quality, synchronized A/V, precise
power cost, or long-term capture reliability. The exposure response, color/zoom
quality and microphone quality still need broader physical qualification.
Short samples around 14–15 FPS are observations, not guaranteed performance.

Venus H.264 experiments previously encountered firmware/kernel failures and are
not a working encoder path. Do not enable the block based solely on a compiled
driver or the partial legacy-transform patch in the development kernel recipe.
Front/secondary cameras, autofocus and full camera ISP tuning are not qualified.

Sources and attribution: [NOTICE](../NOTICE),
[licensing](LICENSING.md), [HA MJPEG](https://www.home-assistant.io/integrations/mjpeg/)
and [HA Stream](https://www.home-assistant.io/integrations/stream/).
