import cv2
import numpy as np
from core.logger import get_logger

logger = get_logger("BackgroundRemover")

class VidyaBackgroundRemover:
    """
    Remove o fundo (borda externa) de uma imagem usando flood fill a partir dos cantos.
    Parâmetros:
        - bg_detect_enabled: ativa/desativa o processamento
        - bg_detect_sensitivity: tolerância de cor (0-100) – quanto maior, mais pixels são considerados fundo
        - bg_replace_color: cor de substituição ('Preto', 'Branco', 'Cinza', 'Transparente' ou um hex #RRGGBB ou #AARRGGBB)
    """

    # Mapeamento de nomes para valores BGR (padrão)
    COLOR_MAP = {
        "Preto": (0, 0, 0),
        "Branco": (255, 255, 255),
        "Cinza": (128, 128, 128),
    }

    def _parse_color(self, color_str: str, need_alpha: bool = False):
        """
        Converte a string de cor para um tuplo BGR ou BGRA.
        - Se for um dos nomes mapeados, retorna o valor correspondente.
        - Se começar com '#', interpreta como hexadecimal (suporta #RRGGBB ou #AARRGGBB).
        - Caso contrário, assume que é 'Transparente' e retorna (0,0,0,0) com alpha=0.
        """
        if color_str in self.COLOR_MAP:
            bgr = self.COLOR_MAP[color_str]
            if need_alpha:
                return (bgr[0], bgr[1], bgr[2], 255)  # opaco
            return bgr

        if color_str.startswith("#"):
            hex_str = color_str.lstrip("#")
            if len(hex_str) == 6:          # #RRGGBB
                r, g, b = int(hex_str[0:2], 16), int(hex_str[2:4], 16), int(hex_str[4:6], 16)
                bgr = (b, g, r)
                if need_alpha:
                    return (b, g, r, 255)
                return bgr
            elif len(hex_str) == 8:        # #AARRGGBB
                a, r, g, b = int(hex_str[0:2], 16), int(hex_str[2:4], 16), int(hex_str[4:6], 16), int(hex_str[6:8], 16)
                if need_alpha:
                    return (b, g, r, a)
                # Se não precisar de alpha, retorna apenas BGR (ignora transparência)
                return (b, g, r)

        # Fallback para 'Transparente'
        if need_alpha:
            return (0, 0, 0, 0)
        return (0, 0, 0)

    def _get_seed_points(self, h, w, margin=5):
        """
        Gera pontos semente para o flood fill: quatro cantos e pontos ao longo das bordas,
        com um pequeno offset da borda para evitar pixels ruidosos.
        """
        seeds = []
        # Cantos
        seeds.extend([(margin, margin), (w - 1 - margin, margin),
                      (margin, h - 1 - margin), (w - 1 - margin, h - 1 - margin)])
        # Borda superior e inferior (amostras)
        for x in range(margin, w - margin, max(1, w // 20)):
            seeds.append((x, margin))
            seeds.append((x, h - 1 - margin))
        # Borda esquerda e direita
        for y in range(margin, h - margin, max(1, h // 20)):
            seeds.append((margin, y))
            seeds.append((w - 1 - margin, y))
        return seeds

    def remove_background(self, img, settings: dict, crop_border: bool = False):
        """
        Aplica a remoção de fundo se `bg_detect_enabled` for True.
        Retorna a imagem modificada (pode ter canal alpha se a cor de substituição for transparente).
        Se `crop_border` for True e o fundo for Transparente, a imagem será cortada no limite do conteúdo.
        """
        if not settings.get("bg_detect_enabled", False):
            return img

        sens = int(settings.get("bg_detect_sensitivity", 0))
        replace_color_str = settings.get("bg_replace_color", "Branco")

        # Determina se precisamos de canal alpha
        need_alpha = (replace_color_str == "Transparente" or
                      (replace_color_str.startswith("#") and len(replace_color_str) == 9))  # #AARRGGBB

        # Converte a imagem para BGRA se for necessário, ou mantém BGR
        if need_alpha:
            if img.shape[2] == 3:
                img = cv2.cvtColor(img, cv2.COLOR_BGR2BGRA)
            elif img.shape[2] == 4:
                pass  # já está BGRA
            else:
                # Caso inesperado: força conversão para BGRA
                img = cv2.cvtColor(img, cv2.COLOR_BGR2BGRA)
        else:
            if img.shape[2] == 4:
                # Se temos alpha mas não precisamos, descartamos
                img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)

        h, w = img.shape[:2]
        # Cria uma máscara de fundo inicial (zeros)
        mask = np.zeros((h + 2, w + 2), dtype=np.uint8)

        # Calcula a tolerância a partir do slider da interface (-50 a 50)
        # O limite máximo seguro recomendado para não apagar o interior do documento é ~120
        if sens >= 0:
            # Slider de 0 a 50: Mapeia de 25 (Padrão Seguro) até 120 (Agressivo)
            tolerance = int(25 + (sens / 50.0) * 95)
        else:
            # Slider de -50 a 0: Mapeia de 1 (Super Rígido) até 25 (Padrão Seguro)
            tolerance = int(25 - (abs(sens) / 50.0) * 24)
            
        tolerance = max(1, min(255, tolerance))

        # Define flags do floodFill: preenche apenas pixels similares, usa conectividade 4
        flags = 4 | cv2.FLOODFILL_FIXED_RANGE | (tolerance << 8)

        # Obtém sementes
        seeds = self._get_seed_points(h, w)

        # PREPARO DA IMAGEM DE TRABALHO:
        # O cv2.floodFill recusa matrizes de 4 canais. Se a imagem estiver em BGRA, 
        # criamos um clone temporário em BGR apenas para o algoritmo enxergar as cores.
        if img.shape[2] == 4:
            img_for_flood = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
        else:
            img_for_flood = img.copy()

        # Aplica flood fill a partir de cada semente (se ainda não preenchida)
        for (sx, sy) in seeds:
            if sx < 0 or sx >= w or sy < 0 or sy >= h:
                continue
            # Verifica se o pixel já foi marcado como fundo (na máscara)
            if mask[sy + 1, sx + 1] == 0:
                
                # Usa a imagem segura de 3 canais
                img_work = img_for_flood.copy()
                
                # Aplica floodFill
                retval, img_work, mask, rect = cv2.floodFill(
                    img_work, mask, (sx, sy), (0, 0, 0),
                    loDiff=(tolerance, tolerance, tolerance),
                    upDiff=(tolerance, tolerance, tolerance),
                    flags=flags
                )

        # A máscara tem 1 onde o flood preencheu (fundo)
        # Converter máscara para booleano
        bg_mask = (mask[1:h+1, 1:w+1] > 0)  # remove borda extra

        # Cor de substituição
        if need_alpha:
            # Para BGRA, a cor de substituição pode ter alpha
            replace_color = self._parse_color(replace_color_str, need_alpha=True)
            # replace_color é (B, G, R, A)
            if replace_color_str == "Transparente":
                # Alpha 0
                replace_color = (0, 0, 0, 0)
                
            # Aplicar a cor: preencher os pixels de fundo
            dst = np.full_like(img, replace_color, dtype=img.dtype)
            # Para os pixels que não são fundo, copiar da imagem original
            dst[~bg_mask] = img[~bg_mask]
            
            # ---> LÓGICA DE AUTO-CROP <---
            # Se o crop foi solicitado E a cor possui transparência total (Canal Alpha == 0)
            if crop_border and replace_color[3] == 0:
                # Encontra as coordenadas Y e X de todos os pixels que pertencem ao foreground (conteúdo)
                y_coords, x_coords = np.where(~bg_mask)
                
                # Previne falhas caso a imagem inteira tenha sido apagada
                if len(y_coords) > 0 and len(x_coords) > 0:
                    y_min, y_max = np.min(y_coords), np.max(y_coords)
                    x_min, x_max = np.min(x_coords), np.max(x_coords)
                    
                    # Corta a matriz fisicamente
                    dst = dst[y_min:y_max+1, x_min:x_max+1]
            
            return dst
        else:
            replace_color = self._parse_color(replace_color_str, need_alpha=False)
            # Para BGR, preencher os pixels de fundo com a cor
            dst = img.copy()
            dst[bg_mask] = replace_color
            return dst
