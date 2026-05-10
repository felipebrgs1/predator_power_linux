import { execSync, spawnSync } from "child_process";
import { existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, rmSync, statSync, writeFileSync } from "fs";
import { tmpdir } from "os";
import { dirname, join, relative } from "path";
import { fileURLToPath } from "url";
import { VENDOR_FILES } from "./embed.js";

const RAPL_PATH = "/sys/class/powercap/intel-rapl/intel-rapl:0";
const DRIVER_MODULE = "predator_power";
const DRIVER_SOURCE_DIR = "predator-power-driver";
const DRIVER_DIR = "/usr/src/predator-power-driver";
const DRIVER_MODULES_LOAD_CONF = `/etc/modules-load.d/${DRIVER_MODULE}.conf`;
const POWER_DEVICE_DIR = "/sys/devices/platform/predator-power";
const FAN_BOOST_PATH = `${POWER_DEVICE_DIR}/fan_boost`;
const FAN_MODE_PATH = `${POWER_DEVICE_DIR}/fan_mode`;
const CPU_FAN_RPM_PATH = `${POWER_DEVICE_DIR}/cpu_fan_rpm`;
const GPU_FAN_RPM_PATH = `${POWER_DEVICE_DIR}/gpu_fan_rpm`;
const THERMAL_PROFILE_PATH = `${POWER_DEVICE_DIR}/thermal_profile`;
const TURBO_OC_PATH = `${POWER_DEVICE_DIR}/turbo_oc`;
const LEGACY_FACER_DIR = "/opt/turbo-fan";
const PROFILE_FILE = `/tmp/predator_profile_${process.getuid?.() || 0}`;
const CONFIG_DIR = `${process.env.HOME}/.config/predator-power`;

export const PROFILES: Record<string, { pl1: number; pl2: number; platform: string }> = {
  balanced: { pl1: 50, pl2: 65, platform: "balanced" },
  performance: { pl1: 75, pl2: 100, platform: "balanced-performance" },
  turbo: { pl1: 100, pl2: 140, platform: "performance" },
};

let vendorDir: string | null = null;

function shouldCopyDriverFile(rel: string): boolean {
  const name = rel.split(/[\\/]/).pop() || rel;
  if (rel.split(/[\\/]/).some((part) => part.startsWith("."))) return false;
  if (name === "Module.symvers" || name === "modules.order") return false;
  if (/\.(o|ko|mod|mod\.c|cmd|o\.d)$/.test(name)) return false;
  return true;
}

export function isRoot() {
  return process.getuid?.() === 0;
}

export function ensureRoot(args?: string[]): boolean {
  if (isRoot()) return true;
  const exe = process.execPath;
  const script = process.argv[1] || "";
  const extra = args || process.argv.slice(2);
  try {
    execSync("which pkexec", { stdio: "ignore" });
    spawnSync("pkexec", [exe, script, ...extra], { stdio: "inherit" });
  } catch {
    spawnSync("sudo", [exe, script, ...extra], { stdio: "inherit" });
  }
  return false;
}

function safeRead(path: string) {
  try {
    return readFileSync(path, "utf-8").trim();
  } catch {
    return "";
  }
}

function safeWrite(path: string, data: string): boolean {
  try {
    writeFileSync(path, data);
    return true;
  } catch {
    return false;
  }
}

export function getVendorRoot() {
  if (vendorDir) return vendorDir;

  const currentFile = fileURLToPath(import.meta.url);
  const devVendor = join(dirname(currentFile), "..", "vendor", DRIVER_SOURCE_DIR);
  if (existsSync(devVendor)) {
    vendorDir = dirname(devVendor);
    return vendorDir;
  }

  const dir = mkdtempSync(join(tmpdir(), "predator_vendor_"));
  const base = join(dir, "vendor", DRIVER_SOURCE_DIR);
  for (const [rel, content] of Object.entries(VENDOR_FILES)) {
    const full = join(base, rel);
    mkdirSync(dirname(full), { recursive: true });
    writeFileSync(full, content);
  }
  vendorDir = dirname(base);
  return vendorDir;
}

export function driverLoaded() {
  try {
    return readFileSync("/proc/modules", "utf-8").includes(DRIVER_MODULE);
  } catch {
    return false;
  }
}

export function platformProfilePath() {
  try {
    const entries = readdirSync("/sys/class/platform-profile");
    for (const entry of entries) {
      const p = `/sys/class/platform-profile/${entry}/profile`;
      if (existsSync(p)) return p;
    }
  } catch {}
  return null;
}

function isClangKernel(): boolean {
  try {
    return readFileSync("/proc/version", "utf-8").includes("clang");
  } catch {
    return false;
  }
}

function isNixOS(): boolean {
  try {
    return existsSync("/etc/NIXOS");
  } catch {
    return false;
  }
}

function archHeadersPackage(kernelRelease: string): string {
  if (kernelRelease.includes("cachyos")) return "linux-cachyos-headers";
  if (kernelRelease.includes("zen")) return "linux-zen-headers";
  if (kernelRelease.includes("lts")) return "linux-lts-headers";
  if (kernelRelease.includes("hardened")) return "linux-hardened-headers";
  return "linux-headers";
}

export function installDriver(): string {
  const src = join(getVendorRoot(), DRIVER_SOURCE_DIR);
  if (!existsSync(src)) {
    return "Driver source not found.";
  }

  const kernelRelease = execSync("uname -r", { encoding: "utf-8" }).trim();
  let useNix = false;
  try {
    execSync("which pacman", { stdio: "ignore" });
    execSync(`pacman -S --needed --noconfirm base-devel ${archHeadersPackage(kernelRelease)}`, { stdio: "ignore" });
  } catch {
    try {
      execSync("which apt-get", { stdio: "ignore" });
      execSync(`apt-get install -y build-essential linux-headers-${kernelRelease} kmod`, { stdio: "ignore" });
    } catch {
      try {
        execSync("which nix-shell", { stdio: "ignore" });
        useNix = true;
      } catch {}
    }
  }

  rmSync(DRIVER_DIR, { recursive: true, force: true });
  mkdirSync(DRIVER_DIR, { recursive: true });

  function copyRecursive(from: string, to: string) {
    for (const entry of readdirSync(from)) {
      const srcPath = join(from, entry);
      const dstPath = join(to, entry);
      const rel = relative(src, srcPath);
      if (!shouldCopyDriverFile(rel)) continue;
      const st = statSync(srcPath);
      if (st.isDirectory()) {
        mkdirSync(dstPath, { recursive: true });
        copyRecursive(srcPath, dstPath);
      } else {
        writeFileSync(dstPath, readFileSync(srcPath));
      }
    }
  }
  copyRecursive(src, DRIVER_DIR);

  const clang = isClangKernel() ? "CC=clang LD=ld.lld" : "";
  let kernelDir = `/lib/modules/${kernelRelease}/build`;
  if (!existsSync(kernelDir)) {
    const nixPaths = [
      `/run/current-system/kernel-modules/lib/modules/${kernelRelease}/build`,
      `/run/booted-system/kernel-modules/lib/modules/${kernelRelease}/build`,
    ];
    for (const p of nixPaths) {
      if (existsSync(p)) {
        kernelDir = p;
        break;
      }
    }
  }
  if (!existsSync(kernelDir)) {
    try {
      const nixStorePath = execSync(
        `ls -d /nix/store/*-linux-${kernelRelease}-dev/lib/modules/${kernelRelease}/build 2>/dev/null | head -n1`,
        { encoding: "utf-8" }
      ).trim();
      if (nixStorePath && existsSync(nixStorePath)) {
        kernelDir = nixStorePath;
      }
    } catch {}
  }
  if (!existsSync(kernelDir) && useNix) {
    try {
      kernelDir = execSync(
        `nix-shell -p linuxPackages_latest.kernel.dev --run "ls -d /nix/store/*-linux-${kernelRelease}-dev/lib/modules/${kernelRelease}/build | head -n1"`,
        { encoding: "utf-8" }
      ).trim();
    } catch {}
  }
  if (!existsSync(kernelDir)) {
    throw new Error(
      `Kernel build directory not found for ${kernelRelease} (looked at ${kernelDir}). ` +
        `On NixOS, ensure your kernel package includes the dev output (e.g., via boot.kernelPackages).`
    );
  }

  if (useNix) {
    const nixPkgs = isClangKernel() ? "gcc gnumake perl clang" : "gcc gnumake perl";
    execSync(`nix-shell -p ${nixPkgs} --run 'export KERNELDIR=${kernelDir} && make clean && make ${clang}'`, {
      cwd: DRIVER_DIR,
      stdio: "inherit",
    });
  } else {
    execSync(`make clean && make ${clang}`, { cwd: DRIVER_DIR, stdio: "inherit", env: { ...process.env, KERNELDIR: kernelDir } });
  }

  const moduleFile = join(DRIVER_DIR, "src", `${DRIVER_MODULE}.ko`);
  if (!existsSync(moduleFile)) {
    throw new Error(`Kernel module was not built: ${moduleFile}`);
  }

  const moduleInstallDir = `/lib/modules/${kernelRelease}/extra`;
  mkdirSync(moduleInstallDir, { recursive: true });
  writeFileSync(join(moduleInstallDir, `${DRIVER_MODULE}.ko`), readFileSync(moduleFile));

  try { execSync("systemctl disable --now turbo-fan.service", { stdio: "ignore" }); } catch {}
  try { rmSync("/etc/systemd/system/turbo-fan.service", { force: true }); } catch {}
  try { execSync("systemctl daemon-reload", { stdio: "ignore" }); } catch {}
  try { rmSync("/etc/modules-load.d/facer.conf", { force: true }); } catch {}
  try { execSync("modprobe -r facer", { stdio: "ignore" }); } catch { try { execSync("rmmod facer", { stdio: "ignore" }); } catch {} }
  try { rmSync(LEGACY_FACER_DIR, { recursive: true, force: true }); } catch {}

  execSync("depmod -a", { stdio: "inherit" });
  try { execSync(`modprobe -r ${DRIVER_MODULE}`, { stdio: "ignore" }); } catch {}
  execSync(`modprobe ${DRIVER_MODULE}`, { stdio: "inherit" });
  writeFileSync(DRIVER_MODULES_LOAD_CONF, `${DRIVER_MODULE}\n`);

  return "Predator power driver installed and loaded.";
}

export function stopConflictingDaemons() {
  const nixos = isNixOS();
  for (const svc of ["power-profiles-daemon", "thermald"]) {
    try {
      execSync(`systemctl is-active --quiet ${svc}`);
      execSync(`systemctl stop ${svc}`);
      if (!nixos) {
        execSync(`systemctl mask ${svc}`);
      }
    } catch {}
  }
}

export function setPower(pl1: number, pl2: number) {
  safeWrite(join(RAPL_PATH, "constraint_0_power_limit_uw"), String(pl1 * 1_000_000));
  safeWrite(join(RAPL_PATH, "constraint_1_power_limit_uw"), String(pl2 * 1_000_000));
}

// Predator power driver thermal_profile values:
// 0=balanced, 1=quiet, 2=performance, 3=turbo, 4=eco
const PROFILE_TO_THERMAL: Record<string, string> = {
  balanced: "0",
  performance: "2",
  turbo: "3",
};

export function setPlatform(profile: string) {
  if (existsSync(THERMAL_PROFILE_PATH)) {
    const val = PROFILE_TO_THERMAL[profile];
    if (val) {
      safeWrite(THERMAL_PROFILE_PATH, val);
      return;
    }
  }

  const path = platformProfilePath();
  if (path) {
    const p = PROFILES[profile];
    safeWrite(path, p?.platform || "balanced");
  }
}

export function setTurboOC(on: boolean): boolean {
  if (existsSync(TURBO_OC_PATH)) {
    return safeWrite(TURBO_OC_PATH, on ? "1" : "0");
  }
  return false;
}

export function readFanBoost(): boolean {
  if (existsSync(FAN_BOOST_PATH)) {
    return safeRead(FAN_BOOST_PATH) === "1";
  }
  return safeRead(TURBO_OC_PATH) === "1";
}

export function setFanBoost(on: boolean) {
  if (on) {
    setPlatform("performance");
    setTurboOC(true);
    safeWrite(FAN_BOOST_PATH, "1");
  } else {
    setTurboOC(false);
    safeWrite(FAN_BOOST_PATH, "0");
    const current = safeRead(PROFILE_FILE) || "balanced";
    setPlatform(current);
  }
}

export function setFanMode(mode: number): string {
  if (!Number.isInteger(mode) || mode < 1 || mode > 2) {
    return "Invalid fan mode. Use 1=auto or 2=turbo.";
  }

  if (!driverLoaded() || !existsSync(FAN_MODE_PATH)) {
    installDriver();
  }

  if (!existsSync(FAN_MODE_PATH)) {
    return `Fan mode control not found: ${FAN_MODE_PATH}`;
  }

  if (!safeWrite(FAN_MODE_PATH, String(mode))) {
    return `Failed to set fan mode ${mode}.`;
  }

  return `Fan mode ${mode} applied.`;
}

export function showFanStatus() {
  const mode = safeRead(FAN_MODE_PATH) || "N/A";
  const cpuRpm = safeRead(CPU_FAN_RPM_PATH) || "N/A";
  const gpuRpm = safeRead(GPU_FAN_RPM_PATH) || "N/A";
  return { mode, cpuRpm, gpuRpm };
}

export function applyProfile(name: string): string {
  const p = PROFILES[name];
  if (!p) return `Unknown profile: ${name}`;

  if (!safeWrite(PROFILE_FILE, name)) {
    return `Permission denied: ${PROFILE_FILE}`;
  }
  stopConflictingDaemons();

  if (!driverLoaded()) {
    installDriver();
  }

  setPower(p.pl1, p.pl2);
  setPlatform(name);

  if (name === "turbo") {
    setTurboOC(true);
  } else {
    setTurboOC(false);
  }

  if (name === "turbo" && existsSync(FAN_BOOST_PATH)) {
    safeWrite(FAN_BOOST_PATH, "1");
  }

  mkdirSync(CONFIG_DIR, { recursive: true });
  safeWrite(join(CONFIG_DIR, "last_profile"), name);
  return `Profile ${name} applied.`;
}

let thermalTimer: ReturnType<typeof setInterval> | null = null;

export function stopThermalControl() {
  if (thermalTimer) {
    clearInterval(thermalTimer);
    thermalTimer = null;
  }
}

export function findPackageTempPath(): string | null {
  try {
    const thermalDir = "/sys/class/thermal";
    for (const zone of readdirSync(thermalDir)) {
      if (!zone.startsWith("thermal_zone")) continue;
      const typePath = join(thermalDir, zone, "type");
      const tempPath = join(thermalDir, zone, "temp");
      if (!existsSync(tempPath) || !existsSync(typePath)) continue;
      const type = readFileSync(typePath, "utf-8").trim().toLowerCase();
      if (type.includes("pkg") || type === "x86_pkg_temp" || type.includes("k10") || type === "tctl" || type === "cpu-thermal") {
        return tempPath;
      }
    }
  } catch {}

  try {
    const hwmonDir = "/sys/class/hwmon";
    for (const entry of readdirSync(hwmonDir)) {
      const namePath = join(hwmonDir, entry, "name");
      if (!existsSync(namePath)) continue;
      const name = readFileSync(namePath, "utf-8").trim().toLowerCase();
      if (name !== "coretemp" && name !== "k10temp") continue;
      for (const sub of readdirSync(join(hwmonDir, entry))) {
        if (!sub.endsWith("_input")) continue;
        const labelPath = join(hwmonDir, entry, sub.replace("_input", "_label"));
        if (existsSync(labelPath)) {
          const label = readFileSync(labelPath, "utf-8").trim().toLowerCase();
          if (label.includes("package") || label.includes("tctl") || label.includes("tdie")) {
            return join(hwmonDir, entry, sub);
          }
        }
        return join(hwmonDir, entry, sub);
      }
    }
  } catch {}

  return null;
}

export function readCpuTemp(tempPath: string): number | null {
  try {
    return parseInt(readFileSync(tempPath, "utf-8").trim()) / 1000;
  } catch {
    return null;
  }
}

export function thermalControl(
  targetTemp: number,
  maxPL1: number,
  maxPL2: number,
  onUpdate?: (temp: number, pl1: number, pl2: number) => void,
  minPL: number = 10
): string {
  const tempPath = findPackageTempPath();
  if (!tempPath) return "CPU temperature sensor not found.";

  stopThermalControl();

  const kp = 5;
  const ki = 0.1;
  let integral = 0;
  let pl1 = maxPL1;
  const pl2ratio = maxPL2 / maxPL1;

  setPower(maxPL1, maxPL2);

  thermalTimer = setInterval(() => {
    const temp = readCpuTemp(tempPath);
    if (temp === null) return;

    const error = temp - targetTemp;
    integral += error * 2;
    integral = Math.max(-100, Math.min(100, integral));

    const adj = kp * error + ki * integral;
    pl1 = Math.max(minPL, Math.min(maxPL1, pl1 - adj));
    const pl2 = Math.max(minPL, Math.min(maxPL2, Math.round(pl1 * pl2ratio)));

    setPower(Math.round(pl1), Math.round(pl2));

    if (onUpdate) onUpdate(temp, Math.round(pl1), Math.round(pl2));
  }, 2000);

  return `Thermal control active: target ${targetTemp}°C (max PL1=${maxPL1}W PL2=${maxPL2}W)`;
}

export function showStatus() {
  const pl1 = Math.floor(Number(safeRead(join(RAPL_PATH, "constraint_0_power_limit_uw")) || "0") / 1_000_000);
  const pl2 = Math.floor(Number(safeRead(join(RAPL_PATH, "constraint_1_power_limit_uw")) || "0") / 1_000_000);
  const fanLegacy = safeRead(FAN_BOOST_PATH);
  const turboVal = safeRead(TURBO_OC_PATH);
  const tpVal = safeRead(THERMAL_PROFILE_PATH);
  const fanStatus = showFanStatus();
  const ecPath = platformProfilePath();
  const ecRaw = tpVal || (ecPath ? safeRead(ecPath) : "");
  const PROFILE_NAMES: Record<string, string> = {
    "0": "Balanced",
    "1": "Quiet",
    "2": "Performance",
    "3": "Turbo",
    "4": "Eco",
    balanced: "Balanced",
    "balanced-performance": "Performance",
    performance: "Performance",
    quiet: "Quiet",
    "low-power": "Eco",
  };
  const ec = PROFILE_NAMES[ecRaw] || (ecRaw ? `Mode ${ecRaw}` : "N/A");
  const driver = driverLoaded() ? "ACTIVE" : "MISSING";
  const fan = fanLegacy === "1" ? "ON" : turboVal === "1" ? "TURBO" : "OFF";
  const fanRpm = fanStatus.cpuRpm === "N/A" && fanStatus.gpuRpm === "N/A" ? "N/A" : `CPU ${fanStatus.cpuRpm} GPU ${fanStatus.gpuRpm}`;
  return { pl1, pl2, fan, fanRpm, ec, driver };
}

export function installService(profile = "balanced"): string {
  if (!ensureRoot(["service", profile])) {
    return "Elevating permissions...";
  }

  if (isNixOS()) {
    return "NixOS manages systemd units declaratively. Please add the service to your configuration.nix instead.";
  }

  const exe = process.execPath;
  const execStart = `${exe} profile ${profile}`;
  const unit = `[Unit]
Description=Predator Power Manager
After=multi-user.target

[Service]
Type=oneshot
ExecStartPre=/bin/sleep 3
ExecStart=${execStart}
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
`;
  writeFileSync("/etc/systemd/system/predator-power.service", unit);
  execSync("systemctl daemon-reload");
  execSync("systemctl enable predator-power.service");
  try {
    execSync("systemctl start predator-power.service");
  } catch (e: any) {
    return `Service enabled but failed to start. Check logs with: journalctl -xeu predator-power.service\n${e.stderr || e.message}`;
  }
  return "Service installed.";
}

export function removeService(): string {
  if (!ensureRoot(["service", "remove"])) {
    return "Elevating permissions...";
  }
  try { execSync("systemctl stop predator-power.service"); } catch {}
  try { execSync("systemctl disable predator-power.service"); } catch {}
  try { rmSync("/etc/systemd/system/predator-power.service", { force: true }); } catch {}
  execSync("systemctl daemon-reload");
  return "Service removed.";
}
