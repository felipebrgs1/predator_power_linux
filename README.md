# Predator Power Manager

Controle de TDP (PL1/PL2) e Fan Boost para Acer Predator no Linux.

## Instalação

Baixe o binário na aba [Releases](../../releases) ou compile:

```bash
# Compilar localmente
./build.sh
sudo cp dist/predator-power /usr/local/bin/
```

## Uso

```bash
# Interface interativa
predator-power tui

# Comandos (pede senha automaticamente)
predator-power status
predator-power profile balanced
predator-power set 80 115
predator-power fanboost 1
```

## Perfis

| Perfil       | PL1   | PL2    |
|-------------|-------|--------|
| balanced    | 50W   | 65W    |
| performance | 80W   | 115W   |
| turbo       | 100W  | 140W   |

## Service (iniciar no boot)

```bash
predator-power service          # instala
predator-power service remove   # remove
```

## Build

```bash
./build.sh
```

## TUI

| Tecla | Ação                    |
|-------|------------------------|
| 1-3   | Aplicar perfil         |
| F     | Toggle Fan Boost       |
| S     | Toggle Auto Service    |
| R     | Refresh                |
| Q     | Sair                   |
