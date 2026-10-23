# Platina display support

The tested Mi 8 Lite has a **Tianma NT36672A 1080 × 2280** panel. Display support
has two separate states:

| State | Status |
|---|---|
| Integration 0.1.1 temporary LCD power/wake helper | Historical fallback, superseded on the tested phone |
| Integration 0.2.0, integrated driver / DT in kernel 7.2.12-r1 | 🟢 RAM boot, normal boot, logo, brightness and ten off/on cycles physically verified |
| Complete LCD rail shutdown | 🟠 Driver votes released, but VSP/VSN remain fixed always-on |

The candidate is in `ports/candidate/linux-postmarketos-qcom-sdm660/0030-platina-tianma-panel.patch`.
It adds the panel-specific command sequence, correct regulator names, reset timing,
DT binding and initialization-error cleanup to the NT36672A driver. The stock
command sequence is recorded in `project/display/tianma-reference.json` and
compared by offline tests. This is not a verified BOE TD4320 configuration.

## Built-in controller and screens

From source version 0.3.1, fresh `make images` builds include the controller,
headless boot hook, versioned boot logo and shutdown screen automatically.
Hardware verification of integration 0.3.0 does not qualify every new full image.
The following manual steps are for an existing installation that lacks those
files; they are not required after installing a newly integrated image.

## Manual controller setup for an existing installation

After testing a successful boot with the integrated driver, install the renderer
and controller on **your phone**. The files listed below are source files from
this repository; transfer them using your own authenticated SSH connection.

```sh
# On the phone, from the directory to which you transferred these scripts:
sudo install -m755 phone-splash.py /usr/local/sbin/platina-splash
sudo install -m755 phone-display.py /usr/local/sbin/platina-display
```

For the logo, run `make splash` on the build host. Transfer its three runtime files
`release.json`, `version` and `frame.bgrx.gz` from `artifacts/platina-linux-0.2.0/`
into a new phone directory `/usr/local/share/platina/releases/0.2.0/`, then create
`/usr/local/share/platina/current` pointing to `releases/0.2.0`. If updating an
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
Tests on the maintainer's phone confirmed all three driver consumer votes return
to zero and vddio is released. VSP/VSN still use inherited fixed always-on
definitions, so full physical rail shutdown and power savings are not established.

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

For a manual existing-installation update, install the hook only after rendering
and powerdown have worked. The clean-image builder installs the full hook and
both screens; SSH remains independent of splash success.

## Hardware acceptance

Confirm the picture physically, test several brightness values and at least ten
off/on cycles, inspect DRM/DCS/kernel errors and compare regulator state before
and after. Verify normal reboot, logo timeout, SSH and temperature/charging.
Measured power savings are a separate result; they have not been established.

Do not live-unbind/rebind the MSM DRM stack: a previous attempt caused an Oops.
For future dashboards the same frame format can carry status screens. Animations
or interactive UIs can later use standard DRM/KMS or a Wayland client after the
panel lifecycle works reliably. Touchscreen support remains a separate porting task.
