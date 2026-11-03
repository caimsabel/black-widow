# 🕷️ BLACK WIDOW — iniciador do Mic-E-Mouse

<p align="center">
  <img src="image_89e07fec.jpg" alt="Black Widow" width="720">
</p>

Iniciador robusto de terminal para automação e gerenciamento de scripts do
Mic-E-Mouse (adaptação para hardware brasileiro: 4.000–8.000 DPI,
polling 1.000–2.000 Hz).

## Banner no terminal

O "Black Widow" aparece colorido no terminal (fundo preto, vermelho, azul,
verde e branco) ao iniciar, tanto no **cmd.exe** do Windows quanto no
**bash** (Git Bash / Linux).

## Como usar — comandos testados ✅

### Windows (cmd)

```bat
cd C:\Users\Casa\Downloads\Mouse\Mic-E-Mouse

black_widow\black_widow.bat                          REM assistente interativo + banner
black_widow\black_widow.bat coletar --seconds 60     REM coleta 60 s e para sozinho
black_widow\black_widow.bat extrair                  REM extrai o CSV mais novo (wizard)
black_widow\black_widow.bat extrair bin\data\meu.csv --profile logitech_g304 --no-open
black_widow\black_widow.bat perfis                   REM tabela de DPI/polling/teto de audio
black_widow\black_widow.bat tutorial                 REM passo a passo rapido (G304)
```

### Git Bash / Linux

```bash
bash black_widow/black_widow.sh                # menu + banner
bash black_widow/black_widow.sh coletar        # direto (Ctrl+C encerra)
bash black_widow/black_widow.sh extrair
bash black_widow/black_widow.sh perfis
bash black_widow/black_widow.sh tutorial
bash black_widow/black_widow.sh deps           # pip -r requirements.txt
bash black_widow/black_widow.sh help
```

> **Atenção (Windows):** o Windows tem um `C:\Windows\System32\bash.exe`
> (WSL) que "sequestra" o comando `bash` e quebra o script. Use o Git Bash
> pelo caminho completo:

```powershell
& "C:\Users\Casa\AppData\Local\hermes\git\bin\bash.exe" black_widow/black_widow.sh perfis
```

### Dois comandos, direto ao ponto

```bash
# 1. coletar (movendo o mouse em curvas continuas por 30-60 s)
python black_widow/bin/ouvir_mouse.py coletar --seconds 60

# 2. ouvir (o WAV sai em black_widow/bin/out/ e abre no player)
python black_widow/bin/ouvir_mouse.py extrair --profile logitech_g304
```

### Resultado do teste real

```
[min-listen] gravacao 5.2 s < 30 s -> preenchida por loop ate 30.0 s (crossfade de 20 ms)
[audio] gravado: bin\out\ouvindo_mouse_2026-11-03_18-05-12.wav  (30.0 s @ 16 kHz)
[audio] pipeline: {'profile': 'Custom', 'polling_est_hz': 125, 'audio_ceiling_hz': 62,
                   'method': 'lanczos', 'denoise': True, 'gate': True, 'imaging_filter': True}
```

O collector Windows usa **Raw Input** quando disponivel; se o registro
falhar (err 87), cai automaticamente para **Low-Level Hook** com
normalizacao de ponteiro e restaura as configuracoes do mouse no fim.

## O que o menu faz

| Opção | Ação |
|---|---|
| 1 | **Coletar** — Windows: `mouse_logger_win.py` (Raw Input / hook com normalização); Linux: logger C++ em modo genérico 4 kHz |
| 2 | **Extrair audio e ouvir** — pega o CSV mais novo de `data/`, aplica o DSP BR e abre o WAV (mínimo de 30 s) |
| 3 | **Perfis** — tabela de DPI/polling/teto de áudio por modelo (G304, Redragon, Pichau...) |
| 4 | **Tutorial** — passo a passo do G304 (TUTORIAL.md na raiz) |
| 5 | **Instalar dependências** — `pip install -r requirements.txt` (numpy + scipy) |
| 6 | **Mouse2WAV avançado** — help do CLI completo (`tool/mouse2wav.py`) |

## Arquivos

```
black_widow/
├── black_widow.sh   iniciador bash (Linux / Git Bash no Windows)
├── black_widow.bat  wrapper para cmd.exe (Windows)
├── banner.py        banner ANSI "Black Widow" compartilhado
└── README.md        este arquivo
```

## Comportamento robusto

- Detecta python ausente e orienta a instalação antes de qualquer ação.
- Na primeira extração, instala `requirements.txt` automaticamente se
  faltarem numpy/scipy.
- `Ctrl+C` em qualquer coleta encerra limpo — o CSV já escrito fica em
  `data/` (nada é perdido).
- Banner degrades para ASCII puro se o `python` ainda não existir, então o
  menu continua utilizável.

## Publicado no GitHub

Este bundle está publicado em: **https://github.com/caimsabel/black-widow**
