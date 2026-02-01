"""
システム環境検出サービス

サーバーのCPU、メモリ、GPU情報を検出し、
ハードウェアに基づいたWhisperモデルの推奨設定を提供する。
"""

import logging
import platform
from typing import Any, Dict, List, Optional

import psutil

logger = logging.getLogger(__name__)


# Whisperモデル情報の定数定義（単一の情報源）
WHISPER_MODELS: List[Dict[str, Any]] = [
    {
        "name": "tiny",
        "parameters": "39M",
        "required_vram_gb": 1.0,
        "required_ram_gb": 1.0,
        "relative_speed": "~32x",
        "description": "最速。精度は低いがテスト用途に最適。",
    },
    {
        "name": "base",
        "parameters": "74M",
        "required_vram_gb": 1.0,
        "required_ram_gb": 1.0,
        "relative_speed": "~16x",
        "description": "高速。軽量なモデルで基本的な文字起こしに対応。",
    },
    {
        "name": "small",
        "parameters": "244M",
        "required_vram_gb": 2.0,
        "required_ram_gb": 2.0,
        "relative_speed": "~6x",
        "description": "バランス型。速度と精度の良いバランス。",
    },
    {
        "name": "medium",
        "parameters": "769M",
        "required_vram_gb": 5.0,
        "required_ram_gb": 5.0,
        "relative_speed": "~2x",
        "description": "高精度。多くの用途で十分な精度を提供。",
    },
    {
        "name": "large-v3",
        "parameters": "1.5B",
        "required_vram_gb": 10.0,
        "required_ram_gb": 10.0,
        "relative_speed": "1x",
        "description": "最高精度。日本語音声に最も高い精度を発揮。",
    },
]

# 有効なモデル名のセット（バリデーション用）
VALID_MODEL_NAMES = {m["name"] for m in WHISPER_MODELS}


class SystemInfoService:
    """
    システムハードウェア情報の検出と推奨モデル選定

    CPU、RAM、GPUの情報を検出し、利用可能なリソースに基づいて
    最適なWhisperモデルとデバイスを推奨する。
    """

    def get_system_info(self) -> Dict[str, Any]:
        """
        システム情報を取得する。

        Returns:
            CPU、RAM、GPU、プラットフォーム情報、モデル一覧、推奨設定を含む辞書
        """
        gpu_info = self._get_gpu_info()
        ram_info = self._get_ram_info()

        return {
            "cpu": self._get_cpu_info(),
            "ram": ram_info,
            "gpu": gpu_info,
            "platform": {
                "system": platform.system(),
                "release": platform.release(),
                "python_version": platform.python_version(),
            },
            "whisper_models": WHISPER_MODELS,
            "recommendation": self._get_recommendation(ram_info, gpu_info),
        }

    def _get_cpu_info(self) -> Dict[str, Any]:
        """
        CPU情報を取得する。

        Returns:
            CPUモデル名、物理コア数、論理コア数、周波数を含む辞書
        """
        # CPUモデル名の取得（プラットフォームにより異なる）
        cpu_model = platform.processor()
        if not cpu_model:
            cpu_model = platform.machine()

        # Windows環境では環境変数からCPU名を取得
        if platform.system() == "Windows":
            import os
            cpu_model = os.environ.get("PROCESSOR_IDENTIFIER", cpu_model)

        # CPU周波数の取得
        freq = psutil.cpu_freq()
        freq_mhz = round(freq.current) if freq else None

        return {
            "model": cpu_model,
            "physical_cores": psutil.cpu_count(logical=False) or 0,
            "logical_cores": psutil.cpu_count(logical=True) or 0,
            "frequency_mhz": freq_mhz,
        }

    def _get_ram_info(self) -> Dict[str, Any]:
        """
        RAM情報を取得する。

        Returns:
            合計容量、空き容量、使用率を含む辞書
        """
        mem = psutil.virtual_memory()
        return {
            "total_gb": round(mem.total / (1024**3), 1),
            "available_gb": round(mem.available / (1024**3), 1),
            "used_percent": mem.percent,
        }

    def _get_gpu_info(self) -> Optional[Dict[str, Any]]:
        """
        GPU情報を取得する（CUDAが利用可能な場合のみ）。

        Returns:
            GPU名、VRAM容量、CUDAバージョンを含む辞書。GPU未検出時はNone。
        """
        try:
            import torch

            if not torch.cuda.is_available():
                return None

            props = torch.cuda.get_device_properties(0)
            vram_total = props.total_mem / (1024**3)

            # 利用可能なVRAMの計算
            vram_reserved = torch.cuda.memory_reserved(0) / (1024**3)
            vram_available = vram_total - vram_reserved

            return {
                "name": torch.cuda.get_device_name(0),
                "vram_total_gb": round(vram_total, 1),
                "vram_available_gb": round(vram_available, 1),
                "cuda_version": torch.version.cuda or "不明",
                "device_count": torch.cuda.device_count(),
            }
        except ImportError:
            logger.info("PyTorchがインストールされていないため、GPU情報を取得できません。")
            return None
        except Exception as e:
            logger.warning("GPU情報の取得に失敗しました: %s", str(e))
            return None

    def _get_recommendation(
        self,
        ram_info: Dict[str, Any],
        gpu_info: Optional[Dict[str, Any]],
    ) -> Dict[str, str]:
        """
        ハードウェアに基づく推奨モデルとデバイスを返す。

        利用可能なメモリの80%以内で実行可能な最大のモデルを推奨する。

        Args:
            ram_info: RAM情報
            gpu_info: GPU情報（Noneの場合はCPUモード）

        Returns:
            推奨モデル名、デバイス、推奨理由を含む辞書
        """
        # GPU利用可能ならGPU推奨
        if gpu_info is not None:
            recommended_device = "cuda"
            available_memory_gb = gpu_info["vram_total_gb"]
            memory_label = f"GPU VRAM {available_memory_gb:.1f}GB"
        else:
            recommended_device = "cpu"
            available_memory_gb = ram_info["available_gb"]
            memory_label = f"RAM {available_memory_gb:.1f}GB（空き）"

        # 利用可能メモリの80%以内で最大のモデルを選択
        usable_memory = available_memory_gb * 0.8
        memory_key = (
            "required_vram_gb" if recommended_device == "cuda" else "required_ram_gb"
        )

        recommended_model = "tiny"  # フォールバック
        for model in WHISPER_MODELS:
            if model[memory_key] <= usable_memory:
                recommended_model = model["name"]

        return {
            "model": recommended_model,
            "device": recommended_device,
            "reason": f"{memory_label}に基づく推奨設定です。",
        }
