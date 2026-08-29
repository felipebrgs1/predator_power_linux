import { spawn, execSync } from "child_process";
import { existsSync, mkdirSync, writeFileSync, readFileSync, rmSync } from "fs";
import { join } from "path";
import { showStatus, showFanStatus, PROFILES } from "./power.js";
import dbus from "dbus-next";
// @ts-ignore deep import for bundling
import { Interface, ACCESS_READ } from "dbus-next/lib/service/interface.js";
// @ts-ignore
import { Variant } from "dbus-next/lib/variant.js";

const BUS_NAME_PREFIX = "org.kde.StatusNotifierItem";
const OBJECT_PATH = "/StatusNotifierItem";
const MENU_PATH = "/StatusNotifierItem/menu";
const WATCHER_BUS = "org.kde.StatusNotifierWatcher";
const WATCHER_PATH = "/StatusNotifierWatcher";
const WATCHER_IFACE = "org.kde.StatusNotifierWatcher";

const ICONS: Record<string, string> = {
  balanced: "power-profile-balanced",
  performance: "power-profile-performance",
  turbo: "power-profile-performance",
  fallback: "preferences-system-power",
};

function currentProfileFromStatus(): string {
  try {
    const s = showStatus();
    for (const [name, p] of Object.entries(PROFILES)) {
      if (s.pl1 === p.pl1 && s.pl2 === p.pl2) return name;
    }
    // fallback: thermal_profile (0=balanced,2=performance,3=turbo)
    try {
      const tp = readFileSync("/sys/devices/platform/predator-power/thermal_profile", "utf-8").trim();
      const map: Record<string, string> = { "0": "balanced", "1": "balanced", "2": "performance", "3": "turbo", "4": "balanced" };
      if (map[tp]) return map[tp];
    } catch {}
    const cfg = join(process.env.HOME || "", ".config/predator-power/last_profile");
    if (existsSync(cfg)) {
      const v = readFileSync(cfg, "utf-8").trim();
      if (v && PROFILES[v]) return v;
    }
  } catch {}
  return "balanced";
}

function iconForProfile(profile: string): string {
  return ICONS[profile] || ICONS.fallback;
}

function runProfileAction(profile: string) {
  const exe = process.execPath;
  const script = process.argv[1] || "";
  // tray runs as user, need pkexec/sudo for power controls
  // try pkexec predator-power profile X (compiled binary path)
  // if running via bun, use bun + script; if compiled, use exe
  const isCompiled = !script.endsWith(".ts") || exe.endsWith("predator-power");
  const cmd = isCompiled ? [exe, "profile", profile] : [exe, script, "profile", profile];
  try {
    execSync("which pkexec", { stdio: "ignore" });
    spawn("pkexec", cmd, { stdio: "inherit", detached: true });
  } catch {
    spawn("sudo", cmd, { stdio: "inherit", detached: true });
  }
}

function runFanMode(mode: number) {
  const exe = process.execPath;
  const script = process.argv[1] || "";
  const isCompiled = !script.endsWith(".ts") || exe.endsWith("predator-power");
  const cmd = isCompiled ? [exe, "fan", "mode", String(mode)] : [exe, script, "fan", "mode", String(mode)];
  try {
    execSync("which pkexec", { stdio: "ignore" });
    spawn("pkexec", cmd, { stdio: "inherit", detached: true });
  } catch {
    spawn("sudo", cmd, { stdio: "inherit", detached: true });
  }
}

function notify(title: string, body: string) {
  try {
    spawn("notify-send", [title, body], { stdio: "ignore", detached: true }).unref();
  } catch {}
}

// --- StatusNotifierItem Interface ---
class StatusNotifierItem extends Interface {
  Category = "ApplicationStatus";
  ItemIsMenu = true;
  Id = "predator-power";
  Title = "Predator Power";
  Status = "Active";
  WindowId = 0;
  IconName = iconForProfile(currentProfileFromStatus());
  OverlayIconName = "";
  AttentionIconName = "";
  AttentionMovieName = "";
  IconThemePath = "";
  ToolTip = ["", [], "Predator Power", "Balanced"] as any;
  Menu = MENU_PATH;

  constructor() {
    super("org.kde.StatusNotifierItem");
  }

  ContextMenu(_x: number, _y: number) {
    // direito -> menu nativo do Plasma (host já mostra menu ao chamar este método)
  }
  Activate(_x: number, _y: number) {
    // esquerdo: no Plasma 6, Category=ApplicationStatus faz o host mostrar o menu no esquerdo também.
    // Mantemos um fallback útil: clique esquerdo cicla perfil (balanced → performance → turbo) e notifica.
    // Se o host já mostrou o menu, o ciclo ainda acontece mas é inofensivo; usuário pode usar direito para menu.
    try {
      const cur = currentProfileFromStatus();
      const order = ["balanced", "performance", "turbo"];
      const next = order[(order.indexOf(cur) + 1) % order.length];
      // Em vez de ciclar sempre, apenas notifica se o usuário segurou? Para não confundir,
      // vamos apenas mostrar status no esquerdo e deixar o menu para o direito, mas com Category=ApplicationStatus
      // o Plasma já abre o menu no esquerdo. Então só notifica.
      const s = showStatus();
      const f = showFanStatus();
      notify("Predator Power", `${cur} • PL1 ${s.pl1}W PL2 ${s.pl2}W • Fan ${f.mode === "2" ? "Turbo" : "Auto"} (${f.cpuRpm}/${f.gpuRpm})`);
    } catch {}
  }
  SecondaryActivate(_x: number, _y: number) {}
  Scroll(_delta: number, _orientation: string) {}

  // signals
  NewIcon() { return; }
  NewAttentionIcon() { return; }
  NewOverlayIcon() { return; }
  NewToolTip() { return; }
  NewStatus(_status: string) { return; }
}

(StatusNotifierItem as any).configureMembers({
  properties: {
    Category: { signature: "s", access: ACCESS_READ },
    Id: { signature: "s", access: ACCESS_READ },
    Title: { signature: "s", access: ACCESS_READ },
    Status: { signature: "s", access: ACCESS_READ },
    WindowId: { signature: "u", access: ACCESS_READ },
    IconName: { signature: "s", access: ACCESS_READ },
    OverlayIconName: { signature: "s", access: ACCESS_READ },
    AttentionIconName: { signature: "s", access: ACCESS_READ },
    AttentionMovieName: { signature: "s", access: ACCESS_READ },
    IconThemePath: { signature: "s", access: ACCESS_READ },
    ToolTip: { signature: "(sa(iiay)ss)", access: ACCESS_READ },
    Menu: { signature: "o", access: ACCESS_READ },
    ItemIsMenu: { signature: "b", access: ACCESS_READ },
  },
  methods: {
    ContextMenu: { inSignature: "ii", outSignature: "" },
    Activate: { inSignature: "ii", outSignature: "" },
    SecondaryActivate: { inSignature: "ii", outSignature: "" },
    Scroll: { inSignature: "is", outSignature: "" },
  },
  signals: {
    NewIcon: { signature: "" },
    NewAttentionIcon: { signature: "" },
    NewOverlayIcon: { signature: "" },
    NewToolTip: { signature: "" },
    NewStatus: { signature: "s" },
  },
});

// --- DBusMenu Interface ---
// spec: https://specifications.freedesktop.org/dbusmenu-spec/latest/
type MenuItem = {
  id: number;
  label?: string;
  type?: string;
  enabled: boolean;
  visible: boolean;
  toggleType?: string;
  toggleState?: number;
  iconName?: string;
  childrenDisplay?: string;
};

let menuRevision = 1;
let trayUpdate: (() => void) | null = null;

function buildMenuProps(): Map<number, Map<string, any>> {
  const profile = currentProfileFromStatus();
  const fan = showFanStatus();
  const isFanTurbo = fan.mode === "2";

  const items: [number, any][] = [
    [0, { "type": new Variant("s", "standard"), "label": new Variant("s", "Predator Power"), "enabled": new Variant("b", false), "visible": new Variant("b", true), "children-display": new Variant("s", "submenu") }],
    [1, { "label": new Variant("s", "Balanced  (50W / 65W)"), "enabled": new Variant("b", true), "visible": new Variant("b", true), "toggle-type": new Variant("s", "radio"), "toggle-state": new Variant("i", profile === "balanced" ? 1 : 0), "icon-name": new Variant("s", "power-profile-balanced") }],
    [2, { "label": new Variant("s", "Performance  (75W / 100W)"), "enabled": new Variant("b", true), "visible": new Variant("b", true), "toggle-type": new Variant("s", "radio"), "toggle-state": new Variant("i", profile === "performance" ? 1 : 0), "icon-name": new Variant("s", "power-profile-performance") }],
    [3, { "label": new Variant("s", "Turbo  (100W / 140W + OC)"), "enabled": new Variant("b", true), "visible": new Variant("b", true), "toggle-type": new Variant("s", "radio"), "toggle-state": new Variant("i", profile === "turbo" ? 1 : 0), "icon-name": new Variant("s", "power-profile-performance") }],
    [10, { "type": new Variant("s", "separator"), "visible": new Variant("b", true) }],
    [5, { "label": new Variant("s", "Fan: Auto"), "enabled": new Variant("b", true), "visible": new Variant("b", true), "toggle-type": new Variant("s", "radio"), "toggle-state": new Variant("i", !isFanTurbo ? 1 : 0) }],
    [6, { "label": new Variant("s", "Fan: Turbo"), "enabled": new Variant("b", true), "visible": new Variant("b", true), "toggle-type": new Variant("s", "radio"), "toggle-state": new Variant("i", isFanTurbo ? 1 : 0) }],
    [11, { "type": new Variant("s", "separator"), "visible": new Variant("b", true) }],
    [7, { "label": new Variant("s", "Mostrar status"), "enabled": new Variant("b", true), "visible": new Variant("b", true), "icon-name": new Variant("s", "dialog-information") }],
    [8, { "label": new Variant("s", "Sair da bandeja"), "enabled": new Variant("b", true), "visible": new Variant("b", true), "icon-name": new Variant("s", "application-exit") }],
  ];
  const map = new Map<number, Map<string, any>>();
  for (const [id, props] of items) {
    map.set(id, new Map(Object.entries(props)));
  }
  return map;
}

function layoutForProps(): any {
  // children of root - each must be a Variant("(ia{sv}av)", [id, props, children])
  const children = [1, 2, 3, 10, 5, 6, 11, 7, 8].map(id => {
    const props = buildMenuProps().get(id)!;
    const dict: any = {};
    for (const [k, v] of props.entries()) dict[k] = v;
    return new Variant("(ia{sv}av)", [id, dict, []]);
  });

  const rootProps: any = {
    "type": new Variant("s", "standard"),
    "label": new Variant("s", "root"),
    "children-display": new Variant("s", "submenu"),
    "visible": new Variant("b", true),
  };

  return [menuRevision, [0, rootProps, children]];
}

class DBusMenu extends Interface {
  Version = 3;
  TextDirection = "ltr";
  Status: string = "normal";
  IconThemePath = "";

  constructor() {
    super("com.canonical.dbusmenu");
  }

  GetLayout(_parentId: number, _recursionDepth: number, _propertyNames: string[]) {
    return layoutForProps();
  }

  GetGroupProperties(ids: number[], _propertyNames: string[]) {
    const all = buildMenuProps();
    const result: any[] = [];
    for (const id of ids) {
      const props = all.get(id);
      if (props) {
        const dict: any = {};
        for (const [k, v] of props.entries()) dict[k] = v;
        result.push([id, dict]);
      } else {
        result.push([id, {}]);
      }
    }
    return result;
  }

  GetProperties(id: number, _propertyNames: string[]) {
    const all = buildMenuProps();
    const props = all.get(id);
    if (!props) return {};
    const dict: any = {};
    for (const [k, v] of props.entries()) dict[k] = v;
    return dict;
  }

  Event(id: number, eventId: string, _data: any, _timestamp: number) {
    if (eventId !== "clicked") return;
    if (id === 1) { runProfileAction("balanced"); notify("Predator Power", "Perfil Balanced aplicado"); }
    else if (id === 2) { runProfileAction("performance"); notify("Predator Power", "Perfil Performance aplicado"); }
    else if (id === 3) { runProfileAction("turbo"); notify("Predator Power", "Perfil Turbo aplicado"); }
    else if (id === 5) { runFanMode(1); notify("Predator Power", "Fan: Auto"); }
    else if (id === 6) { runFanMode(2); notify("Predator Power", "Fan: Turbo"); }
    else if (id === 7) {
      try {
        const s = showStatus();
        const f = showFanStatus();
        notify("Predator Power", `PL1 ${s.pl1}W PL2 ${s.pl2}W | ${s.ec} | Fan ${f.mode} CPU ${f.cpuRpm} GPU ${f.gpuRpm}`);
      } catch {}
    }
    else if (id === 8) {
      notify("Predator Power", "Saindo da bandeja");
      setTimeout(() => process.exit(0), 300);
    }
    // bump revision for next layout
    menuRevision++;
    // força refresh rápido (pkexec é assíncrono, hardware muda em ~1s)
    setTimeout(() => { try { trayUpdate?.(); } catch {} }, 800);
    setTimeout(() => { try { trayUpdate?.(); } catch {} }, 2000);
  }

  EventGroup(_events: any[]) { return []; }
  AboutToShow(_id: number) { return false; }
  AboutToShowGroup(_ids: number[]) { return [false, []]; }

  // signals
  LayoutUpdated(_revision: number, _parent: number) { return; }
  ItemsPropertiesUpdated(_updatedProps: any, _removedProps: any) { return; }
}

(DBusMenu as any).configureMembers({
  properties: {
    Version: { signature: "u", access: ACCESS_READ },
    TextDirection: { signature: "s", access: ACCESS_READ },
    Status: { signature: "s", access: ACCESS_READ },
    IconThemePath: { signature: "s", access: ACCESS_READ },
  },
  methods: {
    GetLayout: { inSignature: "iias", outSignature: "u(ia{sv}av)" },
    GetGroupProperties: { inSignature: "aias", outSignature: "a(ia{sv})" },
    GetProperties: { inSignature: "ias", outSignature: "a{sv}" },
    Event: { inSignature: "isvu", outSignature: "" },
    EventGroup: { inSignature: "a(isvu)", outSignature: "a(isvu)" },
    AboutToShow: { inSignature: "i", outSignature: "b" },
    AboutToShowGroup: { inSignature: "ai", outSignature: "ab" },
  },
  signals: {
    LayoutUpdated: { signature: "ui" },
    ItemsPropertiesUpdated: { signature: "a(ia{sv})a(ias)" },
  },
});

export function installTrayAutostart() {
  const autostartDir = join(process.env.HOME || "", ".config/autostart");
  mkdirSync(autostartDir, { recursive: true });
  const exe = process.execPath;
  const script = process.argv[1] || "";
  const isCompiled = existsSync("/usr/local/bin/predator-power") || !script.endsWith(".ts");
  const execLine = isCompiled
    ? (existsSync("/usr/local/bin/predator-power") ? "/usr/local/bin/predator-power tray" : `${exe} tray`)
    : `${exe} ${script} tray`;
  const desktop = `[Desktop Entry]
Name=Predator Power Tray
Comment=Controle de TDP e perfis Predator na bandeja
Exec=${execLine}
Icon=preferences-system-power
Type=Application
Categories=System;Settings;
X-GNOME-Autostart-enabled=true
X-KDE-autostart-after=panel
StartupNotify=false
Terminal=false
`;
  const path = join(autostartDir, "predator-power-tray.desktop");
  writeFileSync(path, desktop);
  return path;
}

export function removeTrayAutostart() {
  const path = join(process.env.HOME || "", ".config/autostart/predator-power-tray.desktop");
  if (existsSync(path)) rmSync(path);
  return path;
}

export async function startTray() {
  const bus = dbus.sessionBus();
  // single-instance: try stable name first
  const STABLE_NAME = "org.kde.StatusNotifierItem-predator-power";
  try {
    const reply = await (bus as any).requestName(STABLE_NAME, 0x4); // DO_NOT_QUEUE
    if (reply === 2 /* EXISTS */ || reply === 3 /* ALREADY_OWNER */) {
      // another instance already owns stable name -> check if actually running
    }
    // if we got 1 (PRIMARY_OWNER) we own it, but we still use unique name for SNI spec
  } catch {}
  const pid = process.pid;
  const busName = `${BUS_NAME_PREFIX}-${pid}-${Math.floor(Math.random() * 10000)}`;
  try {
    await (bus as any).requestName(busName, 0x4);
  } catch (e: any) {
    console.error("Falha ao registrar bus name:", e.message || e);
    process.exit(1);
  }

  const sni = new StatusNotifierItem();
  const menu = new DBusMenu();

  // Export objects
  (bus as any).export(OBJECT_PATH, sni);
  (bus as any).export(MENU_PATH, menu);

  // Register with watcher
  async function register() {
    try {
      const obj = await bus.getProxyObject(WATCHER_BUS, WATCHER_PATH);
      const watcher = obj.getInterface(WATCHER_IFACE);
      await watcher.RegisterStatusNotifierItem(busName);
      console.log(`[tray] Registrado como ${busName} em ${WATCHER_BUS}`);
    } catch (e: any) {
      // Fallback: try legacy StatusNotifierWatcher path or notify
      console.error("[tray] Falha ao registrar no watcher:", e?.message || e);
      console.log("[tray] Tentando registrar via dbus-send...");
      try {
        execSync(`dbus-send --session --dest=${WATCHER_BUS} --type=method_call ${WATCHER_PATH} ${WATCHER_IFACE}.RegisterStatusNotifierItem string:${busName}`, { stdio: "ignore" });
        console.log("[tray] Registrado via dbus-send");
      } catch {}
    }
  }

  await register();

  // Poll status to update icon/tooltip/checkmarks
  let lastProfile = currentProfileFromStatus();
  let lastIcon = iconForProfile(lastProfile);
  let lastFanMode = "";
  try { lastFanMode = showFanStatus().mode; } catch {}

  function updateIfNeeded() {
    const profile = currentProfileFromStatus();
    const s = showStatus();
    const f = showFanStatus();
    const fanMode = f.mode;
    const icon = iconForProfile(profile);
    const tooltip: any = ["", [], "Predator Power", `${profile} • PL1 ${s.pl1}W PL2 ${s.pl2}W • Fan ${fanMode === "2" ? "Turbo" : "Auto"}`];

    let changed = false;
    if (icon !== sni.IconName) {
      (sni as any).IconName = icon;
      (Interface as any).emitPropertiesChanged(sni, { IconName: icon });
      try { (sni as any).NewIcon(); } catch {}
      changed = true;
    }
    if (profile !== lastProfile || icon !== lastIcon || fanMode !== lastFanMode) {
      (sni as any).ToolTip = tooltip as any;
      (Interface as any).emitPropertiesChanged(sni, { ToolTip: tooltip });
      try { (sni as any).NewToolTip(); } catch {}
      // menu items changed -> notify layout
      menuRevision++;
      try { (menu as any).LayoutUpdated(menuRevision, 0); } catch {}
      // batch property update for menu radios
      try {
        const updated: any[] = [];
        for (const id of [1, 2, 3, 5, 6]) {
          const props = buildMenuProps().get(id);
          if (props) {
            const dict: any = {};
            for (const [k, v] of props.entries()) dict[k] = v;
            updated.push([id, dict]);
          }
        }
        (menu as any).ItemsPropertiesUpdated(updated, []);
      } catch {}
      changed = true;
    }
    lastProfile = profile;
    lastIcon = icon;
    lastFanMode = fanMode;
    if (changed) {
      // console.log(`[tray] update -> ${profile} icon ${icon} fan ${fanMode}`);
    }
  }

  trayUpdate = updateIfNeeded;
  setInterval(updateIfNeeded, 2000);
  updateIfNeeded();

  console.log(`[tray] Predator Power na bandeja (Plasma 6 Wayland)`);
  console.log(`[tray] Clique no ícone para trocar perfil. Use --autostart para iniciar com o sistema.`);
  console.log(`[tray] Perfis: balanced | performance | turbo | Fan Auto/Turbo`);
  console.log(`[tray] PID ${pid} | Bus ${busName} | Pressione Ctrl+C para sair`);

  // keep alive
  process.on("SIGINT", () => { console.log("\n[tray] Saindo..."); process.exit(0); });
  process.on("SIGTERM", () => process.exit(0));

  // prevent exit
  await new Promise(() => {});
}
