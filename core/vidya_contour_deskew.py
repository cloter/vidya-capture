# Arquivo: core/vidya_contour_deskew.py

import cv2
import numpy as np
from core.logger import get_logger

# Logger centralizado do sistema Vidya
logger = get_logger("ContourDeskewer")

class VidyaContourDeskewer:

    def __init__(self, min_area_ratio=0.15, max_angle=45.0, min_rectangularity=0.92):
        """
        Inicializa o corretor de inclinação baseado em geometria.

        :param min_area_ratio: Tamanho mínimo do contorno em relação à área total da imagem.
                               Evita que manchas ou ruídos sejam considerados como a folha.
        :param max_angle: Trava de segurança máxima (geralmente 45 graus pela natureza do minAreaRect).
        :param min_rectangularity: Razão mínima entre a área do contorno e a área do
                               minAreaRect que o envolve (area_contorno / area_retangulo).
                               Um retângulo perfeito tem razão ~1.0. Quando a segmentação
                               "vaza" para o fundo (vinheta/sombra com baixo contraste em
                               algum lado), o contorno deixa de ser um retângulo limpo e
                               essa razão cai — isso distorce o ângulo calculado pelo
                               minAreaRect. Abaixo desse limiar, abortamos em vez de aplicar
                               um ângulo que sabemos ser pouco confiável.
        """
        self.min_area_ratio = min_area_ratio
        self.max_angle = max_angle
        self.min_rectangularity = min_rectangularity

    def _preprocess_for_contour(self, img, invert_mode="Automático"):
        """
        Prepara a imagem apagando os detalhes internos (texto/fotos)
        para focar apenas na borda externa do documento.
        Agora injeta a polaridade correta baseada no contraste do fundo.
        """
        if len(img.shape) == 3:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        else:
            gray = img.copy()

        blurred = cv2.GaussianBlur(gray, (7, 7), 0)

        # ---------------------------------------------------------
        # NOVA LÓGICA: Determinação da Polaridade para o Otsu
        # ---------------------------------------------------------
        thresh_type = cv2.THRESH_BINARY
        
        if invert_mode == "Forçar Fundo Branco":
            # Fundo claro e objeto escuro: inverte para o objeto virar 255 (Branco)
            thresh_type = cv2.THRESH_BINARY_INV
            
        elif invert_mode == "Forçar Fundo Preto":
            # Fundo escuro e objeto claro: Otsu normal já resolve
            thresh_type = cv2.THRESH_BINARY
            
        else: # "Automático"
            # Amostra heurística: lemos 5% das bordas externas para deduzir a cor do fundo
            h, w = gray.shape
            margem = max(1, int(min(h, w) * 0.05))
            
            top = gray[0:margem, :]
            bottom = gray[h-margem:h, :]
            left = gray[:, 0:margem]
            right = gray[:, w-margem:w]
            
            # Média global da intensidade das bordas da imagem original
            mean_border = (np.mean(top) + np.mean(bottom) + np.mean(left) + np.mean(right)) / 4.0
            
            if mean_border > 127:
                # O fundo é predominantemente claro. Precisamos inverter.
                thresh_type = cv2.THRESH_BINARY_INV
                logger.debug(f"Deskew: Fundo claro detectado (média={mean_border:.1f}). Usando BINARY_INV.")
            else:
                # O fundo é escuro.
                thresh_type = cv2.THRESH_BINARY
                logger.debug(f"Deskew: Fundo escuro detectado (média={mean_border:.1f}). Usando BINARY normal.")
        # ---------------------------------------------------------

        # Aplica a binarização com a polaridade calculada acima
        _, thresh = cv2.threshold(blurred, 0, 255, thresh_type + cv2.THRESH_OTSU)

        # Operação morfológica (mantida exatamente como a sua original)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        closed = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel, iterations=1)

        return closed

    def estimate_angle(self, img, invert_mode="Automático"):
        """
        Encontra o maior contorno e calcula a trigonometria exata da aresta superior.
        """
        try:
            h, w = img.shape[:2]
            total_area = h * w

            # Repassa a instrução de polaridade para o pré-processamento
            processed = self._preprocess_for_contour(img, invert_mode)

            # 2. Busca de Contornos
            contours, _ = cv2.findContours(processed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            if not contours:
                logger.warning("Deskew abortado: Nenhum contorno encontrado na imagem.")
                return 0.0

            # 3. Seleciona o maior contorno
            largest_contour = max(contours, key=cv2.contourArea)
            contour_area = cv2.contourArea(largest_contour)

            if contour_area < (total_area * self.min_area_ratio):
                logger.warning("Deskew abortado: O maior contorno encontrado é muito pequeno.")
                return 0.0

            # 4. Extrai os 4 Vértices da caixa delimitadora
            rect = cv2.minAreaRect(largest_contour)
            box = cv2.boxPoints(rect)
            # np.int0 foi removido a partir do NumPy 2.0 (deprecado desde a série 1.20).
            # Em qualquer ambiente com NumPy atualizado isso lançava AttributeError,
            # que era engolido pelo "except Exception" abaixo e fazia esta função
            # devolver 0.0 SEMPRE — ou seja, o deskew nunca era aplicado, silenciosamente.
            box = np.intp(box)

            # 4.1 CHECAGEM DE SANIDADE: o contorno encontrado é mesmo um retângulo?
            # Quando a segmentação "vaza" para o fundo (pouco contraste em algum lado),
            # a área do contorno fica bem menor que a área do retângulo mínimo que o
            # envolve, porque a forma deixa de ser convexa/retangular. Nesse caso o
            # ângulo do minAreaRect não é confiável — é melhor abortar do que girar a
            # imagem com um valor errado.
            rect_w, rect_h = rect[1]
            rect_area = rect_w * rect_h
            rectangularity = (contour_area / rect_area) if rect_area > 0 else 0.0

            if rectangularity < self.min_rectangularity:
                logger.warning(
                    f"Deskew abortado: contorno não é suficientemente retangular "
                    f"(área_contorno/área_retângulo = {rectangularity:.3f}, "
                    f"mínimo exigido = {self.min_rectangularity:.2f}). "
                    f"Provável vazamento da segmentação para o fundo da imagem."
                )
                return 0.0

            # 5. MATEMÁTICA ROBUSTA DE VÉRTICES (Imune a versões do OpenCV)
            # Ordenamos os pontos baseados na soma e diferença dos eixos (x, y)
            # para ancorar perfeitamente os cantos superiores da folha.
            s = box.sum(axis=1)
            diff = np.diff(box, axis=1)

            tl = box[np.argmin(s)]       # Top-Left (Canto superior esquerdo)
            tr = box[np.argmin(diff)]    # Top-Right (Canto superior direito)

            # Calcula o cateto oposto (dy) e o adjacente (dx) da linha superior
            dy = tr[1] - tl[1]
            dx = tr[0] - tl[0]

            # O np.arctan2 devolve o ângulo real da inclinação em relação ao horizonte.
            angle = np.degrees(np.arctan2(dy, dx))

            # Essa abordagem geométrica garante que o ângulo nunca "vire" 90 graus sozinho,
            # ele sempre ficará preso no espectro correto de compensação (-45 a +45).
            if abs(angle) > self.max_angle:
                logger.warning(f"Deskew abortado: O ângulo geométrico ({angle:.2f}°) excedeu o limite do horizonte.")
                return 0.0

            logger.debug(
                f"Ângulo de contorno estimado (Trigonometria exata): {angle:.3f}° "
                f"(retangularidade={rectangularity:.3f})"
            )
            return float(angle)

        except Exception as e:
            logger.error(f"Falha interna ao estimar o contorno no Deskew: {str(e)}")
            return 0.0

    def rotate(self, img, angle):
        """
        Gira a imagem com base no ângulo estimado.
        (Mantém a mesma lógica robusta do seu corretor de texto).
        """
        # Ignora micro-rotações que só gastariam processamento
        if abs(angle) < 0.15:
            logger.info(f"Deskew ignorado: O contorno já está essencialmente reto ({angle:.2f}°).")
            return img, False

        h, w = img.shape[:2]
        center = (w // 2, h // 2)

        M = cv2.getRotationMatrix2D(center, angle, 1.0)
        rotated = cv2.warpAffine(
            img, M, (w, h),
            flags=cv2.INTER_CUBIC,
            borderMode=cv2.BORDER_REPLICATE
        )

        logger.info(f"Deskew de contorno aplicado (Imagem girada em {angle:.3f}°).")
        return rotated, True

    def deskew(self, img, invert_mode="Automático"):
        """
        Orquestra o processo principal de correção baseado na borda.
        """
        logger.debug("Iniciando análise de Deskew por Contorno Externo")

        # Repassa o parâmetro para a estimativa geométrica
        angle = self.estimate_angle(img, invert_mode)

        corrected, changed = self.rotate(img, angle)

        return corrected, angle, changed
