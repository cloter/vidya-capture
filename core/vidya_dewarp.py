# Arquivo: core/vidya_dewarp.py (versão estendida)

import cv2
import numpy as np
from core.logger import get_logger

logger = get_logger("Dewarper")

class VidyaPageDewarper:
    """
    Motor de planificação de curvaturas com detecção automática do tipo de warping.
    Suporta:
        - Curvatura vertical (lombada típica)
        - Curvatura horizontal (ondulação vertical do papel)
        - Distorção de perspectiva (keystone, trapézio)
        - Rotação pura (skew)
    """

    def __init__(self, aggressiveness=1.0, min_line_width_ratio=0.20,
                 auto_mode=True, perspective_fallback=True):
        """
        :param aggressiveness: Força da correção da curvatura (0..2, padrão 1.0)
        :param min_line_width_ratio: Menor largura relativa para considerar uma linha de texto
        :param auto_mode: Se True, detecta o tipo de warping e aplica o melhor método
        :param perspective_fallback: Se True, tenta correção de perspectiva quando aplicável
        """
        self.aggressiveness = float(aggressiveness)
        self.min_line_width_ratio = float(min_line_width_ratio)
        self.auto_mode = auto_mode
        self.perspective_fallback = perspective_fallback

    # -------------------- Métodos originais (preservados) --------------------
    def _curvature_strength(self, coeffs, width):
        poly = np.poly1d(coeffs)
        left = poly(0)
        center = poly(width / 2.0)
        right = poly(width)
        return max(abs(left - center), abs(right - center))

    def _extract_lines(self, gray):
        h, w = gray.shape
        bw = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV, 51, 15
        )
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (max(30, w // 35), 1))
        merged = cv2.dilate(bw, kernel, iterations=1)
        contours, _ = cv2.findContours(merged, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        lines = []
        rejected_small = 0
        rejected_tall = 0
        for cnt in contours:
            x, y, cw, ch = cv2.boundingRect(cnt)
            if cw < w * self.min_line_width_ratio:
                rejected_small += 1
                continue
            if ch > h * 0.08:
                rejected_tall += 1
                continue
            lines.append(cnt)
        logger.debug(f"Linhas extraídas: {len(lines)} | Rejeitadas: {rejected_small} curtas, {rejected_tall} altas")
        return lines

    def _measure_curvature(self, contour, width):
        pts = contour.reshape(-1, 2)
        xs = pts[:, 0]
        ys = pts[:, 1]
        step = max(1, width // 25)
        sample_x = []
        sample_y = []
        for x0 in range(0, width, step):
            mask = ((xs >= x0) & (xs < x0 + step))
            if np.count_nonzero(mask) < 5:
                continue
            sample_x.append(x0 + step / 2)
            sample_y.append(np.median(ys[mask]))
        if len(sample_x) < 8:
            return None
        coeffs = np.polyfit(np.array(sample_x), np.array(sample_y), 2)
        strength = self._curvature_strength(coeffs, width)
        if strength < 1.5:
            return None
        return coeffs

    def flatten(self, img, return_success_flag=True):
        """Método original – corrige apenas curvatura vertical (preservado para compatibilidade)"""
        try:
            if len(img.shape) == 3:
                gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            else:
                gray = img.copy()
            h, w = gray.shape
            
            logger.debug(f"Iniciando análise de Dewarp - Agressividade: {self.aggressiveness:.2f}")
            contours = self._extract_lines(gray)
            if len(contours) < 5:
                logger.warning("Dewarp abortado: linhas insuficientes.")
                return img, False if return_success_flag else img

            curves, strengths = [], []
            for cnt in contours:
                coeffs = self._measure_curvature(cnt, w)
                if coeffs is None: continue
                curves.append(coeffs)
                strengths.append(self._curvature_strength(coeffs, w))
            if len(curves) < 3:
                logger.warning("Curvaturas válidas insuficientes.")
                return img, False if return_success_flag else img

            curves = np.array(curves)
            strengths = np.array(strengths)
            median_strength = np.median(strengths)
            mad_strength = np.median(np.abs(strengths - median_strength))
            if mad_strength > 0:
                keep = (np.abs(strengths - median_strength) < (3 * mad_strength))
                curves = curves[keep]

            avg_coeffs = np.median(curves, axis=0)
            final_strength = self._curvature_strength(avg_coeffs, w)
            if final_strength < 2.0:
                logger.info(f"Trava de planicidade: deflexão {final_strength:.1f}px. Nenhuma correção aplicada.")
                return img, True if return_success_flag else img

            poly = np.poly1d(avg_coeffs)
            xs = np.arange(w).astype(np.float32)
            curve = poly(xs)
            tilt_slope = (curve[-1] - curve[0]) / (w - 1)
            tilt_line = tilt_slope * xs + curve[0]
            pure_belly = curve - tilt_line
            center_idx = int(w / 2)
            displacement = (pure_belly - pure_belly[center_idx]) * self.aggressiveness

            map_x = np.tile(np.arange(w), (h, 1)).astype(np.float32)
            map_y = np.tile(np.arange(h).reshape(-1, 1), (1, w)).astype(np.float32)
            map_y += displacement.astype(np.float32)

            dewarped = cv2.remap(img, map_x, map_y, cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
            logger.info(f"Dewarp vertical aplicado (deflexão {final_strength:.1f}px).")
            return dewarped, True if return_success_flag else dewarped

        except Exception as e:
            logger.error(f"Falha no dewarp vertical: {e}")
            return img, False if return_success_flag else img

    # -------------------- Novos hooks de detecção --------------------
    def _detect_skew_angle(self, gray):
        """Retorna o ângulo de rotação (em graus) usando projeção de gradiente ou momentos."""
        edges = cv2.Canny(gray, 50, 150, apertureSize=3)
        lines = cv2.HoughLines(edges, 1, np.pi/180, threshold=100)
        if lines is None:
            return 0.0
        angles = []
        for rho, theta in lines[:, 0]:
            angle = np.degrees(theta) - 90
            if -45 < angle < 45:
                angles.append(angle)
        if not angles:
            return 0.0
        median_angle = np.median(angles)
        return median_angle

    def _classify_warp_type(self, img):
        """
        Retorna um dos tipos: 'vertical_belly', 'horizontal_belly', 'perspective', 'skew_only'
        Baseia-se na análise de contornos da página e curvatura das linhas.
        """
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if len(img.shape) == 3 else img
        h, w = gray.shape

        # 1. Detecção de perspectiva: verifica se o contorno externo é um quadrilátero não retangular
        thresh = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 51, 15)
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if contours:
            largest = max(contours, key=cv2.contourArea)
            peri = cv2.arcLength(largest, True)
            approx = cv2.approxPolyDP(largest, 0.02 * peri, True)
            if len(approx) == 4:
                # Verifica se os ângulos estão muito distantes de 90° (trapézio)
                rect = cv2.minAreaRect(approx)
                box = cv2.boxPoints(rect)
                box = np.int0(box)
                # Razão de aspecto das diagonais ou desvio do retângulo ideal
                width_rect = rect[1][0]
                height_rect = rect[1][1]
                if width_rect > 0 and height_rect > 0:
                    aspect_ratio = max(width_rect, height_rect) / min(width_rect, height_rect)
                    # Se a página está muito deformada (aspecto fora de 0.7~1.4) pode ser perspectiva
                    if aspect_ratio > 1.5 or aspect_ratio < 0.6:
                        return "perspective"

        # 2. Verifica curvatura vertical: extrai linhas e vê se há deflexão dominante no eixo Y
        lines = self._extract_lines(gray)
        if len(lines) < 5:
            return "skew_only" if abs(self._detect_skew_angle(gray)) > 1.0 else "vertical_belly"

        curvatures = []
        for cnt in lines:
            coeffs = self._measure_curvature(cnt, w)
            if coeffs is not None:
                curvatures.append(self._curvature_strength(coeffs, w))
        if not curvatures:
            return "skew_only"

        median_curve = np.median(curvatures)
        # Se a curvatura vertical é pequena, testa curvatura horizontal (transposto)
        if median_curve < 3.0:
            # Testa curvatura horizontal – rotaciona a imagem e repete o processo
            gray_t = cv2.rotate(gray, cv2.ROTATE_90_CLOCKWISE)
            lines_t = self._extract_lines(gray_t)
            hor_curv = []
            for cnt in lines_t:
                coeffs = self._measure_curvature(cnt, gray_t.shape[1])
                if coeffs is not None:
                    hor_curv.append(self._curvature_strength(coeffs, gray_t.shape[1]))
            if hor_curv and np.median(hor_curv) > 3.0:
                return "horizontal_belly"

        return "vertical_belly" if median_curve > 2.0 else "skew_only"

    # -------------------- Correções específicas --------------------
    def _correct_horizontal_belly(self, img):
        """Corrige curvatura horizontal (deslocamento em X) – similar ao método vertical, mas transposto."""
        img_rot = cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)
        dewarped_rot, success = self.flatten(img_rot, return_success_flag=True)
        if success:
            return cv2.rotate(dewarped_rot, cv2.ROTATE_90_COUNTERCLOCKWISE), True
        else:
            logger.warning("Falha na correção de curvatura horizontal. Retornando original.")
            return img, False

    def _correct_perspective(self, img):
        """Detecta os quatro cantos da página e aplica transformação de perspectiva."""
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if len(img.shape) == 3 else img
        # Binarização e detecção de bordas
        _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        edges = cv2.Canny(thresh, 50, 150)
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return img, False
        largest = max(contours, key=cv2.contourArea)
        peri = cv2.arcLength(largest, True)
        approx = cv2.approxPolyDP(largest, 0.02 * peri, True)
        if len(approx) != 4:
            # Fallback: usar o retângulo envolvente
            rect = cv2.minAreaRect(largest)
            approx = cv2.boxPoints(rect)
            approx = np.int0(approx)

        # Ordenar pontos: [top-left, top-right, bottom-right, bottom-left]
        pts = approx.reshape(4, 2)
        rect = np.zeros((4, 2), dtype=np.float32)
        s = pts.sum(axis=1)
        rect[0] = pts[np.argmin(s)]   # top-left
        rect[2] = pts[np.argmax(s)]   # bottom-right
        diff = np.diff(pts, axis=1)
        rect[1] = pts[np.argmin(diff)] # top-right
        rect[3] = pts[np.argmax(diff)] # bottom-left

        (tl, tr, br, bl) = rect
        widthA = np.linalg.norm(br - bl)
        widthB = np.linalg.norm(tr - tl)
        maxWidth = max(int(widthA), int(widthB))
        heightA = np.linalg.norm(tr - br)
        heightB = np.linalg.norm(tl - bl)
        maxHeight = max(int(heightA), int(heightB))

        dst = np.array([
            [0, 0],
            [maxWidth - 1, 0],
            [maxWidth - 1, maxHeight - 1],
            [0, maxHeight - 1]], dtype=np.float32)

        M = cv2.getPerspectiveTransform(rect, dst)
        warped = cv2.warpPerspective(img, M, (maxWidth, maxHeight))
        logger.info("Correção de perspectiva aplicada.")
        return warped, True

    def _auto_skew_correction(self, img):
        """Rotaciona a imagem para corrigir skew (apenas rotação)."""
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if len(img.shape) == 3 else img
        angle = self._detect_skew_angle(gray)
        if abs(angle) < 0.5:
            return img, True
        h, w = gray.shape
        center = (w // 2, h // 2)
        M = cv2.getRotationMatrix2D(center, angle, 1.0)
        rotated = cv2.warpAffine(img, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
        logger.info(f"Correção de skew aplicada: {angle:.2f}°")
        return rotated, True

    # -------------------- Método público automático --------------------
    def flatten_auto(self, img, return_success_flag=True):
        """
        Detecta automaticamente o tipo de distorção e aplica a correção adequada.
        Retorna (imagem_corrigida, sucesso).
        """
        if not self.auto_mode:
            return self.flatten(img, return_success_flag)

        try:
            warp_type = self._classify_warp_type(img)
            logger.info(f"Tipo de warping detectado: {warp_type}")

            if warp_type == "vertical_belly":
                return self.flatten(img, return_success_flag)
            elif warp_type == "horizontal_belly":
                return self._correct_horizontal_belly(img)
            elif warp_type == "perspective" and self.perspective_fallback:
                return self._correct_perspective(img)
            elif warp_type == "skew_only":
                return self._auto_skew_correction(img)
            else:
                logger.warning(f"Tipo de warping não reconhecido ou fallback desativado: {warp_type}")
                return img, False
        except Exception as e:
            logger.error(f"Erro no flatten_auto: {e}")
            return img, False
