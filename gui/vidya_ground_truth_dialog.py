# Arquivo: gui/vidya_ground_truth_dialog.py

import os
from PyQt5 import QtWidgets, QtCore, QtGui
from core.logger import get_logger
from gui.vidya_crop_marker import VidyaCropMarker

logger = get_logger("GroundTruthUI")

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
        self.marker = VidyaCropMarker(color, opacity, weight)
        self.marker.is_single_mode = True # Força modo simples para evitar cópias bilaterais
        
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

    def _load_current_image(self):
        if self.current_index >= len(self.sampled_images):
            return
            
        img_path = self.sampled_images[self.current_index]
        self.lbl_image_info.setText(f"Editando: {os.path.basename(img_path)}")
        self.lbl_progress.setText(f"{self.current_index + 1} de {len(self.sampled_images)}")
        
        # Atualiza o UI da lista
        self.list_samples.setCurrentRow(self.current_index)
        
        self.scene.clear()
        
        pixmap = QtGui.QPixmap(img_path)
        if pixmap.isNull():
            logger.error(f"Falha ao carregar amostra: {img_path}")
            self._on_next_clicked()
            return
            
        # Lógica de rotação para exibir corretamente
        rot_setting = self.settings.get("rotation_left", "0°") if "Left" in img_path else self.settings.get("rotation_right", "0°")
        angle = int(rot_setting.replace("°", ""))
        if angle != 0:
            pixmap = pixmap.transformed(QtGui.QTransform().rotate(angle))
            
        self.scene.addPixmap(pixmap)
        
        # Adiciona o marcador de volta à cena
        w, h = pixmap.width(), pixmap.height()
        self.marker.set_image_bounds(w, h)
        self.marker.set_geometry({"x": w*0.1, "y": h*0.1, "width": w*0.8, "height": h*0.8}) # Padrão centralizado
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
