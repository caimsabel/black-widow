#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
BLACK WIDOW - banner ANSI compartilhado entre os iniciadores
(black_widow.sh e black_widow.bat).

Arte com fundo preto e as cores da identidade: vermelho, azul, verde e
branco. Compativel com Windows Terminal, conhost (cmd/PowerShell),
bash e Linux xterm.
"""

import os
import sys

# ANSI: fundo preto + cores da marca
V = "\033[0m"
RED = "\033[31;40m"
BLU = "\033[34;40m"
GRN = "\033[32;40m"
WHT = "\033[37;40m"

LINES = [
    (RED, " ______   _                     _         _    _  _       _   "),
    (BLU, "| ___ \\ | |                   | |       | |  | |(_)     | |   "),
    (GRN, "| |_/ / | |  __ _   ___  | | __  | |  | | _   _  | |  ___   _   _   ___"),
    (WHT, "| ___ \\ | | / _` | / __| | |/ /  | |/\\| || | | | | | / _ \\ | | | | / __|"),
    (RED, "| |_/ / | | | (_| | | (__  |   <   \\  /\\  /| | |_| | | || (_) || |_| | \\__ \\"),
    (BLU, "\\____/  |_|  \\__,_|  \\___| |_|\\_\\   \\/  \\/ |_|\\__,_|_|_| \\___/  \\__,_| |___/"),
]


def _force_vt_mode() -> None:
    """Enable ANSI Virtual Terminal processing on the legacy Windows console."""
    if os.name == "nt":
        os.system("")  # classic conhost needs this to activate VT sequences
    # legacy consoles encode text with cp1252: make the emoji degrade
    # gracefully instead of crashing the launcher
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass


def print_banner() -> None:
    _force_vt_mode()
    width = max(len(text) for _, text in LINES)
    print()
    for color, text in LINES:
        print(f"{color}{text.ljust(width)}{V}")
    print(f"{RED}# 🕷️ BLACK WIDOW{V}"
          f" -- {GRN}iniciador Mic-E-Mouse{V}"
          f" -- {WHT}colheita + audio do mouse{V}")
    print()


if __name__ == "__main__":
    print_banner()
