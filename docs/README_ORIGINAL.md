# Mic-E-Mouse: your computer mouse has big ears
![Mic-E-Mouse Visualization](./fig/micemouse.png)
image courtesy of GPT4/Dall-E-3, generated using the keywords "computer mouse with big ears and a microphone as a scroll whell"
## Description

Side-Channel Audio Attack through computer mice.

## Requirements
- [Conda](https://docs.conda.io/en/latest/miniconda.html) or [Mamba](https://mamba.readthedocs.io/en/latest/index.html)
- A computer mouse with a high polling rate (4kHz < ), and a high DPI count (16,000 <).

Brazilian-mouse edition note: the full ML pipeline below still needs the paper's
reference hardware for high-fidelity reconstruction, but far cheaper mice work
with the adapted DSP path (see next section).
## Installation
The conda/mamba environment can be installed with the following command: `conda env create -f environment.yml`

# OUVIR MOUSE (Brazilian hardware adaptation)
Quick start for the common Brazilian gaming-mouse tier (4.000-8.000 DPI,
1.000-2.000 Hz polling: Redragon, Pichau, Logitech G, HyperX...).

```bash
# dependencies for the audio path (light: numpy + scipy only)
pip install -r requirements.txt

# 1) collect
python ouvir_mouse.py coletar                       # Windows (Raw Input / fallback hook)
python ouvir_mouse.py coletar --seconds 120         # scriptable stop
# Linux (original C++ logger, generic modes added):
make -C src/mouse_logger && ./src/mouse_logger/mouse_logger NULL 3

# 2) extract & listen
python ouvir_mouse.py extrair data/data_win_XXX.csv   # WAV in out/, opens the player
python ouvir_mouse.py                                 # interactive wizard

# 3) notebook model path (torch) -- new Lanczos + DPI gain wrapper:
#    from core.signal.preprocess import process_from_file_br
#    T, X, Y = process_from_file_br("data/rec.csv", dpi=4000, method='lanczos')
```

What changed vs. the paper's reference acquisition (>4 kHz / >16,000 DPI):

| Effect of cheaper hardware | Adaptation |
|---|---|
| Polling 1-2 kHz -> audio ceiling 500-1.000 Hz | `imaging_lowpass` Nyquist window tied to the measured polling rate (`core/signal/br_mouse_dsp.py`) |
| 4.000 DPI -> smaller raw counts | DPI gain compensation (`ref 16.000 / dpi`, capped at 8x) + pre-emphasis filter |
| Fabric mousepads -> stationary hiss | spectral subtraction + soft noise gate BEFORE axis normalization |
| Sparse sampling staircasing | Lanczos kernel (auto-sized 8-16 taps) in `resample` / `process_from_file_br` |

Physics to keep in mind: a recording at P Hz polling carries at most P/2 Hz;
at 1 kHz you recover ~500 Hz (F0 + low formants), at 2 kHz ~1 kHz. The
quality scales with polling rate, not DPI.

Windows Raw Input behavior on some builds refuses `RIDEV_INPUTSINK`
(err 87) even with a valid target window; the collector then falls back
to a low-level mouse hook with software pointer normalization
(Enhance-pointer-precision removed, sensitivity read and software-corrected),
restoring settings on exit.
## Repository Structure
- waveformReconstruction_AUDIOMNIST.ipynb: Waveform Reconstruction Experiments for AudioMNIST, including collecting the samples used in the user study
- waveformReconstruction.ipynb: Waveform Reconstruction Experiments for VCTK
- models/: Directory containing all models trained and made public
- fig/: Directory containing all figures and visuals used in the paper and this repo
- core/nn/: Methods used for Neural Networks, dataloaders, network primitives, and utilities
- core/signal/: Methods used for signal processing
- src/: Mouse_Logger and OpenBlok modified sources
- utils/: HTML test to check if browsers can record audio
- vctk/: utils used to automate dataset creation
## DATA
Anonymous Data available [HERE](https://drive.google.com/drive/folders/1DcTldouupfp7BMteE1Br0lq7RCdQQ0Hc?usp=drive_link)

https://drive.google.com/drive/folders/1DcTldouupfp7BMteE1Br0lq7RCdQQ0Hc?usp=drive_link

## Authors
### KEPT ANONYMOUS WHILE UNDER SUBMISSION
## Citation
### KEPT ANONYMOUS WHILE UNDER SUBMISSION