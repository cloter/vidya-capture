# Arquivo: core/vidya_fisheye_calibration.py

import cv2
import numpy as np
import glob
import os
from PyQt5 import QtCore

class FisheyeCalibrationWorker(QtCore.QThread):
    progress_text = QtCore.pyqtSignal(str)     # Emite o status em texto
    progress_value = QtCore.pyqtSignal(int)    # Emite a porcentagem (0 a 100)
    finished = QtCore.pyqtSignal(bool, dict, str) # (Sucesso, Dados JSON, Mensagem de Erro)

    def __init__(self, profile_name, angle, checker_x, checker_y, square_size, images_dir, base_install_path):
        super().__init__()
        self.profile_name = profile_name
        self.angle = angle
        self.checker_x = checker_x
        self.checker_y = checker_y
        self.square_size = float(square_size)
        self.images_dir = images_dir
        self.base_install_path = base_install_path

    def run(self):
        try:
            self.progress_text.emit("Procurando imagens no diretório...")
            self.progress_value.emit(0)
            
            extensoes = ('*.jpg', '*.jpeg', '*.png', '*.JPG', '*.JPEG', '*.PNG')
            imagens = []
            for ext in extensoes:
                imagens.extend(glob.glob(os.path.join(self.images_dir, ext)))
                
            if not imagens:
                self.finished.emit(False, {}, "Nenhuma imagem válida encontrada no diretório informado.")
                return

            checkerboard = (self.checker_x, self.checker_y)
            subpix_criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.1)

            objp = np.zeros((1, checkerboard[0] * checkerboard[1], 3), np.float32)
            objp[0,:,:2] = np.mgrid[0:checkerboard[0], 0:checkerboard[1]].T.reshape(-1, 2)
            objp = objp * self.square_size

            objpoints = []
            imgpoints = []
            shape_imagem = None

            total_imgs = len(imagens)
            for i, nome_ficheiro in enumerate(imagens):
                self.progress_text.emit(f"Analisando cantos: imagem {i+1} de {total_imgs}...")
                
                # Preenche a barra até 80% durante a leitura das imagens
                pct = int((i / total_imgs) * 80)
                self.progress_value.emit(pct)
                
                img = cv2.imread(nome_ficheiro)
                if img is None:
                    continue
                    
                if shape_imagem is None:
                    shape_imagem = img.shape[:2] # Assume a resolução da primeira imagem válida
                    
                if shape_imagem != img.shape[:2]:
                    self.progress_text.emit(f"Aviso: Ignorando {os.path.basename(nome_ficheiro)} por ter resolução diferente.")
                    continue
                    
                gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
                ret, corners = cv2.findChessboardCorners(
                    gray, checkerboard, 
                    cv2.CALIB_CB_ADAPTIVE_THRESH + cv2.CALIB_CB_FAST_CHECK + cv2.CALIB_CB_NORMALIZE_IMAGE
                )
                
                if ret:
                    objpoints.append(objp)
                    cv2.cornerSubPix(gray, corners, (3,3), (-1,-1), subpix_criteria)
                    imgpoints.append(corners)

            if len(objpoints) < 5:
                self.finished.emit(False, {}, "Falha: São necessárias pelo menos 5 imagens válidas com o tabuleiro completamente visível.")
                return

            self.progress_text.emit("Calculando matrizes e coeficientes de distorção (Isso pode levar alguns minutos)...")
            # Emite -1 para ativar o modo "infinito/vai-e-vem" da QProgressBar
            self.progress_value.emit(-1)
            
            N_OK = len(objpoints)
            K = np.zeros((3, 3))
            D = np.zeros((4, 1))
            rvecs = [np.zeros((1, 1, 3), dtype=np.float64) for _ in range(N_OK)]
            tvecs = [np.zeros((1, 1, 3), dtype=np.float64) for _ in range(N_OK)]

            calibration_flags = cv2.fisheye.CALIB_RECOMPUTE_EXTRINSIC + cv2.fisheye.CALIB_CHECK_COND + cv2.fisheye.CALIB_FIX_SKEW

            rms, _, _, _, _ = cv2.fisheye.calibrate(
                objpoints, imgpoints, gray.shape[::-1],
                K, D, rvecs, tvecs, calibration_flags, 
                (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 1e-6)
            )

            self.progress_text.emit("Gravando arquivos de calibração...")
            self.progress_value.emit(95)
            
            safe_profile_name = "".join([c if c.isalnum() else "_" for c in self.profile_name])
            calib_dir = os.path.join(self.base_install_path, "calibrations")
            os.makedirs(calib_dir, exist_ok=True)
            
            k_filename = f"fisheye_K_{safe_profile_name}_angle_{self.angle}.npy"
            d_filename = f"fisheye_D_{safe_profile_name}_angle_{self.angle}.npy"
            
            k_path = os.path.join(calib_dir, k_filename)
            d_path = os.path.join(calib_dir, d_filename)
            
            np.save(k_path, K)
            np.save(d_path, D)
            
            result_data = {
                f"angle_{self.angle}_K": k_path,
                f"angle_{self.angle}_D": d_path,
                f"angle_{self.angle}_rms": float(rms),
                f"angle_{self.angle}_resolution": [shape_imagem[1], shape_imagem[0]] # [Largura, Altura]
            }

            self.progress_value.emit(100)
            self.finished.emit(True, result_data, "Calibração concluída com sucesso!")

        except Exception as e:
            self.finished.emit(False, {}, f"Erro inesperado durante a calibração: {str(e)}")
