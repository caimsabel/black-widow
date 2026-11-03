#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
OUVIR MOUSE - porta de entrada para o Mic-E-Mouse em hardware brasileiro
(4.000-8.000 DPI, polling 1.000-2.000 Hz: Redragon, Pichau, Logitech G,
HyperX, ...).

Iniciacao em 3 passos:

    1) Instalar dependencias do caminho de audio (leve):
           pip install -r requirements.txt

    2) Coletar os dados do mouse (Windows):
           python ouvir_mouse.py coletar
       (Linux: use o logger C++ original -> make -C src/mouse_logger)

    3) Transformar em audio e ouvir:
           python ouvir_mouse.py extrair data/data_win_XXXX.csv
       o WAV sai em out/ e abre no player automaticamente.

Ou simplesmente rode sem argumento para usar o assistente interativo:

    python ouvir_mouse.py
"""

import argparse
import os
import shutil
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

PROFILE_NAMES_TIP = "redragon_m711, pichau_p701, logitech_g304, logitech_g502, hyperx_pulsefire..."


def _fail(msg: str, hint: str = "") -> None:
    print(f"[ERRO] {msg}")
    if hint:
        print(hint)
    sys.exit(1)


def _ensure_audio_deps() -> None:
    try:
        import numpy  # noqa: F401
        import scipy  # noqa: F401
    except ImportError as e:
        _fail(
            f"dependencia faltando ({e.name}).",
            hint="      instale com:  pip install -r requirements.txt\n"
                 "      (so numpy+scipy sao necessarios para OUVIR o mouse; "
                 "a stack completa de ML vem do environment.yml/conda)",
        )


# --------------------------------------------------------------------------
# COLETAR
# --------------------------------------------------------------------------
def cmd_coletar(argv) -> int:
    """Colheita de deltas brutos do mouse via Raw Input (Windows)."""
    if os.name != "nt":
        _fail(
            "em Linux/WiFi-coleta use o logger C++ original:",
            hint="      make -C " + os.path.join(HERE, "..", "src", "mouse_logger") + "\n"
                 "      ./src/mouse_logger/mouse_logger 'black_widow/bin/data/data_%s.csv' 3   "
                 "(3 = modo generico 4kHz)",
        )
    # delega ao collector nativo (bundle local)
    collector = os.path.join(HERE, "mouse_logger_win.py")
    sys.argv = [sys.argv[0]] + list(argv)
    script_globals = {"__name__": "__popup__", "__file__": collector, "__builtins__": __builtins__}
    code = open(collector, encoding="utf-8").read()
    try:
        exec(compile(code, collector, "exec"), script_globals)
    except SystemExit as e:
        return e.code if isinstance(e.code, int) else 0
    return 0


def _newest_csv(*dirs) -> str | None:
    """Most recently modified .csv in the search dirs (newest first)."""
    candidates = []
    for d in dirs:
        d = os.path.abspath(d)
        if os.path.isdir(d):
            for f in os.listdir(d):
                if f.lower().endswith(".csv"):
                    p = os.path.join(d, f)
                    candidates.append((os.path.getmtime(p), p))
    return max(candidates)[1] if candidates else None


def _list_csvs() -> list:
    out = []
    d = os.path.join(HERE, "data")
    if os.path.isdir(d):
        for f in sorted(os.listdir(d)):
            if f.lower().endswith(".csv"):
                out.append(os.path.join(d, f))
    return out


# --------------------------------------------------------------------------
# EXTRAIR
# --------------------------------------------------------------------------
def _extract(csv_path: str, dpi: int, profile: str | None, seconds: float | None,
             stage: str, out_path: str, open_player: bool, deemph: bool) -> int:
    _ensure_audio_deps()
    from core.signal.br_mouse_dsp import extract_mouse_audio, write_wav  # late import

    if not csv_path or not os.path.isfile(csv_path):
        # conveniência: sem CSV dado, usar o mais novo em ./data
        newest = _newest_csv(os.path.join(HERE, "data"), os.path.join(HERE, "out"))
        if newest:
            print(f"[csv] usando o mais recente: {newest}")
            csv_path = newest
        else:
            _fail(f"arquivo CSV nao encontrado: {csv_path}",
                  hint="      rode antes:  python ouvir_mouse.py coletar\n"
                       "      (fica gravado em ./data/data_win_*.csv)")

    if stage == "raw":
        from core.signal.br_mouse_dsp import load_mouse_csv, resample_nonuniform
        deltaT, nuX, nuY = load_mouse_csv(csv_path, max_seconds=seconds)
        T, X, Y = resample_nonuniform(deltaT, nuX, nuY, Fs=16000,
                                      method="lanczos", taps=12, gain=1.0)
        audio = (X + Y) / 2.0
        info_note = "raw (sem DSP) - para comparar A/B"
    else:
        result = extract_mouse_audio(
            csv_path,
            dpi=dpi,
            profile=profile,
            method="lanczos",
            preemph_coeff=0.0 if deemph else 0.90,  # deemph p/ ouvir: menos HF aguda
            max_seconds=seconds,
        )
        audio = result["mono"]
        if deemph:
            from core.signal.br_mouse_dsp import deemphasis
            audio = deemphasis(audio, 0.90)
        info_note = result["info"]

    if len(audio) == 0:
        _fail("gravacao vazia ou muito curta (sao poucos eventos no CSV? Colete por >= 30 s movendo o mouse).")

    # minimo de 30 s audíveis: coletas curtas sao preenchidas por loop
    from core.signal.br_mouse_dsp import ensure_min_seconds, MIN_LISTEN_SECONDS
    min_listen = float(os.environ.get("MICEMOUSE_MIN_LISTEN", MIN_LISTEN_SECONDS))
    before_s = len(audio) / 16000.0
    audio, padded = ensure_min_seconds(audio, Fs=16000, min_seconds=min_listen)
    if padded:
        print(f"[min-listen] gravacao {before_s:.1f} s < {min_listen:.0f} s -> preenchida "
              f"por loop ate {len(audio) / 16000.0:.1f} s (crossfade de 20 ms)")

    write_wav(out_path, audio, Fs=16000)
    secs = len(audio) / 16000.0
    print(f"\n[audio] gravado: {out_path}  ({secs:.1f} s @ 16 kHz)")
    print(f"[audio] pipeline: {info_note}")
    if open_player and os.name == "nt":
        try:
            os.startfile(out_path)  # abre no player padrao do Windows
            print(f"[audio] tocando: {out_path}")
        except OSError:
            pass
    print("\nDica: compare com a versao em bruto:")
    print(f"   python ouvir_mouse.py extrair \"{csv_path}\" --stage raw")
    return 0


def _ask(msg: str, default: str = "") -> str:
    try:
        val = input(f"{msg} [{default}]: ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\ncancelled.")
        sys.exit(1)
    return val or default


def wizard_extrair() -> int:
    newest = _newest_csv(os.path.join(HERE, "data"))
    default_csv = os.path.basename(newest) if newest else "data/data_win_XXX.csv"
    csv_path = _ask("Caminho do CSV coletado (Enter = mais recente)", default_csv)
    if not os.path.isabs(csv_path) and not os.path.sep in csv_path:
        data_dir = os.path.join(HERE, "data")
        cand = os.path.join(data_dir, csv_path)
        if os.path.isfile(cand):
            csv_path = cand
        else:
            csv_path = _newest_csv(os.path.join(HERE, "data")) if csv_path == default_csv else csv_path
    if not os.path.isfile(csv_path):
        candidates = _list_csvs()
        if candidates:
            print("\nCSVs disponiveis na pasta data/:")
            ordered = sorted(candidates, key=os.path.getmtime, reverse=True)
            for i, c in enumerate(ordered[:10], 1):
                print(f"  [{i}] {os.path.basename(c)}")
            sel = _ask("numero do arquivo (ou Enter para o mais recente)", "1")
            if sel.strip() == "":
                csv_path = ordered[0]
            elif sel.isdigit() and 1 <= int(sel) <= len(ordered[:10]):
                csv_path = ordered[:10][int(sel) - 1]
            else:
                _fail(f"o arquivo {csv_path} nao existe")
        else:
            _fail(f"o arquivo {csv_path} nao existe e nada encontrei em ./data",
                  hint="      rode:  python ouvir_mouse.py coletar")
    dpi_s = _ask("DPI configurado no mouse (Enter = usa o do perfil/default)", "")
    dpi = int(dpi_s) if dpi_s.isdigit() else None
    seconds_s = _ask("extrair somente os primeiros N segundos (em branco = arquivo todo)")
    secs = float(seconds_s) if seconds_s else None
    out_path = os.path.join(HERE, "out", f"ouvindo_mouse_{time.strftime('%H-%M-%S')}.wav")
    return _extract(csv_path, dpi, None, secs, "mono", out_path, open_player=True, deemph=False)


def wizard() -> int:
    _ensure_audio_deps()
    print("=" * 64)
    print("  OUVIR MOUSE (Mic-E-Mouse adaptado p/ hardware BR)")
    print("  periferico modesto: 4.000-8.000 DPI / polling 1-2 kHz")
    print("=" * 64)
    print("""
  [1] Coletar dados do mouse (Windows, Raw Input, Ctrl+C encerra)
  [2] Extrair audio de um CSV ja coletado e ouvir
  [3] Extrair audio em modo RAW (sem DSP - comparar A/B)
  [4] Listar perfis de mouse e instrucoes
  [5] Tutorial simples passo a passo (ex.: Logitech G304)
  [0] Sair
""")
    choice = _ask("opcao", "1").strip().lower()
    if choice == "1":
        return cmd_coletar([])
    if choice == "2":
        return wizard_extrair()
    if choice == "3":
        csv_path = _ask("Caminho do CSV")
        out_path = os.path.join(HERE, "out", f"raw_{time.strftime('%H-%M-%S')}.wav")
        return _extract(csv_path, 0, None, None, "raw", out_path, open_player=True, deemph=False)
    if choice == "4":
        return cmd_perfis([])
    if choice == "5":
        return cmd_tutorial([])
    print("tchau.")
    return 0


# --------------------------------------------------------------------------
# TUTORIAL
# --------------------------------------------------------------------------
TUTORIAL_TEXT = """
TUTORIAL RAPIDO (Logitech G304) - cmd.exe do Windows

  PASSO 0 (uma vez so):
     cd C:\\Users\\Casa\\Downloads\\Mouse\\Mic-E-Mouse
     python -m pip install -r requirements.txt

  PASSO 1 (mouse): no G Hub, DPI = 12.000; o polling do G304 e fixo 1.000 Hz.

  PASSO 2 (coletar 30-60 s, movendo o mouse em curvas continuas!):
     python ouvir_mouse.py coletar
     Ctrl+C encerra -> cria data\\data_win_<data-hora>.csv

  PASSO 3 (ouvir - acha o CSV mais novo sozinho):
     python ouvir_mouse.py extrair
     ...ou com o perfil explicito:
     python ouvir_mouse.py extrair --profile logitech_g304

ERROS COMUNS:
   --profile --logitech_g304  ->  correto:  --profile logitech_g304 (sem -- no valor)
   src/... como comando       ->  correto:  python src\\mouse_logger\\mouse_logger_win.py
   "dependencia faltando"     ->  rode o PASSO 0 de novo
   "CSV nao encontrado"       ->  pouco coletado? afaste: faca o PASSO 2 de novo
   arquivo parado/de ruido    ->  mova o mouse DURANTE a coleta

O G304 (1 kHz) reproduz ate ~500 Hz de audio: ouvir voce escuta graves,
sopro e entonacao do movimento - nao e uma voz cristalina. Tutorial
completo: TUTORIAL.md na raiz. Detalhes de cada perfil: perfis.
"""


def cmd_tutorial(argv) -> int:
    print(TUTORIAL_TEXT)
    # se o tutorial em arquivo existe, oferecer o caminho dele
    t = os.path.join(HERE, "TUTORIAL.md")
    if os.path.isfile(t):
        print(f"(guia completo em arquivo: {t})")
    return 0


# --------------------------------------------------------------------------
# INFO
# --------------------------------------------------------------------------
def cmd_perfis(argv) -> int:
    _ensure_audio_deps()
    from core.signal.br_mouse import PROFILES, polling_viability
    print(f"{'perfil':<22} {'DPI':>7} {'polling':>8}   obs")
    print("-" * 80)
    for key, prof in sorted(PROFILES.items()):
        viab = polling_viability(prof.polling_rate)
        print(f"{key:<22} {prof.dpi:>7} {prof.polling_rate:>6}Hz   "
              f"teto de audio ~{viab['audio_ceiling_hz']:.0f} Hz - {prof.note}")
    print("""
COMO USAR PERFIS:
  python tool/mouse2wav.py data/rec.csv --profile redragon_m711
  ... ou passe DPI/polling manualmente:
  python tool/mouse2wav.py data/rec.csv --dpi 7200 --polling 1000

O POLLING LIMITA O TETO: um mouse de 1 kHz reproduz ate ~500 Hz de
audio; a 2 kHz, ~1 kHz. A banda de voz (300-3400 Hz) e capturada
parcialmente - a inteligibilidade vem do tratamento DSP desta adaptacao.
""")
    return 0


# --------------------------------------------------------------------------
# Argparse facade
# --------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(
        prog="ouvir_mouse.py",
        description="OUVIR MOUSE - coletar e extrair audio do mouse (Mic-E-Mouse BR edition).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    sub = ap.add_subparsers(dest="cmd")

    ap_coletar = sub.add_parser("coletar", help="coletar dados do mouse (Windows Raw Input)")

    ap_extrair = sub.add_parser("extrair", help="CSV coletado -> WAV audivel (out/). Sem CSV: usa o mais novo em data/")
    ap_extrair.add_argument("csv", nargs="?", default=None,
                            help="caminho do CSV coletado (opcional: pega o mais recente de data/)")
    ap_extrair.add_argument("--dpi", type=int, default=None,
                            help="DPI configurado no mouse (em branco: usa o do --profile)")
    ap_extrair.add_argument("--profile", default=None, help=f"perfil preset ({PROFILE_NAMES_TIP})")
    ap_extrair.add_argument("--seconds", type=float, default=None,
                            help="extrair apenas os N primeiros segundos")
    ap_extrair.add_argument("--stage", default="mono", choices=["mono", "raw"],
                            help="'raw' = sem DSP (comparar A/B)")
    ap_extrair.add_argument("--out", default=None, help="caminho do WAV de saida")
    ap_extrair.add_argument("--no-open", action="store_true", help="nao abrir o player ao final")
    ap_extrair.add_argument("--deemph", action="store_true",
                            help="compensar a pre-enfase antes de salvar (som mais 'natural')")

    sub.add_parser("perfis", help="listar perfis de mouse BR e ceilings de audio")
    sub.add_parser("tutorial", help="tutorial rapido passo a passo (cmd.exe)")

    args, rest = ap.parse_known_args()
    if not args.cmd:
        return wizard()
    if args.cmd == "coletar":
        return cmd_coletar(rest)
    if args.cmd == "extrair":
        out_path = args.out or os.path.join(
            HERE, "out", f"ouvindo_mouse_{time.strftime('%Y-%m-%d_%H-%M-%S')}.wav"
        )
        return _extract(args.csv, args.dpi, args.profile, args.seconds,
                        args.stage, out_path, open_player=not args.no_open,
                        deemph=args.deemph)
    if args.cmd == "perfis":
        return cmd_perfis(rest)
    if args.cmd == "tutorial":
        return cmd_tutorial(rest)
    return 0


if __name__ == "__main__":
    sys.exit(main())
