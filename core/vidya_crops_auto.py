# Arquivo: core/vidya_crops_auto.py

import os
import json
import glob
import cv2
import numpy as np
from core.logger import get_logger
from core.config import load_settings

logger = get_logger("AutoCrop")

class VidyaCropsAuto:
    @staticmethod
    def process_images(image_paths: list) -> int:
        settings = load_settings()
        
        # Carrega as configurações de Crop
        blur_val = settings.get("ac_blur", 11)
        dilate_val = settings.get("ac_dilate", 2)
        pad_val = settings.get("ac_pad", 3) / 100.0
        min_area_val = settings.get("ac_min_area", 1.5) / 100.0
        invert_mode = settings.get("ac_invert", "Automático")
        max_crops = int(settings.get("ac_max_crops", 0))
        
        processed_count = 0
        for img_path in image_paths:
            if not img_path or not os.path.exists(img_path): continue
            
            try:
                base_dir = os.path.dirname(img_path)
                base_name = os.path.basename(img_path)
                name_no_ext = base_name.rsplit('.', 1)[0]
                main_json = os.path.join(base_dir, f"{name_no_ext}.json")
                
                # 1. Limpa clipes antigos (órfãos) para dar lugar aos novos
                for cf in glob.glob(os.path.join(base_dir, f"{name_no_ext}_clip_*.json")):
                    try: os.remove(cf)
                    except: pass

                # 2. Processa com OpenCV
                img = cv2.imread(img_path)
                if img is None: continue
                
                h, w = img.shape[:2]
                img_area = h * w
                
                gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
                
                # Desfoque paramétrico
                b_size = blur_val if blur_val % 2 != 0 else blur_val + 1
                blurred = cv2.GaussianBlur(gray, (b_size, b_size), 0)
                
                # Binarização de Otsu
                _, thresh = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
                
                # Lógica Direcionada de Contraste
                if invert_mode == "Forçar Fundo Branco":
                    thresh = cv2.bitwise_not(thresh)
                elif invert_mode == "Automático":
                    border_pixels = np.concatenate([thresh[0, :], thresh[-1, :], thresh[:, 0], thresh[:, -1]])
                    if np.mean(border_pixels) > 127:
                        thresh = cv2.bitwise_not(thresh)
                
                # Dilatação Morfológica Paramétrica
                if dilate_val > 0:
                    kernel = np.ones((5, 5), np.uint8)
                    thresh = cv2.dilate(thresh, kernel, iterations=dilate_val)
                
                contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                
                valid_rects = []
                for c in contours:
                    area = cv2.contourArea(c)
                    if img_area * min_area_val < area < img_area * 0.95:
                        cx, cy, cw, ch = cv2.boundingRect(c)
                        # Padding automático
                        pad_x, pad_y = int(cw * pad_val), int(ch * pad_val)
                        nx = max(0, cx - pad_x)
                        ny = max(0, cy - pad_y)
                        nw = min(w - nx, cw + 2 * pad_x)
                        nh = min(h - ny, ch + 2 * pad_y)
                        
                        # --- INÍCIO: Inteligência Poligonal Vetorial ---
                        poly_pts = []
                        
                        # Salvamos o polígono como o quinto elemento da tupla
                        valid_rects.append((nx, ny, nw, nh, poly_pts))
                
                if not valid_rects:
                    logger.warning(f"Auto Crop: Nenhum documento válido detectado em {base_name}")
                    continue
                    
                # Ordena os recortes do maior para o menor (compara a área baseada em W * H)
                valid_rects.sort(key=lambda r: r[2]*r[3], reverse=True)
                
                if max_crops > 0:
                    valid_rects = valid_rects[:max_crops]
                
                # 3. Grava o MAIOR documento no JSON principal
                main_rect = valid_rects[0]
                main_data = {}
                if os.path.exists(main_json):
                    with open(main_json, 'r', encoding='utf-8') as f:
                        main_data = json.load(f)
                
                main_data["crop_geometry"] = {
                    "x": main_rect[0], "y": main_rect[1],
                    "width": main_rect[2], "height": main_rect[3], 
                    "polygon": main_rect[4] # <- O array preenchido ou vazio
                }
                
                with open(main_json, 'w', encoding='utf-8') as f:
                    json.dump(main_data, f, indent=4)
                    
                # 4. Grava os documentos secundários como sub-clipes
                for idx, rect in enumerate(valid_rects[1:]):
                    clip_json = os.path.join(base_dir, f"{name_no_ext}_clip_{idx+1}.json")
                    clip_data = {
                        "source_image": base_name,
                        "crop_geometry": {
                            "x": rect[0], "y": rect[1],
                            "width": rect[2], "height": rect[3], 
                            "polygon": rect[4]
                        }
                    }
                    with open(clip_json, 'w', encoding='utf-8') as f:
                        json.dump(clip_data, f, indent=4)
                        
                processed_count += 1
            except Exception as e:
                logger.error(f"Falha crítica no AutoCrop da imagem {img_path}: {e}")
                
        return processed_count
