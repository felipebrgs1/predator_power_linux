# 🚀 Predator TDP Manager - Guia de Uso

Este utilitário permite controlar o consumo de energia (TDP), perfis de performance e fans do seu Acer Predator no Linux.

## ✨ Funcionalidades Principais

*   **Perfis de Energia**: Alteração rápida entre modos Silent, Balanced, Performance e Extreme.
*   **Controle de TDP**: Ajuste manual dos limites PL1 e PL2 do processador Intel.
*   **Auto Turbo (Background)**: Monitoramento inteligente que liga as ventoinhas no máximo quando o PC esquenta e volta ao normal quando esfria.

## 🌡️ Como funciona o Auto Turbo?

O sistema monitora a temperatura constantemente em segundo plano:
*   **CPU >= 80°C** ou **GPU >= 70°C**: Ativa o modo **Turbo** (Fans no Máximo).
*   **CPU < 75°C** e **GPU < 65°C**: Retorna ao perfil que você estava usando antes.

## 🚀 Passo a Passo (Início Rápido)

Siga estas etapas para configurar tudo no seu Predator:

### 1. Preparar o Módulo de Kernel
O módulo `acer_thermal_lite` é o que permite ao Linux conversar com o hardware da Acer:
```bash
sudo ./tdp-manager.sh facer build
```

### 2. Configurar o Atalho (Opcional)
Se quiser que o gerenciador apareça no seu menu de aplicativos:
```bash
# Permissão de execução para os scripts
chmod +x tdp-manager.sh tdp-manager-gui.py auto-turbo-daemon.py
```

### 3. Abrir a Interface Gráfica
```bash
./tdp-manager-gui.py
```

### 4. Ativar o Auto Turbo
Na interface, ligue a chave **"Background Auto Turbo"**. 
*   Isso vai pedir sua senha para criar e iniciar o serviço de sistema.
*   Uma vez ativado, o monitoramento de 80°C/70°C funcionará sempre, mesmo após reiniciar o PC.

---

## 🛠️ Como usar a Interface (GUI)

1.  **Escolher Perfil**: Clique nos botões (Silent, Balanced, etc) para aplicar uma configuração pré-definida.
2.  **Ajuste Manual**: Use os sliders para definir um PL1/PL2 customizado e clique em "Apply".
3.  **Background Auto Turbo**: Ligue esta chave para ativar o serviço automático de ventoinhas. **Uma vez ligado, você pode fechar a janela que ele continuará funcionando.**
4.  **Keep Applied**: Se ativado, o sistema impede que o hardware baixe seu TDP sozinho (Anti-Throttle).

## ⚠️ Requisitos
*   Utilize o botão de "Auto Turbo" na interface para ativar o serviço de fundo.
*   É necessária a senha de administrador (sudo) para aplicar as alterações de hardware.

---

## 📖 Documentação Adicional
Para detalhes sobre a arquitetura do sistema, scripts de backend e funcionamento dos serviços, consulte a [Documentação Técnica](doc/TECHNICAL_INFO.md).

---

## 🤝 Créditos e Agradecimentos
Este projeto foi baseado e utiliza conceitos fundamentais do módulo [facer](https://github.com/JafarAkhondali/acer-predator-turbo-and-rgb-keyboard-linux-module), desenvolvido por Jafar Akhondali. O controle do Embedded Controller (EC) da Acer para laptops Predator no Linux só é possível graças ao excelente trabalho de engenharia reversa realizado nesse projeto original.
