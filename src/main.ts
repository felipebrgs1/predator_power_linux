import { readFileSync } from "fs";
import { execSync } from "child_process";
import {
  applyProfile,
  setFanBoost,
  showStatus,
  installFacer,
  facerLoaded,
  installService,
  removeService,
  isRoot,
} from "./power.js";

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
  const facer = facerLoaded();
  const warn = isRoot() ? "" : "  (!) Use sudo ou pkexec\n";
  process.stdout.write(
    "\x1Bc" +
    `  PREDATOR POWER MANAGER\n` +
    `  CPU: ${cpuNameCached}\n` +
    `  PL1: ${s.pl1}W  PL2: ${s.pl2}W  Fan: ${s.fan}  Mode: ${s.ec}\n` +
    `  Facer: ${facer ? "ACTIVE" : "MISSING"}\n` +
    warn +
    `\n` +
    `  [1] Balanced     50W/65W\n` +
    `  [2] Performance  75W/100W +Turbo OC\n` +
    `  [3] Turbo       100W/140W +Turbo OC\n` +
    `  [F]an  [D]river  [S]ervice  [Q]uit\n`
  );
}

function restore() {
  try { process.stdin.setRawMode(false); } catch {}
  process.stdin.pause();
}

function main() {
  if (!process.stdin.isTTY) {
    console.log("Not a TTY. Use: predator-power profile <name>");
    process.exit(1);
  }
  try { process.stdin.setRawMode(true); } catch {}
  process.stdin.resume();
  process.stdin.setEncoding("utf-8");

  process.on("SIGINT", () => { restore(); process.exit(0); });
  draw();

  process.stdin.on("data", (data: string) => {
    const key = data.toLowerCase();
    if (key === "q" || key === "\x1b" || key === "\x03") {
      restore();
      process.exit(0);
    } else if (key === "f") {
      setFanBoost(!showStatus().fan.includes("ON"));
      draw();
    } else if (key === "d") {
      restore();
      try { console.log(installFacer()); } catch (e: any) { console.error("Error:", e.message || e); }
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
    }
  });
}

main();
