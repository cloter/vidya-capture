# Arquivo: core/camera_calculator.py

import math
from typing import Tuple, Dict

class CameraCalculator:
    """Motor de cálculo estático para engenharia óptica de digitalização."""

    @staticmethod
    def calc_resolution_from_dpi(width_cm: float, height_cm: float, dpi: int) -> Dict[str, float]:
        """Calcula a resolução e megapixels necessários a partir de um DPI alvo."""
        if width_cm <= 0 or height_cm <= 0 or dpi <= 0:
            return {"px_w": 0.0, "px_h": 0.0, "mp": 0.0}

        px_w = (width_cm / 2.54) * dpi
        px_h = (height_cm / 2.54) * dpi
        mp = (px_w * px_h) / 1_000_000

        return {"px_w": round(px_w), "px_h": round(px_h), "mp": round(mp, 1)}

    @staticmethod
    def calc_dpi_from_resolution(width_cm: float, height_cm: float, sensor_mp: float) -> Dict[str, float]:
        """Calcula o DPI máximo alcançável com base nos Megapixels informados."""
        if width_cm <= 0 or height_cm <= 0 or sensor_mp <= 0:
            return {"px_w": 0.0, "px_h": 0.0, "dpi": 0.0}

        area_inches = (width_cm / 2.54) * (height_cm / 2.54)
        total_pixels = sensor_mp * 1_000_000
        
        # DPI = Raiz quadrada (Total de Pixels / Área em Polegadas Quadradas)
        dpi = math.sqrt(total_pixels / area_inches)
        
        # Estima as dimensões em pixels mantendo a proporção geométrica
        ratio = width_cm / height_cm
        px_h = math.sqrt(total_pixels / ratio)
        px_w = px_h * ratio

        return {"px_w": round(px_w), "px_h": round(px_h), "dpi": round(dpi)}

    @staticmethod
    def calc_sensor_utilization(sensor_w_px: int, sensor_h_px: int, capture_w_cm: float, doc_w_cm: float, doc_h_cm: float) -> Dict[str, float]:
        """Audita o desperdício do sensor cruzando a área capturada versus a área do documento."""
        if capture_w_cm <= 0 or sensor_w_px <= 0 or doc_w_cm <= 0:
            return {"real_dpi": 0.0, "useful_mp": 0.0, "utilization_pct": 0.0}

        # Calcula o DPI real baseando-se na largura física projetada no sensor
        real_dpi = sensor_w_px / (capture_w_cm / 2.54)
        
        # Calcula quantos pixels caem efetivamente em cima do papel
        useful_px_w = (doc_w_cm / 2.54) * real_dpi
        useful_px_h = (doc_h_cm / 2.54) * real_dpi
        
        # Limita ao tamanho máximo do sensor caso o documento seja maior que a captura
        useful_px_w = min(useful_px_w, float(sensor_w_px))
        useful_px_h = min(useful_px_h, float(sensor_h_px))

        useful_mp = (useful_px_w * useful_px_h) / 1_000_000
        sensor_mp = (sensor_w_px * sensor_h_px) / 1_000_000
        
        utilization_pct = (useful_mp / sensor_mp) * 100 if sensor_mp > 0 else 0

        return {
            "real_dpi": round(real_dpi), 
            "useful_mp": round(useful_mp, 2), 
            "utilization_pct": round(utilization_pct, 1)
        }

    @staticmethod
    def calc_ideal_capture_width(sensor_w_px: int, target_dpi: int) -> float:
        """Calcula qual deve ser a largura física na mesa para atingir o DPI exato."""
        if target_dpi <= 0:
            return 0.0
        # Formula: Largura_Polegadas = Pixels / DPI
        capture_w_inches = sensor_w_px / target_dpi
        capture_w_cm = capture_w_inches * 2.54
        return round(capture_w_cm, 2)

    @staticmethod
    def calc_distance(sensor_w_mm: float, focal_len_mm: float, fov_w_cm: float) -> float:
        """Calcula a altura da câmera (Aproximação de Lente Fina)."""
        if sensor_w_mm <= 0 or focal_len_mm <= 0:
            return 0.0
        dist_cm = (focal_len_mm * fov_w_cm) / sensor_w_mm
        return round(dist_cm, 2)

    @staticmethod
    def calc_focal_length(sensor_w_mm: float, dist_cm: float, fov_w_cm: float) -> float:
        """Calcula a lente necessária para um espaço restrito."""
        if fov_w_cm <= 0:
            return 0.0
        focal_mm = (dist_cm * sensor_w_mm) / fov_w_cm
        return round(focal_mm, 1)
        
    @staticmethod
    def calc_estimated_file_size(width_cm: float, height_cm: float, dpi: int, color_channels: float, compression_ratio: float) -> dict:
        """
        Estima o tamanho de um arquivo de imagem em MB e projeta o peso de um lote de 1000 imagens.
        color_channels: 3 (RGB), 1 (Grayscale), 0.125 (Preto e Branco 1-bit).
        compression_ratio: Multiplicador estimado do formato (ex: 1.0 para TIFF raw, 0.5 para PNG).
        """
        if width_cm <= 0 or height_cm <= 0 or dpi <= 0:
            return {"mb_per_image": 0.0, "gb_per_1000": 0.0}

        # Converte dimensões para polegadas e calcula a matriz total de pixels
        px_w = (width_cm / 2.54) * dpi
        px_h = (height_cm / 2.54) * dpi
        total_pixels = px_w * px_h

        # Tamanho bruto na memória em bytes (Pixels x Canais de Cor)
        raw_bytes = total_pixels * color_channels

        # Aplica o peso do algoritmo de compressão do formato escolhido
        final_bytes = raw_bytes * compression_ratio

        # Converte bytes para Megabytes (MB)
        mb = final_bytes / (1024 * 1024)
        
        # Projeta o peso de um lote padrão de 1000 páginas em Gigabytes (GB)
        gb_1000 = (mb * 1000) / 1024

        return {
            "mb_per_image": round(mb, 2), 
            "gb_per_1000": round(gb_1000, 2)
        }
