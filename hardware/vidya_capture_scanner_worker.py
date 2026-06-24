# Arquivo: hardware/vidya_capture_scanner_worker.py

import io
import os
import time
import json
import sane
import hashlib 
from PIL import Image, ImageEnhance
from PyQt5 import QtCore, QtGui
from core.config import TEMP_DIR
from core.logger import get_logger

Image.MAX_IMAGE_PIXELS = None

logger = get_logger("ScannerWorker")

class VidyaScannerWorker(QtCore.QThread):
    """
    Worker assíncrono para controlo de Scanners (Flatbed, Planetários, ADF) via backend SANE.
    Mantém paridade total com workers PTP e V4L2.
    """
    
    frame_ready = QtCore.pyqtSignal(bytes)
    capture_complete = QtCore.pyqtSignal(str)
    error_signal = QtCore.pyqtSignal(str)

    def __init__(self, port_address: str = None, position: str = "Left"):
        super().__init__()
        self.port_address = port_address
        self.position = position
        self.scanner = None
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
            logger.error(f"Erro inesperado no worker Scanner {self.position}: {str(e)}")
            self.error_signal.emit(str(e))
        finally:
            self._disconnect()

    def _connect(self):
        try:
            sane.init()
        except Exception:
            pass 
            
        try:
            if not self.port_address:
                devices = sane.get_devices()
                if not devices:
                    raise RuntimeError("Nenhum scanner SANE encontrado no sistema.")
                self.port_address = devices[0][0]
                
            self.scanner = sane.open(self.port_address)
            logger.info(f"Scanner {self.position} ({self.port_address}) inicializado com sucesso.")
            
        except Exception as e:
            raise RuntimeError(f"Falha ao conectar com o Scanner {self.port_address}: {e}")

    # =========================================================================
    # NOVO: INJEÇÃO SANE TOLERANTE A FALHAS (Tolerant Injection)
    # =========================================================================
    def _configure_sensor(self):
        """
        Injeta os parâmetros de digitalização no hardware usando a API SANE.
        Respeita a Máquina de Estados do SANE: Modos Maiores primeiro, Resolução e Geometria no fim.
        """
        if not self.scanner: return

        dpi = int(self.settings.get("scanner_dpi", 300))
        color_mode = self.settings.get("scanner_color_mode", "Color")
        source = self.settings.get("scanner_source", "Flatbed")
        paper = self.settings.get("scanner_paper_size", "Máximo do Vidro")
        brightness = int(self.settings.get("scanner_brightness", 0))
        contrast = int(self.settings.get("scanner_contrast", 0))

        # ==========================================================
        # FASE 1: MODOS MAIORES (Podem causar reset no driver)
        # ==========================================================
        # 1. Fonte de Alimentação (Flatbed vs ADF)
        try:
            self.scanner.source = source
        except Exception as e:
            logger.debug(f"Scanner recusou source '{source}': {e}")

        # 2. Modo de Cor
        try:
            self.scanner.mode = color_mode
        except Exception as e:
            logger.debug(f"Scanner recusou mode '{color_mode}': {e}")
            try: # Tenta alternativa comum em backends antigos
                if color_mode == "Color": self.scanner.mode = "24bit Color"
            except: pass

        # ==========================================================
        # FASE 2: RESOLUÇÃO E AJUSTES FINOS
        # ==========================================================
        # 3. Resolução Arquivística (DPI)
        try:
            # Padrão para a maioria (Epson, Canon, Fujitsu)
            self.scanner.resolution = dpi
        except Exception as e:
            logger.debug(f"Falha na variável 'resolution'. Tentando eixos separados (HP/Brother): {e}")
            try:
                # Padrão para HP (hpaio) e Brother
                self.scanner.x_resolution = dpi
                self.scanner.y_resolution = dpi
            except Exception as e2:
                logger.debug(f"Scanner recusou resolução {dpi} completamente: {e2}")

        # 4. Brilho e Contraste via Hardware
        if brightness != 0:
            try: self.scanner.brightness = brightness
            except Exception: pass
            
        if contrast != 0:
            try: self.scanner.contrast = contrast
            except Exception: pass

        # 5. Formato de Papel (Geometria do Carro de Luz em Milímetros)
        if paper != "Máximo do Vidro":
            paper_sizes = {
                "A4 (210x297mm)": (210.0, 297.0),
                "A3 (297x420mm)": (297.0, 420.0),
                "A2 (420x594mm)": (420.0, 594.0),
                "US Letter": (215.9, 279.4),
                "US Legal": (215.9, 355.6)
            }
            if paper in paper_sizes:
                w_mm, h_mm = paper_sizes[paper]
                try:
                    self.scanner.tl_x = 0.0
                    self.scanner.tl_y = 0.0
                    self.scanner.br_x = w_mm
                    self.scanner.br_y = h_mm
                except Exception as e:
                    logger.debug(f"Scanner recusou limites físicos para o recorte '{paper}': {e}")
            
        self._emit_standby_frame()

    def _emit_standby_frame(self):
        image = QtGui.QImage(1000, 1500, QtGui.QImage.Format_RGB32)
        image.fill(QtCore.Qt.darkGray)
        
        painter = QtGui.QPainter(image)
        painter.setPen(QtGui.QColor("white"))
        font = painter.font()
        font.setPointSize(30)
        painter.setFont(font)
        painter.drawText(image.rect(), QtCore.Qt.AlignCenter, f"SCANNER PRONTO\n{self.position}\nAguardando Comando...")
        painter.end()

        byte_array = QtCore.QByteArray()
        buffer = QtCore.QBuffer(byte_array)
        buffer.open(QtCore.QIODevice.WriteOnly)
        image.save(buffer, "JPG", quality=80)
        
        self.frame_ready.emit(byte_array.data())

    def _get_hardware_metadata(self) -> dict:
        meta = {
            "device_class": "Scanner SANE",
            "port": str(self.port_address)
        }
        
        if self.scanner:
            try:
                meta["vendor"] = getattr(self.scanner, 'vendor', 'Desconhecido')
                meta["model"] = getattr(self.scanner, 'model', 'Desconhecido')
                if hasattr(self.scanner, 'resolution'): meta["dpi"] = self.scanner.resolution
                if hasattr(self.scanner, 'mode'): meta["color_mode"] = self.scanner.mode
            except Exception as e:
                logger.debug(f"Aviso: Não foi possível extrair metadados completos do SANE: {e}")
                
        return meta

    def trigger_capture(self, mode="Nova Captura", target_path=None, crop_geometry=None, batch_ts=None):
        if self.mode == "preview":
            logger.debug(f"Sinal de captura recebido para a câmara {self.position}. Modo: {mode}")
            self.current_capture_mode = mode
            self.current_crop_geometry = crop_geometry
            self.current_batch_ts = batch_ts 
            self.mode = "capture"

    def _operation_loop(self):
        while self.is_running:
            if self.mode == "preview":
                time.sleep(0.1) 
            elif self.mode == "capture":
                self._execute_full_capture()
                self.mode = "preview"
                self._emit_standby_frame()

    # =========================================================================
    # INTOCADO: CAPTURA FÍSICA NO DISCO (APENAS MINIALTERAÇÃO DO PREVIEW)
    # =========================================================================
    def _execute_full_capture(self):
        logger.info(f"A iniciar varredura do scanner [{getattr(self, 'current_capture_mode', 'Nova Captura')}] no nó {self.position}...")
        
        try:
            self.scanner.start()
            img = self.scanner.snap()
            
            timestamp = getattr(self, 'current_batch_ts', None) or str(int(time.time()))
            
            # ---> PROTEÇÃO DE GUI: Cria um preview em miniatura (Thumbnail) da varredura real <---
            byte_io = io.BytesIO()
            preview_img = img.copy()
            # ---<

            # ---> PROTEÇÃO DE GUI: Cria um preview em miniatura (Thumbnail) da varredura real <---
            # Isso impede que matrizes massivas (ex: A2 a 600 DPI com ~10.000px) travem a interface
            byte_io = io.BytesIO()
            preview_img = img.copy()
            preview_img.thumbnail((2000, 2000)) # Limita renderização RAM, preservando o objeto físico
            preview_img.save(byte_io, format="JPEG", quality=85)
            self.frame_ready.emit(byte_io.getvalue())
            logger.debug(f"Varredura concluída. Renderizando resultado no visor ({self.position}).")

            if getattr(self, 'current_capture_mode', 'Nova Captura') == "Teste":
                logger.info(f"Modo Teste concluído ({self.position}). Nenhuma gravação no disco.")
                return

            hw_meta = self._get_hardware_metadata()

            fmt = self.settings.get("image_format", "JPG").upper()
            ext = "tif" if fmt == "TIFF" else fmt.lower()
            local_filename = f"Temp_{self.position}_{timestamp}.{ext}"
            target_path = os.path.join(self.working_dir, local_filename)

            rot_setting = self.settings.get(f"rotation_{self.position.lower()}", "0°")
            angle = int(rot_setting.replace("°", ""))
            if angle != 0:
                img = img.rotate(-angle, expand=True)

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

            save_kwargs = {}
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

            # GRAVAÇÃO REAL E INTOCADA DA IMAGEM ORIGINAL GIGANTE NO DISCO
            img.save(target_path, **save_kwargs)

            file_hash = None
            if getattr(self, 'settings', {}).get("custody_calc_hash_on_capture", False):
                with open(target_path, "rb") as f:
                    file_hash = hashlib.sha256(f.read()).hexdigest()
                    logger.debug(f"Hash SHA-256 SANE gerado: {file_hash[:8]}...")
                    
            json_path = target_path.rsplit('.', 1)[0] + ".json"
            
            sidecar_data = {
                "timestamp": timestamp,
                "position": self.position,
                "preservation": {
                    "hardware_environment": hw_meta
                }
            }
            
            if hasattr(self, 'current_crop_geometry') and self.current_crop_geometry:
                sidecar_data["crop_geometry"] = self.current_crop_geometry
            
            if file_hash:
                sidecar_data["preservation"]["sha256_raw_fixity"] = file_hash

            try:
                with open(json_path, 'w', encoding='utf-8') as f:
                    json.dump(sidecar_data, f, indent=4)
            except Exception as e:
                logger.error(f"Erro ao selar cadeia de custódia no JSON do Scanner ({json_path}): {e}")

            logger.info(f"Artefato do Scanner persistido com sucesso ({fmt}): {target_path}")
            self.capture_complete.emit(target_path)
            
        except Exception as e:
            logger.error(f"Erro durante a varredura do scanner {self.position}: {e}")
            self.error_signal.emit(str(e))            

    def _disconnect(self):
        if self.scanner:
            try:
                self.scanner.close()
            except Exception:
                pass
        try:
            sane.exit()
        except Exception:
            pass
        logger.info(f"Conexão com o Scanner {self.position} encerrada.")

    def stop(self):
        self.is_running = False
        self.wait()
