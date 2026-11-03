# 🕷️ BLACK WIDOW — iniciador do Mic-E-Mouse

Iniciador robusto de terminal para automação e gerenciamento de scripts do
Mic-E-Mouse (adaptação para hardware brasileiro: 4.000–8.000 DPI,
polling 1.000–2.000 Hz).

## Banner no terminal

O "Black Widow" aparece colorido no terminal (fundo preto, vermelho, azul,
verde e branco) ao iniciar, tanto no **cmd.exe** do Windows quanto no
**bash** (Git Bash / Linux).

## Como usar

### Windows (cmd)

```bat
cd C:\Users\Casa\Downloads\Mouse\Mic-E-Mouse
black_widow\black_widow.bat           REM menu + banner
black_widow\black_widow.bat extrair   REM direto: extrai o CSV mais novo
black_widow\black_widow.bat coletar   REM direto: coleta
```

### Git Bash / Linux

```bash
bash black_widow/black_widow.sh            # menu + banner
bash black_widow/black_widow.sh coletar    # direto
bash black_widow/black_widow.sh extrair
bash black_widow/black_widow.sh perfis
bash black_widow/black_widow.sh tutorial
bash black_widow/black_widow.sh deps       # pip -r requirements.txt
bash black_widow/black_widow.sh help
```

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

## Publicar no GitHub

A pasta é auto-contida e commitável junto com o resto do repositório:

```bash
git add black_widow/
git commit -m "feat: Black Widow bash launcher"
git push
```
