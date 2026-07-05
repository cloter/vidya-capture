# Arquivo: gui/vidya_ground_truth_dialog.py

import os
import json # <--- ADICIONAR
import cv2  # <--- ADICIONAR
import numpy as np # <--- ADICIONAR
from PyQt5 import QtWidgets, QtCore, QtGui
from core.logger import get_logger
from gui.vidya_crop_marker import VidyaCropMarker
from core.config import COLOR_MAP # <--- ADICIONE ESTA LINHA PARA RESGATAR A PALETA DE CORES

logger = get_logger("GroundTruthUI")

# ===================================================================================
# NOVO MARCADOR ESPECIALIZADO: GROUND TRUTH (REDIMENSIONAMENTO PELOS CANTOS)
# ===================================================================================
class VidyaGTCropMarker(QtWidgets.QGraphicsRectItem):
    """
    Marcador customizado de bounding box que permite redimensionamento nativo
    pelos cantos e pelas arestas com feedback visual de cursores e bloqueio de margens.
    """
    def __init__(self, color_name, opacity, weight):
        super().__init__()
        # Permite seleção, movimento completo e detecção de colisões
        self.setFlags(QtWidgets.QGraphicsItem.ItemIsSelectable | 
                      QtWidgets.QGraphicsItem.ItemIsMovable | 
                      QtWidgets.QGraphicsItem.ItemSendsGeometryChanges)
        self.setAcceptHoverEvents(True)
        
        hex_color = COLOR_MAP.get(color_name, "#FF0000")
        color = QtGui.QColor(hex_color)
        
        self.pen_weight = max(2, weight // 20)
        self.active_pen = QtGui.QPen(color, self.pen_weight)
        self.active_pen.setJoinStyle(QtCore.Qt.MiterJoin)
        self.setPen(self.active_pen)
        
        brush_color = QtGui.QColor(color)
        brush_color.setAlpha(int((opacity / 100.0) * 255))
        self.setBrush(QtGui.QBrush(brush_color))
        
        self.resizing = None
        self.handle_size = 40 # Zona de clique ampliada para facilitar o manuseamento
        self.image_w = 0
        self.image_h = 0
        
    def set_image_bounds(self, w, h):
        self.image_w = w
        self.image_h = h

    def get_geometry(self):
        r = self.rect()
        p = self.pos()
        return {"x": r.x() + p.x(), "y": r.y() + p.y(), "width": r.width(), "height": r.height()}

    def set_geometry(self, geom):
        self.setPos(0, 0)
        self.setRect(geom["x"], geom["y"], geom["width"], geom["height"])

    def _get_handle(self, pos):
        """Mapeia se o clique do rato ocorreu num dos cantos ou arestas."""
        r = self.rect()
        x, y, w, h = r.x(), r.y(), r.width(), r.height()
        hs = self.handle_size
        
        # Cantos
        if pos.x() >= x + w - hs and pos.y() >= y + h - hs: return "BR"
        if pos.x() <= x + hs and pos.y() >= y + h - hs: return "BL"
        if pos.x() >= x + w - hs and pos.y() <= y + hs: return "TR"
        if pos.x() <= x + hs and pos.y() <= y + hs: return "TL"
        
        # Arestas Laterais
        if pos.x() >= x + w - hs: return "R"
        if pos.x() <= x + hs: return "L"
        if pos.y() >= y + h - hs: return "B"
        if pos.y() <= y + hs: return "T"
        
        return None

    def hoverMoveEvent(self, event):
        """Altera o formato do ponteiro do rato ao passar por cima das alavancas."""
        handle = self._get_handle(event.pos())
        if handle in ["TL", "BR"]: self.setCursor(QtCore.Qt.SizeFDiagCursor)
        elif handle in ["TR", "BL"]: self.setCursor(QtCore.Qt.SizeBDiagCursor)
        elif handle in ["L", "R"]: self.setCursor(QtCore.Qt.SizeHorCursor)
        elif handle in ["T", "B"]: self.setCursor(QtCore.Qt.SizeVerCursor)
        else: self.setCursor(QtCore.Qt.SizeAllCursor)
        super().hoverMoveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self.resizing = self._get_handle(event.pos())
            if self.resizing:
                self._resize_start_rect = self.rect()
                self._resize_start_pos = event.scenePos()
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.resizing:
            delta = event.scenePos() - self._resize_start_pos
            r = self._resize_start_rect
            p = self.pos()
            
            x, y, w, h = r.x(), r.y(), r.width(), r.height()
            
            # Aplica a força de arraste
            if "R" in self.resizing: w += delta.x()
            if "L" in self.resizing: 
                x += delta.x()
                w -= delta.x()
            if "B" in self.resizing: h += delta.y()
            if "T" in self.resizing:
                y += delta.y()
                h -= delta.y()
                
            # Limite mínimo de encolhimento
            min_w, min_h = 40, 40
            if w < min_w:
                if "L" in self.resizing: x -= (min_w - w)
                w = min_w
            if h < min_h:
                if "T" in self.resizing: y -= (min_h - h)
                h = min_h
                
            # Bloqueio das margens Esquerda e Topo contra os limites da imagem
            if p.x() + x < 0:
                diff = 0 - (p.x() + x)
                x += diff
                w -= diff
            if p.y() + y < 0:
                diff = 0 - (p.y() + y)
                y += diff
                h -= diff
                
            # Bloqueio das margens Direita e Base contra os limites da imagem
            if self.image_w > 0 and (p.x() + x + w > self.image_w):
                w = self.image_w - (p.x() + x)
            if self.image_h > 0 and (p.y() + y + h > self.image_h):
                h = self.image_h - (p.y() + y)
                
            self.setRect(x, y, w, h)
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton and self.resizing:
            self.resizing = None
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def itemChange(self, change, value):
        """Impede que o marcador seja arrastado por completo para fora da fotografia."""
        if change == QtWidgets.QGraphicsItem.ItemPositionChange and self.scene():
            if self.image_w > 0 and self.image_h > 0:
                new_pos = value
                r = self.rect()
                nx, ny = new_pos.x(), new_pos.y()
                
                if nx + r.x() < 0: nx = -r.x()
                if ny + r.y() < 0: ny = -r.y()
                if nx + r.x() + r.width() > self.image_w: nx = self.image_w - r.width() - r.x()
                if ny + r.y() + r.height() > self.image_h: ny = self.image_h - r.height() - r.y()
                
                return QtCore.QPointF(nx, ny)
        return super().itemChange(change, value)
        
    def paint(self, painter, option, widget=None):
        super().paint(painter, option, widget)
        # Feedback Visual: Desenha alças grossas nos cantos para instruir o utilizador
        painter.setPen(self.active_pen)
        painter.setBrush(QtGui.QBrush(self.active_pen.color()))
        r = self.rect()
        hs = self.pen_weight * 3
        half = hs / 2.0
        
        corners = [
            QtCore.QRectF(r.left() - half, r.top() - half, hs, hs),
            QtCore.QRectF(r.right() - half, r.top() - half, hs, hs),
            QtCore.QRectF(r.left() - half, r.bottom() - half, hs, hs),
            QtCore.QRectF(r.right() - half, r.bottom() - half, hs, hs)
        ]
        for c in corners:
            painter.drawRect(c)
# ===================================================================================

class VidyaGroundTruthDialog(QtWidgets.QDialog):
    """
    Interface focada para o utilizador anotar o "Gabarito" (Ground Truth)
    nas amostras selecionadas antes de iniciar o Optuna.
    """
    
    def __init__(self, sampled_images: list, calibration_config: dict, settings: dict, parent=None):
        super().__init__(parent)
        self.sampled_images = sampled_images
        self.calibration_config = calibration_config
        self.settings = settings
        
        self.current_index = 0
        self.ground_truth_data = {}  # Mapeia: caminho_da_imagem -> geometria_ideal
        
        self.setWindowTitle("Assistente de Calibração IA - Marcação de Ground Truth")
        self.resize(1024, 720)
        self.setModal(True)
        
        self._setup_ui()
        self._load_current_image()

    def _setup_ui(self):
        layout = QtWidgets.QHBoxLayout(self)
        
        # --- PAINEL ESQUERDO (Progresso) ---
        left_panel = QtWidgets.QWidget()
        left_panel.setFixedWidth(250)
        left_layout = QtWidgets.QVBoxLayout(left_panel)
        
        lbl_inst = QtWidgets.QLabel("<b>Imagens Sorteadas</b><br><small>Ajuste o quadro para indicar à IA onde está o documento real.</small>")
        lbl_inst.setWordWrap(True)
        left_layout.addWidget(lbl_inst)
        
        self.list_samples = QtWidgets.QListWidget()
        for img_path in self.sampled_images:
            item = QtWidgets.QListWidgetItem(os.path.basename(img_path))
            item.setData(QtCore.Qt.UserRole, img_path)
            # Ícone de pendente
            item.setIcon(QtGui.QIcon.fromTheme("dialog-warning"))
            self.list_samples.addItem(item)
            
        self.list_samples.setCurrentRow(0)
        self.list_samples.setSelectionMode(QtWidgets.QAbstractItemView.NoSelection) # Impede pulos
        
        left_layout.addWidget(self.list_samples)
        
        # --- PAINEL DIREITO (Visor) ---
        right_panel = QtWidgets.QWidget()
        right_layout = QtWidgets.QVBoxLayout(right_panel)
        
        self.lbl_image_info = QtWidgets.QLabel("Carregando...")
        self.lbl_image_info.setStyleSheet("font-weight: bold; font-size: 11pt;")
        right_layout.addWidget(self.lbl_image_info)
        
        self.view = QtWidgets.QGraphicsView()
        self.scene = QtWidgets.QGraphicsScene()
        self.view.setScene(self.scene)
        self.view.setRenderHints(QtGui.QPainter.Antialiasing | QtGui.QPainter.SmoothPixmapTransform)
        right_layout.addWidget(self.view)
        
        # Instancia o marcador de recorte (aproveitando as cores das preferências)
        color = self.settings.get("marker_color_left", "Vermelho")
        opacity = self.settings.get("marker_opacity", 8)
        weight = self.settings.get("marker_thickness_weight", 100)
        
        # ---> INSERÇÃO DA SUBSTITUIÇÃO:
        self.marker = VidyaGTCropMarker(color, opacity, weight)
        
        # --- BARRA INFERIOR (Controles) ---
        bottom_layout = QtWidgets.QHBoxLayout()
        self.lbl_progress = QtWidgets.QLabel(f"1 de {len(self.sampled_images)}")
        
        self.btn_next = QtWidgets.QPushButton(" Confirmar e Avançar")
        self.btn_next.setIcon(QtGui.QIcon.fromTheme("go-next"))
        self.btn_next.setStyleSheet("background-color: #2980b9; color: white; font-weight: bold; padding: 8px;")
        self.btn_next.clicked.connect(self._on_next_clicked)
        
        bottom_layout.addWidget(self.lbl_progress)
        bottom_layout.addStretch()
        bottom_layout.addWidget(self.btn_next)
        
        right_layout.addLayout(bottom_layout)
        
        layout.addWidget(left_panel)
        layout.addWidget(right_panel)

    # =========================================================================
    # MOTOR DE PREPARAÇÃO EM RAM (MICRO-PIPELINE GEOMÉTRICA)
    # =========================================================================
    def _cv2_to_qpixmap(self, cv_img):
        """Converte matrizes nativas do OpenCV (BGR) para o formato seguro da GUI (QPixmap)."""
        height, width, channels = cv_img.shape
        bytesPerLine = channels * width
        cv_rgb = cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGB)
        qImg = QtGui.QImage(cv_rgb.data, width, height, bytesPerLine, QtGui.QImage.Format_RGB888)
        # O .copy() é crucial para impedir Segmentation Faults quando o Python limpar a memória
        return QtGui.QPixmap.fromImage(qImg).copy()

    def _post_deskew_crop_in_ram(self, img):
        """Replica a matemática de auto-crop (isolamento da página) pós-deskew na RAM."""
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
            valid_rects = []
            for c in contours:
                area = cv2.contourArea(c)
                if img_area * min_area_val < area < img_area * 0.95:
                    cx, cy, cw, ch = cv2.boundingRect(c)
                    pad_x, pad_y = int(cw * pad_val), int(ch * pad_val)
                    nx = max(0, cx - pad_x)
                    ny = max(0, cy - pad_y)
                    nw = min(w - nx, cw + 2 * pad_x)
                    nh = min(h - ny, ch + 2 * pad_y)
                    valid_rects.append((nx, ny, nw, nh))
                    
            if not valid_rects: return img
            valid_rects.sort(key=lambda r: r[2]*r[3], reverse=True)
            nx, ny, nw, nh = valid_rects[0]
            return img[ny:ny+nh, nx:nx+nw]
        except Exception as e:
            logger.error(f"Falha no auto-crop em RAM: {e}")
            return img

    def _prepare_image_in_ram(self, img_path):
        """Carrega a imagem original e aplica 100% da geometria exigida no projeto ativo."""
        img = cv2.imread(img_path)
        if img is None: return None
        
        json_path = img_path.rsplit('.', 1)[0] + ".json"
        
        # 1. Aplicar cortes e alinhamentos manuais (Herdados do Vidya Capture)
        homographics_run = False
        if os.path.exists(json_path):
            try:
                with open(json_path, 'r', encoding='utf-8') as f:
                    meta = json.load(f)
                    
                manual_pts = meta.get("manual_deskew", [])
                if manual_pts and len(manual_pts) == 4:
                    pts = np.array([[p["x"], p["y"]] for p in manual_pts], dtype="float32")
                    s = pts.sum(axis=1)
                    diff = np.diff(pts, axis=1)
                    rect = np.zeros((4, 2), dtype="float32")
                    rect[0] = pts[np.argmin(s)]
                    rect[2] = pts[np.argmax(s)]
                    rect[1] = pts[np.argmin(diff)]
                    rect[3] = pts[np.argmax(diff)]
                    
                    orig_h, orig_w = img.shape[:2]
                    dst = np.array([[0, 0], [orig_w - 1, 0], [orig_w - 1, orig_h - 1], [0, orig_h - 1]], dtype="float32")
                    M = cv2.getPerspectiveTransform(rect, dst)
                    img = cv2.warpPerspective(img, M, (orig_w, orig_h))
                    homographics_run = True
                
                # Se não houve 4 pontos, aplica o crop geométrico normal do utilizador
                if not homographics_run:
                    geom = meta.get("crop_geometry", {})
                    if geom:
                        x = int(geom.get("x", 0)); y = int(geom.get("y", 0))
                        w = int(geom.get("width", img.shape[1])); h = int(geom.get("height", img.shape[0]))
                        x = max(0, x); y = max(0, y)
                        w = min(w, img.shape[1] - x); h = min(h, img.shape[0] - y)
                        img = img[y:y+h, x:x+w]
            except Exception as e:
                logger.error(f"Erro ao carregar metadados na amostra {img_path}: {e}")

        # 2. Deskew de Contorno (Limpeza do Fundo de Mesa)
        if self.settings.get("proc_contour_deskew", False):
            try:
                from core.vidya_contour_deskew import VidyaContourDeskewer
                contour_deskewer = VidyaContourDeskewer()
                ac_invert = self.settings.get("ac_invert", "Automático")
                img, _, changed = contour_deskewer.deskew(img, invert_mode=ac_invert)
                if changed:
                    img = self._post_deskew_crop_in_ram(img)
            except Exception as e:
                logger.error(f"Erro no Deskew de Contorno da amostra: {e}")

        # 3. Deskew de Texto (Alinhamento Fino para o Tesseract OCR)
        if self.settings.get("proc_deskew", True):
            try:
                from core.vidya_deskew import VidyaDeskewer
                deskew_agg = float(self.settings.get("deskew_aggressiveness", 1.0))
                deskewer = VidyaDeskewer(max_angle=15.0)
                img, _, _ = deskewer.deskew(img, aggressiveness=deskew_agg)
            except Exception as e:
                logger.error(f"Erro no Deskew de Texto da amostra: {e}")
                
        # 4. Dewarp (Planificação de Páginas Curvas)
        if self.settings.get("proc_dewarp", False):
            try:
                from core.vidya_dewarp import VidyaPageDewarper
                dewarp_agg = float(self.settings.get("dewarp_aggressiveness", 1.0))
                dewarper = VidyaPageDewarper(aggressiveness=dewarp_agg)
                flattened_img, success = dewarper.flatten(img)
                if success:
                    img = flattened_img
            except Exception as e:
                logger.error(f"Erro no Dewarp da amostra: {e}")

        return img
    # =========================================================================
    
    def _load_current_image(self):
        if self.current_index >= len(self.sampled_images):
            return
            
        img_path = self.sampled_images[self.current_index]
        self.lbl_image_info.setText(f"Editando: {os.path.basename(img_path)}")
        self.lbl_progress.setText(f"{self.current_index + 1} de {len(self.sampled_images)}")
        
        # Atualiza a lista lateral
        self.list_samples.setCurrentRow(self.current_index)
        
        # Remove fisicamente o marcador da cena antes de limpar
        if self.marker.scene() == self.scene:
            self.scene.removeItem(self.marker)
            
        self.scene.clear()
        
        # =====================================================================
        # NOVA INTEGRAÇÃO: Executa a Micro-Pipeline antes de mostrar a imagem
        # =====================================================================
        cv_img = self._prepare_image_in_ram(img_path)
        if cv_img is None:
            logger.error(f"Falha ao carregar ou processar amostra na RAM: {img_path}")
            self._on_next_clicked() # Pula a imagem corrompida automaticamente
            return
            
        pixmap = self._cv2_to_qpixmap(cv_img)
        # =====================================================================
        
        # Lógica de rotação legada (para garantir que a interface espelhe perfeitamente a UI principal)
        rot_setting = self.settings.get("rotation_left", "0°") if "Left" in img_path else self.settings.get("rotation_right", "0°")
        angle = int(rot_setting.replace("°", ""))
        if angle != 0:
            pixmap = pixmap.transformed(QtGui.QTransform().rotate(angle), QtCore.Qt.SmoothTransformation)
            
        self.scene.addPixmap(pixmap)
        
        # As dimensões agora são da imagem PERFEITAMENTE PLANA e ALINHADA
        w, h = pixmap.width(), pixmap.height()
        self.marker.set_image_bounds(w, h)
        
        # Se for o primeiro acesso da IA a esta amostra, propõe uma caixa inicial com uma folga amigável
        if img_path not in self.ground_truth_data:
            self.marker.set_geometry({"x": w*0.05, "y": h*0.05, "width": w*0.9, "height": h*0.9}) 
            
        self.scene.addItem(self.marker)
        
        # Ajusta a visualização (Zoom out para caber)
        self.view.fitInView(self.scene.itemsBoundingRect(), QtCore.Qt.KeepAspectRatio)

    def _on_next_clicked(self):
        # 1. Salva a geometria atual no dicionário de Ground Truth
        current_path = self.sampled_images[self.current_index]
        self.ground_truth_data[current_path] = self.marker.get_geometry()
        
        # 2. Marca na lista visual como concluído
        item = self.list_samples.item(self.current_index)
        item.setIcon(QtGui.QIcon.fromTheme("emblem-default")) # Ícone de check (sucesso)
        
        self.current_index += 1
        
        # 3. Verifica se acabou
        if self.current_index >= len(self.sampled_images):
            self.accept() # Fecha o dialog com status de Sucesso
        else:
            # Transição visual para a última imagem
            if self.current_index == len(self.sampled_images) - 1:
                self.btn_next.setText(" Concluir Anotações e Iniciar IA")
                self.btn_next.setStyleSheet("background-color: #27ae60; color: white; font-weight: bold; padding: 8px;")
                self.btn_next.setIcon(QtGui.QIcon.fromTheme("system-run"))
                
            self._load_current_image()

    def get_ground_truth(self) -> dict:
        """Retorna o dicionário com as coordenadas perfeitas desenhadas pelo humano."""
        return self.ground_truth_data
