# Platina display support

The tested Mi 8 Lite has a **Tianma NT36672A 1080 × 2280** panel. Display support
has two separate states:

| State | Status |
|---|---|
| Integration 0.1.1 logo with a temporary LCD power/wake helper | 🟢 Physically verified, including automatic start and subsequent backlight shutdown |
| Integrated driver / DT in kernel 7.2.12-r1 | 🟠 Compiled and audited offline; physical boot and power cycles pending |

The candidate is in `ports/candidate/linux-postmarketos-qcom-sdm660/0030-platina-tianma-panel.patch`.
It adds the panel-specific command sequence, correct regulator names, reset timing,
DT binding and initialization-error cleanup to the NT36672A driver. The stock
command sequence is recorded in `project/display/tianma-reference.json` and
compared by offline tests. This is not a verified BOE TD4320 configuration.

## Optional controller setup

After testing a successful boot with the integrated driver, install the renderer
and controller on **your phone**. The files listed below are source files from
this repository; transfer them using your own authenticated SSH connection.

```sh
# On the phone, from the directory to which you transferred these scripts:
sudo install -m755 phone-splash.py /usr/local/sbin/platina-splash
sudo install -m755 phone-display.py /usr/local/sbin/platina-display
```

For the logo, run `make splash` on the build host. Transfer its three runtime files
`release.json`, `version` and `frame.bgrx.gz` from `artifacts/platina-linux-0.1.1/`
into a new phone directory `/usr/local/share/platina/releases/0.1.1/`, then create
`/usr/local/share/platina/current` pointing to `releases/0.1.1`. If updating an
existing setup, back up its assets/hook first and use a new versioned directory.
The phone renderer uses Python's standard library, without Pillow or a desktop.

```sh
sudo platina-display status
sudo platina-display on --brightness 25
sudo platina-display brightness --brightness 10
sudo platina-display off
sudo platina-display show --seconds 7
sudo platina-display show --directory /PATH/TO/CUSTOM-FRAME --seconds 60
```

`status` only reads sysfs. Changes require root and the actual bound Tianma driver;
the tool refuses the old panel-simple driver or a simultaneously loaded temporary
DCS helper. `on` keeps the current framebuffer visible until `off` is requested;
it may show the console. `show` is bounded to one hour and turns the panel off on
completion, ordinary error, SIGTERM or Ctrl-C. Display operations share the splash
lock. An external SIGKILL cannot run Python cleanup.

`off` requests `FB_BLANK_POWERDOWN` through DRM after clearing the backlight.
A brightness value of zero alone is not proof that the LCD rails are powered off.
Regulator counts and actual repeated wake behavior must be checked on the device.

Prepare another image on the build host:

```sh
python3 scripts/prepare-display-frame.py picture.png --output artifacts/custom-frame
```

The converter preserves aspect ratio, adds black padding and produces a preview,
BGRX framebuffer data and a checksum manifest. Transfer the generated frame bundle
separately; this command does not contact the phone.

## Boot logo

The optional `phone-headless.start` hook starts the logo in the background for
seven seconds, with a timeout and cleanup. On the integrated panel it selects the
new controller. On the old boot it selects the temporary session only when that
kernel-specific module was explicitly installed. Do not install the old helper
blindly, or auto-load it alongside the integrated driver.

Only install the hook after manual rendering and powerdown have worked. The
current clean-image builder keeps the backlight dark and does not automatically
install a generated splash bundle. SSH must remain independent of splash success.

## Hardware acceptance

Confirm the picture physically, test several brightness values and at least ten
off/on cycles, inspect DRM/DCS/kernel errors and compare regulator state before
and after. Verify normal reboot, logo timeout, SSH and temperature/charging.
Measured power savings are a separate result; they have not been established.

Do not live-unbind/rebind the MSM DRM stack: a previous attempt caused an Oops.
For future dashboards the same frame format can carry status screens. Animations
or interactive UIs can later use standard DRM/KMS or a Wayland client after the
panel lifecycle works reliably. Touchscreen support remains a separate porting task.
