import { execSync, spawnSync } from "child_process";
import { existsSync, mkdirSync, mkdtempSync, readFileSync, readdirSync, rmSync, statSync, writeFileSync } from "fs";
import { tmpdir } from "os";
import { dirname, join, relative } from "path";
import { fileURLToPath } from "url";
import { VENDOR_FILES } from "./embed.js";

const RAPL_PATH = "/sys/class/powercap/intel-rapl/intel-rapl:0";
const FAN_BOOST_PATH = "/sys/devices/platform/acer-thermal-lite/fan_boost";
const PROFILE_FILE = "/tmp/predator_profile";
const CONFIG_DIR = `${process.env.HOME}/.config/predator-power`;
const FACER_DIR = "/opt/turbo-fan";

export const PROFILES: Record<string, { pl1: number; pl2: number; platform: string }> = {
  balanced: { pl1: 50, pl2: 65, platform: "balanced" },
  performance: { pl1: 80, pl2: 115, platform: "balanced-performance" },
  turbo: { pl1: 100, pl2: 140, platform: "performance" },
};

let vendorDir: string | null = null;

export function isRoot() {
  return process.getuid?.() === 0;
}

export function ensureRoot(args?: string[]) {
  if (isRoot()) return;
  const exe = process.execPath;
  const script = process.argv[1] || "";
  const extra = args || process.argv.slice(2);
  // prefer pkexec if available
  try {
    execSync("which pkexec", { stdio: "ignore" });
    spawnSync("pkexec", [exe, script, ...extra], { stdio: "inherit" });
  } catch {
    spawnSync("sudo", [exe, script, ...extra], { stdio: "inherit" });
  }
  process.exit(0);
}

function safeRead(path: string) {
  try {
    return readFileSync(path, "utf-8").trim();
  } catch {
    return "";
  }
}

function safeWrite(path: string, data: string) {
  writeFileSync(path, data);
}

export function getVendorRoot() {
  if (vendorDir) return vendorDir;

  // modo dev: vendor/ ao lado do src/
  const currentFile = fileURLToPath(import.meta.url);
  const devVendor = join(dirname(currentFile), "..", "vendor", "acer-turbo-driver");
  if (existsSync(devVendor)) {
    vendorDir = dirname(devVendor);
    return vendorDir;
  }

  // standalone: extrair de VENDOR_FILES
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

export function installFacer(): string {
  const src = join(getVendorRoot(), "acer-turbo-driver");
  if (!existsSync(src)) {
    return "Driver source not found.";
  }

  // instalar deps
  try {
    execSync("which pacman", { stdio: "ignore" });
    execSync("pacman -S --needed --noconfirm git base-devel linux-headers rsync", { stdio: "ignore" });
  } catch {
    try {
      execSync("which apt-get", { stdio: "ignore" });
      const kernel = execSync("uname -r", { encoding: "utf-8" }).trim();
      execSync(`apt-get install -y git build-essential linux-headers-${kernel} rsync`, { stdio: "ignore" });
    } catch {}
  }

  // copiar para /opt/turbo-fan
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

  // patch install.sh
  const installSh = join(FACER_DIR, "install.sh");
  let installContent = readFileSync(installSh, "utf-8");
  installContent = installContent.replace(
    "/sys/bus/wmi/devices/7A4DDFE7-5B5D-40B4-8595-4408E0CC7F56/",
    "/sys/bus/wmi/devices/7A4DDFE7-5B5D-40B4-8595-4408E0CC7F56*"
  );
  writeFileSync(installSh, installContent);

  // compilar e carregar
  execSync("chmod +x ./*.sh", { cwd: FACER_DIR });
  execSync("bash -c 'source ./install.sh'", { cwd: FACER_DIR, stdio: "inherit" });

  // instalar serviço turbo-fan
  try {
    execSync("bash -c 'source ./install_service.sh install'", { cwd: FACER_DIR, stdio: "inherit" });
  } catch {}

  return "Driver installed and loaded.";
}

export function stopConflictingDaemons() {
  for (const svc of ["power-profiles-daemon", "thermald"]) {
    try {
      execSync(`systemctl is-active --quiet ${svc}`);
      execSync(`systemctl stop ${svc}`);
      execSync(`systemctl mask ${svc}`);
    } catch {}
  }
}

export function setPower(pl1: number, pl2: number) {
  safeWrite(join(RAPL_PATH, "constraint_0_power_limit_uw"), String(pl1 * 1_000_000));
  safeWrite(join(RAPL_PATH, "constraint_1_power_limit_uw"), String(pl2 * 1_000_000));
}

export function setPlatform(profile: string) {
  const path = facerProfilePath();
  if (path) {
    safeWrite(path, profile);
  }
}

export function readFanBoost(): boolean {
  return safeRead(FAN_BOOST_PATH) === "1";
}

export function setFanBoost(on: boolean) {
  if (on) {
    setPlatform("performance");
    safeWrite(FAN_BOOST_PATH, "1");
  } else {
    safeWrite(FAN_BOOST_PATH, "0");
    const current = safeRead(PROFILE_FILE) || "balanced";
    const platform = PROFILES[current]?.platform || "balanced";
    setPlatform(platform);
  }
}

export function applyProfile(name: string): string {
  const p = PROFILES[name];
  if (!p) return `Unknown profile: ${name}`;

  safeWrite(PROFILE_FILE, name);
  stopConflictingDaemons();

  if (!facerLoaded()) {
    installFacer();
  }

  setPower(p.pl1, p.pl2);

  if (readFanBoost()) {
    setPlatform("performance");
  } else {
    setPlatform(p.platform);
  }

  if (name === "turbo") {
    setFanBoost(true);
  }

  mkdirSync(CONFIG_DIR, { recursive: true });
  safeWrite(join(CONFIG_DIR, "last_profile"), name);
  return `Profile ${name} applied.`;
}

export function showStatus() {
  const pl1 = Math.floor(Number(safeRead(join(RAPL_PATH, "constraint_0_power_limit_uw")) || "0") / 1_000_000);
  const pl2 = Math.floor(Number(safeRead(join(RAPL_PATH, "constraint_1_power_limit_uw")) || "0") / 1_000_000);
  const fan = safeRead(FAN_BOOST_PATH);
  const ecPath = facerProfilePath();
  const ec = ecPath ? safeRead(ecPath) : "N/A";
  const facer = facerLoaded() ? "ACTIVE" : "MISSING";
  return { pl1, pl2, fan: fan === "1" ? "ON" : "OFF", ec, facer };
}

export function installService(profile = "balanced") {
  ensureRoot(["service", profile]);
  const bin = process.argv[1] ? execSync(`readlink -f "${process.argv[1]}"`, { encoding: "utf-8" }).trim() : process.execPath;
  const unit = `[Unit]
Description=Predator Power Manager
After=multi-user.target

[Service]
Type=oneshot
ExecStartPre=/bin/sleep 3
ExecStart=${bin} profile ${profile}
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
`;
  writeFileSync("/etc/systemd/system/predator-power.service", unit);
  execSync("systemctl daemon-reload");
  execSync("systemctl enable predator-power.service");
  execSync("systemctl start predator-power.service");
  return "Service installed.";
}

export function removeService() {
  ensureRoot(["service", "remove"]);
  try { execSync("systemctl stop predator-power.service"); } catch {}
  try { execSync("systemctl disable predator-power.service"); } catch {}
  try { rmSync("/etc/systemd/system/predator-power.service", { force: true }); } catch {}
  execSync("systemctl daemon-reload");
  return "Service removed.";
}
