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

    def _preprocess_for_contour(self, img):
        """
        Prepara a imagem apagando os detalhes internos (texto/fotos)
        para focar apenas na borda externa do documento.
        """
        if len(img.shape) == 3:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        else:
            gray = img.copy()

        # ATENÇÃO: o blur e o closing aqui são propositalmente leves.
        # Um blur pesado (ex: 15x15) e um closing agressivo (ex: 9x9, 2 iterações)
        # fazem a máscara binária "vazar" para o fundo nos trechos onde o contraste
        # entre o documento e o fundo (ex: vinheta/sombra) é mais fraco. Isso transforma
        # o contorno externo em uma mancha não-retangular, e o cv2.minAreaRect ajustado
        # a essa mancha entrega um ângulo sistematicamente errado (confirmado: chegava a
        # sobrestimar a inclinação real em ~40%, fazendo o deskew sobre-rotacionar a
        # imagem em vez de endireitá-la). Mantemos blur/closing suficientes para tirar
        # ruído de digitalização e fechar pequenos rasgos no papel, mas sem exagerar.
        blurred = cv2.GaussianBlur(gray, (7, 7), 0)

        # Binarização de Otsu geralmente funciona bem se houver contraste
        # entre a folha de arquivo e o fundo da digitalização.
        _, thresh = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

        # Operação morfológica para fechar pequenos buracos (rasgos no papel) sem
        # expandir agressivamente a borda para fora do documento.
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        closed = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel, iterations=1)

        return closed

    def estimate_angle(self, img):
        """
        Encontra o maior contorno e calcula a trigonometria exata da aresta superior.
        """
        try:
            h, w = img.shape[:2]
            total_area = h * w

            # 1. Pré-processamento
            processed = self._preprocess_for_contour(img)

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

    def deskew(self, img):
        """
        Orquestra o processo principal de correção baseado na borda.
        """
        logger.debug("Iniciando análise de Deskew por Contorno Externo")

        angle = self.estimate_angle(img)

        # Como extraímos a trigonometria explicitamente de tl (esquerda) para tr (direita),
        # a polaridade do ângulo já sai perfeitamente mapeada para anular o erro na
        # matriz do getRotationMatrix2D. Não precisamos mais de gambiarras com o sinal!
        corrected, changed = self.rotate(img, angle)

        return corrected, angle, changed
