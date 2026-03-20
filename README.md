# Predator Power Manager (Acer Predator)

Controle de TDP (PL1/PL2) e Fan Boost para laptops Acer Predator no Linux. Ferramenta leve e eficiente com interface visual (TUI) e serviço de boot.

---

## 🚀 Passo a Passo: Instalação no Sistema

Siga estas etapas para compilar e instalar o programa permanentemente no seu Linux:

### 1. Compilar o programa
Certifique-se de ter o Python instalado e execute o script de build para gerar o binário único:
```bash
./build.sh
```
O arquivo final será gerado em `dist/predator-power`.

### 2. Mover para o diretório de binários
Para que você possa rodar o comando `predator-power` de qualquer lugar, mova-o para `/usr/local/bin`:
```bash
sudo cp dist/predator-power /usr/local/bin/
sudo chmod +x /usr/local/bin/predator-power
```

### 3. Configurar inicialização automática (Boot)
Para garantir que o perfil de energia seja aplicado sempre que você ligar o laptop:

- **Via Interface Visual (Recomendado):** Digite `predator-power` no terminal e pressione a tecla **[S]**. O status deve mudar para `Auto Service: ON`.
- **Via Comando Direto:** 
  ```bash
  sudo predator-power service
  ```

---

## 🛠️ Como Usar

### Interface Visual (TUI)
Basta digitar o comando sem argumentos (ou com `tui`):
```bash
predator-power
```
*Dica: O programa usará `pkexec` para pedir sua senha caso não seja executado como root.*

### Comandos de Terminal
| Comando | Descrição |
|---------|-----------|
| `predator-power status` | Mostra o TDP e Fan Boost atual |
| `predator-power profile balanced` | Aplica perfil equilibrado (50W/65W) |
| `predator-power profile turbo` | Aplica perfil máximo (100W/140W) |
| `predator-power fanboost 1` | Liga o Fan Boost (Turbo das ventoinhas) |
| `predator-power service remove` | Remove o serviço de boot |

---

## 📊 Perfis Pré-configurados

| Perfil | PL1 (Sustentado) | PL2 (Pico) | Fan Boost |
| :--- | :--- | :--- | :--- |
| **Balanced** | 50W | 65W | OFF |
| **Performance** | 80W | 115W | OFF |
| **Turbo** | 100W | 140W | **ON** |

---

## ⌨️ Atalhos da Interface (TUI)

- **[1], [2], [3]**: Alternar entre perfis.
- **[F]**: Ligar/Desligar Fan Boost (Turbo de ventoinha).
- **[S]**: Ativar/Desativar serviço de boot (Auto Service).
- **[R]**: Atualizar status manualmente.
- **[Q]**: Sair da interface.
