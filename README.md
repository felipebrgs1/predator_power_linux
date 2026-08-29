# Predator Power Manager (Acer Predator)

Controle de TDP (PL1/PL2), perfil térmico, Fan Boost e Turbo OC para laptops Acer Predator no Linux.

## Instalação

```bash
git clone https://github.com/seu-repo/predator_power_linux
cd predator_power_linux
bun install
bun run build
sudo cp dist/predator-power /usr/local/bin/
```

## Uso

### Bandeja do sistema (KDE Plasma 6 - Wayland/X11)
```bash
predator-power tray                 # inicia na bandeja (ícone perto do relógio)
predator-power tray --autostart     # iniciar automaticamente com o sistema
predator-power tray --no-autostart  # remover autostart
```
Menu da bandeja:
- **Balanced / Performance / Turbo** (radio, mostra perfil ativo)
- **Fan: Auto / Turbo**
- **Mostrar status** (notificação com PL1/PL2, RPM)
- **Sair da bandeja**

> A troca de perfil usa `pkexec` e vai pedir senha. O ícone e tooltip atualizam a cada 2s.

Instalação do autostart + ícone:
```bash
bun run build
sudo cp dist/predator-power /usr/local/bin/
cp predator-power-tray.desktop ~/.config/autostart/
# ou: predator-power tray --autostart
```

### Interface interativa (TUI)
```bash
sudo predator-power
```
Teclas: **1 2 3** = perfis, **F** = fan/turbo, **D** = instalar driver, **S** = service boot, **Q** = sair

### Linha de comando
```bash
predator-power profile balanced    # 50W/65W
predator-power profile performance # 75W/100W
predator-power profile turbo      # 100W/140W + Turbo OC
predator-power fan status         # modo e RPM das ventoinhas
predator-power fan mode 2         # 1=auto, 2=turbo
predator-power fan probe 8        # testa modos 1/2 por 8s cada
predator-power fan curve 75 65    # turbo >=75°C, auto <=65°C
predator-power driver             # reinstala/recarrega o driver
predator-power service            # ativar boot automático
predator-power service remove     # remover boot
predator-power tray               # modo bandeja KDE
```

## Perfis

| Perfil | PL1 | PL2 | Turbo OC |
|--------|-----|-----|----------|
| Balanced | 50W | 65W | OFF |
| Performance | 75W | 100W | OFF |
| Turbo | 100W | 140W | ON |

## Requisitos

- Linux (testado em CachyOS, Arch)
- `linux-headers` (para compilar o driver `predator_power`)

## Driver

O projeto usa um driver próprio e mínimo, sem RGB de teclado:

- módulo: `predator_power`
- sysfs: `/sys/devices/platform/predator-power/`
- boot: `/etc/modules-load.d/predator_power.conf`

O botão **D** instala o módulo, remove o serviço legado `turbo-fan` se existir e deixa o driver carregando automaticamente no boot.

Sysfs exposto pelo driver:

- `thermal_profile`
- `turbo_oc`
- `fan_boost`
- `fan_mode`
- `cpu_fan_rpm`
- `gpu_fan_rpm`

`fan_mode` usa `1=auto` e `2=turbo`. O modo `3` foi bloqueado porque zerou as ventoinhas no teste real.
