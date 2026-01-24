# 🛠️ Documentação Técnica - Predator Power Control

Este documento detalha a arquitetura e o funcionamento interno do sistema de controle térmico e de energia para laptops Acer Predator (Intel 12th Gen).

## 🏗️ Arquitetura do Sistema

O sistema é dividido em três camadas:

### 1. Backend (`tdp-manager.sh`)
O "motor" do sistema. É um script bash que interage diretamente com as interfaces do Kernel Linux:
*   **RAPL (Intel Power Capping)**: `/sys/class/powercap/intel-rapl/intel-rapl:0` - Controla os limites PL1 e PL2 em microwatts.
*   **CPUFreq**: `/sys/devices/system/cpu/cpu*/cpufreq/` - Gerencia o Governor e o EPP (Energy Performance Preference).
*   **Platform Profile (facer/acer_thermal_lite)**: `/sys/class/platform-profile/` - Comanda o EC (Embedded Controller) da Acer para mudar o modo térmico (incluindo o Turbo Fan).

### 2. Daemon de Monitoramento (`auto-turbo-daemon.py`)
Serviço Python em background que implementa a lógica térmica inteligente.
*   **Service**: Gerenciado via `systemd` (`auto-turbo.service`).
*   **Gatilhos**: Monitora CPU (via thermal_sys) e GPU (via `nvidia-smi`).
*   **Comunicação**: Lê o perfil desejado pelo usuário em `/tmp/tdp_desired_profile` para saber para qual modo retornar após o resfriamento.
*   **Histerese**: Implementa margem de 5°C para evitar oscilações rápidas (flapping) das ventoinhas.

### 3. Interface Gráfica (`tdp-manager-gui.py`)
Frontend em GTK3 que fornece controle visual ao usuário.
*   **Threaded Operations**: Aplicações de perfil rodam em threads separadas para não congelar a UI.
*   **Polinic**: Atualiza o status de temps e PL1/PL2 a cada 1 segundo.
*   **Service Control**: Ativa/Desativa o serviço `systemd` via subprocessos `pkexec`.

## 🛰️ Fluxo de Dados do Auto Turbo

1. O usuário seleciona "Balanced" no GUI.
2. O GUI escreve "balanced" em `/tmp/tdp_desired_profile`.
3. O Daemon detecta **CPU > 80°C**.
4. O Daemon executa `tdp-manager.sh profile turbo`.
5. O Daemon monitora até **CPU < 75°C**.
6. O Daemon lê "balanced" do arquivo de backup e executa `tdp-manager.sh profile balanced`.

## 📂 Localização de Arquivos Críticos

*   **Log do Core**: `/tmp/tdp-manager.log`
*   **Módulo de Kernel**: `acer_thermal_lite/acer_thermal_lite.ko`
*   **Unit do Systemd**: `/etc/systemd/system/auto-turbo.service`
*   **Comunicação IPC**: `/tmp/tdp_desired_profile`
