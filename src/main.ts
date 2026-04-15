import {
  createCliRenderer,
  BoxRenderable,
  TextRenderable,
  SelectRenderable,
  SelectRenderableEvents,
} from "@opentui/core";
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
} from "./power.js";

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

function serviceActive(): boolean {
  try {
    const out = execSync("systemctl is-active predator-power", { encoding: "utf-8" });
    return out.trim() === "active";
  } catch {
    return false;
  }
}

async function main() {
  const renderer = await createCliRenderer({
    exitOnCtrlC: true,
    screenMode: "alternate-screen",
  });
  renderer.start();

  const root = renderer.root;
  root.flexDirection = "column";
  root.padding = 1;
  root.gap = 1;

  const header = new TextRenderable(renderer, {
    id: "header",
    content: " {bold}PREDATOR POWER MANAGER{/bold} ",
  });
  root.add(header);

  const statusBox = new BoxRenderable(renderer, {
    id: "statusBox",
    border: true,
    title: " Status ",
    padding: 1,
    flexDirection: "column",
    gap: 0,
  });
  root.add(statusBox);

  const cpuText = new TextRenderable(renderer, {
    id: "cpu",
    content: `CPU: ${cpuNameCached}`,
  });
  const plText = new TextRenderable(renderer, {
    id: "pl",
    content: "PL1: ?W  PL2: ?W",
  });
  const fanText = new TextRenderable(renderer, {
    id: "fan",
    content: "Fan Boost: ?",
  });
  const ecText = new TextRenderable(renderer, {
    id: "ec",
    content: "EC: N/A  Facer: ?",
  });

  statusBox.add(cpuText);
  statusBox.add(plText);
  statusBox.add(fanText);
  statusBox.add(ecText);

  const actions = new SelectRenderable(renderer, {
    id: "actions",
    options: [
      { name: "Balanced", description: "PL1=50W PL2=65W", value: "balanced" },
      { name: "Performance", description: "PL1=80W PL2=115W", value: "performance" },
      { name: "Turbo", description: "PL1=100W PL2=140W + Fan Boost", value: "turbo" },
      { name: "Toggle Fan Boost", description: "Liga/desliga ventoinha turbo", value: "fan" },
      { name: "Install Driver", description: "Instala driver Acer (facer)", value: "driver" },
      { name: "Toggle Boot Service", description: "Ativa/desativa serviço de boot", value: "service" },
      { name: "Quit", description: "Sair", value: "quit" },
    ],
    wrapSelection: true,
    border: true,
    title: " Actions ",
    flexGrow: 1,
  });
  root.add(actions);

  actions.focus();

  const updateStatus = async () => {
    const s = showStatus();
    plText.content = `PL1: {yellow}${s.pl1}W{/yellow}  PL2: {yellow}${s.pl2}W{/yellow}`;
    fanText.content = `Fan Boost: ${s.fan === "ON" ? "{green}" + s.fan + "{/green}" : "{yellow}" + s.fan + "{/yellow}"}`;
    ecText.content = `EC: {cyan}${s.ec}{/cyan}  Facer: ${s.facer === "ACTIVE" ? "{green}" + s.facer + "{/green}" : "{red}" + s.facer + "{/red}"}`;
    renderer.requestRender();
  };

  await updateStatus();
  const interval = setInterval(updateStatus, 1000);

  actions.on(SelectRenderableEvents.ITEM_SELECTED, async (_index: number, option: any) => {
    const val = option.value;
    if (val === "quit") {
      clearInterval(interval);
      renderer.destroy();
      process.exit(0);
    } else if (val === "fan") {
      setFanBoost(!showStatus().fan.includes("ON"));
    } else if (val === "driver") {
      installFacer();
    } else if (val === "service") {
      if (await serviceActive()) {
        removeService();
      } else {
        installService();
      }
    } else {
      applyProfile(val);
    }
    setTimeout(updateStatus, 300);
  });
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
