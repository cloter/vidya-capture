# Arquivo: hardware/mock_camera.py

import time
import os
import json
import io
import hashlib
import random  # <--- NOVA IMPORTAÇÃO
import math    # <--- NOVA IMPORTAÇÃO
from PIL import Image, ImageEnhance
from PyQt5 import QtCore, QtGui
from core.logger import get_logger
from core.config import TEMP_DIR


logger = get_logger("MockCamera")

class MockCamera(QtCore.QThread):
    """
    Simula uma câmera no barramento para testes de Interface.
    Refatorada para ser 100% compatível com as rotinas PTP e V4L2, 
    incluindo Cadeia de Custódia, Hashes e Pós-processamento de Imagem.
    """
    frame_ready = QtCore.pyqtSignal(bytes)
    capture_complete = QtCore.pyqtSignal(str)
    error_signal = QtCore.pyqtSignal(str)

    def __init__(self, port_address: str = None, position: str = "Left"):
        super().__init__()
        self.port_address = port_address
        self.position = position
        self.is_running = False
        self.mode = "preview"
        self.working_dir = TEMP_DIR
        self.settings = {} # Segurança de inicialização
        
        os.makedirs(TEMP_DIR, exist_ok=True)
        logger.debug(f"MockCamera inicializada para a posição: {self.position}")

    def _get_hardware_metadata(self) -> dict:
        """Fornece metadados simulados para espelhar a Cadeia de Custódia (PREMIS)."""
        return {
            "device_class": "Mock/Simulated",
            "port": self.port_address or "Virtual Port",
            "model": "Vidya Virtual Camera V1",
            "resolution": "1500x1000",
            "codec": "SIMULATED_RAW"
        }

    def trigger_capture(self, mode="Nova Captura", target_path=None, crop_geometry=None, batch_ts=None):
        """Método público para solicitar a inversão de estado para alta resolução."""
        if self.mode == "preview":
            logger.debug(f"Sinal de captura recebido na MockCamera {self.position}. Modo: {mode}")
            self.current_capture_mode = mode
            self.current_crop_geometry = crop_geometry
            self.current_target_path = target_path 
            self.current_batch_ts = batch_ts       
            self.mode = "capture"

    def run(self):
        """Laço infinito de simulação de hardware."""
        self.is_running = True
        logger.info(f"MockCamera {self.position} simulando conexão na porta: {self.port_address}")
        
        while self.is_running:
            if self.mode == "preview":
                time.sleep(0.1) # Poupa CPU no Live View
            elif self.mode == "capture":
                self._execute_full_capture()
                self.mode = "preview"
                
        logger.info(f"Conexão com a MockCamera {self.position} encerrada com segurança.")

    def _execute_full_capture(self):
        """Simula o I/O mecânico espelhando a arquitetura das máquinas reais."""
        logger.info(f"A iniciar captura simulada [{getattr(self, 'current_capture_mode', 'Nova Captura')}] no nó {self.position}...")
        
        time.sleep(1.2) # Simula o delay mecânico da câmara real
        
        # =============================================================
        # 1. GERAÇÃO DA IMAGEM CRUA (SIMULAÇÃO DO SENSOR)
        # =============================================================
        image = QtGui.QImage(1500, 1000, QtGui.QImage.Format_RGB32)
        color = QtCore.Qt.gray if self.position == "Left" else QtCore.Qt.lightGray
        image.fill(color)
        
        timestamp = getattr(self, 'current_batch_ts', None) or str(int(time.time()))
        
        painter = QtGui.QPainter(image)
        painter.setRenderHint(QtGui.QPainter.Antialiasing) # Ativa o anti-aliasing para os sólidos 3D ficarem polidos
        tp = random.randint(0, 5)
        MockShapeRenderer.render_background_noise(painter, 1500, 1000, num_shapes=35, render_type=tp)
        
        painter.setPen(QtGui.QColor("black"))
        font = painter.font()
        font.setPointSize(40)
        painter.setFont(font)
        painter.drawText(image.rect(), QtCore.Qt.AlignCenter, f"MOCK PAGE\n{self.position}\n{timestamp}")
        painter.end()

        # Envia a cópia provisória para o visor central (Live View simulado)
        byte_array = QtCore.QByteArray()
        buffer = QtCore.QBuffer(byte_array)
        buffer.open(QtCore.QIODevice.WriteOnly)
        image.save(buffer, "JPG", quality=85)
        buffer.close() 
        image_data = byte_array.data()
        
        self.frame_ready.emit(image_data)
        logger.debug(f"Imagem simulada renderizada no visor central ({self.position}).")

        if getattr(self, 'current_capture_mode', 'Nova Captura') == "Teste":
            logger.info(f"Modo Teste concluído ({self.position}). Nada salvo no HD.")
            return

        # =============================================================
        # 2. DEFINIÇÃO DO CAMINHO ALVO E CADEIA DE CUSTÓDIA
        # =============================================================
        hw_meta = self._get_hardware_metadata()
        target_path = getattr(self, 'current_target_path', None)
        
        if target_path and os.path.exists(os.path.dirname(target_path)):
            # MODO SUBSTITUIÇÃO: Herda o timestamp do arquivo que vai ser sobreposto
            try:
                filename = os.path.basename(target_path)
                file_ts = filename.split('_')[2].split('.')[0]
                if file_ts.isdigit(): timestamp = file_ts
            except Exception:
                pass
            fmt = "TIFF" if target_path.lower().endswith((".tif", ".tiff")) else ("PNG" if target_path.lower().endswith(".png") else "JPG")
        else:
            # MODO NOVA CAPTURA: Utiliza o padrão TEMPORÁRIO aguardado pelo Orquestrador
            fmt = self.settings.get("image_format", "JPG").upper()
            ext = "tif" if fmt == "TIFF" else fmt.lower()
            local_filename = f"Temp_{self.position}_{timestamp}.{ext}" 
            target_path = os.path.join(self.working_dir, local_filename)

        # =============================================================
        # 3. ENCODER PIL COMPLETO & PÓS-PROCESSAMENTO DE SOFTWARE
        # =============================================================
        img = Image.open(io.BytesIO(image_data))
        
        rot_setting = self.settings.get(f"rotation_{self.position.lower()}", "0°")
        angle = int(rot_setting.replace("°", ""))
        if angle != 0:
            img = img.rotate(-angle, expand=True)

        post_bright = self.settings.get("post_brightness", 0)
        post_contrast = self.settings.get("post_contrast", 0)

        if post_bright != 0:
            enhancer = ImageEnhance.Brightness(img)
            img = enhancer.enhance(1.0 + (post_bright / 100.0))

        if post_contrast != 0:
            enhancer = ImageEnhance.Contrast(img)
            img = enhancer.enhance(1.0 + (post_contrast / 100.0))

        save_kwargs = {}
        if fmt == "JPG":
            save_kwargs["format"] = "JPEG"
            save_kwargs["quality"] = int(self.settings.get("jpg_quality", 95))
        elif fmt == "PNG":
            save_kwargs["format"] = "PNG"
            save_kwargs["compress_level"] = int(self.settings.get("png_compression", 6))
        elif fmt == "TIFF":
            save_kwargs["format"] = "TIFF"
            comp_type = self.settings.get("tiff_compression", "Sem compressão")
            if comp_type == "Compressão lossless LZW": save_kwargs["compression"] = "tiff_lzw"
            elif comp_type == "Compressão lossless ZIP": save_kwargs["compression"] = "tiff_adobe_deflate"
            elif comp_type == "Compressão JPEG": save_kwargs["compression"] = "tiff_jpeg"
            else: save_kwargs["compression"] = None

        # Grava no Disco Rígido
        img.save(target_path, **save_kwargs)

        # =============================================================
        # 4. HASHER DE CUSTÓDIA
        # =============================================================
        file_hash = None
        if self.settings.get("custody_calc_hash_on_capture", False):
            with open(target_path, "rb") as f:
                file_hash = hashlib.sha256(f.read()).hexdigest()
                logger.debug(f"Hash SHA-256 gerado para MockCamera: {file_hash[:8]}...")

        # =============================================================
        # 5. SIDECAR JSON ARQUIVÍSTICO (IDÊNTICO AOS OUTROS WORKERS)
        # =============================================================
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
            logger.error(f"Erro ao selar cadeia de custódia no JSON MOCK {json_path}: {e}")

        logger.info(f"Artefato MOCK persistido com sucesso ({fmt}): {target_path}")
        self.capture_complete.emit(target_path)

    def stop(self):
        """Sinaliza paragem limpa da thread simulada."""
        self.is_running = False
        self.wait()
      

# =====================================================================
# NOVA CLASSE: Renderizador de Formas 3D para Ruído Visual
# =====================================================================
class MockShapeRenderer:
    """Classe responsável por gerar e espalhar formas geométricas 2D e 3D no fundo da imagem Mock."""
    
    @staticmethod
    def render_background_noise(painter: QtGui.QPainter, width: int, height: int, num_shapes: int = 35, render_type: int = 3):
        # ---> INSERÇÃO: Se for 0, sai imediatamente e não desenha formas
        if render_type <= 2:
            return

        cx, cy = width / 2.0, height / 2.0
        
        # Raio base da distribuição oblonga (elíptica) para desviar do centro exato
        base_rx = width * 0.35
        base_ry = height * 0.35

        # Dicionários de formas categorizadas
        shapes_2d = ['circle', 'square', 'triangle']
        shapes_3d = ['sphere', 'cube', 'cylinder', 'torus']

        # Filtro com base no parâmetro
        if render_type == 1:
            shapes = shapes_2d
        elif render_type == 2:
            shapes = shapes_3d
        else:  # render_type == 3 ou qualquer outro valor (Fallback de segurança)
            shapes = shapes_2d + shapes_3d

        for _ in range(num_shapes):
            # Calcula o ângulo aleatório ao longo da elipse (0 a 360 graus em radianos)
            theta = random.uniform(0, 2 * math.pi)
            
            # Adiciona um offset aleatório para que não fiquem numa linha perfeita
            offset_radius = random.uniform(0.6, 1.4) 
            
            x = cx + (base_rx * offset_radius * math.cos(theta))
            y = cy + (base_ry * offset_radius * math.sin(theta))
            
            # Tamanho variado
            size = random.uniform(40, 130)
            shape_type = random.choice(shapes)
            
            MockShapeRenderer._draw_shape(painter, x, y, size, shape_type)

    @staticmethod
    def _get_random_color() -> QtGui.QColor:
        # Gera cores pastéis/suaves para não ofuscar muito o texto principal
        return QtGui.QColor(random.randint(60, 220), random.randint(60, 220), random.randint(60, 220))

    @staticmethod
    def _draw_shape(painter: QtGui.QPainter, x: float, y: float, size: float, shape_type: str):
        painter.save()
        painter.translate(x, y)
        painter.rotate(random.uniform(0, 360)) # Rotação base para ângulos de projeção variados
        
        color = MockShapeRenderer._get_random_color()
        s = size / 2.0  # Meio tamanho para facilitar o desenho a partir do centro (0,0)
        
        if shape_type == 'circle':
            painter.setBrush(QtGui.QBrush(color))
            painter.setPen(QtCore.Qt.NoPen)
            painter.drawEllipse(QtCore.QPointF(0, 0), s, s)
            
        elif shape_type == 'square':
            painter.setBrush(QtGui.QBrush(color))
            painter.setPen(QtCore.Qt.NoPen)
            painter.drawRect(QtCore.QRectF(-s, -s, size, size))
            
        elif shape_type == 'triangle':
            painter.setBrush(QtGui.QBrush(color))
            painter.setPen(QtCore.Qt.NoPen)
            poly = QtGui.QPolygonF([QtCore.QPointF(0, -s), QtCore.QPointF(s, s), QtCore.QPointF(-s, s)])
            painter.drawPolygon(poly)
            
        elif shape_type == 'sphere':
            # Gradiente radial para simular iluminação 3D (fonte de luz no canto superior esquerdo)
            gradient = QtGui.QRadialGradient(QtCore.QPointF(-s/2, -s/2), size)
            gradient.setColorAt(0, color.lighter(160))
            gradient.setColorAt(0.8, color.darker(120))
            gradient.setColorAt(1, color.darker(180))
            painter.setBrush(QtGui.QBrush(gradient))
            painter.setPen(QtCore.Qt.NoPen)
            painter.drawEllipse(QtCore.QPointF(0, 0), s, s)
            
        elif shape_type == 'cube':
            # Projeção isométrica simulada de um cubo
            top_poly = QtGui.QPolygonF([QtCore.QPointF(0, -s), QtCore.QPointF(s, -s/2), QtCore.QPointF(0, 0), QtCore.QPointF(-s, -s/2)])
            left_poly = QtGui.QPolygonF([QtCore.QPointF(-s, -s/2), QtCore.QPointF(0, 0), QtCore.QPointF(0, s), QtCore.QPointF(-s, s/2)])
            right_poly = QtGui.QPolygonF([QtCore.QPointF(0, 0), QtCore.QPointF(s, -s/2), QtCore.QPointF(s, s/2), QtCore.QPointF(0, s)])
            
            painter.setPen(QtCore.Qt.NoPen)
            painter.setBrush(QtGui.QBrush(color.lighter(140)))  # Topo iluminado
            painter.drawPolygon(top_poly)
            painter.setBrush(QtGui.QBrush(color))               # Face frontal
            painter.drawPolygon(left_poly)
            painter.setBrush(QtGui.QBrush(color.darker(160)))   # Face em sombra
            painter.drawPolygon(right_poly)
            
        elif shape_type == 'cylinder':
            # Corpo do cilindro com gradiente linear
            gradient = QtGui.QLinearGradient(-s/2, 0, s/2, 0)
            gradient.setColorAt(0, color.darker(150))
            gradient.setColorAt(0.4, color.lighter(130))
            gradient.setColorAt(1, color.darker(150))
            painter.setBrush(QtGui.QBrush(gradient))
            painter.setPen(QtCore.Qt.NoPen)
            painter.drawRect(QtCore.QRectF(-s/2, -s/2, s, s))
            
            # Base do cilindro
            painter.drawEllipse(QtCore.QPointF(0, s/2), s/2, s/4)
            # Topo iluminado
            painter.setBrush(QtGui.QBrush(color.lighter(140)))
            painter.drawEllipse(QtCore.QPointF(0, -s/2), s/2, s/4)

        elif shape_type == 'torus':
            # Simulação de um Toroide (Donut) usando bordas grossas projetadas com sombra
            painter.setBrush(QtCore.Qt.NoBrush)
            pen = QtGui.QPen()
            pen.setWidthF(s / 1.5)
            pen.setJoinStyle(QtCore.Qt.RoundJoin)
            pen.setCapStyle(QtCore.Qt.RoundCap)
            
            # Desenha a "sombra" ou base ligeiramente deslocada
            pen.setColor(color.darker(160))
            painter.setPen(pen)
            painter.drawEllipse(QtCore.QPointF(s/6, s/6), s, s)
            
            # Desenha o anel superior principal
            pen.setColor(color.lighter(110))
            painter.setPen(pen)
            painter.drawEllipse(QtCore.QPointF(0, 0), s, s)

        painter.restore()
# =====================================================================
