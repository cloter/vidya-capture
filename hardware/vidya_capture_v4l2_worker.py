# Arquivo: hardware/vidya_capture_v4l2_worker.py

from PIL import Image, ImageEnhance
import cv2
import io
import os
import time
import json
import numpy as np
import hashlib # <--- ADICIONADO PARA CADEIA DE CUSTÓDIA
from PyQt5 import QtCore
from core.config import TEMP_DIR
from core.logger import get_logger

logger = get_logger("V4L2Worker")

class VidyaV4L2Worker(QtCore.QThread):
    frame_ready = QtCore.pyqtSignal(bytes)
    capture_complete = QtCore.pyqtSignal(str)
    error_signal = QtCore.pyqtSignal(str)

    def __init__(self, port_address=None, position: str = "Left"):
        super().__init__()
        self.port_address = port_address
        self.position = position
        self.cap = None
        self.is_running = False
        self.mode = "preview"
        self.working_dir = TEMP_DIR
        self.settings = {}

    def run(self):
        self.is_running = True
        try:
            self._connect()
            self._configure_sensor()
            self._operation_loop()
        except Exception as e:
            logger.error(f"Erro no worker V4L2 {self.position}: {str(e)}")
            self.error_signal.emit(str(e))
        finally:
            self._disconnect()

    def _connect(self):
        addr = self.port_address
        if isinstance(addr, str) and addr.isdigit(): addr = int(addr)
        elif addr is None: addr = 0
        self.cap = cv2.VideoCapture(addr, cv2.CAP_V4L2)
        if not self.cap.isOpened(): raise RuntimeError(f"Não foi possível abrir o vídeo: {addr}")

    def _configure_sensor(self):
        if not self.cap: return

        # Transforma o endereço (ex: 0 ou 2) na chave do dicionário (ex: "/dev/video0")
        port_str = str(self.port_address)
        node_key = f"/dev/video{port_str}" if port_str.isdigit() else port_str

        # Verifica se o utilizador definiu regras estritas na "Detecção Avançada"
        adv_config = self.settings.get("v4l2_advanced_config", {})
        device_cfg = adv_config.get(node_key)

        if device_cfg and device_cfg.get("codec"):
            logger.info(f"Aplicando configuração de hardware estrita para {node_key}: {device_cfg}")
            fourcc = cv2.VideoWriter_fourcc(*device_cfg["codec"])
            self.cap.set(cv2.CAP_PROP_FOURCC, fourcc)
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, int(device_cfg["width"]))
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, int(device_cfg["height"]))
            
        else:
            # Comportamento padrão: Varredura Rápida (tenta forçar MJPG limite)
            force_max_res = self.settings.get("force_max_resolution", True)
            if force_max_res:
                fourcc = cv2.VideoWriter_fourcc(*'MJPG')
                self.cap.set(cv2.CAP_PROP_FOURCC, fourcc)
                self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 6000) 
                self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 6000)
            else:
                self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
                self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)

        # Restante da configuração padrão
        try: self.cap.set(cv2.CAP_PROP_AUTOFOCUS, 0)
        except Exception: pass
        try: self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        except Exception: pass

    def _get_hardware_metadata(self) -> dict:
        """Extrai a identidade do dispositivo lendo o SysFS do Linux e o OpenCV."""
        meta = {
            "device_class": "Video4Linux2",
            "port": str(self.port_address)
        }
        
        # 1. Tenta extrair o nome real do hardware no Linux (ex: 'Logitech C920')
        try:
            port_str = str(self.port_address)
            dev_id = f"video{port_str}" if port_str.isdigit() else os.path.basename(port_str)
            sysfs_name = f"/sys/class/video4linux/{dev_id}/name"
            if os.path.exists(sysfs_name):
                with open(sysfs_name, 'r', encoding='utf-8') as f:
                    meta["model"] = f.read().strip()
        except Exception:
            pass
            
        # 2. Tenta extrair a resolução e codec com que o OpenCV ancorou no dispositivo
        if self.cap and self.cap.isOpened():
            try:
                w = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                h = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                meta["resolution"] = f"{w}x{h}"
                
                fourcc = int(self.cap.get(cv2.CAP_PROP_FOURCC))
                if fourcc != 0:
                    codec = "".join([chr((fourcc >> 8 * i) & 0xFF) for i in range(4)])
                    meta["codec"] = codec.strip()
            except Exception:
                pass
                
        return meta

    # ---> ARMAZENAMENTO DO CAMINHO ALVO
    def trigger_capture(self, mode="Nova Captura", target_path=None, crop_geometry=None, batch_ts=None):
        if self.mode == "preview":
            self.current_capture_mode = mode
            self.current_target_path = target_path # Guarda o caminho alvo da substituição
            self.current_crop_geometry = crop_geometry
            self.current_batch_ts = batch_ts 
            self.mode = "capture"

    def _operation_loop(self):
        consecutive_errors = 0
        while self.is_running:
            if self.mode == "preview":
                ret, frame = self.cap.read()
                if ret:
                    _, buffer = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 70])
                    self.frame_ready.emit(buffer.tobytes())
                    consecutive_errors = 0
                else:
                    consecutive_errors += 1
                    if consecutive_errors > 10: time.sleep(1)
                time.sleep(0.03) 
            elif self.mode == "capture":
                self._execute_full_capture()
                self.mode = "preview"

    def _execute_full_capture(self):
        # Limpa o buffer antigo para pegar a imagem mais recente
        for _ in range(5): self.cap.grab()
            
        ret, frame = self.cap.read()
        if not ret: return

        # Envia uma cópia comprimida em tempo real para a interface
        _, buffer = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
        self.frame_ready.emit(buffer.tobytes())
        
        if getattr(self, 'current_capture_mode', 'Nova Captura') == "Teste": return

        # =============================================================
        # NOVO: GERAÇÃO DA CADEIA DE CUSTÓDIA (SHA-256 E PREMIS)
        # =============================================================

        hw_meta = self._get_hardware_metadata()

        # ---> LÓGICA DE SOBRESCRITA EXATA <---
        target_path = getattr(self, 'current_target_path', None)
        if target_path and os.path.exists(os.path.dirname(target_path)):
            # Tenta roubar o timestamp do arquivo que vai ser esmagado
            try:
                filename = os.path.basename(target_path)
                timestamp = filename.split('_')[2].split('.')[0]
            except Exception:
                timestamp = getattr(self, 'current_batch_ts', None) or str(int(time.time()))
        else:
            # Captura normal
            timestamp = getattr(self, 'current_batch_ts', None) or str(int(time.time()))
            fmt = self.settings.get("image_format", "JPG").upper()
            ext = "tif" if fmt == "TIFF" else fmt.lower()
            local_filename = f"Temp_{self.position}_{timestamp}.{ext}"
            target_path = os.path.join(self.working_dir, local_filename)

        # Transforma de BGR (OpenCV) para RGB (PIL) e aplica Rotação
        img_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        img = Image.fromarray(img_rgb)
        
        rot_setting = self.settings.get(f"rotation_{self.position.lower()}", "0°")
        angle = int(rot_setting.replace("°", ""))
        if angle != 0: img = img.rotate(-angle, expand=True)
        
        # =============================================================
        # NOVO: PÓS-PROCESSAMENTO DE IMAGEM (SOFTWARE)
        # =============================================================
        post_bright = self.settings.get("post_brightness", 0)
        post_contrast = self.settings.get("post_contrast", 0)

        # Só processa se o operador tirou o slider do zero
        if post_bright != 0:
            enhancer = ImageEnhance.Brightness(img)
            img = enhancer.enhance(1.0 + (post_bright / 100.0))

        if post_contrast != 0:
            enhancer = ImageEnhance.Contrast(img)
            img = enhancer.enhance(1.0 + (post_contrast / 100.0))
        # =============================================================

        # =============================================================
        # ENCODER PIL COMPLETO PARA FORMATO E COMPRESSÃO CONFIGURADOS
        # =============================================================
        save_kwargs = {}
        fmt = self.settings.get("image_format", "JPG").upper()
        if fmt == "JPG":
            save_kwargs["format"] = "JPEG"
            cmpr = save_kwargs["quality"] = int(getattr(self, 'settings', {}).get("jpg_quality", 95))
            logger.debug(f"Formato: {fmt} | Qualidade: {cmpr}")
        elif fmt == "PNG":
            save_kwargs["format"] = "PNG"
            cmpr = save_kwargs["compress_level"] = int(getattr(self, 'settings', {}).get("png_compression", 6))
            logger.debug(f"Formato: {fmt} | Compressão: {cmpr}")
        elif fmt == "TIFF":
            save_kwargs["format"] = "TIFF"
            cmpr = comp_type = getattr(self, 'settings', {}).get("tiff_compression", "Sem compressão")
            if comp_type == "Compressão lossless LZW":
                save_kwargs["compression"] = "tiff_lzw"
            elif comp_type == "Compressão lossless ZIP":
                save_kwargs["compression"] = "tiff_adobe_deflate"
            elif comp_type == "Compressão JPEG":
                save_kwargs["compression"] = "tiff_jpeg"
            else:
                save_kwargs["compression"] = None
            logger.debug(f"Formato: {fmt} | Compressão: {cmpr}")

        # Guarda no disco rígido
        img.save(target_path, **save_kwargs)

        # ---> CORREÇÃO DE CUSTÓDIA: Hash do arquivo físico (Após Gravação) <---
        file_hash = None
        if getattr(self, 'settings', {}).get("custody_calc_hash_on_capture", False):
            with open(target_path, "rb") as f:
                file_hash = hashlib.sha256(f.read()).hexdigest()
                logger.debug(f"Hash SHA-256 V4L2 gerado: {file_hash[:8]}...")
        # ----------------------------------------------------------------------
                
        # =============================================================
        # GERAÇÃO INCONDICIONAL DO ARQUIVO SIDECAR ARQUIVÍSTICO
        # =============================================================
        json_path = target_path.rsplit('.', 1)[0] + ".json"
        
        sidecar_data = {
            "timestamp": timestamp,
            "position": self.position,
            "preservation": {
                "hardware_environment": hw_meta
            }
        }
        
        # Adiciona a geometria apenas se ela existir, mas sem impedir a criação do JSON
        if hasattr(self, 'current_crop_geometry') and self.current_crop_geometry:
            sidecar_data["crop_geometry"] = self.current_crop_geometry
        
        # Injeta a prova criptográfica, se habilitada
        if file_hash:
            sidecar_data["preservation"]["sha256_raw_fixity"] = file_hash

        try:
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(sidecar_data, f, indent=4)
        except Exception as e:
            logger.error(f"Erro ao selar cadeia de custódia no JSON {json_path}: {e}")

        logger.info(f"Artefato V4L2 físico persistido ({fmt}): {target_path}")
        self.capture_complete.emit(target_path)

    def _disconnect(self):
        if self.cap and self.cap.isOpened(): self.cap.release()

    def stop(self):
        self.is_running = False
        self.wait()
