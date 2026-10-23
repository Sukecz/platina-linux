// SPDX-License-Identifier: GPL-2.0-only
/* Bounded Platina LCD diagnostics, without detaching or replacing DRM. */
#include <linux/delay.h>
#include <linux/init.h>
#include <linux/module.h>
#include <linux/of.h>
#include <linux/regulator/consumer.h>
#include <drm/drm_mipi_dsi.h>

static bool wake;
static bool enable_iovcc;
static bool own_enable;
static struct regulator *iovcc;
module_param(wake, bool, 0400);
module_param(enable_iovcc, bool, 0400);
MODULE_PARM_DESC(wake, "Send standard DCS sleep-out/display-on after reading status");
static int read_result, wake_result;
static int io_enabled;
static unsigned char power_before, power_after;
module_param(read_result, int, 0444);
module_param(io_enabled, int, 0444);
module_param(wake_result, int, 0444);
module_param(power_before, byte, 0444);
module_param(power_after, byte, 0444);

static int __init platina_panel_dcs_init(void)
{
	struct device_node *node;
	struct mipi_dsi_device *dsi;
	unsigned long flags;

	if (!of_machine_is_compatible("xiaomi,platina"))
		return -ENODEV;
	node = of_find_node_by_path("/soc@0/display-subsystem@c900000/dsi@c994000/panel@0");
	if (!node)
		return -ENODEV;
	dsi = of_find_mipi_dsi_device_by_node(node);
	of_node_put(node);
	if (!dsi)
		return -ENODEV;
	iovcc = regulator_get_optional(&dsi->dev, "iovcc");
	if (IS_ERR(iovcc)) {
		io_enabled = PTR_ERR(iovcc);
		iovcc = NULL;
		read_result = -EHOSTDOWN;
		goto done;
	}
	io_enabled = regulator_is_enabled(iovcc);
	if (!io_enabled && enable_iovcc) {
		wake_result = regulator_enable(iovcc);
		if (!wake_result) {
			own_enable = true;
			io_enabled = regulator_is_enabled(iovcc);
		}
	}
	if (io_enabled <= 0) {
		read_result = -EHOSTDOWN;
		goto done;
	}

	flags = dsi->mode_flags;
	dsi->mode_flags |= MIPI_DSI_MODE_LPM;
	read_result = mipi_dsi_dcs_read(dsi, 0x0a, &power_before, 1);
	if (wake && read_result == 1) {
		wake_result = mipi_dsi_dcs_exit_sleep_mode(dsi);
		if (!wake_result) {
			msleep(120);
			wake_result = mipi_dsi_dcs_set_display_on(dsi);
			msleep(20);
		}
		if (!wake_result)
			read_result = mipi_dsi_dcs_read(dsi, 0x0a, &power_after, 1);
	}
	dsi->mode_flags = flags;
done:
	put_device(&dsi->dev);
	pr_info("platina-panel-dcs: iovcc=%d read=%d power_before=0x%02x power_after=0x%02x wake=%d\n",
		io_enabled, read_result, power_before, power_after, wake_result);
	return 0;
}

static void __exit platina_panel_dcs_exit(void)
{
	if (own_enable)
		regulator_disable(iovcc);
	if (iovcc)
		regulator_put(iovcc);
}
module_init(platina_panel_dcs_init);
module_exit(platina_panel_dcs_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("Platina read-only DCS status and optional standard LCD wake test");
