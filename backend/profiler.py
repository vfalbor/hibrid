"""Detección de capacidades de la máquina (multiplataforma) -> qué puede ejecutar.

Implementa la guía de BenchAgent: psutil (RAM/CPU) + pynvml/nvidia-smi/torch (VRAM
NVIDIA) + system_profiler (Apple). Traduce el hardware detectado al mayor modelo
ejecutable en Q4 y a una "clase de máquina".
"""
from __future__ import annotations

import platform
import shutil
import subprocess
from dataclasses import asdict, dataclass


@dataclass
class HardwareProfile:
    os: str
    arch: str
    cpu: str
    cpu_cores_physical: int
    ram_gb: float
    gpu_vendor: str          # "nvidia" | "amd" | "apple" | "none"
    gpu_name: str
    vram_gb: float           # VRAM dedicada; en Apple = memoria unificada utilizable
    apple_silicon: bool
    # Derivados:
    machine_class: str = ""
    max_local_params_b: float = 0.0   # mayor modelo (B params) ejecutable en Q4

    def to_dict(self) -> dict:
        return asdict(self)


# ---------- detección de RAM/CPU ----------

def _ram_gb() -> float:
    try:
        import psutil
        return round(psutil.virtual_memory().total / 1e9, 1)
    except Exception:
        try:
            return round(int(subprocess.check_output(["sysctl", "-n", "hw.memsize"])) / 1e9, 1)
        except Exception:
            return 0.0


def _cpu_info() -> tuple[str, int]:
    cores = 0
    try:
        import psutil
        cores = psutil.cpu_count(logical=False) or 0
    except Exception:
        pass
    name = platform.processor() or platform.machine()
    try:
        if platform.system() == "Darwin":
            name = subprocess.check_output(
                ["sysctl", "-n", "machdep.cpu.brand_string"], text=True
            ).strip()
    except Exception:
        pass
    return name, cores


# ---------- detección de GPU ----------

def _nvidia_vram_gb() -> float:
    # 1) pynvml (programático)
    try:
        import pynvml
        pynvml.nvmlInit()
        h = pynvml.nvmlDeviceGetHandleByIndex(0)
        total = pynvml.nvmlDeviceGetMemoryInfo(h).total
        pynvml.nvmlShutdown()
        return round(total / 1e9, 1)
    except Exception:
        pass
    # 2) torch
    try:
        import torch
        if torch.cuda.is_available():
            return round(torch.cuda.get_device_properties(0).total_memory / 1e9, 1)
    except Exception:
        pass
    # 3) nvidia-smi
    if shutil.which("nvidia-smi"):
        try:
            out = subprocess.check_output(
                ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
                text=True,
            ).strip().splitlines()[0]
            return round(float(out) / 1024, 1)  # MiB -> GB
        except Exception:
            pass
    return 0.0


def _nvidia_name() -> str:
    if shutil.which("nvidia-smi"):
        try:
            return subprocess.check_output(
                ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"], text=True
            ).strip().splitlines()[0]
        except Exception:
            pass
    return "NVIDIA GPU"


def _detect_gpu(ram_gb: float) -> tuple[str, str, float, bool]:
    system = platform.system()
    arch = platform.machine().lower()
    apple = system == "Darwin" and arch in ("arm64", "aarch64")
    if apple:
        # Memoria unificada: reservar ~3 GB para el SO.
        usable = max(0.0, ram_gb - 3.0)
        name = "Apple Silicon"
        try:
            chip = subprocess.check_output(
                ["sysctl", "-n", "machdep.cpu.brand_string"], text=True
            ).strip()
            if chip:
                name = chip
        except Exception:
            pass
        return "apple", name, usable, True

    vram = _nvidia_vram_gb()
    if vram > 0:
        return "nvidia", _nvidia_name(), vram, False

    if shutil.which("rocm-smi"):
        return "amd", "AMD GPU (ROCm)", 0.0, False  # VRAM AMD no parseada aquí

    return "none", "CPU only", 0.0, False


# ---------- traducción a clase de máquina + modelo máximo ----------

def _max_params_q4(profile_vram_gb: float, ram_gb: float, gpu_vendor: str) -> float:
    """Mayor modelo (B params) ejecutable en Q4: params ~= (mem-2)/0.65."""
    if gpu_vendor == "apple":
        budget = profile_vram_gb            # ya descontado SO
    elif gpu_vendor == "nvidia" and profile_vram_gb > 0:
        budget = profile_vram_gb - 2
    else:
        budget = ram_gb - 3                 # CPU-only
    params = max(0.0, budget / 0.65)
    if gpu_vendor == "none":
        params = min(params, 8.0)           # CPU: límite por velocidad, no por memoria
    return round(params, 1)


def _classify(gpu_vendor: str, vram_gb: float, ram_gb: float) -> str:
    if gpu_vendor == "apple":
        if ram_gb >= 64: return "apple_silicon_64gb+"
        if ram_gb >= 32: return "apple_silicon_32gb"
        if ram_gb >= 16: return "apple_silicon_16gb"
        return "apple_silicon_8gb"
    if gpu_vendor == "nvidia":
        if vram_gb >= 48: return "server_gpu_48gb+"
        if vram_gb >= 24: return "gpu_24gb"
        if vram_gb >= 12: return "gpu_12_16gb"
        if vram_gb >= 8:  return "gpu_8gb"
        return "gpu_small"
    # CPU-only
    if ram_gb >= 16: return "cpu_16gb"
    return "cpu_8gb"


def detect() -> HardwareProfile:
    ram = _ram_gb()
    cpu_name, cores = _cpu_info()
    vendor, gpu_name, vram, apple = _detect_gpu(ram)
    p = HardwareProfile(
        os=platform.system(),
        arch=platform.machine(),
        cpu=cpu_name,
        cpu_cores_physical=cores,
        ram_gb=ram,
        gpu_vendor=vendor,
        gpu_name=gpu_name,
        vram_gb=vram,
        apple_silicon=apple,
    )
    p.machine_class = _classify(vendor, vram, ram)
    p.max_local_params_b = _max_params_q4(vram, ram, vendor)
    return p


if __name__ == "__main__":
    import json
    print(json.dumps(detect().to_dict(), indent=2, ensure_ascii=False))
