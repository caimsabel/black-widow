#!/usr/bin/env bash
# ==========================================================================
#  🕷️ BLACK WIDOW - iniciador do Mic-E-Mouse (Linux + Git Bash unificado)
#  Automacao e gerenciamento de scripts de colheita/audicao do mouse
#  (hardware BR: 4.000-8.000 DPI, polling 1-2 kHz)
#
#  Bonito no terminal:
#     bash black_widow/black_widow.sh            # menu
#     bash black_widow/black_widow.sh coletar    # Linux: logger C++ door CSV;
#                                                # Git-Bash: collector Windows
#     bash black_widow/black_widow.sh extrair    # audio direto do CSV novo
#     bash black_widow/black_widow.sh perfis | tutorial | help | deps
# ==========================================================================

set -o pipefail
# forgiving by design: menus do not die on a single failed action.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="${PYTHON:-python3}"
command -v "$PYTHON" >/dev/null 2>&1 || PYTHON=python
BIN="$SCRIPT_DIR/bin"                      # standalone tool bundle
DOCS="$SCRIPT_DIR/docs"                    # tutorial, upgrade readmes
MOUSES="$SCRIPT_DIR/mouses"                # hardware profiles data

# --------------------------------------------------------------------------
# colors (BLACK WIDOW identity)
# --------------------------------------------------------------------------
if [ -t 1 ]; then
    RED=$'\033[31m'; GRN=$'\033[32m'; BLU=$'\033[34m'; WHT=$'\033[37m'
    BOLD=$'\033[1m'; DIM=$'\033[2m';  RST=$'\033[0m'
else
    RED=; GRN=; BLU=; WHT=; BOLD=; DIM=; RST=
fi

say()  { printf '%s\n' "$*"; }
err()  { printf '%s[ERRO]%s %s\n' "$RED" "$RST" "$*" >&2; }
ok()   { printf '%s[OK]%s %s\n' "$GRN" "$RST" "$*"; }
warn() { printf '%s[AVISO]%s %s\n' "$RED" "$RST" "$*"; }
hr()   { printf '%s%s%s\n' "$DIM" "----------------------------------------------------------------" "$RST"; }

banner() {
    "$PYTHON" "$SCRIPT_DIR/banner.py" 2>/dev/null && return 0
    cat <<'NOBANNER'
 ______   _                     _         _    _  _       _
| ___ \ | |                   | |       | |  | |(_)     | |
| |_/ / | |  __ _   ___  | | __  | |  | | _   _  | |  ___   _   _   ___
| ___ \ | | / _` | / __| | |/ /  | |/\| || | | | | | / _ \ | | | | / __|
| |_/ / | | | (_| | | (__  |   <   \  /\  /| | |_| | | || (_) || |_| | \__ \
\____/  |_|  \__,_|  \___| |_|\_\   \/  \/ |_|\__,_|_|_| \___/  \__,_| |___/
# BLACK WIDOW -- iniciador Mic-E-Mouse
NOBANNER
}

# --------------------------------------------------------------------------
# checks
# --------------------------------------------------------------------------
check_python() {
    if ! command -v "$PYTHON" >/dev/null 2>&1; then
        err "python nao encontrado no PATH."
        say "  instale: python.org (Windows) / sudo apt install python3 python3-pip"
        return 1
    fi
    return 0
}

check_audio_deps() {
    check_python || return 1
    if ! "$PYTHON" -c "import numpy, scipy" >/dev/null 2>&1; then
        warn "numpy/scipy não instalados - instalando agora..."
        install_deps || { err "instale manualmente: $PYTHON -m pip install -r requirements.txt"; return 1; }
    fi
    return 0
}

install_deps() {
    check_python || return 1
    local req="$SCRIPT_DIR/../requirements.txt"
    [ -f "$req" ] || req="$SCRIPT_DIR/requirements.txt"
    "$PYTHON" -m pip install -r "$req" || return 1
    ok "dependencias instaladas"
}

# --------------------------------------------------------------------------
# actions
# --------------------------------------------------------------------------
act_collect() {
    mkdir -p "$BIN/data"
    if [ -n "${OS:-}" ] || [[ "$(uname -s)" == *MINGW* || "$(uname -s)" == *MSYS* ]]; then
        # Git-Bash on Windows: collector via raw input / hook fallback
        "$PYTHON" "$BIN/mouse_logger_win.py" "$@" \
            && ok "CSV gerado em ./bin/data/" \
            || warn "coleta interrompida (Ctrl+C e normal - o CSV fica todo em bin/data/)"
    else
        # Linux: logger C++ original (modo generico 4 kHz), CSV ja no bundle
        local PROJ="$(dirname "$SCRIPT_DIR")"
        if [ ! -f "$PROJ/src/mouse_logger/Makefile" ]; then
            err "repositorio Mic-E-Mouse nao encontrado abaixo de $PROJ."
            say "  clone o repositorio original: git clone https://github.com/AICPS/Mic-E-Mouse.git"
            return 1
        fi
        say "Linux: compilando o logger C++ (modo generico 4 kHz)..."
        make -C "$PROJ/src/mouse_logger" || { err "compilacao do logger falhou"; return 1; }
        "$PROJ/src/mouse_logger/mouse_logger" "black_widow/bin/data/data_%s.csv" 3 \
            && ok "CSV gerado em ./bin/data/" \
            || warn "coleta encerrada (Ctrl+C e normal - o CSV fica em bin/data/)"
    fi
}

act_extract() {
    check_audio_deps || return 1
    cd "$BIN"                       # outputs land inside the bundle (bin/out)
    "$PYTHON" ouvir_mouse.py extrair "$@"
}

act_profiles() {
    check_audio_deps || return 1
    cd "$BIN"
    "$PYTHON" ouvir_mouse.py perfis
}

act_tutorial() {
    if [ -f "$SCRIPT_DIR/../TUTORIAL.md" ]; then
        cat "$SCRIPT_DIR/../TUTORIAL.md"
    elif [ -f "$DOCS/TUTORIAL.md" ]; then
        cat "$DOCS/TUTORIAL.md"
    else
        warn "TUTORIAL.md nao encontrado"
    fi
}

# --------------------------------------------------------------------------
# menu
# --------------------------------------------------------------------------
menu() {
    local op
    while true; do
        hr
        printf '%s%s%s\n' "$BOLD" "  BLACK WIDOW - Mic-E-Mouse BR (4k-8k DPI / polling 1-2 kHz)" "$RST"
        hr
        say "  ${GRN}[1]${RST} Coletar dados do mouse     (Ctrl+C encerra)"
        say "  ${GRN}[2]${RST} Extrair audio e ouvir      (min. 30 s, WAV em bin/out/)"
        say "  ${GRN}[3]${RST} Perfis de mouse            (dados em mouses/)"
        say "  ${GRN}[4]${RST} Tutorial simples           (G304 passo a passo)"
        say "  ${GRN}[5]${RST} Instalar dependencias      (pip install requirements)"
        say "  ${GRN}[6]${RST} Mouse2WAV avancado         (bin/mouse2wav.py)"
        say "  ${RED}[0]${RST} Sair"
        hr
        read -r -p "  opcao: " op
        case "$op" in
            1) act_collect ;;
            2) act_extract ;;
            3) act_profiles ;;
            4) act_tutorial ;;
            5) install_deps ;;
            6)
                "$PYTHON" "$BIN/mouse2wav.py" --help 2>/dev/null \
                    || { warn "mouse2wav.py indisponivel - falta numpy/scipy? use a opcao 5"; }
                ;;
            0) say "ate logo, ${RED}viuva${RST}."; exit 0 ;;
            *) warn "opcao invalida (0-6)" ;;
        esac
        if [ -t 0 ]; then
            read -r -p "  Enter para voltar ao menu... " _ || true
        fi
    done
}

# --------------------------------------------------------------------------
# entry
# --------------------------------------------------------------------------
banner
check_python || exit 1

case "${1:-}" in
    ""|menu) menu ;;
    coletar)  shift; act_collect "$@" ;;
    extrair)  shift; act_extract "$@" ;;
    perfis)   shift; act_profiles "$@" ;;
    tutorial) shift; act_tutorial ;;
    deps)     install_deps ;;
    -h|--help|help)
        hr
        say "  ${BOLD}BLACK WIDOW${RST} - usos:"
        say "    bash black_widow/black_widow.sh               menu"
        say "    bash black_widow/black_widow.sh coletar       coleta (Linux C++ / Git-Bash raw)"
        say "    bash black_widow/black_widow.sh extrair       audio"
        say "    bash black_widow/black_widow.sh perfis"
        say "    bash black_widow/black_widow.sh tutorial"
        say "    bash black_widow/black_widow.sh deps"
        say ""
        say "  Bundle: ${DIM}bin/ (ferramenta), mouses/ (dados), docs/ (mic-e-mouse + agradecimentos)${RST}"
        ;;
    *) warn "comando desconhecido: $1 (use help)" ;;
esac
