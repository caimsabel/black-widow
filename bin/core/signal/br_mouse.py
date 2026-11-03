"""
Adaptation layer for consumer mice in the 4,000-8,000 DPI range with
1,000-4,000 Hz polling rates (Redragon, Pichau, Logitech G, HyperX, etc.).

The original Mic-E-Mouse pipeline was calibrated for extreme hardware
(Razer Viper 8KHz: 8 kHz polling, >16,000 DPI). Cheaper hardware produces:

  1. Fewer samples per second  -> less acoustic bandwidth
     (N Hz polling reproduces at most N/2 Hz of audio content).
  2. Smaller delta magnitudes  -> weaker signal in raw counts
     (the sensor reports fewer counts per inch of movement).

This module handles both effects:
  - `estimate_polling_rate()`  measures the effective polling rate from a
    recorded CSV so the user does not have to guess it.
  - `HardwareProfile` / `gain_from_dpi()` rescale the raw deltas to match
    the reference acquisition hardware (8 kHz / 16,000 DPI).
  - `polling_viability` reports the real Nyquist audio ceiling of the
    recording, so callers can set expectations for the voice band
    (300-3,400 Hz) they can actually recover.

Profiles are presets only - every field can be overridden on the command
line or in the notebooks.
"""

from dataclasses import dataclass
from typing import Dict, Optional

import numpy as np

# ----------------------------------------------------------------------------
# Reference hardware used to train the public models
# ----------------------------------------------------------------------------
REF_POLLING_RATE = 8000   # Hz  (Razer Viper 8KHz)
REF_DPI = 16000           # counts per inch
# Target acquisition Fs used across the whole repo (audio output rate)
TARGET_FS = 16000


@dataclass(frozen=True)
class HardwareProfile:
    """Raw sensor characteristics of a consumer mouse."""
    name: str
    dpi: int              # max (or configured) counts per inch
    polling_rate: int     # Hz
    note: str = ""


# ----------------------------------------------------------------------------
# Presets for popular mice in the Brazilian market
# (values are the consumer-available/configured defaults, override freely)
# ----------------------------------------------------------------------------
PROFILES: Dict[str, HardwareProfile] = {
    "redragon_cobra":   HardwareProfile("Redragon Cobra",        10000, 1000, "Max Colombian variant 12.4k; defaults ship at 10k"),
    "redragon_m711":    HardwareProfile("Redragon M711 Cobra",    7200, 1000, "Common mid-tier Redragon gaming mouse"),
    "redragon_m808":    HardwareProfile("Redragon M808 Storm",   12400, 1000, "Top-tier Redragon polling is still 1kHz"),
    "pichau_p701":      HardwareProfile("Pichau P701",            6400, 1000, "House-brand gaming mouse"),
    "logitech_g304":    HardwareProfile("Logitech G304/G305",    12000, 1000, "Best-selling Logitech in Brazil"),
    "logitech_g502":    HardwareProfile("Logitech G502 HERO",    25600, 1000, "Used in the paper as the 1kHz reference"),
    "hyperx_pulsefire": HardwareProfile("HyperX Pulsefire Haste",16000, 1000, "Up to 16k DPI, still 1kHz polling"),
    "razer_viper_8k":   HardwareProfile("Razer Viper 8KHz",      20000, 8000, "Paper reference hardware"),
    "custom":           HardwareProfile("Custom",                 8000, 1000, "Override dpi/polling via CLI args"),
}

DEFAULT_PROFILE = "custom"


def get_profile(name: str) -> HardwareProfile:
    """Look up a preset profile by (case-insensitive) name."""
    key = name.strip().lower().replace(" ", "_").replace("-", "_")
    if key not in PROFILES:
        raise KeyError(f"Unknown profile '{name}'. Known profiles: {sorted(PROFILES)}")
    return PROFILES[key]


# ----------------------------------------------------------------------------
# Polling-rate estimation
# ----------------------------------------------------------------------------
def estimate_polling_rate(deltaT, robust: bool = True) -> int:
    """
    Estimate the effective polling rate of a recording from the
    nonuniform inter-event deltaT vector (microseconds).

    Works with NumPy arrays or PyTorch tensors (any object NumPy can
    consume). Uses the median (robust to OS scheduling gaps and USB
    transfer bursts) and snaps to the nearest common polling rate.

    :param deltaT: 1D array of inter-event time deltas in microseconds.
    :param robust: If True use the median, otherwise the mean (not recommended).
    :return: Estimated polling rate in Hz (snapped to 125/250/500/1000/.../8000).
    """
    deltaT = np.asarray(deltaT, dtype=np.float64)
    if deltaT.size < 2:
        raise ValueError("need at least two samples to estimate polling rate")

    common_rates = np.array(
        [125, 250, 500, 1000, 2000, 4000, 8000, 16000], dtype=np.float64
    )
    stat = np.median(deltaT) if robust else np.mean(deltaT)
    rate = 1e6 / stat
    # Snap to the nearest advertised rate.
    snapped = int(common_rates[np.argmin(np.abs(common_rates - rate))])
    return snapped


def polling_viability(polling_rate: int) -> Dict[str, object]:
    """
    Report what a given polling rate can physically deliver.

    :return: dict with the Nyquist audio ceiling in Hz and the recommended
             interpolation kernel size for upsampling to TARGET_FS.
    """
    ceiling = polling_rate // 2
    # Larger kernel for lower rates: more tap overlap smooths the
    # staircase introduced by upsampling a sparse signal.
    if polling_rate >= 8000:
        taps = 2
    elif polling_rate >= 4000:
        taps = 8
    elif polling_rate >= 2000:
        taps = 12
    else:
        taps = 16
    return {
        "polling_rate_hz": polling_rate,
        "audio_ceiling_hz": ceiling,
        "upsample_ratio": TARGET_FS / polling_rate,
        "recommended_lanczos_taps": taps,
    }


# ----------------------------------------------------------------------------
# DPI / amplitude compensation
# ----------------------------------------------------------------------------
def gain_from_dpi(dpi: int, ref_dpi: int = REF_DPI) -> float:
    """
    Amplitude gain that maps deltas recorded at `dpi` CPI to the scale the
    models were trained on (`ref_dpi` CPI).

    Lower-DPI sensors emit fewer counts per inch, so the reconstructed
    waveform amplitude in counts is proportionally smaller. Compensating
    with ref/dpi restores the acoustic energy level before normalization.
    The gain is capped to avoid blowing out very-low-DPI office mice.
    """
    if dpi <= 0:
        raise ValueError("dpi must be positive")
    gain = ref_dpi / dpi
    return float(min(gain, 8.0))


def resolve_gain(
    profile: Optional[HardwareProfile] = None,
    dpi: Optional[int] = None,
    explicit_gain: Optional[float] = None,
) -> float:
    """
    Resolve the final amplitude gain, in priority order:
    explicit_gain > dpi argument > profile dpi > no gain (1.0).
    """
    if explicit_gain is not None:
        if explicit_gain <= 0:
            raise ValueError("gain must be positive")
        return float(explicit_gain)
    if dpi is not None and dpi > 0:
        return gain_from_dpi(dpi)
    if profile is not None:
        return gain_from_dpi(profile.dpi)
    return 1.0
