import { readFileSync } from "fs";
import { execSync } from "child_process";
import {
  applyProfile,
  setFanBoost,
  showStatus,
  installDriver,
  driverLoaded,
  installService,
  removeService,
  isRoot,
  ensureRoot,
  thermalControl,
  stopThermalControl,
} from "./power.js";

function runThermalCLI() {
  const targetTemp = parseInt(process.argv[3] || "80");
  const maxPL1 = parseInt(process.argv[4] || "80");
  const minPL = parseInt(process.argv[5] || "40");
  const maxPL2 = maxPL1;
  if (!ensureRoot(["thermal", String(targetTemp), String(maxPL1), String(minPL)])) process.exit(0);
  process.stdin.resume();
  process.stdin.setEncoding("utf-8");
  try { process.stdin.setRawMode(true); } catch {}
  console.log(applyProfile("performance"));
  const result = thermalControl(targetTemp, maxPL1, maxPL2, (temp, pl1, pl2) => {
    process.stdout.write(`\rTemp: ${temp.toFixed(1)}°C | PL1: ${pl1}W PL2: ${pl2}W | Target: ${targetTemp}°C | [Q]uit  `);
  }, minPL);
  process.stdout.write("\n" + result + "\n");
  process.stdin.on("data", (data: string) => {
    if (data.toLowerCase() === "q" || data === "\x03") {
      stopThermalControl();
      try { process.stdin.setRawMode(false); } catch {}
      process.stdin.pause();
      process.exit(0);
    }
  });
}

const cmd = process.argv[2];
if (cmd === "service") {
  const action = process.argv[3];
  if (action === "remove") {
    console.log(removeService());
  } else {
    console.log(installService(action || "balanced"));
  }
  process.exit(0);
} else if (cmd === "profile") {
  const profile = process.argv[3] || "balanced";
  console.log(applyProfile(profile));
  process.exit(0);
} else if (cmd === "thermal") {
  runThermalCLI();
}

let cpuNameCached = "Unknown";
try {
  const cpuinfo = readFileSync("/proc/cpuinfo", "utf-8");
  for (const line of cpuinfo.split("\n")) {
    if (line.startsWith("model name")) {
      cpuNameCached = line.split(":")[1].trim();
      break;
    }
  }
} catch {}

function draw() {
  const s = showStatus();
  const driver = driverLoaded();
  const warn = isRoot() ? "" : "  (!) Use sudo ou pkexec\n";
  process.stdout.write(
    "\x1Bc" +
    `  PREDATOR POWER MANAGER\n` +
    `  CPU: ${cpuNameCached}\n` +
    `  PL1: ${s.pl1}W  PL2: ${s.pl2}W  Fan: ${s.fan}  Mode: ${s.ec}\n` +
    `  Driver: ${driver ? "ACTIVE" : "MISSING"}\n` +
    warn +
    `\n` +
    `  [1] Balanced     50W/65W\n` +
    `  [2] Performance  75W/100W\n` +
    `  [3] Turbo       100W/140W +Turbo OC\n` +
    `  [4] Thermal     40-80W range @80°C target\n` +
    `  [F]an  [D]river  [S]ervice  [Q]uit\n`
  );
}

function restore() {
  try { process.stdin.setRawMode(false); } catch {}
  process.stdin.pause();
}

function main() {
  if (cmd === "thermal") return;
  if (!process.stdin.isTTY) {
    console.log("Not a TTY. Use: predator-power profile <name>");
    process.exit(1);
  }
  try { process.stdin.setRawMode(true); } catch {}
  process.stdin.resume();
  process.stdin.setEncoding("utf-8");

  process.on("SIGINT", () => { stopThermalControl(); restore(); process.exit(0); });
  draw();

  let thermalModeActive = false;

  process.stdin.on("data", (data: string) => {
    const key = data.toLowerCase();

    if (thermalModeActive) {
      if (key === "q" || key === "\x1b" || key === "\x03") {
        stopThermalControl();
        thermalModeActive = false;
        draw();
      }
      return;
    }

    if (key === "q" || key === "\x1b" || key === "\x03") {
      restore();
      process.exit(0);
    } else if (key === "f") {
      setFanBoost(!showStatus().fan.includes("ON"));
      draw();
    } else if (key === "d") {
      restore();
      try { console.log(installDriver()); } catch (e: any) { console.error("Error:", e.message || e); }
      process.exit(0);
    } else if (key === "s") {
      restore();
      try {
        let active = false;
        try { const out = execSync("systemctl is-active predator-power", { encoding: "utf-8" }); active = out.trim() === "active"; } catch {}
        console.log(active ? removeService() : installService());
      } catch (e: any) { console.error("Error:", e.message || e); }
      process.exit(0);
    } else if (key === "1" || key === "2" || key === "3") {
      const profiles = ["balanced", "performance", "turbo"];
      const profile = profiles[parseInt(key) - 1];
      console.log(applyProfile(profile));
      draw();
    } else if (key === "4") {
      thermalModeActive = true;
      process.stdout.write("\x1Bc  THERMAL MODE (40-80W range @80°C target)\n\n");
      const result = thermalControl(80, 80, 80, (temp, pl1, pl2) => {
        process.stdout.write(`\rTemp: ${temp.toFixed(1)}°C | PL1: ${pl1}W PL2: ${pl2}W | Target: 80°C | [Q]uit  `);
      }, 40);
      if (result.includes("not found")) {
        process.stdout.write(result + "\n");
        thermalModeActive = false;
        setTimeout(draw, 2000);
      } else {
        process.stdout.write(result + "\n");
      }
    }
  });
}

main();
