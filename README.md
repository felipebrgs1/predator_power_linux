# Predator Power Manager (Acer Predator)

Controle de TDP (PL1/PL2) e Fan Boost para laptops Acer Predator no Linux. Ferramenta leve e eficiente com interface visual (TUI) e serviço de boot.

---

## Requisitos

- [Bun](https://bun.sh) instalado

## 🚀 Passo a Passo: Instalação no Sistema

Siga estas etapas para compilar e instalar o programa permanentemente no seu Linux:

### 1. Compilar o programa
```bash
bun install
bun run build
```
O arquivo final será gerado em `dist/predator-power` (binário único e independente).

### 2. Mover para o diretório de binários
Para que você possa rodar o comando `predator-power` de qualquer lugar, mova-o para `/usr/local/bin`:
```bash
sudo cp dist/predator-power /usr/local/bin/
sudo chmod +x /usr/local/bin/predator-power
```

### 3. Configurar inicialização automática (Boot)
Para garantir que o perfil de energia seja aplicado sempre que você ligar o laptop:

- **Via Interface Visual (Recomendado):** Digite `predator-power` no terminal e pressione a tecla **[S]**.
- **Via Comando Direto:** 
  ```bash
  sudo predator-power service
  ```
  Ou para remover:
  ```bash
  sudo predator-power service remove
  ```

---

## 🛠️ Como Usar

### Interface Visual (TUI)
Basta digitar o comando sem argumentos:
```bash
predator-power
```
*Dica: O programa usará `pkexec` para pedir sua senha caso não seja executado como root.*

### Comandos de Terminal
| Comando | Descrição |
|---------|-----------|
| `predator-power profile balanced` | Aplica perfil equilibrado (50W/65W) |
| `predator-power profile performance` | Aplica perfil performance (80W/115W) |
| `predator-power profile turbo` | Aplica perfil máximo (100W/140W + Fan Boost) |
| `predator-power service` | Ativa o serviço de boot |
| `predator-power service remove` | Remove o serviço de boot |

*Nota: A instalação/atualização do driver e o controle manual do Fan Boost são feitos pela interface TUI (atalhos **[D]** e **[F]**).*

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
- **[D]**: Instalar/Atualizar driver da comunidade Acer (facer).
- **[Q]**: Sair da interface.
