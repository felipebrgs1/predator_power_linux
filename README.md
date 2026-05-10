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

### Interface interativa
```bash
sudo predator-power
```
Teclas: **1 2 3** = perfis, **F** = fan/turbo, **D** = instalar driver, **S** = service boot, **Q** = sair

### Linha de comando
```bash
predator-power profile balanced    # 50W/65W
predator-power profile performance # 75W/100W
predator-power profile turbo      # 100W/140W + Turbo OC
predator-power service            # ativar boot automático
predator-power service remove     # remover boot
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
