# Arquivo: hardware/vidya_capture_scanner_worker.py

from PIL import Image, ImageEnhance
import io
import os
import time
import json
import gphoto2 as gp
import hashlib
from PyQt5 import QtCore
from core.config import TEMP_DIR
from core.logger import get_logger

logger = get_logger("CameraWorker")

class VidyaCameraWorker(QtCore.QThread):
    """
    Worker assíncrono para controlo de câmaras via PTP.
    Opera fora da Main GUI Thread para evitar congelamentos durante operações I/O intensivas.
    """
    
    # Sinais Qt para comunicação segura com a GUI
    frame_ready = QtCore.pyqtSignal(bytes)
    capture_complete = QtCore.pyqtSignal(str)
    error_signal = QtCore.pyqtSignal(str)

    def __init__(self, port_address: str = None, position: str = "Left"):
        super().__init__()
        self.port_address = port_address
        self.position = position
        self.camera = gp.Camera()
        self.is_running = False
        self.mode = "preview"  # Modos: 'preview' ou 'capture'
        
        # Variável dinâmica de destino, inicialmente aponta para TEMP_DIR
        self.working_dir = TEMP_DIR
        self.settings = {} # <--- NOVO: Garante que não falha se a Main não passar logo os settings

    def run(self):
        """Ponto de entrada da QThread."""
        self.is_running = True
        try:
            self._connect()
            self._configure_canon_eos()
            self._operation_loop()
        except gp.GPhoto2Error as e:
            logger.error(f"Exceção gphoto2 no nó {self.position}: {str(e)}")
            self.error_signal.emit(str(e))
        except Exception as e:
            logger.error(f"Erro inesperado no worker da câmara {self.position}: {str(e)}")
            self.error_signal.emit(str(e))
        finally:
            if self.camera:
                self.camera.exit()
                logger.info(f"Conexão com a câmara {self.position} encerrada.")

    def _connect(self):
        """Inicializa a câmara, mapeando a porta USB se especificada."""
        if self.port_address:
            port_info_list = gp.PortInfoList()
            port_info_list.load()
            idx = port_info_list.lookup_path(self.port_address)
            self.camera.set_port_info(port_info_list[idx])
        
        self.camera.init()
        logger.info(f"Câmara {self.position} (Porta: {self.port_address or 'Auto'}) inicializada com sucesso.")

    def _configure_canon_eos(self):
        """
        Ajusta parâmetros nativos críticos para a arquitetura da EOS.
        Levanta o espelho físico para o Live View e otimiza o gatilho.
        """
        try:
            config = self.camera.get_config()
            
            # 1. Tenta levantar o espelho físico (Viewfinder) para permitir o Live View
            try:
                viewfinder = config.get_child_by_name("viewfinder")
                viewfinder.set_value(1) # 1 = Habilita a transmissão de vídeo MJPEG
                self.camera.set_config(config)
                logger.debug(f"Espelho (Viewfinder) levantado com sucesso na {self.position}.")
            except gp.GPhoto2Error:
                pass # Algumas câmaras não precisam desta ordem explícita
                
            # 2. Localiza e altera o comportamento de disparo remoto para imediato
            try:
                eos_remote_release = config.get_child_by_name("eosremoterelease")
                eos_remote_release.set_value("Immediate")
                self.camera.set_config(config)
            except gp.GPhoto2Error:
                pass

        except gp.GPhoto2Error as e:
            logger.warning(f"Aviso nas configurações avançadas Canon: {e}")

    def _get_hardware_metadata(self) -> dict:
        """Extrai os metadados físicos da câmara DSLR via protocolo PTP."""
        meta = {
            "device_class": "DSLR/PTP",
            "port": self.port_address or "USB Auto"
        }
        if not self.camera:
            return meta
            
        try:
            config = self.camera.get_config()
            # Tenta extrair o modelo exato da máquina
            try: meta["model"] = config.get_child_by_name("cameramodel").get_value()
            except: pass
            
            # Tenta extrair o número de série (Crucial para auditorias)
            try: meta["serial_number"] = config.get_child_by_name("serialnumber").get_value()
            except: pass
            
            # Tenta extrair a lente acoplada
            try: meta["lens"] = config.get_child_by_name("lensname").get_value()
            except: pass
        except Exception as e:
            logger.debug(f"Aviso: Não foi possível extrair metadados PTP completos: {e}")
            
        return meta

    # =========================================================================
    # ASSINATURA ATUALIZADA PARA RECEBER OS MESMOS DADOS DO MOCK
    # =========================================================================
    def trigger_capture(self, mode="Nova Captura", target_path=None, crop_geometry=None, batch_ts=None):
        """Método público para a GUI solicitar a inversão de estado para alta resolução."""
        if self.mode == "preview":
            logger.debug(f"Sinal de captura recebido para a câmara {self.position}. Modo: {mode}")
            self.current_capture_mode = mode
            self.current_crop_geometry = crop_geometry
            self.current_batch_ts = batch_ts # <--- Memoriza o código do par
            self.mode = "capture"

    def _operation_loop(self):
        """
        Laço infinito que alterna entre o streaming do Live View (MJPEG)
        e a interrupção para transferência de RAW/JPEG nativo.
        Blindado para não morrer em engasgos do barramento USB.
        """
        consecutive_errors = 0
        while self.is_running:
            if self.mode == "preview":
                try:
                    # Tenta capturar um frame do Live View
                    camera_file = self.camera.capture_preview()
                    file_data = camera_file.get_data_and_size()
                    byte_data = memoryview(file_data).tobytes()
                    
                    # Devolve para a interface e zera o contador de erros
                    self.frame_ready.emit(byte_data)
                    consecutive_errors = 0 
                    time.sleep(0.03) 
                    
                except gp.GPhoto2Error as e:
                    # Timeouts ou erros [-1] são comuns se o buffer USB engasgar ou
                    # a câmara estiver a calcular o foco. Não deixamos a thread morrer!
                    consecutive_errors += 1
                    time.sleep(0.2) # Pausa um pouco maior para a câmara "respirar"
                    
                    if consecutive_errors % 15 == 0:
                        logger.debug(f"Câmara {self.position} a aguardar estabilização do Live View (Erro {e.code})...")
                    continue # Volta para o início do while e tenta o próximo frame
                    
            elif self.mode == "capture":
                self._execute_full_capture()
                self.mode = "preview"

# =========================================================================
    # LÓGICA DE CAPTURA ATUALIZADA (MEMÓRIA, SIDECAR, CUSTÓDIA E MODOS)
    # =========================================================================
    def _execute_full_capture(self):
        """Executa a rotina de hardware e I/O com blindagem contra colisões de barramento."""
        logger.info(f"A iniciar captura de alta resolução [{getattr(self, 'current_capture_mode', 'Nova Captura')}] no nó {self.position}...")
        
        try:
            # 1. Pausa estratégica: permite que o barramento USB esvazie o último frame
            time.sleep(0.4)

            # 2. Desativa o Live View (baixa o espelho) para libertar o I/O
            try:
                config = self.camera.get_config()
                viewfinder = config.get_child_by_name("viewfinder")
                viewfinder.set_value(0)
                self.camera.set_config(config)
                time.sleep(0.2) 
            except gp.GPhoto2Error:
                pass 

            # 3. Limpa qualquer evento fantasma preso na fila do gphoto2 (Flush)
            while True:
                ev_type, ev_data = self.camera.wait_for_event(10)
                if ev_type == gp.GP_EVENT_TIMEOUT:
                    break

            # =================================================================
            # NOVA LÓGICA: LAÇO DE VARREDURA DE EVENTOS (EVENT LOOP)
            # =================================================================
            # 4. Efetua o disparo limpo
            self.camera.trigger_capture()

            # 5. Aguarda que o ficheiro apareça varrendo a fila de eventos
            file_path = None
            timeout_timer = time.time() + 8.0 # Dá até 8 segundos para ficheiros RAW muito pesados
            
            while time.time() < timeout_timer:
                ev_type, ev_data = self.camera.wait_for_event(500) # Verifica a cada 0.5s
                
                if ev_type == gp.GP_EVENT_FILE_ADDED:
                    file_path = ev_data
                    break # Encontrou o ficheiro! Quebra o laço e continua.
                elif ev_type == gp.GP_EVENT_TIMEOUT:
                    continue # Nenhuma novidade no USB, continua a aguardar.
                else:
                    # Recebeu outros eventos (como o ID 0). Apenas ignora e continua a ler a fila.
                    continue 

            # 6. Avalia se o ficheiro foi encontrado no laço
            if file_path:
                timestamp = getattr(self, 'current_batch_ts', None) or str(int(time.time()))
                
                # Download para a memória RAM
                camera_file = self.camera.file_get(
                    file_path.folder, file_path.name, gp.GP_FILE_TYPE_NORMAL
                )
                file_data = camera_file.get_data_and_size()
                byte_data = memoryview(file_data).tobytes()
                
                # Emite a foto real para a interface
                self.frame_ready.emit(byte_data)
                logger.debug(f"Imagem física renderizada no visor central ({self.position}).")
                
                if getattr(self, 'current_capture_mode', 'Nova Captura') == "Teste":
                    logger.info(f"Modo Teste concluído ({self.position}). Nada salvo no HD.")
                    return 

                # =============================================================
                # NOVO: GERAÇÃO DA CADEIA DE CUSTÓDIA (SHA-256 E PREMIS)
                # =============================================================

                hw_meta = {}
                if hasattr(self, '_get_hardware_metadata'):
                    hw_meta = self._get_hardware_metadata()

                # =============================================================
                # ENCODER PIL COMPLETO PARA FORMATO E COMPRESSÃO CONFIGURADOS
                # =============================================================
                fmt = getattr(self, 'settings', {}).get("image_format", "JPG").upper()
                ext = "tif" if fmt == "TIFF" else fmt.lower()
                local_filename = f"Temp_{self.position}_{timestamp}.{ext}"
                target_path = os.path.join(self.working_dir, local_filename)

                # Carrega o objeto de imagem em memória
                img = Image.open(io.BytesIO(byte_data))
                
                # Aproveita e aplica a rotação física antes do encode, caso configurado
                rot_setting = getattr(self, 'settings', {}).get(f"rotation_{self.position.lower()}", "0°")
                angle = int(rot_setting.replace("°", ""))
                if angle != 0:
                    img = img.rotate(-angle, expand=True)

                # =============================================================
                # NOVO: PÓS-PROCESSAMENTO DE IMAGEM (SOFTWARE)
                # =============================================================
                post_bright = getattr(self, 'settings', {}).get("post_brightness", 0)
                post_contrast = getattr(self, 'settings', {}).get("post_contrast", 0)

                # Só processa se o operador tirou o slider do zero
                if post_bright != 0:
                    enhancer = ImageEnhance.Brightness(img)
                    img = enhancer.enhance(1.0 + (post_bright / 100.0))

                if post_contrast != 0:
                    enhancer = ImageEnhance.Contrast(img)
                    img = enhancer.enhance(1.0 + (post_contrast / 100.0))
                # =============================================================

                # Compila os argumentos dinâmicos para a biblioteca Pillow
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

                # Guarda o ficheiro final estruturado de forma limpa no HD
                img.save(target_path, **save_kwargs)

                # ---> CORREÇÃO DE CUSTÓDIA: Hash do arquivo físico (Após Gravação) <---
                file_hash = None
                if getattr(self, 'settings', {}).get("custody_calc_hash_on_capture", False):
                    with open(target_path, "rb") as f:
                        file_hash = hashlib.sha256(f.read()).hexdigest()
                        logger.debug(f"Hash SHA-256 gerado para a captura: {file_hash[:8]}...")
                # ----------------------------------------------------------------------
                            
                # =============================================================
                # GERAÇÃO INCONDICIONAL DO ARQUIVO SIDECAR ARQUIVÍSTICO
                # =============================================================
                json_path = target_path.rsplit('.', 1)[0] + ".json"
                
                # O pacote base de metadados é SEMPRE gerado para garantir a Cadeia de Custódia
                sidecar_data = {
                    "timestamp": timestamp,
                    "position": self.position,
                    "preservation": {
                        "hardware_environment": hw_meta
                    }
                }
                
                # Injeta a geometria apenas se existir, mas NÃO impede a criação do JSON
                if hasattr(self, 'current_crop_geometry') and self.current_crop_geometry:
                    sidecar_data["crop_geometry"] = self.current_crop_geometry
                
                # Injeta a prova criptográfica, se habilitada nas preferências
                if file_hash:
                    sidecar_data["preservation"]["sha256_raw_fixity"] = file_hash

                # Grava no disco rígido com um bloco try/except para evitar quebra da thread
                try:
                    with open(json_path, 'w', encoding='utf-8') as f:
                        json.dump(sidecar_data, f, indent=4)
                except Exception as e:
                    logger.error(f"Erro ao selar cadeia de custódia no JSON da Câmera ({json_path}): {e}")

                logger.info(f"Artefato físico persistido com sucesso ({fmt}): {target_path}")
                self.capture_complete.emit(target_path)
                
            else:
                # O laço atingiu os 8 segundos e o ficheiro não apareceu
                logger.warning(f"Timeout: A foto foi tirada, mas o ficheiro não retornou na {self.position}.")

        except gp.GPhoto2Error as e:
            logger.error(f"Erro de disparo contornado no nó {self.position}: {e.string}")
            self.error_signal.emit(f"Falha contornada: {e.string}")
        except Exception as e:
            logger.error(f"Erro inesperado de hardware no nó {self.position}: {str(e)}")
        finally:
            # 7. Restaura o Live View (levanta o espelho) para o próximo ciclo
            try:
                config = self.camera.get_config()
                viewfinder = config.get_child_by_name("viewfinder")
                viewfinder.set_value(1)
                self.camera.set_config(config)
            except Exception:
                pass

    def stop(self):
        """Sinaliza paragem limpa da thread."""
        self.is_running = False
        self.wait()
