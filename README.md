# TDP Manager - Gerenciador de Potência Intel para Linux

Um gerenciador de TDP (Thermal Design Power) para processadores Intel 12ª geração (Alder Lake) no Linux, similar ao ThrottleStop do Windows.

**Desenvolvido para Acer Predator PT316-51s com Intel i7-12700H**

## 🎯 Problema Resolvido

No Linux, laptops Acer Predator ficam limitados a um TDP baixo (~35W) porque o **Embedded Controller (EC)** usa o modo "quiet" por padrão, mesmo com os limites RAPL configurados para valores maiores.

Este projeto:
1. **Controla o EC da Acer** via módulo `facer` (equivalente ao PredatorSense)
2. **Ajusta os limites RAPL** (PL1/PL2)
3. **Configura governor e EPP** do intel_pstate

## 📦 Arquivos

| Arquivo | Descrição |
|---------|-----------|
| `tdp-manager.sh` | Script CLI principal |
| `tdp-manager-gui.py` | Interface gráfica GTK3 |
| `benchmark.sh` | Benchmark de stress com monitoramento |
| `tdp-manager.desktop` | Atalho para menu |

## 🚀 Instalação

### 1. Instalar o módulo Acer Predator (obrigatório para desbloquear o TDP real)

```bash
# Instalar dependências
sudo pacman -S linux-headers rsync   # Arch
# OU
sudo apt install linux-headers-$(uname -r) rsync  # Debian/Ubuntu

# Clonar e instalar o módulo facer
git clone https://github.com/JafarAkhondali/acer-predator-turbo-and-rgb-keyboard-linux-module
cd acer-predator-turbo-and-rgb-keyboard-linux-module
chmod +x ./*.sh
sudo ./install_service.sh

# IMPORTANTE: Editar o service.sh para adicionar predator_v4=1
sudo sed -i 's|insmod .*/facer.ko$|& predator_v4=1|' /opt/turbo-fan/service.sh
```

### 2. Instalar o TDP Manager

```bash
# Clone este repositório
git clone https://github.com/seu-usuario/tdp-manager.git
cd tdp-manager

# Torne executável
chmod +x tdp-manager.sh benchmark.sh

# Teste
./tdp-manager.sh status

# Aplique o perfil de performance
sudo ./tdp-manager.sh profile performance

# Instale para aplicar no boot
sudo ./tdp-manager.sh service install performance
```

## 🎮 Perfis Disponíveis

| Perfil | PL1 | PL2 | EC Mode | Uso |
|--------|-----|-----|---------|-----|
| 🔇 Silent | 15W | 25W | quiet | Bateria, silêncio |
| ⚖️ Balanced | 60W | 80W | balanced | Uso diário |
| ⚡ Performance | 80W | 115W | balanced | Desenvolvimento |
| 🚀 Turbo | 100W | 140W | balanced | Gaming |
| 🔥 Extreme | 115W | 160W | balanced | Benchmarks |

## 📋 Comandos

```bash
# Ver status completo
./tdp-manager.sh status

# Aplicar perfil
sudo ./tdp-manager.sh profile performance

# Monitorar em tempo real
./tdp-manager.sh monitor

# Valores personalizados
sudo ./tdp-manager.sh set 70 100

# Controlar individualmente
sudo ./tdp-manager.sh governor performance
sudo ./tdp-manager.sh epp performance

# Instalar/remover serviço
sudo ./tdp-manager.sh service install performance
sudo ./tdp-manager.sh service remove

# Ajuda
./tdp-manager.sh help
```

## 📊 Benchmark

```bash
# Executar stress test de 30 segundos
./benchmark.sh 30
```

Exemplo de saída:
```
╔════════════════════════════════════════════════════════════════╗
║          Mini CPU Benchmark - Intel i7-12700H                 ║
╠════════════════════════════════════════════════════════════════╣
║ Duration: 30s | CPUs: 20 | Governor: performance
╚════════════════════════════════════════════════════════════════╝

Time   | Temp  | Freq (P-Core) | Power | Status
  1s   |  81°C | 4.10 GHz     |  75W  | Running
  ...
```

## 🖥️ Interface Gráfica

```bash
# Instalar dependências (Arch)
sudo pacman -S python-gobject gtk3

# Executar
python3 tdp-manager-gui.py
```

## ⚙️ Como Funciona

### Níveis de controle:

1. **Acer EC (Embedded Controller)** - O limitador REAL
   - Controlado via módulo `facer`
   - Modos: `quiet` (35W), `balanced` (60-80W+)
   - Equivalente ao PredatorSense no Windows

2. **Intel RAPL** - Limites de software
   - `/sys/class/powercap/intel-rapl/`
   - PL1 (sustentado) e PL2 (burst)

3. **Intel P-State** - Governor e EPP
   - `performance` vs `powersave`
   - EPP controla agressividade do boost

### Arquitetura:

```
┌─────────────────────────────────────────────────────────────┐
│                    TDP Manager                              │
├─────────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐       │
│  │   Acer EC    │  │  Intel RAPL  │  │ Intel Pstate │       │
│  │   (facer)    │  │  (PL1/PL2)   │  │ (Gov/EPP)    │       │
│  └──────────────┘  └──────────────┘  └──────────────┘       │
│         │                 │                 │               │
│         ▼                 ▼                 ▼               │
│  ┌─────────────────────────────────────────────────────┐    │
│  │              CPU Power/Performance                  │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

## 🐛 Troubleshooting

### "Acer EC: unavailable"
Isso ocorre quando o módulo `facer` não expõe a interface de controle do perfil. Para corrigir:

1. **Recompilar o módulo**:
   ```bash
   cd acer-predator-turbo-and-rgb-keyboard-linux-module
   make
   ```

2. **Instalar com o parâmetro correto**:
   ```bash
   # Copiar para o diretório de módulos do kernel atual
   sudo mkdir -p /lib/modules/$(uname -r)/extra
   sudo cp src/facer.ko /lib/modules/$(uname -r)/extra/
   sudo depmod -a
   ```

3. **Configurar carregamento persistente**:
   ```bash
   # Definir parâmetro predator_v4=1 (Essencial para i7-12700H)
   echo "options facer predator_v4=1" | sudo tee /etc/modprobe.d/facer.conf
   
   # Carregar no boot
   echo "facer" | sudo tee /etc/modules-load.d/facer.conf
   ```

4. **Reiniciar ou carregar manualmente**:
   ```bash
   sudo modprobe facer
   ```

### Frequência ainda baixa após mudar perfil
```bash
# Verificar governor
cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor

# Deve ser "performance", se for "powersave":
sudo ./tdp-manager.sh governor performance
```

### Serviço não inicia no boot
```bash
# Verificar dependências
systemctl status turbo-fan  # Deve estar running
systemctl status tdp-manager

# Logs
journalctl -u tdp-manager -b
```

## 🔗 Dependências e Links

- [acer-predator-turbo-and-rgb-keyboard-linux-module](https://github.com/JafarAkhondali/acer-predator-turbo-and-rgb-keyboard-linux-module) - Módulo facer
- [Intel RAPL Documentation](https://www.kernel.org/doc/html/latest/power/powercap/powercap.html)
- [Arch Wiki - CPU frequency scaling](https://wiki.archlinux.org/title/CPU_frequency_scaling)

## 📄 Licença

MIT License - Use por sua conta e risco!

## 🤝 Compatibilidade

Testado em:
- **Acer Predator Triton 300 (PT316-51s)** - Intel i7-12700H
- Arch Linux 6.17.x

Deve funcionar em outros modelos Acer Predator suportados pelo módulo facer.
