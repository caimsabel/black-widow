"""
DSP adaptation layer for low-polling / mid-DPI mice (Brazilian hardware).

Original Mic-E-Mouse targets: >= 8 kHz polling, >= 16,000 DPI.
Adapted targets:     1-2 kHz polling, 4,000-8,000 DPI (Redragon, Pichau,
Logitech G, HyperX, ...).

Physics you have to know before reading further:

  * A recording sampled at P Hz (the polling rate) carries at most P/2 Hz
    of information. A 1 kHz mouse reproduces up to ~500 Hz of audio; a
    2 kHz mouse up to ~1 kHz. Nothing can recover the 300-3,400 Hz speech
    band beyond that ceiling -- the design goal below is to use the
    available band to the limit and keep resampling images/artifacts out
    of it.

  * Below 8,000 DPI the sensor emits fewer counts per inch, so the
    reconstructed waveform amplitude (in counts) is smaller than the
    training reference. A first-order pre-emphasis filter restores the
    spectral energy balance instead of a naive static gain, which would
    amplify the low-frequency surface rumble that dominates cheap
    setup (fabric mousepads, glass desks, laminated tables).

  * Fabric mousepads add stationary broadband noise ("static surface
    hiss") that appears as a flat noise floor. Denoising runs BEFORE axis
    normalization so the normalization statistics are computed on the
    cleaned signal, not on the noise floor.

Pipeline (per axis, X and Y):

  [CSV deltas] -> nonuniform->uniform resample (Lanczos, +DPI gain)
               -> imaging/Nyquist low-pass  (req. 1)
               -> spectral subtraction w/ noise floor estimate (req. 3)
               -> soft noise gate                               (req. 3)
               -> pre-emphasis (HF amplification)               (req. 2)
               -> joint per-axis normalization
               -> mono (=(X+Y)/2)

NumPy/SciPy only: no PyTorch required for the collection->audio path,
so this can run on any machine; the torch path in core/signal/preprocess.py
unchanged for the model notebooks.
"""

import os
import wave
from typing import Optional, Tuple

import numpy as np

try:
    from scipy.signal import butter, istft, lfilter, sosfiltfilt, stft
    _HAS_SCIPY = True
except ImportError:  # pragma: no cover - scipy is a hard dep for the DSP path
    _HAS_SCIPY = False

from core.signal.br_mouse import (
    DEFAULT_PROFILE,
    PROFILES,
    REF_DPI,
    REF_POLLING_RATE,
    TARGET_FS,
    HardwareProfile,
    estimate_polling_rate,
    gain_from_dpi,
    get_profile,
    polling_viability,
    resolve_gain,
)

# --------------------------------------------------------------------------
# Constants
# --------------------------------------------------------------------------
VOICE_BAND_LOW = 300.0      # Hz, telephony speech band start
VOICE_BAND_HIGH = 3400.0    # Hz, telephony speech band end
PREEMPH_COEFF = 0.90        # first-order pre-emphasis coefficient (~+6 dB/oct)
NOISE_FRAME = 512           # STFT window samples @ 16 kHz (32 ms)
NOISE_HOP = 160             # STFT hop @ 16 kHz (10 ms)
OVERSUBTRACTION = 2.5       # alpha: how aggressively to subtract the noise floor
SPECTRAL_FLOOR = 0.04       # beta: keep at least -28 dB relative spectral floor

# Minimum audible output: shorter captures get loop-padded up to this.
MIN_LISTEN_SECONDS = 30.0


def _require_scipy() -> None:
    if not _HAS_SCIPY:
        raise ImportError("the DSP pipeline needs scipy: pip install scipy")


# --------------------------------------------------------------------------
# Minimum listening length (loop-padded, crossfaded)
# --------------------------------------------------------------------------
def ensure_min_seconds(
    audio: np.ndarray,
    Fs: int = TARGET_FS,
    min_seconds: float = MIN_LISTEN_SECONDS,
    fade_ms: float = 20.0,
) -> tuple:
    """
    Guarantee a minimum duration for the audible output.

    Recordings shorter than `min_seconds` are loop-padded by repeating the
    processed signal (single pass loop). Each joint receives a `fade_ms`
    equal-power crossfade between the tail of the previous copy and the
    head of the incoming one, hiding the repetition (no click). Longer
    recordings pass through unchanged.

    :return: (audio, padded) -- `padded` is True when loop-padding occurred.
    """
    n = len(audio)
    need = int(round(min_seconds * Fs))
    if n == 0 or min_seconds <= 0 or n >= need:
        return audio, False

    fade = min(int(round(fade_ms * Fs / 1000.0)), n // 4)
    step = n - fade
    # equal-power window: cos^2-style rising ramp on the incoming copy head
    w = np.sin(np.linspace(0.0, np.pi / 2.0, fade)) ** 0.5

    out = np.zeros(need)
    pos = 0
    written = False
    while pos < need:
        end = min(need, pos + n)
        take = end - pos
        chunk = audio[:take]
        if pos == 0:
            out[:take] = chunk
        elif take <= fade:
            # tail join of the final partial copy
            out[pos:end] = out[pos:end] * (1 - w[:take]) + chunk * w[:take]
        else:
            out[pos + fade:end] = chunk[fade:]
            # blend the head of the incoming copy with the tail already there
            out[pos:pos + fade] = out[pos:pos + fade] * (1 - w) + chunk[:fade] * w
        written = True
        pos += step
    return out, written


# --------------------------------------------------------------------------
# Req. 1 -- Nyquist window / anti-imaging low-pass
# --------------------------------------------------------------------------
def imaging_lowpass(
    x: np.ndarray,
    Fs: int = TARGET_FS,
    polling_rate: int = 1000,
    voice_ceiling: float = VOICE_BAND_HIGH,
    order: int = 6,
    skip_if_fast: bool = True,
) -> np.ndarray:
    """
    Zero-phase Nyquist-window filter applied after resampling.

    Upsampling a P Hz signal to Fs Hz with a windowed-sinc kernel still
    leaves residual spectral images around multiples of the polling rate
    (energy between P/2 and Fs/2 that is NOT part of the original band).
    Filtering at 0.92 * P/2 removes those images. For fast mice
    (>= 8 kHz polling, the original hardware) the filter is skipped by
    default to leave the trained-on bandwidth untouched.

    The cutoff is additionally capped at the telephony voice ceiling so
    the passband always stays inside the speech band of interest.

    :param x: 1D resampled signal (uniform Fs).
    :param Fs: Uniform sampling rate of the resampled signal.
    :param polling_rate: Native polling rate of the recording (Hz).
    :param voice_ceiling: Upper limit of the voice band (Hz).
    :param order: Butterworth SOS order.
    :param skip_if_fast: Do not filter when polling_rate >= 8 kHz.
    :return: Filtered signal (zero-phase, no group delay).
    """
    _require_scipy()
    nyquist_ceiling = polling_rate / 2.0
    if skip_if_fast and polling_rate >= REF_POLLING_RATE:
        # Original hardware: no adaptation filter.
        return x
    # 92% of the Nyquist ceiling keeps a wide transition band inside the
    # information band while carving off the imaging skirts.
    cutoff = min(0.92 * nyquist_ceiling, voice_ceiling)
    if cutoff <= 0 or cutoff >= Fs / 2:
        return x
    sos = butter(order, cutoff, btype="low", fs=Fs, output="sos")
    return sosfiltfilt(sos, x)


# --------------------------------------------------------------------------
# Req. 3 -- stationary noise removal (fabric mousepad static)
# --------------------------------------------------------------------------
def _stft_mag_pow(
    x: np.ndarray,
    Fs: int,
    n_db: int = NOISE_FRAME,
    hop: int = NOISE_HOP,
):
    """Signed STFT and magnitude/power spectrograms."""
    _require_scipy()
    _, _, Zxx = stft(
        x, fs=Fs, nperseg=n_db, noverlap=n_db - hop, window="hann", padded=True
    )
    mag = np.abs(Zxx)
    return Zxx, mag, mag ** 2


def estimate_noise_floor(
    x: np.ndarray,
    Fs: int = TARGET_FS,
    frame: int = NOISE_FRAME,
    hop: int = NOISE_HOP,
    quiet_fraction: float = 0.10,
) -> np.ndarray:
    """
    Estimate the stationary noise floor magnitude spectrum.

    Assumes the quietest frames of the recording are mostly surface
    noise (mouse at rest on the fabric / desk rail, unused gestures) --
    standard behaviour for fabric mousepads where the noise is
    stationary. Averages the |STFT| power of the bottom `quiet_fraction`
    of frames.

    :param x: 1D signal (uniform Fs). Pass a still mouse segment for
              the best estimate; the paradox is not required.
    :param quiet_fraction: Fraction (0-1) of least-energetic frames used.
    :return: Magnitude spectrum sqrt(power) per bin of the noise floor.
    """
    _, _, power = _stft_mag_pow(x, Fs, frame, hop)
    frame_energy = power.sum(axis=0)
    n_quiet = max(1, int(power.shape[1] * quiet_fraction))
    quiet_idx = np.argsort(frame_energy)[:n_quiet]
    noise_power = power[:, quiet_idx].mean(axis=1)
    return np.sqrt(noise_power)


def noise_floor_from_recording(
    noise: np.ndarray,
    Fs: int = TARGET_FS,
    frame: int = NOISE_FRAME,
    hop: int = NOISE_HOP,
) -> np.ndarray:
    """
    Noise floor spectrum from an explicit still-mouse recording
    (e.g. the original pipeline's `noise_*.csv` captures).
    """
    _, _, power = _stft_mag_pow(noise, Fs, frame, hop)
    return np.sqrt(power.mean(axis=1))


def spectral_subtraction(
    x: np.ndarray,
    Fs: int = TARGET_FS,
    noise_mag: Optional[np.ndarray] = None,
    frame: int = NOISE_FRAME,
    hop: int = NOISE_HOP,
    alpha: float = OVERSUBTRACTION,
    beta: float = SPECTRAL_FLOOR,
) -> np.ndarray:
    """
    Magnitude-domain spectral subtraction with spectral flooring.

    |X_hat(f,t)| = max(|X(f,t)| - alpha * |N(f)|, beta * |X(f,t)|)

    The floor `beta` prevents the classic musical-noise artifact of
    trivial spectral subtraction. Phase is untouched (STFT phase is
    relatively robust against magnitude suppression).

    :param noise_mag: Pre-estimated noise magnitude spectrum
                      (see `estimate_noise_floor` /
                      `noise_floor_from_recording`). If None it is
                      estimated from the quietest frames of `x` itself.
    :return: Denoised time-domain signal.
    """
    _require_scipy()
    if len(x) < frame:
        return x
    Zxx, mag, _ = _stft_mag_pow(x, Fs, frame, hop)
    if noise_mag is None:
        quiet_fraction_est = 0.10
        noise_mag = estimate_noise_floor(x, Fs, frame, hop, quiet_fraction_est)
    noise_mag = np.asarray(noise_mag)[: mag.shape[0]]
    # Floor magnitude to avoid division blowup on silent bins.
    denom = np.maximum(mag, 1e-12)
    gain = np.maximum(mag - alpha * noise_mag[:, None], beta * mag) / denom
    _, x_clean = istft(Zxx * gain, fs=Fs, nperseg=frame, noverlap=frame - hop)
    return np.pad(x_clean, (0, max(0, len(x) - len(x_clean))))[: len(x)]


def soft_noise_gate(
    x: np.ndarray,
    Fs: int = TARGET_FS,
    hop: int = 64,
    gate_percentile: float = 20.0,
    threshold_mult: float = 1.6,
    release_ms: float = 40.0,
    floor_db: float = -18.0,
) -> np.ndarray:
    """
    Complementary short-time RMS gate (downward expander).

    Frames whose RMS sits below `threshold_mult * P20(rms)` (i.e. the
    at-rest surface noise band) are attenuated by `floor_db`; frames
    above the threshold are untouched. A per-sample one-pole envelope
    with `release_ms` time constant removes switching artifacts.

    :param gate_percentile: Percentile of frame RMS used to anchor the
                            noise level.
    :param threshold_mult: Multiplier over that percentile to open the gate.
    :param floor_db: Maximum attenuation in dB applied to gated frames.
    :return: Gated signal.
    """
    n_frames = max(1, len(x) // hop)
    frames = np.split(x[: n_frames * hop], n_frames)
    rms = np.sqrt(np.mean([f ** 2 for f in frames], axis=1) + 1e-24)
    thr = threshold_mult * np.percentile(rms, gate_percentile)
    frame_gain = np.where(rms >= thr, 1.0, max(1e-3, 10 ** (floor_db / 20.0)))
    # Upsample per-frame gain to per-sample, then smooth with a one-pole
    # envelope (attack/release) to avoid switching artifacts.
    sample_gain = np.repeat(frame_gain, hop)[: len(x)]
    if len(sample_gain) < len(x):
        sample_gain = np.concatenate([sample_gain, np.full(len(x) - len(sample_gain), frame_gain[-1])])
    a = 1.0 - np.exp(-1.0 / max(1e-6, release_ms * Fs / 1000.0))
    envelope = lfilter([a], [1, -(1 - a)], sample_gain)
    return x * envelope


# --------------------------------------------------------------------------
# Req. 2 -- HF amplification / pre-emphasis
# --------------------------------------------------------------------------
def preemphasis(
    x: np.ndarray,
    coeff: float = PREEMPH_COEFF,
) -> np.ndarray:
    """
    First-order pre-emphasis: y[n] = x[n] - coeff * x[n-1].

    Y(f) = X(f) * (1 - coeff * e^{-jw}); slope is roughly flat at DC and
    rises ~6 dB/octave before the pole-zero pair. This restores the HF
    energy share that the sparse sampling / low sensor CPI leaves
    buried under LF surface rumble without amplifying the rumble.

    Use `deemphasis` to invert for playback.
    """
    y = np.empty_like(x)
    y[0] = x[0]
    np.subtract(x[1:], coeff * x[:-1], out=y[1:])
    return y


def deemphasis(
    x: np.ndarray,
    coeff: float = PREEMPH_COEFF,
) -> np.ndarray:
    """Inverse of `preemphasis` (y[n] = x[n] + coeff*y[n-1])."""
    return lfilter([1.0], [1.0, -coeff], x)


# --------------------------------------------------------------------------
# Normalization
# --------------------------------------------------------------------------
def normalize_axes(
    X: np.ndarray,
    Y: np.ndarray,
    headroom: float = 0.98,
    percentile: float = 99.5,
) -> tuple:
    """
    Joint robust normalization of both axes.

    A shared scale (percentile of |.| over BOTH channels) is used so the
    X/Y ratio -- which carries the phase information for binaural-style
    source separation -- is preserved. Clipped to ~full scale afterwards.

    :return: (X_norm, Y_norm, scale) with scale for debug/QA.
    """
    ref = max(
        np.percentile(np.abs(X), percentile),
        np.percentile(np.abs(Y), percentile),
        1e-12,
    )
    Xn = np.clip(X / ref * headroom, -headroom, headroom)
    Yn = np.clip(Y / ref * headroom, -headroom, headroom)
    return Xn, Yn, ref


# --------------------------------------------------------------------------
# Nonuniform -> uniform resampler (NumPy mirror of preprocess.resample)
# --------------------------------------------------------------------------
def resample_nonuniform(
    deltaT: np.ndarray,
    nuX: np.ndarray,
    nuY: Optional[np.ndarray] = None,
    Fs: int = TARGET_FS,
    method: str = "lanczos",
    taps: int = 12,
    gain: float = 1.0,
):
    """
    Torch-free resampling from nonuniform event deltas to a uniform grid.

    Same math as `core/signal/preprocess.py:resample` (so notebooks and
    CLI agree) but implemented in NumPy/SciPy. `taps` is used by the
    windowed-sinc ('lanczos') kernel: larger taps (12-16) smooth the
    staircase of upsampling a 1-2 kHz recording to 16 kHz.

    :param deltaT: Inter-event time deltas in microseconds.
    :param gain: Amplitude gain applied to X/Y before interpolation.
    :return: (T_seconds, X, Y)
    """
    deltaT = np.asarray(deltaT, dtype=np.float64)
    nuX = np.asarray(nuX, dtype=np.float64) * gain
    nuY = None if nuY is None else np.asarray(nuY, dtype=np.float64) * gain

    Tcumul = np.cumsum(deltaT) - deltaT[0]
    Tmax = Tcumul[-1]
    n_out = max(int(Tmax * Fs / 1e6), 1)
    T_uniform = np.linspace(0.0, Tmax, n_out)

    idx = np.searchsorted(Tcumul, T_uniform, side="right") - 1
    idx = np.clip(idx, 0, Tcumul.shape[0] - 2)
    W = (T_uniform - Tcumul[idx]) / (Tcumul[idx + 1] - Tcumul[idx])

    if method == "nearest":
        Xr = nuX[idx]
        Yr = nuY[idx] if nuY is not None else np.zeros_like(Xr)
    elif method == "linear":
        Xr = (1 - W) * nuX[idx] + W * nuX[idx + 1]
        Yr = (1 - W) * nuY[idx] + W * nuY[idx + 1]
    elif method == "cubic":
        # Hermite / Catmull-Rom equivalent of the torch implementation.
        W0 = 2 * W ** 3 - 3 * W ** 2 + 1
        W1 = -2 * W ** 3 + 3 * W ** 2
        Xr = W0 * nuX[idx] + W1 * nuX[idx + 1]
        Yr = W0 * nuY[idx] + W1 * nuY[idx + 1]
    elif method == "sinc":
        f = np.sinc((1 - W))
        f1 = np.sinc(W)
        Xr = f * nuX[idx] + f1 * nuX[idx + 1]
        Yr = f * nuY[idx] + f1 * nuY[idx + 1]
    elif method == "lanczos":
        # np.sinc uses sin(pi x)/(pi x), matching sinc() in preprocess.py.
        offs = np.arange(-taps + 1, taps + 1)
        idx_j = np.clip(idx[:, None] + offs[None, :], 0, Tcumul.shape[0] - 1)
        fr = W[:, None] - offs[None, :]
        k = np.sinc(fr) * np.sinc(fr / taps)
        inside = np.abs(fr) < taps
        k = np.where(inside, k, 0.0)
        k /= np.maximum(k.sum(axis=1, keepdims=True), 1e-12)
        Xr = (k * nuX[idx_j]).sum(axis=1)
        Yr = (k * nuY[idx_j]).sum(axis=1)
    else:
        raise ValueError(f"unknown interpolation method: {method}")

    return T_uniform / 1e6, Xr, Yr


# --------------------------------------------------------------------------
# Full extraction pipeline
# --------------------------------------------------------------------------
def load_mouse_csv(path: str, max_seconds: Optional[float] = None):
    """
    Load a Mic-E-Mouse CSV (`offset, x, y` with microsecond deltas).

    :param max_seconds: Keep only events whose cumulative time <= N s.
    :return: (deltaT_us float64, X, Y float64)
    """
    data = np.loadtxt(path, delimiter=",", skiprows=1, dtype=np.float64)
    deltaT = data[:, 0]
    X = data[:, 1]
    Y = data[:, 2]
    if max_seconds is not None:
        cum = np.cumsum(deltaT) - deltaT[0]
        keep = np.searchsorted(cum, max_seconds * 1e6, side="right")
        n = min(max(keep + 2, 2), len(deltaT))  # include the event that crosses the limit + 1
        deltaT = deltaT[:n]
        X = X[:n]
        Y = Y[:n]
    return deltaT, X, Y


def extract_mouse_audio(
    csv_path: str,
    dpi: Optional[int] = 4000,
    polling_rate: Optional[int] = None,
    profile: Optional[str] = None,
    Fs: int = TARGET_FS,
    method: str = "lanczos",
    taps: Optional[int] = None,
    gain: Optional[float] = None,
    denoise: bool = True,
    gate: bool = True,
    preemph_coeff: float = PREEMPH_COEFF,
    imaging_filter: bool = True,
    noise_csv: Optional[str] = None,
    max_seconds: Optional[float] = None,
) -> dict:
    """
    Extract audible audio from a mouse CSV recording, adapted for
    4,000 DPI / 1-2 kHz hardware.

    :param dpi: Configured sensor CPI (amplitude gain compensation).
    :param polling_rate: Native polling rate; estimated from the CSV if None.
    :param profile: name from `core/signal/br_mouse.py:PROFILES` preset;
                    overridable by explicit `dpi`/`gain`.
    :param method: Interpolation ('lanczos' recommended for <= 4 kHz polling).
    :param taps: Lanczos kernel radius (auto from polling rate if None).
    :param denoise: Spectral subtraction stage (req 3).
    :param gate: Soft noise gate stage (req 3).
    :param preemph_coeff: 0 disables pre-emphasis (req 2).
    :param imaging_filter: Nyquist-window low-pass (req 1).
    :param noise_csv: Optional still-mouse CSV for an explicit noise floor.
    :return: dict with keys:
        Fs           - uniform output rate
        polling_est  - estimated effective polling rate (Hz)
        X, Y         - processed axes
        mono         - (X + Y) / 2
        info         - dict of all pipeline decisions (for QA)
    """
    # -- Profile resolution ------------------------------------------------
    prof = get_profile(profile) if profile else get_profile(DEFAULT_PROFILE)
    if dpi is None and profile is None:
        dpi = prof.dpi
    eff_gain = resolve_gain(prof, dpi, gain)

    # -- Load ---------------------------------------------------------------
    deltaT, nuX, nuY = load_mouse_csv(csv_path, max_seconds=max_seconds)
    est_polling = polling_rate or estimate_polling_rate(deltaT)
    viab = polling_viability(est_polling)
    if taps is None:
        taps = int(viab["recommended_lanczos_taps"])

    # -- Resample (req 0: DPI gain folded into resampler) -------------------
    T, X, Y = resample_nonuniform(
        deltaT, nuX, nuY, Fs=Fs, method=method, taps=taps, gain=eff_gain
    )

    info = {
        "profile": prof.name if profile else DEFAULT_PROFILE,
        "dpi": dpi,
        "gain": eff_gain,
        "polling_est_hz": est_polling,
        "audio_ceiling_hz": viab["audio_ceiling_hz"],
        "method": method,
        "taps": taps,
        "denoise": denoise,
        "gate": gate,
        "preemph_coeff": preemph_coeff,
        "imaging_filter": imaging_filter,
        "seconds": float(T[-1]) if len(T) else 0.0,
    }

    # -- Noise floor (from explicit still recording, or in-situ) ------------
    noise_mag = None
    if noise_csv is not None:
        nT, nX, nY = load_mouse_csv(noise_csv)
        nTu, nXu, nYu = resample_nonuniform(
            nT, nX, nY, Fs=Fs, method=method, taps=taps, gain=eff_gain
        )
        noise_mag = noise_floor_from_recording((nXu + nYu) / 2.0, Fs)

    def process_axis(axis: np.ndarray) -> np.ndarray:
        out = axis
        if imaging_filter:
            # Req. 1: Nyquist window / anti-imaging before anything else.
            out = imaging_lowpass(out, Fs, est_polling)
        if denoise:
            # Req. 3: spectral subtraction before normalization.
            out = spectral_subtraction(out, Fs, noise_mag=noise_mag)
        if gate:
            out = soft_noise_gate(out, Fs)
        if preemph_coeff:
            # Req. 2: HF amplification.
            out = preemphasis(out, preemph_coeff)
        return out

    X = process_axis(X)
    Y = process_axis(Y)

    X, Y, scale = normalize_axes(X, Y)
    info["norm_scale"] = float(scale)

    return {
        "Fs": Fs,
        "polling_est": est_polling,
        "X": X,
        "Y": Y,
        "mono": (X + Y) / 2.0,
        "info": info,
    }


# --------------------------------------------------------------------------
# WAVIO (stdlib only, no torchaudio dependency)
# --------------------------------------------------------------------------
def write_wav(
    path: str,
    audio: np.ndarray,
    Fs: int = TARGET_FS,
) -> str:
    """
    Write 1D float audio to a 16-bit PCM WAV file using only the stdlib.

    :return: The path written.
    """
    audio = np.asarray(audio, dtype=np.float64).reshape(-1)
    audio = np.nan_to_num(audio, nan=0.0, posinf=0.0, neginf=0.0)
    headroom = np.max(np.abs(audio))
    if headroom > 1.0:
        audio = audio / headroom * 0.98
    samples = (audio * 32767.0).astype(np.int16)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(int(Fs))
        wf.setcomptype("NONE", "PCM")
        wf.writeframes(samples.tobytes())
    return path
