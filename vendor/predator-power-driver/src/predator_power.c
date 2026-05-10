// SPDX-License-Identifier: GPL-2.0-or-later
/*
 * Predator Power Manager WMI driver
 *
 * Focused Acer Predator gaming controls extracted from the public Acer WMI
 * research and the acer-predator-turbo-and-rgb-keyboard-linux-module project.
 * This driver intentionally omits keyboard RGB, hotkeys, rfkill, backlight and
 * accelerometer handling. User space only needs thermal profile, turbo OC and
 * fan boost controls.
 */

#define pr_fmt(fmt) KBUILD_MODNAME ": " fmt

#include <linux/bitfield.h>
#include <linux/acpi.h>
#include <linux/kernel.h>
#include <linux/module.h>
#include <linux/platform_device.h>
#include <linux/slab.h>
#include <linux/types.h>
#include <linux/version.h>
#include <linux/wmi.h>

#define PREDATOR_WMID_GUID "7A4DDFE7-5B5D-40B4-8595-4408E0CC7F56"

#define PREDATOR_WMID_SET_GAMING_LED_METHODID          2
#define PREDATOR_WMID_SET_GAMING_FAN_BEHAVIOR          14
#define PREDATOR_WMID_SET_GAMING_MISC_SETTING_METHODID 22
#define PREDATOR_WMID_GET_GAMING_MISC_SETTING_METHODID 23

#define PREDATOR_MISC_SETTING_STATUS_MASK GENMASK_ULL(7, 0)
#define PREDATOR_MISC_SETTING_INDEX_MASK  GENMASK_ULL(7, 0)
#define PREDATOR_MISC_SETTING_VALUE_MASK  GENMASK_ULL(15, 8)

#define PREDATOR_MISC_SETTING_PLATFORM_PROFILE 0x0B

enum predator_thermal_profile {
	PREDATOR_PROFILE_BALANCED = 0,
	PREDATOR_PROFILE_QUIET = 1,
	PREDATOR_PROFILE_PERFORMANCE = 2,
	PREDATOR_PROFILE_TURBO = 3,
	PREDATOR_PROFILE_ECO = 4,
};

static struct platform_device *predator_power_device;
static bool turbo_state;
static bool fan_boost_state;
static u8 thermal_profile_state = PREDATOR_PROFILE_BALANCED;

static unsigned int cpu_fans = 1;
static unsigned int gpu_fans = 1;
module_param(cpu_fans, uint, 0644);
module_param(gpu_fans, uint, 0644);
MODULE_PARM_DESC(cpu_fans, "Number of CPU fans used when building the fan mode payload");
MODULE_PARM_DESC(gpu_fans, "Number of GPU fans used when building the fan mode payload");

static bool predator_obj_to_u64(union acpi_object *obj, u64 *out)
{
	u32 tmp32;

	if (!obj || !out)
		return false;

	switch (obj->type) {
	case ACPI_TYPE_INTEGER:
		*out = obj->integer.value;
		return true;
	case ACPI_TYPE_BUFFER:
		if (obj->buffer.length >= sizeof(*out)) {
			memcpy(out, obj->buffer.pointer, sizeof(*out));
			return true;
		}
		if (obj->buffer.length >= sizeof(tmp32)) {
			memcpy(&tmp32, obj->buffer.pointer, sizeof(tmp32));
			*out = tmp32;
			return true;
		}
		return false;
	default:
		return false;
	}
}

static int predator_wmi_eval(u32 method_id, const void *input_data,
			     acpi_size input_size, u64 *out)
{
	struct acpi_buffer input = {
		.length = input_size,
		.pointer = (void *)input_data,
	};
	struct acpi_buffer result = { ACPI_ALLOCATE_BUFFER, NULL };
	union acpi_object *obj;
	acpi_status status;
	int err = 0;

	status = wmi_evaluate_method(PREDATOR_WMID_GUID, 0, method_id, &input, &result);
	if (ACPI_FAILURE(status))
		return -EIO;

	obj = result.pointer;
	if (out && !predator_obj_to_u64(obj, out))
		err = -ENOMSG;

	kfree(result.pointer);
	return err;
}

static int predator_wmi_eval_u64(u32 method_id, u64 in, u64 *out)
{
	return predator_wmi_eval(method_id, &in, sizeof(in), out);
}

static int predator_wmi_eval_u32(u32 method_id, u32 in, u64 *out)
{
	return predator_wmi_eval(method_id, &in, sizeof(in), out);
}

static int predator_get_misc_setting(u8 setting, u8 *value)
{
	u32 input32 = FIELD_PREP(PREDATOR_MISC_SETTING_INDEX_MASK, setting);
	u64 input64 = input32;
	u64 result = 0;
	int err;

	err = predator_wmi_eval_u32(PREDATOR_WMID_GET_GAMING_MISC_SETTING_METHODID,
				    input32, &result);
	if (err)
		err = predator_wmi_eval_u64(PREDATOR_WMID_GET_GAMING_MISC_SETTING_METHODID,
					input64, &result);
	if (err)
		return err;

	if (FIELD_GET(PREDATOR_MISC_SETTING_STATUS_MASK, result))
		return -EIO;

	*value = FIELD_GET(PREDATOR_MISC_SETTING_VALUE_MASK, result);
	return 0;
}

static int predator_set_misc_setting(u8 setting, u8 value)
{
	u64 input = 0;
	u64 result = 0;
	int err;

	input |= FIELD_PREP(PREDATOR_MISC_SETTING_INDEX_MASK, setting);
	input |= FIELD_PREP(PREDATOR_MISC_SETTING_VALUE_MASK, value);

	err = predator_wmi_eval_u64(PREDATOR_WMID_SET_GAMING_MISC_SETTING_METHODID,
				    input, &result);
	if (err)
		return err;

	if (FIELD_GET(PREDATOR_MISC_SETTING_STATUS_MASK, result))
		return -EIO;

	return 0;
}

static int predator_set_thermal_profile(u8 profile)
{
	int err;

	err = predator_set_misc_setting(PREDATOR_MISC_SETTING_PLATFORM_PROFILE, profile);
	if (err)
		/* Some older BIOS implementations accept the raw profile value. */
		err = predator_wmi_eval_u64(PREDATOR_WMID_SET_GAMING_MISC_SETTING_METHODID,
					profile, NULL);
	if (err)
		return err;

	thermal_profile_state = profile;
	return 0;
}

static int predator_keep_first_error(int first_err, int next)
{
	return first_err ? first_err : next;
}

static int predator_set_led(bool enable)
{
	return predator_wmi_eval_u64(PREDATOR_WMID_SET_GAMING_LED_METHODID,
				    enable ? 0x10001 : 0x1, NULL);
}

static int predator_set_fan_mode(u8 fan_mode)
{
	u64 fan_config1 = 0;
	u64 fan_config2 = 0;
	unsigned int total_fans = cpu_fans + gpu_fans;
	unsigned int i;

	/* fan_mode 1 = automatic, fan_mode 2 = turbo. */
	if (cpu_fans > 0)
		fan_config2 |= 1;
	for (i = 0; i < total_fans; i++)
		fan_config2 |= BIT_ULL(i + 1);
	for (i = 0; i < gpu_fans; i++)
		fan_config2 |= BIT_ULL(i + 3);

	if (cpu_fans > 0)
		fan_config1 |= fan_mode;
	for (i = 0; i < total_fans; i++)
		fan_config1 |= (u64)fan_mode << (2 * i + 2);
	for (i = 0; i < gpu_fans; i++)
		fan_config1 |= (u64)fan_mode << (2 * i + 6);

	return predator_wmi_eval_u64(PREDATOR_WMID_SET_GAMING_FAN_BEHAVIOR,
				    fan_config2 | (fan_config1 << 16), NULL);
}

static int predator_set_oc(bool enable)
{
	int err = 0;

	if (enable) {
		err = predator_keep_first_error(err,
			predator_wmi_eval_u64(PREDATOR_WMID_SET_GAMING_MISC_SETTING_METHODID,
					       0x205, NULL));
		err = predator_keep_first_error(err,
			predator_wmi_eval_u64(PREDATOR_WMID_SET_GAMING_MISC_SETTING_METHODID,
					       0x207, NULL));
	} else {
		err = predator_keep_first_error(err,
			predator_wmi_eval_u64(PREDATOR_WMID_SET_GAMING_MISC_SETTING_METHODID,
					       0x5, NULL));
		err = predator_keep_first_error(err,
			predator_wmi_eval_u64(PREDATOR_WMID_SET_GAMING_MISC_SETTING_METHODID,
					       0x7, NULL));
	}

	return err;
}

static int predator_set_turbo(bool enable)
{
	int err = 0;

	err = predator_keep_first_error(err, predator_set_led(enable));
	err = predator_keep_first_error(err, predator_set_fan_mode(enable ? 2 : 1));
	err = predator_keep_first_error(err, predator_set_oc(enable));
	if (err)
		return err;

	turbo_state = enable;
	fan_boost_state = enable;
	return 0;
}

static ssize_t thermal_profile_show(struct device *dev,
				    struct device_attribute *attr, char *buf)
{
	u8 profile;

	if (!predator_get_misc_setting(PREDATOR_MISC_SETTING_PLATFORM_PROFILE, &profile))
		thermal_profile_state = profile;

	return sysfs_emit(buf, "%u\n", thermal_profile_state);
}

static ssize_t thermal_profile_store(struct device *dev,
				     struct device_attribute *attr,
				     const char *buf, size_t count)
{
	unsigned int profile;
	int err;

	err = kstrtouint(buf, 0, &profile);
	if (err)
		return err;
	if (profile > PREDATOR_PROFILE_ECO)
		return -EINVAL;

	err = predator_set_thermal_profile(profile);
	if (err)
		return err;

	return count;
}
static DEVICE_ATTR_RW(thermal_profile);

static ssize_t turbo_oc_show(struct device *dev,
			     struct device_attribute *attr, char *buf)
{
	return sysfs_emit(buf, "%d\n", turbo_state);
}

static ssize_t turbo_oc_store(struct device *dev,
			      struct device_attribute *attr,
			      const char *buf, size_t count)
{
	bool enable;
	int err;

	err = kstrtobool(buf, &enable);
	if (err)
		return err;

	err = predator_set_turbo(enable);
	if (err)
		return err;

	return count;
}
static DEVICE_ATTR_RW(turbo_oc);

static ssize_t fan_boost_show(struct device *dev,
			      struct device_attribute *attr, char *buf)
{
	return sysfs_emit(buf, "%d\n", fan_boost_state);
}

static ssize_t fan_boost_store(struct device *dev,
			       struct device_attribute *attr,
			       const char *buf, size_t count)
{
	bool enable;
	int err;

	err = kstrtobool(buf, &enable);
	if (err)
		return err;

	err = predator_set_fan_mode(enable ? 2 : 1);
	if (err)
		return err;

	fan_boost_state = enable;
	return count;
}
static DEVICE_ATTR_RW(fan_boost);

static int predator_power_probe(struct platform_device *pdev)
{
	int err;

	err = device_create_file(&pdev->dev, &dev_attr_thermal_profile);
	if (err)
		return err;

	err = device_create_file(&pdev->dev, &dev_attr_turbo_oc);
	if (err)
		goto remove_thermal_profile;

	err = device_create_file(&pdev->dev, &dev_attr_fan_boost);
	if (err)
		goto remove_turbo_oc;

	return 0;

remove_turbo_oc:
	device_remove_file(&pdev->dev, &dev_attr_turbo_oc);
remove_thermal_profile:
	device_remove_file(&pdev->dev, &dev_attr_thermal_profile);
	return err;
}

static void predator_power_remove_files(struct platform_device *pdev)
{
	device_remove_file(&pdev->dev, &dev_attr_fan_boost);
	device_remove_file(&pdev->dev, &dev_attr_turbo_oc);
	device_remove_file(&pdev->dev, &dev_attr_thermal_profile);
}

#if LINUX_VERSION_CODE >= KERNEL_VERSION(6, 11, 0)
static void predator_power_remove(struct platform_device *pdev)
{
	predator_power_remove_files(pdev);
}
#else
static int predator_power_remove(struct platform_device *pdev)
{
	predator_power_remove_files(pdev);
	return 0;
}
#endif

static struct platform_driver predator_power_driver = {
	.driver = {
		.name = "predator-power",
	},
	.probe = predator_power_probe,
	.remove = predator_power_remove,
};

static int __init predator_power_init(void)
{
	int err;

	if (!wmi_has_guid(PREDATOR_WMID_GUID)) {
		pr_err("required Acer gaming WMI GUID not found\n");
		return -ENODEV;
	}

	err = platform_driver_register(&predator_power_driver);
	if (err)
		return err;

	predator_power_device = platform_device_register_simple("predator-power",
							 PLATFORM_DEVID_NONE, NULL, 0);
	if (IS_ERR(predator_power_device)) {
		err = PTR_ERR(predator_power_device);
		platform_driver_unregister(&predator_power_driver);
		return err;
	}

	pr_info("Predator power controls loaded\n");
	return 0;
}

static void __exit predator_power_exit(void)
{
	platform_device_unregister(predator_power_device);
	platform_driver_unregister(&predator_power_driver);
	pr_info("Predator power controls unloaded\n");
}

module_init(predator_power_init);
module_exit(predator_power_exit);

MODULE_AUTHOR("Predator Power Manager contributors");
MODULE_DESCRIPTION("Acer Predator turbo and power WMI controls");
MODULE_LICENSE("GPL");
MODULE_ALIAS("wmi:" PREDATOR_WMID_GUID);
MODULE_ALIAS("platform:predator-power");
