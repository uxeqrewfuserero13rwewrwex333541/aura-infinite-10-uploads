"""
Modulo del visualizador radial v8 (definitivo).

Estrategia: render PIL frame-by-frame.
  - librosa analiza el audio (mel spectrogram + onset envelope)
  - Por cada frame del video, se dibujan 110 barras radiales identicas alrededor
    del vinilo, cuya altura depende de la amplitud de cada banda de frecuencia
  - El vinilo "pulsa" suavemente segun la deteccion de bass

Uso:
    from radial_visualizer import render_radial_video
    render_radial_video(base_png, vinyl_img, audio_path, out_path, duration=180)
"""
from __future__ import annotations
import math
import subprocess
import sys
from pathlib import Path
import numpy as np
import librosa
from PIL import Image, ImageDraw
from scipy.ndimage import uniform_filter1d

from imageio_ffmpeg import get_ffmpeg_exe

FFMPEG = get_ffmpeg_exe()

# ====== CONFIG VISUALIZADOR v8 ======
W, H = 1920, 1080
CENTER_X = W // 2
CENTER_Y = int(H * 0.46)
VINYL_RADIUS = 250
VINYL_SIZE = VINYL_RADIUS * 2

INNER_R = VINYL_RADIUS + 8        # base de las barras (pegadas al vinilo, con margen pequeno)
BAR_MAX_HEIGHT = 140              # altura maxima al pico (mas largas)
BAR_MIN_HEIGHT = 4                # altura minima visible
BAR_WIDTH = 8                     # ancho de cada barra
BAR_RADIUS = 3                    # esquinas redondeadas
NUM_BARS = 110                    # densidad alrededor del vinilo

# Sensibilidad: cuanto mas alto, MENOS reactivo (necesita mas energia para crecer).
# 1.4 = sensible. 2.5 = solo se mueve con bass/peaks fuertes.
SENSITIVITY_GAMMA = 2.5

FPS = 20
PULSE_AMPLITUDE = 0.05            # max scale del vinilo (5%)
# ====================================


def analyze_audio(audio_path: Path, duration: float | None = None
                  ) -> tuple[np.ndarray, np.ndarray, float]:
    """Analiza el audio y devuelve:
       - bar_amps: shape (n_frames, NUM_BARS), valores [0..1]
       - pulse_scales: shape (n_frames,), valores [1.0 .. 1+PULSE_AMPLITUDE]
       - duration_used: duracion real procesada (en segundos)
    """
    if duration is not None:
        y, sr = librosa.load(str(audio_path), sr=22050, duration=duration)
    else:
        y, sr = librosa.load(str(audio_path), sr=22050)
    duration_used = len(y) / sr

    n_frames = int(duration_used * FPS)
    hop = max(1, int(sr / FPS))

    # Mel spectrogram con NUM_BARS bandas
    mel = librosa.feature.melspectrogram(
        y=y, sr=sr, n_mels=NUM_BARS, hop_length=hop, fmin=40, fmax=11000,
    )
    mel_db = librosa.power_to_db(mel, ref=np.max)
    mel_norm = np.clip((mel_db + 80) / 80, 0, 1)
    mel_norm = uniform_filter1d(mel_norm, size=3, axis=1)

    src_t = np.linspace(0, duration_used, mel_norm.shape[1])
    dst_t = np.linspace(0, duration_used, n_frames)
    bar_amps = np.zeros((n_frames, NUM_BARS))
    for b in range(NUM_BARS):
        bar_amps[:, b] = np.interp(dst_t, src_t, mel_norm[b])
    bar_amps = bar_amps ** SENSITIVITY_GAMMA   # gamma alto = menos reactivo

    # Pulse del vinilo (onset envelope = bass detection)
    onset = librosa.onset.onset_strength(y=y, sr=sr, hop_length=hop)
    onset_t = librosa.frames_to_time(np.arange(len(onset)), sr=sr, hop_length=hop)
    onset_norm = onset / onset.max() if onset.max() > 0 else onset
    pulse = np.interp(dst_t, onset_t, onset_norm)
    pulse_scales = 1.0 + PULSE_AMPLITUDE * pulse

    return bar_amps, pulse_scales, duration_used


def render_frame(base: Image.Image, vinyl: Image.Image,
                 bar_heights: np.ndarray, pulse_scale: float) -> Image.Image:
    """Genera UN frame: base + vinilo escalado + barras radiales."""
    frame = base.copy()

    # 1) Vinilo con pulse
    new_size = int(VINYL_SIZE * pulse_scale)
    vinyl_scaled = vinyl.resize((new_size, new_size), Image.LANCZOS)
    vx = CENTER_X - new_size // 2
    vy = CENTER_Y - new_size // 2
    frame.paste(vinyl_scaled, (vx, vy), vinyl_scaled)

    # 2) Barras radiales en una capa transparente para alpha-composite
    draw_canvas = Image.new("RGBA", frame.size, (0, 0, 0, 0))
    for i, h_norm in enumerate(bar_heights):
        height = int(BAR_MIN_HEIGHT + (BAR_MAX_HEIGHT - BAR_MIN_HEIGHT) * h_norm)
        if height < BAR_MIN_HEIGHT:
            continue
        bar_img = Image.new("RGBA", (BAR_WIDTH, height), (0, 0, 0, 0))
        ImageDraw.Draw(bar_img).rounded_rectangle(
            (0, 0, BAR_WIDTH, height), radius=BAR_RADIUS, fill=(0, 0, 0, 255)
        )
        angle_deg = i * (360 / NUM_BARS) - 90
        angle_rad = math.radians(angle_deg)
        rot_deg = -(angle_deg + 90)
        bar_rotated = bar_img.rotate(rot_deg, resample=Image.BILINEAR, expand=True)

        # Posicionar de modo que la BASE de la barra quede exactamente en INNER_R
        # (no el centro). Asi las barras cortas tambien tocan el borde del vinilo.
        radial_dist = INNER_R + height / 2
        cx = CENTER_X + radial_dist * math.cos(angle_rad)
        cy = CENTER_Y + radial_dist * math.sin(angle_rad)
        bw, bh = bar_rotated.size
        draw_canvas.paste(bar_rotated, (int(cx - bw / 2), int(cy - bh / 2)), bar_rotated)

    return Image.alpha_composite(frame.convert("RGBA"), draw_canvas).convert("RGB")


def render_radial_video(base_png: Path, vinyl_img: Image.Image,
                        audio_path: Path, out_path: Path,
                        duration: float | None = None,
                        verbose: bool = True) -> Path:
    """Renderiza el video completo con visualizador radial.

    base_png: imagen base 1920x1080 SIN el vinilo central (skip_center=True)
    vinyl_img: PIL Image RGBA del vinilo con la portada
    audio_path: ruta al mp3
    out_path: ruta de salida del .mp4
    duration: en segundos. None = usar toda la cancion
    """
    if verbose:
        print("  [viz] Analizando audio...")
    bar_amps, pulse_scales, duration_used = analyze_audio(audio_path, duration)
    n_frames = bar_amps.shape[0]
    if verbose:
        print(f"  [viz] {n_frames} frames @ {FPS}fps ({duration_used:.1f}s)")

    base_img = Image.open(base_png).convert("RGB")

    cmd = [
        FFMPEG, "-y",
        "-f", "rawvideo", "-vcodec", "rawvideo",
        "-pix_fmt", "rgb24",
        "-s", f"{W}x{H}",
        "-r", str(FPS),
        "-i", "-",
        "-i", str(audio_path),
        "-t", str(duration_used),
        "-c:v", "libx264", "-preset", "fast", "-crf", "20",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest", str(out_path),
    ]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)

    for fi in range(n_frames):
        frame = render_frame(base_img, vinyl_img, bar_amps[fi], pulse_scales[fi])
        proc.stdin.write(frame.tobytes())
        if verbose and (fi + 1) % 100 == 0:
            print(f"  [viz] frame {fi+1}/{n_frames}")

    proc.stdin.close()
    rc = proc.wait()
    if rc != 0:
        err = proc.stderr.read().decode()[-2000:]
        raise RuntimeError(f"FFmpeg fallo: {err}")
    return out_path
