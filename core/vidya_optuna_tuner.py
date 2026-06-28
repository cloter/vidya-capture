# Arquivo: core/vidya_optuna_tuner.py

import os
import cv2
import numpy as np
import optuna
import logging
import tesserocr
import tesserocr
from PIL import Image
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
            
            # ---> INÍCIO DA INSERÇÃO: Controle Avançado de Multithreading <---
            
            # 1. Resgata o limite de núcleos configurado pelo utilizador na aba OCR
            jobs = int(self.settings.get("ocr_jobs", 2))
            
            # 2. Thread Pinning: Trava o multithreading interno do OpenCV e Tesseract.
            # Como o Optuna fará a paralelização orquestrada das imagens (n_jobs), 
            # forçamos os motores gráficos a usarem apenas 1 thread por job para evitar o travamento da CPU.
            os.environ['OMP_THREAD_LIMIT'] = '1'
            cv2.setNumThreads(1)
            # ---> FIM DA INSERÇÃO <---
            
            if self.config.get("target_crop"):
                self.progress_update.emit(0, "Iniciando calibração de Auto-Crop...")
                crop_study = optuna.create_study(direction="maximize")
                
                # ---> INÍCIO DA ALTERAÇÃO: Execução Paralela com Callback <---
                self.completed_crop_trials = 0
                
                def crop_callback(study, trial):
                    self.completed_crop_trials += 1
                    progress = int((self.completed_crop_trials / total_trials) * (50 if self.config.get("target_ocr") else 100))
                    self.progress_update.emit(progress, f"Otimizando Recorte... Iteração {self.completed_crop_trials}/{total_trials}")

                # O Optuna agora distribui os testes pelos núcleos físicos permitidos!
                crop_study.optimize(self._objective_crop, n_trials=total_trials, n_jobs=jobs, callbacks=[crop_callback])
                # ---> FIM DA ALTERAÇÃO <---
                
                best_crop = crop_study.best_params
                logger.info(f"Melhor IoU (Crop) alcançado: {crop_study.best_value:.4f}")
                self.optimal_params.update(best_crop)

            if self.config.get("target_ocr"):
                self.progress_update.emit(50 if self.config.get("target_crop") else 0, "Iniciando calibração de OCR...")
                ocr_study = optuna.create_study(direction="maximize")
                
                # ---> INÍCIO DA ALTERAÇÃO: Execução Paralela com Callback <---
                self.completed_ocr_trials = 0
                
                def ocr_callback(study, trial):
                    self.completed_ocr_trials += 1
                    base_prog = 50 if self.config.get("target_crop") else 0
                    progress = base_prog + int((self.completed_ocr_trials / total_trials) * (50 if self.config.get("target_crop") else 100))
                    self.progress_update.emit(progress, f"Otimizando Binarização... Iteração {self.completed_ocr_trials}/{total_trials}")

                # O Optuna agora distribui os testes pelos núcleos físicos permitidos!
                ocr_study.optimize(self._objective_ocr, n_trials=total_trials, n_jobs=jobs, callbacks=[ocr_callback])
                # ---> FIM DA ALTERAÇÃO <---
                
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
        """Tenta encontrar os parâmetros de Binarização que geram o texto mais legível usando a API C++ (tesserocr)."""
        
        denoise_h = trial.suggest_float("ocr_denoise_h", 0.0, 20.0)
        clahe_clip = trial.suggest_float("ocr_clahe_clip", 1.0, 6.0)
        block_size = trial.suggest_int("ocr_block_size", 11, 51, step=2)
        c_val = trial.suggest_int("ocr_c_val", 2, 25)
        
        # Recupera a string de idiomas, que pode conter o caractere '+' (ex: "por+eng")
        lang_code = self.settings.get("ocr_lang", "por")
        
        # Separa os idiomas para validação física dos arquivos
        langs_to_check = lang_code.split('+')
        
        # Mapeamento de caminhos comuns no Linux Mint / Ubuntu
        tess_paths = [
            "/usr/share/tesseract-ocr/5/tessdata/",    # Tesseract 5 (Mint 21+)
            "/usr/share/tesseract-ocr/4.00/tessdata/", # Tesseract 4 (Mint 20)
            "/usr/share/tessdata/",
            "/usr/local/share/tessdata/"
        ]
        
        valid_tessdata = None
        for p in tess_paths:
            # Verifica se TODOS os arquivos .traineddata requisitados existem neste diretório
            all_exist = all(os.path.exists(os.path.join(p, f"{lang}.traineddata")) for lang in langs_to_check)
            if all_exist:
                valid_tessdata = p
                break
                
        if not valid_tessdata:
            missing_files = [f"{lang}.traineddata" for lang in langs_to_check]
            logger.error(f"Abortando trial: pacote(s) {missing_files} não encontrados simultaneamente nos diretórios padrão.")
            return 0.0
        
        total_confidence = 0.0
        valid_samples = 0
        
        for path, img in self.ram_images.items():
            try:
                # 1. Replica o pipeline de OCR Prep (OpenCV)
                gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if len(img.shape) == 3 else img.copy()
                
                if denoise_h > 0.5:
                    gray = cv2.fastNlMeansDenoising(gray, None, float(denoise_h), 7, 21)
                    
                clahe = cv2.createCLAHE(clipLimit=float(clahe_clip), tileGridSize=(8,8))
                gray = clahe.apply(gray)
                
                bin_img = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, block_size, c_val)
                
                # 2. Converte a matriz OpenCV (NumPy) para Imagem PIL (Exigência da API C++)
                pil_img = Image.fromarray(bin_img)
                
                # 3. Interage diretamente com a Memória C++ passando o 'path' e a string original 'lang_code' (ex: "por+eng")
                with tesserocr.PyTessBaseAPI(path=valid_tessdata, lang=lang_code) as api:
                    api.SetImage(pil_img)
                    api.Recognize() # Executa a leitura
                    
                    # Retorna uma lista simples de inteiros com a confiança de cada palavra (0 a 100)
                    confidences = api.AllWordConfidences() 
                    
                    if confidences:
                        # Remover zeros absolutos que geralmente representam lixo/manchas
                        valid_confs = [c for c in confidences if c > 0]
                        if valid_confs:
                            avg_conf = sum(valid_confs) / len(valid_confs)
                            total_confidence += avg_conf
                            
                valid_samples += 1
                
            except Exception as e:
                logger.error(f"Erro no ensaio de OCR via C++: {e}")
                return 0.0

        return total_confidence / max(1, valid_samples)
