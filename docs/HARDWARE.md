# Xiaomi Mi 8 Lite / platina hardware

The target is **Xiaomi Mi 8 Lite**, codename **platina**, Qualcomm **Snapdragon 660
(SDM660)**, ARM64. Maintainer tests used model **M1808D2TG**, 4 GB RAM and 64 GB eMMC.
Verify your own device; its marketing name alone does not identify the board.

The tested LCD is **Tianma NT36672A**, 1080 × 2280. The original community port
selected a BOE TD4320 descriptor. Those panels are not interchangeable merely
because their resolution matches. The current source candidate changes the DT
to the tested Tianma variant. BOE devices require their own configuration and test.

The device package uses USB network gadget mode and NetworkManager. Charging
behavior depends on the cable, host port and charger. Test the chosen supply
under the intended load; a visible charge indicator is not a sustained power test.
The phone has to stay awake for this headless-server use case.

Before repurposing an older phone, inspect its battery and check its storage
health. Keep a recovery route through the unlocked bootloader and Fastboot.
See the [feature matrix](../README.md#feature-status) for actual support status.

The tested rear-camera path is Sony IMX363 with a DW9714 focus actuator. Optional
browser audio uses one tested built-in microphone path. Other camera suppliers,
front/secondary sensors and other microphone paths are not interchangeable proof
of support. See [camera status and limitations](CAMERA.md).
