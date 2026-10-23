# Shutdown buttons and screen

The tested Mi 8 Lite uses **Power + Volume Up** for an orderly Linux shutdown.
The OpenRC service `platina-power-chord` is enabled in newly built images.

1. Disconnect USB/the charger so the phone runs on its battery.
2. Hold Power and Volume Up together for at least three seconds.
3. Release both buttons. The Platina logo, version and Power off screen appear
   while Linux shuts down. On battery, the tested phone stays off.

With USB power attached, shutdown still runs, but the bootloader starts the phone
again in charger mode and Linux boots normally. This is an accepted limitation.
Reconnecting a charger can also start the phone. There is no automatic waiting
for cable removal and no separate charging-only operating mode.

The service uses both evdev inputs. Short combinations, individual keys, repeats
and lost input events do not request shutdown. It acts only after both keys have
been released. This requires a running kernel and userspace service; it is not
an independent emergency power cut for a frozen phone. Existing long-Power reset
and bootloader key combinations are unchanged.

The screen indicates shutdown is in progress. Physical darkness alone is not
proof that the phone is fully off. The shutdown behavior was physically verified
in 0.3.0; the 0.3.1 in-place update passed screen-preview and restart checks with
the same button policy. Fresh full-image packaging is audited separately.

For diagnosis on a phone running a newly built 0.3.1 image:

```sh
rc-service platina-power-chord status
sudo platina-poweroff --preview
sudo python3 /usr/local/libexec/platina-image-runtime audit
```

Preview only shows the screen for five seconds. The audit reads installed files
and checksums without accessing display/input hardware or requesting shutdown.
The image runtime contains no experimental PMIC module or PMIC autoload rule.
