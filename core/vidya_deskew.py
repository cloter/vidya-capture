# Arquivo: core/vidya_deskew.py

import cv2
import numpy as np
from core.logger import get_logger

# Chama o nosso logger centralizado do sistema
logger = get_logger("Deskewer")

class VidyaDeskewer:

    def __init__(self, min_line_width_ratio=0.15, max_angle=15.0):
        self.min_line_width_ratio = min_line_width_ratio
        self.max_angle = max_angle

    def estimate_angle(self, img):
        try:
            if len(img.shape) == 3:
                gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            else:
                gray = img.copy()

            # Binarização
            bw = cv2.adaptiveThreshold(
                gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                cv2.THRESH_BINARY_INV, 51, 15
            )

            h, w = bw.shape

            # Une palavras na mesma linha
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (max(30, w // 40), 1))
            merged = cv2.dilate(bw, kernel, iterations=1)
            
            contours, _ = cv2.findContours(merged, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            angles = []
            weights = []
            rejected_small = 0
            rejected_tall = 0

            for cnt in contours:
                x, y, cw, ch = cv2.boundingRect(cnt)

                # Ignora ruídos e colunas muito curtas ou altas
                if cw < w * self.min_line_width_ratio:
                    rejected_small += 1
                    continue
                if ch > h * 0.10:
                    rejected_tall += 1
                    continue

                # Extração matemática robusta do vetor da linha
                [vx, vy, x0, y0] = cv2.fitLine(cnt, cv2.DIST_L2, 0, 0.01, 0.01)
                angle = np.degrees(np.arctan2(vy, vx))
                angle = angle[0] # Extrai o float do array numpy

                # Normaliza para o limite do horizonte [-90, 90]
                if angle > 90:
                    angle -= 180
                elif angle < -90:
                    angle += 180

                angles.append(angle)
                weights.append(cw) # O peso da decisão é o comprimento da linha

            logger.debug(f"Linhas extraídas: {len(angles)} válidas | Rejeitadas: {rejected_small} curtas, {rejected_tall} altas")

            if len(angles) < 3:
                logger.warning("Deskew abortado: Linhas de texto insuficientes para estimar a inclinação.")
                return 0.0

            angles = np.array(angles)
            weights = np.array(weights)

            # Filtragem Estatística MAD (Exclui falsos ângulos causados por carimbos tortos)
            median = np.median(angles)
            deviation = np.abs(angles - median)
            mad = np.median(deviation)

            if mad > 0:
                keep = deviation < (3 * mad)
                angles = angles[keep]
                weights = weights[keep]

            if len(angles) == 0:
                logger.warning("Deskew abortado: Nenhuma linha sobreviveu ao filtro estatístico de ruído.")
                return 0.0

            final_angle = np.average(angles, weights=weights)

            if abs(final_angle) > self.max_angle:
                logger.warning(f"Deskew abortado: O ângulo estimado ({final_angle:.2f}°) excede a trava de segurança ({self.max_angle}°).")
                return 0.0

            logger.debug(f"Ângulo base estimado para correção: {final_angle:.3f}°")
            return float(final_angle)

        except Exception as e:
            logger.error(f"Falha interna ao estimar ângulo no Deskew: {str(e)}")
            return 0.0

    def rotate(self, img, angle):
        # Ignora micro-rotações abaixo do limiar percetível
        if abs(angle) < 0.15:
            logger.info(f"Deskew ignorado: A página já está reta (A correção de {angle:.2f}° é irrelevante).")
            return img, False

        h, w = img.shape[:2]
        center = (w // 2, h // 2)

        M = cv2.getRotationMatrix2D(center, angle, 1.0)
        rotated = cv2.warpAffine(
            img, M, (w, h),
            flags=cv2.INTER_CUBIC,
            borderMode=cv2.BORDER_REPLICATE
        )

        logger.info(f"Deskew aplicado com sucesso (Matriz girada em {angle:.3f}°).")
        return rotated, True

    def deskew(self, img, aggressiveness=1.0):
        logger.debug(f"Iniciando análise de Deskew - Agressividade: {aggressiveness:.2f}")
        
        angle = self.estimate_angle(img)
        
        # A MÁGICA DA CORREÇÃO (Sem o sinal de menos!)
        # O ângulo positivo do fitLine anula-se naturalmente com 
        # a rotação anti-horária da matriz do OpenCV.
        correction_angle = angle * aggressiveness
        
        corrected, changed = self.rotate(img, correction_angle)

        return corrected, correction_angle, changed
