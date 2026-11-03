#!/usr/bin/env python
"""
Mouse2WAV: "hear" a Mic-E-Mouse recording, no PyTorch required.

Converts a collected mouse CSV (`offset, x, y`, microsecond deltas,
signed counts) into an audible WAV file, applying the Brazil-hardware
DSP adaptation chain from core/signal/br_mouse_dsp.py:

  1. Lanczos-12 nonuniform resample with DPI gain compensation
  2. Nyquist-window anti-imaging low-pass (tied to the polling rate)
  3. Spectral subtraction + soft gate (fabric mousepad static)
  4. Pre-emphasis (HF amplification below 8,000 DPI)
  5. Joint X/Y normalization -> mono

Usage:
    python tool/mouse2wav.py data/data_2026-11-03.csv --dpi 4000 --out out/mouse.wav
    python tool/mouse2wav.py recording.csv --profile redragon_m711
    python tool/mouse2wav.py recording.csv --no-denoise --no-gate --no-preemph   # raw listen
    python tool/mouse2wav.py noise_capture.csv --out noise.wav --deemph          # A/B noise floor

Requires: numpy, scipy.
"""

import argparse
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.signal.br_mouse import PROFILES  # noqa: E402
from core.signal.br_mouse_dsp import (  # noqa: E402
    MIN_LISTEN_SECONDS,
    PREEMPH_COEFF,
    extract_mouse_audio,
    ensure_min_seconds,
    write_wav,
)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Convert a Mic-E-Mouse mouse CSV into an audible WAV "
                    "(Brazilian hardware: 4,000 DPI / 1-2 kHz polling).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("csv", help="path to the collected mouse CSV (offset, x, y)")
    p.add_argument("--out", default="out/mouse_heard.wav", help="output WAV path")
    p.add_argument("--profile", default=None, choices=sorted(PROFILES),
                   help="hardware preset (dpi/polling/gain)")
    p.add_argument("--dpi", type=int, default=None,
                   help="configured sensor DPI (default: uses the --profile value)")
    p.add_argument("--polling", type=int, default=None,
                   help="native polling rate in Hz; estimated from the CSV if omitted "
                        "(only useful to override a bad median estimate)")
    p.add_argument("--seconds", type=float, default=None,
                   help="keep only the first N seconds of the recording")
    p.add_argument("--min-listen", type=float, default=MIN_LISTEN_SECONDS,
                   help="minimum audible output duration in seconds; shorter captures "
                        "are loop-padded with crossfade (0 disables)")
    p.add_argument("--gain", type=float, default=None,
                   help="explicit amplitude gain overriding the DPI compensation")
    p.add_argument("--method", default="lanczos",
                   choices=["lanczos", "sinc", "cubic", "linear", "nearest"],
                   help="resampling kernel for the nonuniform->uniform step")
    p.add_argument("--taps", type=int, default=None,
                   help="Lanczos kernel radius (auto from polling rate if omitted)")
    p.add_argument("--no-imaging-filter", action="store_true",
                   help="disable the Nyquist-window anti-imaging low-pass (req 1)")
    p.add_argument("--no-denoise", action="store_true",
                   help="disable spectral subtraction (req 3)")
    p.add_argument("--no-gate", action="store_true",
                   help="disable the soft noise gate (req 3)")
    p.add_argument("--no-preemph", action="store_true",
                   help="disable pre-emphasis (req 2)")
    p.add_argument("--preemph-coeff", type=float, default=PREEMPH_COEFF,
                   help="pre-emphasis coefficient (0.90-0.97 typical)")
    p.add_argument("--noise-csv", default=None,
                   help="optional still-mouse capture CSV to build the noise floor")
    p.add_argument("--deemph", action="store_true",
                   help="pre-emphasis compensation before saving (restores spectral balance)")
    p.add_argument("--stage", default="mono", choices=["mono", "raw"],
                   help="'mono' = (X+Y)/2 of the processed axes; "
                        "'raw' = skip processing, plain Lanczos resample only (A/B listen)")
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    if not os.path.isfile(args.csv):
        print(f"error: CSV not found: {args.csv}", file=sys.stderr)
        return 2

    if args.stage == "raw":
        # A/B listen: plain resample + DPI gain, no DSP.
        from core.signal.br_mouse_dsp import load_mouse_csv, resample_nonuniform
        deltaT, nuX, nuY = load_mouse_csv(args.csv, max_seconds=args.seconds)
        T, X, Y = resample_nonuniform(
            deltaT, nuX, nuY, Fs=16000, method=args.method,
            taps=(args.taps or 12), gain=(args.gain or 1.0),
        )
        audio = (X + Y) / 2.0
        info_note = "raw (no DSP)"
    else:
        result = extract_mouse_audio(
            args.csv,
            dpi=args.dpi,
            polling_rate=args.polling,
            profile=args.profile,
            method=args.method,
            taps=args.taps,
            gain=args.gain,
            denoise=not args.no_denoise,
            gate=not args.no_gate,
            preemph_coeff=(0.0 if args.no_preemph else args.preemph_coeff),
            imaging_filter=not args.no_imaging_filter,
            noise_csv=args.noise_csv,
            max_seconds=args.seconds,
        )
        audio = result["mono"]
        if args.deemph:
            from core.signal.br_mouse_dsp import deemphasis
            audio = deemphasis(audio, args.preemph_coeff)
        info_note = result["info"]

    # minimum 30 s of listening output (loop + crossfade when short)
    min_listen = max(0.0, float(args.min_listen or 0.0))
    if min_listen > 0:
        before_s = len(audio) / 16000.0
        audio, padded = ensure_min_seconds(audio, Fs=16000, min_seconds=min_listen)
        if padded:
            print(f"[min-listen] gravacao {before_s:.1f} s < {min_listen:.0f} s "
                  f"-> preenchida por loop ate {len(audio) / 16000.0:.1f} s (crossfade 20 ms)")

    out = write_wav(args.out, audio, Fs=16000)
    seconds = len(audio) / 16000.0
    print(f"written: {out} ({seconds:.2f} s @ 16 kHz)")
    print(f"pipeline: {info_note}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
