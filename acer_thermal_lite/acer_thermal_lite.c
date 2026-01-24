#include <linux/module.h>
#include <linux/init.h>
#include <linux/acpi.h>
#include <linux/platform_device.h>
#include <linux/platform_profile.h>
#include <linux/bitfield.h>
#include <linux/wmi.h>

#define WMID_GUID "7A4DDFE7-5B5D-40B4-8595-4408E0CC7F56"
#define METHOD_SET 22
#define METHOD_GET 23

#define ACER_MISC_SETTING_INDEX_MASK GENMASK_ULL(7, 0)
#define ACER_MISC_SETTING_VALUE_MASK GENMASK_ULL(15, 8)
#define ACER_MISC_SETTING_STATUS_MASK GENMASK_ULL(31, 16)
#define ACER_PLATFORM_PROFILE_INDEX 0x0B

MODULE_AUTHOR("Antigravity AI (based on facer)");
MODULE_DESCRIPTION("Simplified Acer Predator Thermal Profile Driver");
MODULE_LICENSE("GPL");

enum {
    ACER_PROFILE_ECO         = 0x06,
    ACER_PROFILE_TURBO       = 0x05,
    ACER_PROFILE_PERFORMANCE = 0x04,
    ACER_PROFILE_BALANCED    = 0x01,
    ACER_PROFILE_QUIET       = 0x00,
};

static struct platform_device *pdev;

static int wmi_gaming_execute(u32 method_id, u64 input_val, u64 *output_val)
{
    struct acpi_buffer input = { sizeof(u64), &input_val };
    struct acpi_buffer result = { ACPI_ALLOCATE_BUFFER, NULL };
    union acpi_object *obj;
    acpi_status status;
    int ret = 0;

    status = wmi_evaluate_method(WMID_GUID, 0, method_id, &input, &result);
    if (ACPI_FAILURE(status))
        return -EIO;

    obj = result.pointer;
    if (obj && output_val) {
        if (obj->type == ACPI_TYPE_INTEGER)
            *output_val = obj->integer.value;
        else if (obj->type == ACPI_TYPE_BUFFER && obj->buffer.length >= 8)
            *output_val = *(u64 *)obj->buffer.pointer;
        else
            ret = -ENOMSG;
    }

    kfree(result.pointer);
    return ret;
}

static int acer_lite_profile_get(struct device *dev, enum platform_profile_option *profile)
{
    u64 input = ACER_PLATFORM_PROFILE_INDEX;
    u64 result;
    int ret;
    u8 val;

    ret = wmi_gaming_execute(METHOD_GET, input, &result);
    if (ret) return ret;

    if (FIELD_GET(ACER_MISC_SETTING_STATUS_MASK, result))
        return -EIO;

    val = FIELD_GET(ACER_MISC_SETTING_VALUE_MASK, result);

    switch (val) {
    case ACER_PROFILE_TURBO:       *profile = PLATFORM_PROFILE_PERFORMANCE; break;
    case ACER_PROFILE_PERFORMANCE: *profile = PLATFORM_PROFILE_BALANCED_PERFORMANCE; break;
    case ACER_PROFILE_BALANCED:    *profile = PLATFORM_PROFILE_BALANCED; break;
    case ACER_PROFILE_QUIET:       *profile = PLATFORM_PROFILE_QUIET; break;
    case ACER_PROFILE_ECO:         *profile = PLATFORM_PROFILE_LOW_POWER; break;
    default: return -EOPNOTSUPP;
    }

    return 0;
}

static int acer_lite_profile_set(struct device *dev, enum platform_profile_option profile)
{
    u64 input = ACER_PLATFORM_PROFILE_INDEX;
    u64 result;
    u8 val;

    switch (profile) {
    case PLATFORM_PROFILE_PERFORMANCE:          val = ACER_PROFILE_TURBO; break;
    case PLATFORM_PROFILE_BALANCED_PERFORMANCE: val = ACER_PROFILE_PERFORMANCE; break;
    case PLATFORM_PROFILE_BALANCED:             val = ACER_PROFILE_BALANCED; break;
    case PLATFORM_PROFILE_QUIET:                val = ACER_PROFILE_QUIET; break;
    case PLATFORM_PROFILE_LOW_POWER:            val = ACER_PROFILE_ECO; break;
    default: return -EOPNOTSUPP;
    }

    input |= FIELD_PREP(ACER_MISC_SETTING_VALUE_MASK, val);

    return wmi_gaming_execute(METHOD_SET, input, &result);
}

static int acer_lite_profile_probe(void *drvdata, unsigned long *choices)
{
    set_bit(PLATFORM_PROFILE_LOW_POWER, choices);
    set_bit(PLATFORM_PROFILE_QUIET, choices);
    set_bit(PLATFORM_PROFILE_BALANCED, choices);
    set_bit(PLATFORM_PROFILE_BALANCED_PERFORMANCE, choices);
    set_bit(PLATFORM_PROFILE_PERFORMANCE, choices);
    return 0;
}

static const struct platform_profile_ops acer_lite_profile_ops = {
    .probe = acer_lite_profile_probe,
    .profile_get = acer_lite_profile_get,
    .profile_set = acer_lite_profile_set,
};

static int __init acer_thermal_lite_init(void)
{
    int err;
    struct device *pp_dev;

    if (!wmi_has_guid(WMID_GUID)) {
        pr_err("acer_thermal_lite: Gaming WMI GUID not found\n");
        return -ENODEV;
    }

    pdev = platform_device_register_simple("acer-thermal-lite", PLATFORM_DEVID_NONE, NULL, 0);
    if (IS_ERR(pdev))
        return PTR_ERR(pdev);

    pp_dev = devm_platform_profile_register(&pdev->dev, "acer-thermal-lite", NULL, &acer_lite_profile_ops);
    if (IS_ERR(pp_dev)) {
        err = PTR_ERR(pp_dev);
        pr_err("acer_thermal_lite: Failed to register platform profile: %d\n", err);
        platform_device_unregister(pdev);
        return err;
    }

    pr_info("acer_thermal_lite: Loaded successfully\n");
    return 0;
}

static void __exit acer_thermal_lite_exit(void)
{
    if (pdev)
        platform_device_unregister(pdev);
    pr_info("acer_thermal_lite: Unloaded\n");
}

module_init(acer_thermal_lite_init);
module_exit(acer_thermal_lite_exit);
