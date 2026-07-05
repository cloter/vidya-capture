# Arquivo: core/vidya_optuna_tuner.py

import os
import json
import cv2
import numpy as np
import re
import optuna
import pytesseract
from PyQt5 import QtCore
from core.logger import get_logger

logger = get_logger("OptunaTuner")

class VidyaOptunaTuner(QtCore.QThread):
    progress_update = QtCore.pyqtSignal(int, str)
    optimization_finished = QtCore.pyqtSignal(dict)
    optimization_error = QtCore.pyqtSignal(str)

    def __init__(self, ground_truth_data: dict, config: dict, settings: dict):
        super().__init__()
        self.ground_truth_data = ground_truth_data
        self.config = config
        self.settings = settings
        
        self.cached_rois = [] # Armazenará as amostras já endireitadas e cortadas
        self._is_cancelled = False

    def terminate(self):
        """Sinal seguro para abortar a thread a pedido do utilizador."""
        self._is_cancelled = True
        super().terminate()

    # =========================================================================
    # REPLICAÇÃO DA MICRO-PIPELINE GEOMÉTRICA (PARA GARANTIR A PRECISÃO DO CROP)
    # =========================================================================
    def _post_deskew_crop_in_ram(self, img):
        try:
            h, w = img.shape[:2]
            img_area = h * w
            blur_val = self.settings.get("ac_blur", 11)
            dilate_val = self.settings.get("ac_dilate", 2)
            pad_val = self.settings.get("ac_pad", 3) / 100.0
            min_area_val = self.settings.get("ac_min_area", 1.5) / 100.0
            invert_mode = self.settings.get("ac_invert", "Automático")
            
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            b_size = blur_val if blur_val % 2 != 0 else blur_val + 1
            blurred = cv2.GaussianBlur(gray, (b_size, b_size), 0)
            _, thresh = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            
            if invert_mode == "Forçar Fundo Branco": thresh = cv2.bitwise_not(thresh)
            elif invert_mode == "Automático":
                border_pixels = np.concatenate([thresh[0, :], thresh[-1, :], thresh[:, 0], thresh[:, -1]])
                if np.mean(border_pixels) > 127: thresh = cv2.bitwise_not(thresh)
                    
            if dilate_val > 0:
                kernel = np.ones((5, 5), np.uint8)
                thresh = cv2.dilate(thresh, kernel, iterations=dilate_val)
                
            contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            valid_rects = []
            for c in contours:
                area = cv2.contourArea(c)
                if img_area * min_area_val < area < img_area * 0.95:
                    cx, cy, cw, ch = cv2.boundingRect(c)
                    pad_x, pad_y = int(cw * pad_val), int(ch * pad_val)
                    nx = max(0, cx - pad_x); ny = max(0, cy - pad_y)
                    nw = min(w - nx, cw + 2 * pad_x); nh = min(h - ny, ch + 2 * pad_y)
                    valid_rects.append((nx, ny, nw, nh))
                    
            if not valid_rects: return img
            valid_rects.sort(key=lambda r: r[2]*r[3], reverse=True)
            nx, ny, nw, nh = valid_rects[0]
            return img[ny:ny+nh, nx:nx+nw]
        except: return img

    def _prepare_image_in_ram(self, img_path):
        img = cv2.imread(img_path)
        if img is None: return None
        json_path = img_path.rsplit('.', 1)[0] + ".json"
        
        homographics_run = False
        if os.path.exists(json_path):
            try:
                with open(json_path, 'r', encoding='utf-8') as f: meta = json.load(f)
                manual_pts = meta.get("manual_deskew", [])
                if manual_pts and len(manual_pts) == 4:
                    pts = np.array([[p["x"], p["y"]] for p in manual_pts], dtype="float32")
                    s = pts.sum(axis=1); diff = np.diff(pts, axis=1)
                    rect = np.zeros((4, 2), dtype="float32")
                    rect[0] = pts[np.argmin(s)]; rect[2] = pts[np.argmax(s)]
                    rect[1] = pts[np.argmin(diff)]; rect[3] = pts[np.argmax(diff)]
                    orig_h, orig_w = img.shape[:2]
                    dst = np.array([[0, 0], [orig_w - 1, 0], [orig_w - 1, orig_h - 1], [0, orig_h - 1]], dtype="float32")
                    M = cv2.getPerspectiveTransform(rect, dst)
                    img = cv2.warpPerspective(img, M, (orig_w, orig_h))
                    homographics_run = True
                if not homographics_run:
                    geom = meta.get("crop_geometry", {})
                    if geom:
                        x, y = int(geom.get("x", 0)), int(geom.get("y", 0))
                        w, h = int(geom.get("width", img.shape[1])), int(geom.get("height", img.shape[0]))
                        x, y = max(0, x), max(0, y)
                        w, h = min(w, img.shape[1] - x), min(h, img.shape[0] - y)
                        img = img[y:y+h, x:x+w]
            except: pass

        if self.settings.get("proc_contour_deskew", False):
            try:
                from core.vidya_contour_deskew import VidyaContourDeskewer
                img, _, changed = VidyaContourDeskewer().deskew(img, invert_mode=self.settings.get("ac_invert", "Automático"))
                if changed: img = self._post_deskew_crop_in_ram(img)
            except: pass

        if self.settings.get("proc_deskew", True):
            try:
                from core.vidya_deskew import VidyaDeskewer
                img, _, _ = VidyaDeskewer(max_angle=15.0).deskew(img, aggressiveness=float(self.settings.get("deskew_aggressiveness", 1.0)))
            except: pass
                
        if self.settings.get("proc_dewarp", False):
            try:
                from core.vidya_dewarp import VidyaPageDewarper
                flattened_img, success = VidyaPageDewarper(aggressiveness=float(self.settings.get("dewarp_aggressiveness", 1.0))).flatten(img)
                if success: img = flattened_img
            except: pass

        return img

    # =========================================================================
    # FLUXO PRINCIPAL DA THREAD
    # =========================================================================
    def run(self):
        try:
            # ---> INÍCIO DA CORREÇÃO: Força o Tesseract a respeitar o limite de CPU do utilizador
            ocr_jobs = self.settings.get("ocr_jobs", 2)
            os.environ["OMP_THREAD_LIMIT"] = str(ocr_jobs)
            # ---> FIM DA CORREÇÃO
            
            self.progress_update.emit(2, "Inicializando motor de Inteligência Artificial...")
            
            # 1. Preparação em Memória (Isto demorava em 0%, agora informa o utilizador!)
            total_images = len(self.ground_truth_data)
            for idx, (img_path, geom) in enumerate(self.ground_truth_data.items()):
                if self._is_cancelled: return
                
                # Progresso de 5% a 30% reservado para a extração
                prog = 5 + int((idx / total_images) * 25)
                self.progress_update.emit(prog, f"Alinhando amostra {idx+1}/{total_images} em memória RAM...")
                
                flat_img = self._prepare_image_in_ram(img_path)
                if flat_img is not None:
                    x, y = int(geom["x"]), int(geom["y"])
                    w, h = int(geom["width"]), int(geom["height"])
                    
                    # Trava de segurança para não extrapolar limites e crashar o OpenCV
                    x, y = max(0, x), max(0, y)
                    w = min(w, flat_img.shape[1] - x)
                    h = min(h, flat_img.shape[0] - y)
                    
                    if w > 0 and h > 0:
                        roi = flat_img[y:y+h, x:x+w]
                        # Já guardamos em Escala de Cinza para o Optuna não precisar converter 150 vezes
                        gray_roi = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
                        self.cached_rois.append(gray_roi)

            if not self.cached_rois:
                self.optimization_error.emit("Nenhuma amostra válida pôde ser extraída.")
                return

            # 2. Configuração do Optuna
            self.progress_update.emit(32, "Configurando espaço de busca matemático...")
            
            # Ocultar o log "sujo" que o Optuna imprime no terminal nativamente
            optuna.logging.set_verbosity(optuna.logging.WARNING) 
            study = optuna.create_study(direction="maximize")
            
            # 3. Execução das Iterações com "Callback" (Para o progress bar andar do 35% ao 95%)
            trials = self.config.get("trials", 150)
            
            def optuna_callback(study, trial):
                if self._is_cancelled:
                    study.stop()
                    
                current_prog = 35 + int((trial.number / trials) * 60)
                best_val = study.best_value if study.best_trial else 0.0
                msg = f"Avaliando Iteração {trial.number}/{trials} (Melhor Score: {best_val:.2f})"
                self.progress_update.emit(current_prog, msg)
                
            study.optimize(self._objective, n_trials=trials, callbacks=[optuna_callback])
            
            if self._is_cancelled: return
            
            # 4. Finalização e Fecho
            self.progress_update.emit(98, "Compilando melhores hiperparâmetros...")
            best_params = study.best_params
            
            # Previne erro de serialização no JSON convertendo numpy ints para python ints
            for k, v in best_params.items():
                if isinstance(v, np.integer): best_params[k] = int(v)
                elif isinstance(v, np.floating): best_params[k] = float(v)
            
            self.progress_update.emit(100, "Calibração concluída!")
            self.optimization_finished.emit(best_params)
            
        except Exception as e:
            logger.error(f"Erro fatal no Optuna: {e}")
            self.optimization_error.emit(str(e))

    def _objective(self, trial):
        """Espaço de Busca (Search Space) restrito estritamente à Binarização do OCR"""
        denoise_h = trial.suggest_float("ocr_denoise_h", 5.0, 25.0)
        clahe_clip = trial.suggest_float("ocr_clahe_clip", 1.0, 5.0)
        block_size = trial.suggest_int("ocr_block_size", 11, 71, step=2) # Obrigatório ser ímpar no OpenCV
        c_val = trial.suggest_int("ocr_c_val", 2, 20)
        
        scores = []
        clahe = cv2.createCLAHE(clipLimit=clahe_clip, tileGridSize=(8,8))
        
        for gray_roi in self.cached_rois:
            # 1. Filtro de Ruído Não-Local (Remove textura de papel velho)
            denoised = cv2.fastNlMeansDenoising(gray_roi, None, h=denoise_h)
            
            # 2. Equalização de Histograma (Traz o texto apagado à tona)
            enhanced = clahe.apply(denoised)
            
            # 3. Binarização Adaptativa (A principal mágica para separar texto de fundo)
            thresh = cv2.adaptiveThreshold(
                enhanced, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
                cv2.THRESH_BINARY, block_size, c_val
            )
            
            # 4. Leitura e Validação via Tesseract (psm 6 assume um bloco de texto unificado)
            text = pytesseract.image_to_string(thresh, config='--psm 6')
            
            # 5. Métrica de Recompensa (Fitness Function)
            # Premiamos o OCR se ele encontrar letras e números reais.
            valid_chars = len(re.findall(r'[a-zA-Z0-9À-ÿ]', text))
            
            # Penalizamos FORTEMENTE se o OCR criar lixo visual (indicativo de ruído no fundo)
            garbage_chars = len(re.findall(r'[^a-zA-Z0-9À-ÿ\s\.,;:!?\-\(\)\[\]]', text))
            
            score = valid_chars - (garbage_chars * 2.0)
            scores.append(score)
            
        return np.mean(scores)
