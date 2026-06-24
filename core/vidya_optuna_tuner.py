# Arquivo: core/vidya_optuna_tuner.py

import cv2
import numpy as np
import optuna
import logging
from PyQt5 import QtCore
from core.logger import get_logger

# Desativa os logs verbosos padrão do Optuna para não poluir o terminal
optuna.logging.set_verbosity(optuna.logging.WARNING)

logger = get_logger("OptunaTuner")

class VidyaOptunaTuner(QtCore.QThread):
    progress_update = QtCore.pyqtSignal(int, str)
    optimization_finished = QtCore.pyqtSignal(dict)
    optimization_error = QtCore.pyqtSignal(str)

    def __init__(self, ground_truth_data: dict, config: dict, current_settings: dict):
        super().__init__()
        self.ground_truth = ground_truth_data
        self.config = config
        self.settings = current_settings
        self.optimal_params = {}

        # Pré-carrega as imagens em RAM uma única vez para não castigar o disco
        self.ram_images = {}
        for path in self.ground_truth.keys():
            img = cv2.imread(path)
            if img is not None:
                self.ram_images[path] = img
            else:
                logger.warning(f"Falha ao carregar {path} para a RAM do Optuna.")

    def run(self):
        try:
            total_trials = self.config.get("trials", 150)
            
            if self.config.get("target_crop"):
                self.progress_update.emit(0, "Iniciando calibração de Auto-Crop...")
                crop_study = optuna.create_study(direction="maximize")
                
                # Otimiza passando a barra de progresso
                for i in range(total_trials):
                    crop_study.optimize(self._objective_crop, n_trials=1)
                    progress = int(((i + 1) / total_trials) * (50 if self.config.get("target_ocr") else 100))
                    self.progress_update.emit(progress, f"Otimizando Recorte... Iteração {i+1}/{total_trials}")
                
                best_crop = crop_study.best_params
                logger.info(f"Melhor IoU (Crop) alcançado: {crop_study.best_value:.4f}")
                self.optimal_params.update(best_crop)

            if self.config.get("target_ocr"):
                self.progress_update.emit(50 if self.config.get("target_crop") else 0, "Iniciando calibração de OCR...")
                ocr_study = optuna.create_study(direction="maximize")
                
                for i in range(total_trials):
                    ocr_study.optimize(self._objective_ocr, n_trials=1)
                    base_prog = 50 if self.config.get("target_crop") else 0
                    progress = base_prog + int(((i + 1) / total_trials) * (50 if self.config.get("target_crop") else 100))
                    self.progress_update.emit(progress, f"Otimizando Binarização... Iteração {i+1}/{total_trials}")
                
                best_ocr = ocr_study.best_params
                logger.info(f"Melhor Confiança (OCR) alcançada: {ocr_study.best_value:.2f}%")
                self.optimal_params.update(best_ocr)

            self.progress_update.emit(100, "Calibração concluída com sucesso!")
            self.optimization_finished.emit(self.optimal_params)

        except Exception as e:
            logger.error(f"Falha crítica no motor Optuna: {str(e)}")
            self.optimization_error.emit(str(e))

    # =========================================================================
    # FUNÇÃO OBJETIVO 1: AUTO-CROP (Métrica: Intersection over Union - IoU)
    # =========================================================================
    def _objective_crop(self, trial):
        """Tenta encontrar os parâmetros que geram o recorte mais próximo do gabarito humano."""
        
        # O Optuna sugere os valores
        blur_val = trial.suggest_int("ac_blur", 3, 31, step=2) # Deve ser sempre ímpar para o OpenCV
        dilate_val = trial.suggest_int("ac_dilate", 0, 10)
        invert_mode = trial.suggest_categorical("ac_invert", ["Forçar Fundo Preto", "Forçar Fundo Branco", "Automático"])
        
        min_area_val = self.settings.get("ac_min_area", 1.5) / 100.0
        
        total_iou = 0.0
        valid_samples = 0
        
        for path, img in self.ram_images.items():
            gt_geom = self.ground_truth.get(path)
            if not gt_geom: continue
            
            # Caixa do Gabarito (Humano)
            box_gt = [gt_geom["x"], gt_geom["y"], gt_geom["width"], gt_geom["height"]]
            
            # Aplica o pipeline do vidya_crops_auto.py em RAM
            h, w = img.shape[:2]
            img_area = h * w
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            blurred = cv2.GaussianBlur(gray, (blur_val, blur_val), 0)
            _, thresh = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            
            if invert_mode == "Forçar Fundo Branco":
                thresh = cv2.bitwise_not(thresh)
            elif invert_mode == "Automático":
                border_pixels = np.concatenate([thresh[0, :], thresh[-1, :], thresh[:, 0], thresh[:, -1]])
                if np.mean(border_pixels) > 127:
                    thresh = cv2.bitwise_not(thresh)
                    
            if dilate_val > 0:
                kernel = np.ones((5, 5), np.uint8)
                thresh = cv2.dilate(thresh, kernel, iterations=dilate_val)
                
            contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            
            best_box_pred = None
            max_area = 0
            
            for c in contours:
                area = cv2.contourArea(c)
                if img_area * min_area_val < area < img_area * 0.95:
                    if area > max_area:
                        max_area = area
                        cx, cy, cw, ch = cv2.boundingRect(c)
                        best_box_pred = [cx, cy, cw, ch]
                        
            # Calcula o IoU se a IA encontrou algum retângulo válido
            if best_box_pred:
                iou = self._calculate_iou(box_gt, best_box_pred)
                total_iou += iou
            valid_samples += 1

        # O Score final é a média do IoU nas amostras. Queremos maximizar isso.
        return total_iou / max(1, valid_samples)

    def _calculate_iou(self, boxA, boxB):
        """Matemática de sobreposição: 1.0 é um match perfeito, 0.0 é falha total."""
        xA = max(boxA[0], boxB[0])
        yA = max(boxA[1], boxB[1])
        xB = min(boxA[0] + boxA[2], boxB[0] + boxB[2])
        yB = min(boxA[1] + boxA[3], boxB[1] + boxB[3])

        interArea = max(0, xB - xA) * max(0, yB - yA)
        boxAArea = boxA[2] * boxA[3]
        boxBArea = boxB[2] * boxB[3]

        iou = interArea / float(boxAArea + boxBArea - interArea)
        return iou

    # =========================================================================
    # FUNÇÃO OBJETIVO 2: OCR (Métrica: Confiança Tesseract)
    # =========================================================================
    def _objective_ocr(self, trial):
        """Tenta encontrar os parâmetros de Binarização que geram o texto mais legível."""
        import pytesseract
        
        denoise_h = trial.suggest_float("ocr_denoise_h", 0.0, 20.0)
        clahe_clip = trial.suggest_float("ocr_clahe_clip", 1.0, 6.0)
        block_size = trial.suggest_int("ocr_block_size", 11, 51, step=2)
        c_val = trial.suggest_int("ocr_c_val", 2, 25)
        
        total_confidence = 0.0
        valid_samples = 0
        
        for path, img in self.ram_images.items():
            try:
                # Replica o pipeline de OCR Prep
                gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if len(img.shape) == 3 else img.copy()
                
                if denoise_h > 0.5:
                    gray = cv2.fastNlMeansDenoising(gray, None, float(denoise_h), 7, 21)
                    
                clahe = cv2.createCLAHE(clipLimit=float(clahe_clip), tileGridSize=(8,8))
                gray = clahe.apply(gray)
                
                bin_img = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, block_size, c_val)
                
                # Extrai os dados do motor Tesseract em memória
                data = pytesseract.image_to_data(bin_img, lang=self.settings.get("ocr_lang", "por"), output_type=pytesseract.Output.DICT)
                
                # Filtra apenas os scores de palavras reais (ignora espaços em branco/blocos com score -1)
                confidences = [int(c) for c in data['conf'] if c != '-1']
                
                if confidences:
                    avg_conf = sum(confidences) / len(confidences)
                    total_confidence += avg_conf
                valid_samples += 1
                
            except Exception as e:
                # Se o Tesseract não estiver instalado, a otimização de OCR falhará graciosamente
                logger.error(f"Erro no ensaio de OCR: {e}")
                return 0.0

        return total_confidence / max(1, valid_samples)
