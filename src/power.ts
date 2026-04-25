import { execSync, spawnSync } from "child_process";
import { existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, rmSync, statSync, writeFileSync } from "fs";
import { tmpdir } from "os";
import { dirname, join, relative } from "path";
import { fileURLToPath } from "url";
import { VENDOR_FILES } from "./embed.js";

const RAPL_PATH = "/sys/class/powercap/intel-rapl/intel-rapl:0";
const FAN_BOOST_PATH = "/sys/devices/platform/acer-thermal-lite/fan_boost";
const THERMAL_PROFILE_PATH = "/sys/devices/platform/acer-wmi/thermal_profile";
const TURBO_OC_PATH = "/sys/devices/platform/acer-wmi/turbo_oc";
const PROFILE_FILE = `/tmp/predator_profile_${process.getuid?.() || 0}`;
const CONFIG_DIR = `${process.env.HOME}/.config/predator-power`;
const FACER_DIR = "/opt/turbo-fan";

export const PROFILES: Record<string, { pl1: number; pl2: number; platform: string }> = {
  balanced: { pl1: 50, pl2: 65, platform: "balanced" },
  performance: { pl1: 75, pl2: 100, platform: "balanced-performance" },
  turbo: { pl1: 100, pl2: 140, platform: "performance" },
};

let vendorDir: string | null = null;

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
  const devVendor = join(dirname(currentFile), "..", "vendor", "acer-turbo-driver");
  if (existsSync(devVendor)) {
    vendorDir = dirname(devVendor);
    return vendorDir;
  }

  const dir = mkdtempSync(join(tmpdir(), "predator_vendor_"));
  const base = join(dir, "vendor", "acer-turbo-driver");
  for (const [rel, content] of Object.entries(VENDOR_FILES)) {
    const full = join(base, rel);
    mkdirSync(dirname(full), { recursive: true });
    writeFileSync(full, content);
  }
  vendorDir = dirname(base);
  return vendorDir;
}

export function facerLoaded() {
  try {
    return readFileSync("/proc/modules", "utf-8").includes("facer");
  } catch {
    return false;
  }
}

export function facerProfilePath() {
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

export function installFacer(): string {
  const src = join(getVendorRoot(), "acer-turbo-driver");
  if (!existsSync(src)) {
    return "Driver source not found.";
  }

  let useNix = false;
  try {
    execSync("which pacman", { stdio: "ignore" });
    execSync("pacman -S --needed --noconfirm git base-devel linux-headers rsync", { stdio: "ignore" });
  } catch {
    try {
      execSync("which apt-get", { stdio: "ignore" });
      const kernel = execSync("uname -r", { encoding: "utf-8" }).trim();
      execSync(`apt-get install -y git build-essential linux-headers-${kernel} rsync`, { stdio: "ignore" });
    } catch {
      try {
        execSync("which nix-shell", { stdio: "ignore" });
        useNix = true;
      } catch {}
    }
  }

  rmSync(FACER_DIR, { recursive: true, force: true });
  mkdirSync(FACER_DIR, { recursive: true });

  function copyRecursive(from: string, to: string) {
    for (const entry of readdirSync(from)) {
      const srcPath = join(from, entry);
      const dstPath = join(to, entry);
      const st = statSync(srcPath);
      if (st.isDirectory()) {
        mkdirSync(dstPath, { recursive: true });
        copyRecursive(srcPath, dstPath);
      } else {
        writeFileSync(dstPath, readFileSync(srcPath));
      }
    }
  }
  copyRecursive(src, FACER_DIR);

  execSync("chmod +x ./*.sh", { cwd: FACER_DIR });
  const clang = isClangKernel() ? "CC=clang LD=ld.lld" : "";
  const kernelRelease = execSync("uname -r", { encoding: "utf-8" }).trim();
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
      cwd: FACER_DIR,
      stdio: "inherit",
    });
  } else {
    execSync(`make clean && make ${clang}`, { cwd: FACER_DIR, stdio: "inherit", env: { ...process.env, KERNELDIR: kernelDir } });
  }

  execSync("rmmod acer_wmi 2>/dev/null; rmmod facer 2>/dev/null; insmod src/facer.ko", { cwd: FACER_DIR, stdio: "inherit" });

  try {
    execSync("bash -c 'source ./install_service.sh install'", { cwd: FACER_DIR, stdio: "inherit" });
  } catch {}

  return "Driver installed and loaded.";
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

// Mapeia nome do perfil para valor do thermal_profile sysfs
// 0=quiet, 1=balanced, 4=performance
const PROFILE_TO_THERMAL: Record<string, string> = {
  balanced: "1",
  performance: "4",
  turbo: "4",
};

export function setPlatform(profile: string) {
  if (existsSync(THERMAL_PROFILE_PATH)) {
    const val = PROFILE_TO_THERMAL[profile];
    if (val) {
      safeWrite(THERMAL_PROFILE_PATH, val);
      return;
    }
  }

  const path = facerProfilePath();
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

export function applyProfile(name: string): string {
  const p = PROFILES[name];
  if (!p) return `Unknown profile: ${name}`;

  if (!safeWrite(PROFILE_FILE, name)) {
    return `Permission denied: ${PROFILE_FILE}`;
  }
  stopConflictingDaemons();

  if (!facerLoaded()) {
    installFacer();
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

export function showStatus() {
  const pl1 = Math.floor(Number(safeRead(join(RAPL_PATH, "constraint_0_power_limit_uw")) || "0") / 1_000_000);
  const pl2 = Math.floor(Number(safeRead(join(RAPL_PATH, "constraint_1_power_limit_uw")) || "0") / 1_000_000);
  const fanLegacy = safeRead(FAN_BOOST_PATH);
  const turboVal = safeRead(TURBO_OC_PATH);
  const tpVal = safeRead(THERMAL_PROFILE_PATH);
  const ecPath = facerProfilePath();
  const ecRaw = ecPath ? safeRead(ecPath) : tpVal || "";
  const PROFILE_NAMES: Record<string, string> = { "0": "Quiet", "1": "Balanced", "4": "Performance" };
  const ec = PROFILE_NAMES[ecRaw] || (ecRaw ? `Mode ${ecRaw}` : "N/A");
  const facer = facerLoaded() ? "ACTIVE" : "MISSING";
  const fan = fanLegacy === "1" ? "ON" : turboVal === "1" ? "TURBO" : "OFF";
  return { pl1, pl2, fan, ec, facer };
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
