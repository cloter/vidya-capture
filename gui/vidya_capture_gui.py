# Arquivo: gui/vidya_capture_gui.py

from PyQt5 import QtWidgets, QtCore, QtGui
import os
import json
from core.logger import get_logger
from core.config import load_settings, save_settings
from gui.vidya_crop_marker import VidyaCropMarker
from gui.vidya_settings_dialog import VidyaSettingsDialog
from gui.vidya_thumbnail_panel import VidyaThumbnailPanel
from gui.vidya_theme_manager import VidyaThemeManager

logger = get_logger("VidyaGUI")

class VidyaCropUndoManager:
    """Gerencia snapshots de 1 nível estrito com sistema de Rascunhos em 2 etapas."""
    def __init__(self):
        self.snapshot = None
        self.draft_snapshot = None

    def clear(self, position=None):
        if position:
            if self.snapshot and self.snapshot["position"] == position:
                self.snapshot = None
            if self.draft_snapshot and self.draft_snapshot["position"] == position:
                self.draft_snapshot = None
        else:
            self.snapshot = None
            self.draft_snapshot = None

    def save_draft(self, position: str, main_marker, active_clips: list):
        self.draft_snapshot = {
            "position": position,
            "main": main_marker.get_geometry(),
            "clips": [clip.get_geometry() for clip in active_clips if clip.scene()]
        }

    def commit_draft(self, current_main_geom, current_clips_geom):
        """Avalia se a foto do rascunho é diferente da atual. Se sim, oficializa."""
        if not self.draft_snapshot: return
        
        # Avaliação de clique acidental vs clique de edição real
        changed = False
        if self.draft_snapshot["main"] != current_main_geom:
            changed = True
        elif self.draft_snapshot["clips"] != current_clips_geom:
            changed = True
            
        if changed:
            self.snapshot = self.draft_snapshot
            
        self.draft_snapshot = None

    def pop_state(self) -> tuple:
        if not self.snapshot: return None, None
        snap = self.snapshot
        self.snapshot = None  
        return snap["position"], snap

class VidyaMainWindow(QtWidgets.QMainWindow):
    invert_requested = QtCore.pyqtSignal()
    capture_requested = QtCore.pyqtSignal(str, dict, dict)
    settings_updated = QtCore.pyqtSignal(dict)
    reload_requested = QtCore.pyqtSignal()
    shutdown_requested = QtCore.pyqtSignal()
    
    show_splash_requested = QtCore.pyqtSignal() # <--- NOVO: Sinal para o F4

    def __init__(self):
        super().__init__()
        vidya_version = os.getenv("VIDYA_VERSION", "Desconhecida")
        
        self.setWindowTitle(f"Vidya Capture - Digitalização de Acervos - Versão {vidya_version}")
        self.resize(1024, 600)
        
        # Ajuste o caminho 'assets/icon.png' de acordo com o local físico da sua imagem
        icon_path = os.path.join(os.path.dirname(__file__), '..', 'assets', 'vidya_capture_icon.png')
        if os.path.exists(icon_path):
            self.setWindowIcon(QtGui.QIcon(icon_path))
        # ---------------------------------------
        
        QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_UseHighDpiPixmaps)

        self.capture_modes = ["Nova Captura", "Substituir", "Teste"]
        self.current_mode_index = 0
        self.zoom_factor = 1.0
        
        self._THUMB_MIN_W  = 160   
        self._THUMB_MAX_W  = 400   
        self._VIEW_BASE_W  = 380   
        self._VIEW_ABS_MIN = 260
        self._BUTTONS_MIN_W = 800
        
        self.is_single_mode = False  
        self.is_reviewing = False
        self.review_actions = ["Substituir Par", "Substituir Esquerda", "Substituir Direita", "Inserir Antes", "Inserir Depois", "Alterar Recorte"]
        self.current_review_action_index = 0
        self.pending_review_action = None
        self.pending_replace_paths = {}
        
        self.active_clips = [] 
        
        # ---> INÍCIO DA INSERÇÃO: ESTADOS DO DESKEW MANUAL
        self.is_picking_deskew = False
        self.deskew_position = "Left"
        self.deskew_marker_left = None
        self.deskew_marker_right = None
        # ---> FIM DA INSERÇÃO
        
        self.pending_crop_reset = {"Left": False, "Right": False}
        self.current_image_dims = {"Left": (0, 0), "Right": (0, 0)}
        self.live_pixmaps = {"Left": None, "Right": None} 
        
        # --- NOVO: RASTREADOR DE BORDAS ---
        self.image_borders = {"Left": None, "Right": None}
        
        self.device_name_left = "Câmera Esquerda"
        self.device_name_right = "Câmera Direita"
        
        self.undo_manager = VidyaCropUndoManager()
                
        self.settings = load_settings()
        self.dynamic_label_color = "#2c3e50" # Cor padrão clara
        self._setup_ui()
        self._apply_theme() # -> INSERIR ESTA LINHA NO FINAL DO INIT

    def apply_project_mode(self, is_single_mode: bool):
        self.is_single_mode = is_single_mode
        
        self._THUMB_MIN_W = 130 if is_single_mode else 160
        self._BUTTONS_MIN_W = 660 if is_single_mode else 800 
        
        if hasattr(self, 'thumbnail_panel'):
            self.thumbnail_panel.setMinimumWidth(self._THUMB_MIN_W)

        if is_single_mode:
            min_w = max(self._BUTTONS_MIN_W, self._VIEW_ABS_MIN + 20)
        else:
            min_w = max(self._BUTTONS_MIN_W, self._VIEW_ABS_MIN * 2 + 20)
            
        if hasattr(self, 'left_container'):
            self.left_container.setMinimumWidth(min_w)
        
        if hasattr(self, 'right_view_wrapper'):
            self.right_view_wrapper.setVisible(not is_single_mode)
            
        self.chk_replicate.setVisible(not is_single_mode)
        self.btn_invert.setVisible(not is_single_mode)
        
        if is_single_mode:
            self.review_actions = ["Substituir Imagem", "Inserir Antes", "Inserir Depois"]
            self.btn_remove_last.setText(" Remover última")
            self.btn_remove_last.setToolTip("Del: Remove a última imagem capturada ou selecionada")
            self.view_left.setToolTip("<b>Dica:</b> Arraste as bordas para ajustar o recorte ou <b>clique com o botão direito</b> para mais opções.\n<b>Experimente</b> a função <i>[P] Proporção</i>")
        else:
            self.review_actions = ["Substituir Par", "Substituir Esquerda", "Substituir Direita", "Inserir Antes", "Inserir Depois"]
            self.btn_remove_last.setText(" Remover duas últimas")
            self.btn_remove_last.setToolTip("Del: Remove o último par capturado ou selecionado")
            self.view_left.setToolTip("<b>Dica:</b> Arraste as bordas ou <b>clique com o botão direito</b> para mais opções.\n<b>Experimente</b> <i>[P] Proporção</i> e <i>[R] Replicar</i>")

        if hasattr(self, 'marker_left'): self.marker_left.is_single_mode = is_single_mode
        if hasattr(self, 'marker_right'): self.marker_right.is_single_mode = is_single_mode

        self.update_status_bar()
        self.load_project_workspace()
        
        if hasattr(self, 'splitter'):
            self._rebalance_splitter()
            
        logger.info(f"Interface adaptada. Modo Câmera Única: {is_single_mode}. Thumb Min Width: {self._THUMB_MIN_W}px")

    def set_device_names(self, left_name: str, right_name: str):
        self.device_name_left = left_name
        self.device_name_right = right_name
        if not self.is_reviewing:
            if self.is_single_mode:
                self.lbl_info_left.setText(f"{self.device_name_left}  (Aguardando vídeo...)")
            else:
                self.lbl_info_left.setText(f"{self.device_name_left}  (Aguardando vídeo...)")
                self.lbl_info_right.setText(f"{self.device_name_right}  (Aguardando vídeo...)")

    def _setup_ui(self):
        central_widget = QtWidgets.QWidget()
        self.setCentralWidget(central_widget)
        
        master_layout = QtWidgets.QHBoxLayout(central_widget)
        master_layout.setContentsMargins(8, 8, 8, 8)

        self.shortcut_f11 = QtWidgets.QShortcut(QtGui.QKeySequence("F11"), self)
        self.shortcut_f11.activated.connect(self._toggle_fullscreen)
        self.shortcut_f10 = QtWidgets.QShortcut(QtGui.QKeySequence("F10"), self)
        self.shortcut_f10.activated.connect(self._toggle_maximize)
        
        self.splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
        master_layout.addWidget(self.splitter)

        self.left_container = QtWidgets.QWidget()
        left_panel_layout = QtWidgets.QVBoxLayout(self.left_container)
        left_panel_layout.setContentsMargins(8, 8, 8, 8)
        
        self.left_container.setMinimumWidth(max(self._BUTTONS_MIN_W, self._VIEW_ABS_MIN * 2 + 20))
        
        self.thumbnail_panel = VidyaThumbnailPanel(self.settings)
        self.thumbnail_panel.pair_selected.connect(self.show_review_pair)
        
        # ---> NOVAS INSERÇÕES:
        self.thumbnail_panel.delete_item_requested.connect(self._on_context_menu_delete)
        self.thumbnail_panel.rebuild_finished.connect(self.reload_requested.emit)
        # ---> FIM DAS INSERÇÕES
        
        self.thumbnail_panel.auto_crop_requested.connect(self._on_auto_crop_requested)
        
        self.thumbnail_panel.setMinimumWidth(self._THUMB_MIN_W) 
        self.thumbnail_panel.setToolTip("<b style='color: #2980b9;'>Dica:</b> Clique nas miniaturas para editar.")
       
        control_layout = QtWidgets.QHBoxLayout()
        
        self.btn_prefs = QtWidgets.QPushButton(" Preferências")
        self.btn_prefs.setIcon(QtGui.QIcon.fromTheme("preferences-system")) 
        self.btn_prefs.clicked.connect(self._open_settings)
        self.btn_prefs.setToolTip("F2: Abre a janela de configuração")
        
        # -> INÍCIO DA INSERÇÃO: Botão de Tema (Modificado)
        self.btn_theme = QtWidgets.QPushButton()
        self.btn_theme.setFixedWidth(40) # Mantém o botão pequeno
        
        # Aplica o Negrito na fonte do botão
        font_theme = self.btn_theme.font()
        font_theme.setBold(True)
        self.btn_theme.setFont(font_theme)
        
        # Lê o estado atual nas configurações para definir a letra inicial
        is_dark_initial = self.settings.get("dark_mode", False)
        self.btn_theme.setText(" E" if is_dark_initial else " C")
        
        self.btn_theme.clicked.connect(self._toggle_theme)
        self.btn_theme.setToolTip("Alternar entre Tema Claro (C) e Escuro (E)")
        # -> FIM DA INSERÇÃO
        
        self.shortcut_f7 = QtWidgets.QShortcut(QtGui.QKeySequence("F7"), self)
        self.shortcut_f7.activated.connect(self._on_zoom_out_clicked)
        
        self.shortcut_f8 = QtWidgets.QShortcut(QtGui.QKeySequence("F8"), self)
        self.shortcut_f8.activated.connect(self._on_zoom_in_clicked)
        
        self.btn_invert = QtWidgets.QPushButton(" Inverter")
        self.btn_invert.setIcon(QtGui.QIcon.fromTheme("object-flip-horizontal"))
        self.btn_invert.clicked.connect(self.invert_requested.emit)
        self.btn_invert.setToolTip("F3: Inverte os dispositivos de captura")
        
        self.btn_adjust = QtWidgets.QPushButton(" Reiniciar")
        self.btn_adjust.setIcon(QtGui.QIcon.fromTheme("zoom-fit-best"))
        self.btn_adjust.clicked.connect(self._on_adjust_panels_clicked)       
        self.btn_adjust.setToolTip("F5/Esc: Sai do modo de edição / Reinicia a interface") 
        
        self.btn_zoom_out = QtWidgets.QPushButton(" Menos zoom")
        self.btn_zoom_out.setIcon(QtGui.QIcon.fromTheme("zoom-out"))
        self.btn_zoom_out.clicked.connect(self._on_zoom_out_clicked)
        self.btn_zoom_out.setToolTip("F7: Diminui o zoom das imagens")

        self.btn_zoom_in = QtWidgets.QPushButton(" Mais zoom")
        self.btn_zoom_in.setIcon(QtGui.QIcon.fromTheme("zoom-in"))
        self.btn_zoom_in.clicked.connect(self._on_zoom_in_clicked)
        self.btn_zoom_in.setToolTip("F8: Aumenta o zoom das imagens")
        
        self.btn_process = QtWidgets.QPushButton(" Exportar")
        self.btn_process.setObjectName("btn_process") # -> ADICIONE ESTA LINHA
        self.btn_process.setIcon(QtGui.QIcon.fromTheme("system-run"))
        self.btn_process.setStyleSheet("background-color: #2196F3; color: white; font-weight: bold;")
        self.btn_process.setToolTip("F12: Aplica os algoritmos de corte,\n  alinhamento e planificação e cria\n  o PDF/A final com OCR")

        self.chk_keep_ratio = QtWidgets.QCheckBox(" Proporção")
        self.chk_keep_ratio.setChecked(self.settings.get("keep_crop_ratio", False))
        self.chk_keep_ratio.stateChanged.connect(self._on_keep_ratio_changed)
        self.chk_keep_ratio.setToolTip("P: Trava a proporção do quadro de corte da imagem")

        self.chk_replicate = QtWidgets.QCheckBox(" Replicar")
        self.chk_replicate.setChecked(self.settings.get("replicate_crop", False))
        self.chk_replicate.stateChanged.connect(self._on_replicate_changed)
        self.chk_replicate.setToolTip("R: Replica os quadros de corte esquerda/direita")
                
        control_layout.addWidget(self.btn_prefs)
        control_layout.addWidget(self.btn_adjust)
        control_layout.addWidget(self.btn_invert)
        control_layout.addWidget(self.btn_zoom_out) 
        control_layout.addWidget(self.btn_zoom_in)  
        control_layout.addWidget(self.chk_keep_ratio) 
        control_layout.addWidget(self.chk_replicate) 
        control_layout.addWidget(self.btn_process)
        control_layout.addWidget(self.btn_theme) # -> ADICIONAR ESTA LINHA        
        control_layout.addStretch()
        left_panel_layout.addLayout(control_layout)

        view_layout = QtWidgets.QHBoxLayout()
        
        self.left_view_wrapper = QtWidgets.QWidget()
        self.left_view_wrapper.setMinimumWidth(self._VIEW_ABS_MIN) 
        left_view_container = QtWidgets.QVBoxLayout(self.left_view_wrapper)
        left_view_container.setContentsMargins(0, 0, 0, 0)
        
        self.right_view_wrapper = QtWidgets.QWidget()
        self.right_view_wrapper.setMinimumWidth(self._VIEW_ABS_MIN) 
        right_view_container = QtWidgets.QVBoxLayout(self.right_view_wrapper)
        right_view_container.setContentsMargins(0, 0, 0, 0)
        
        label_style = "font-size: 11pt; font-weight: bold; color: #2c3e50; padding-bottom: 2px;"
        
        self.lbl_info_left = QtWidgets.QLabel(f"{self.device_name_left} (Aguardando...)")
        self.lbl_info_left.setAlignment(QtCore.Qt.AlignCenter)
        self.lbl_info_left.setStyleSheet(label_style)
        
        self.lbl_info_right = QtWidgets.QLabel(f"{self.device_name_right} (Aguardando...)")
        self.lbl_info_right.setAlignment(QtCore.Qt.AlignCenter)
        self.lbl_info_right.setStyleSheet(label_style)

        self.view_left = QtWidgets.QGraphicsView()
        self.view_right = QtWidgets.QGraphicsView()
        
        self.view_left.viewport().installEventFilter(self)
        self.view_right.viewport().installEventFilter(self)

        self.view_left.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        self.view_right.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        
        for view in (self.view_left, self.view_right):
            view.setRenderHints(QtGui.QPainter.Antialiasing | QtGui.QPainter.SmoothPixmapTransform)
            view.setOptimizationFlags(QtWidgets.QGraphicsView.DontSavePainterState)
            view.setViewportUpdateMode(QtWidgets.QGraphicsView.SmartViewportUpdate)

        self.scene_left = QtWidgets.QGraphicsScene()
        self.scene_right = QtWidgets.QGraphicsScene()
        
        self.view_left.setScene(self.scene_left)
        self.view_right.setScene(self.scene_right)
        
        color_left = self.settings.get("marker_color_left", "Vermelho")
        color_right = self.settings.get("marker_color_right", "Verde")
        opacity = self.settings.get("marker_opacity", 8)
        weight = self.settings.get("marker_thickness_weight", 100)
        
        self.marker_left = VidyaCropMarker(color_left, opacity, weight)
        self.marker_right = VidyaCropMarker(color_right, opacity, weight)

        self.marker_left.copy_exact_callback = lambda: self._copy_crop_geometry("Right", "Left", mirror=False)
        self.marker_left.copy_mirror_callback = lambda: self._copy_crop_geometry("Right", "Left", mirror=True)
        self.marker_right.copy_exact_callback = lambda: self._copy_crop_geometry("Left", "Right", mirror=False)
        self.marker_right.copy_mirror_callback = lambda: self._copy_crop_geometry("Left", "Right", mirror=True)
        
        self.marker_left.maximize_local_callback = lambda: self._maximize_crop("Left")
        self.marker_left.maximize_both_callback = lambda: self._maximize_crop("Both")
        self.marker_right.maximize_local_callback = lambda: self._maximize_crop("Right")
        self.marker_right.maximize_both_callback = lambda: self._maximize_crop("Both")
        
        self.marker_left.resize_percent_callback = self._resize_crop_percent
        self.marker_right.resize_percent_callback = self._resize_crop_percent
        
        self.marker_left.reset_all_clips_callback = self._reset_crops_and_maximize
        self.marker_right.reset_all_clips_callback = self._reset_crops_and_maximize
        
        # ---> INÍCIO DA INSERÇÃO: MAPEAMENTO DOS CALLBACKS DO DESKEW
        self.marker_left.start_manual_deskew_callback = lambda marker: self._start_manual_deskew("Left")
        self.marker_right.start_manual_deskew_callback = lambda marker: self._start_manual_deskew("Right")
        # ---> FIM DA INSERÇÃO
        # ... logo abaixo de start_manual_deskew_callback = lambda...
        self.marker_left.cancel_manual_deskew_callback = lambda marker: self._cancel_manual_deskew("Left")
        self.marker_right.cancel_manual_deskew_callback = lambda marker: self._cancel_manual_deskew("Right")
        
        # ---> ADICIONE ESTAS DUAS LINHAS:
        self.marker_left.remove_manual_deskew_callback = self._remove_manual_deskew
        self.marker_right.remove_manual_deskew_callback = self._remove_manual_deskew
        
        self.marker_left.add_clip_callback = self._add_new_clip
        self.marker_left.duplicate_callback = self._duplicate_clip  # Adicione esta linha
        
        self.marker_left.toggle_ratio_callback = self._toggle_keep_ratio
        self.marker_right.toggle_ratio_callback = self._toggle_keep_ratio
        self.marker_left.toggle_replicate_callback = self._toggle_replicate
        self.marker_right.toggle_replicate_callback = self._toggle_replicate
        
        self.marker_left.sync_callback = lambda: self._sync_crops("Left")
        self.marker_right.sync_callback = lambda: self._sync_crops("Right")

        self.marker_left.save_undo_state_callback = self._save_undo_snapshot    # <--- ADICIONE
        self.marker_right.save_undo_state_callback = self._save_undo_snapshot   # <--- ADICIONE

        is_replicate_kept = self.settings.get("replicate_crop", False)
        if hasattr(self.marker_left, 'set_replicate_state'): self.marker_left.set_replicate_state(is_replicate_kept)
        if hasattr(self.marker_right, 'set_replicate_state'): self.marker_right.set_replicate_state(is_replicate_kept)        

        is_ratio_kept = self.settings.get("keep_crop_ratio", False)
        if hasattr(self.marker_left, 'set_keep_ratio'): self.marker_left.set_keep_ratio(is_ratio_kept)
        if hasattr(self.marker_right, 'set_keep_ratio'): self.marker_right.set_keep_ratio(is_ratio_kept)

        self.marker_left.set_geometry(self.settings.get("marker_left_geometry"))
        self.marker_right.set_geometry(self.settings.get("marker_right_geometry"))
        
        self.scene_left.addItem(self.marker_left)
        self.scene_right.addItem(self.marker_right)
        
        left_view_container.addWidget(self.lbl_info_left)
        left_view_container.addWidget(self.view_left, stretch=1)
        right_view_container.addWidget(self.lbl_info_right)
        right_view_container.addWidget(self.view_right, stretch=1)
        
        view_layout.addWidget(self.left_view_wrapper, stretch=1)
        view_layout.addWidget(self.right_view_wrapper, stretch=1)
        left_panel_layout.addLayout(view_layout)
        
        capture_toolbar_layout = QtWidgets.QHBoxLayout()
        
        self.btn_remove_last = QtWidgets.QPushButton(" Remover")
        self.btn_remove_last.setIcon(QtGui.QIcon.fromTheme("edit-delete"))
        self.btn_remove_last.setMinimumHeight(40)
        self.btn_remove_last.clicked.connect(self._on_remove_last_clicked)
        
        self.btn_capture = QtWidgets.QPushButton(" CAPTURAR")
        self.btn_capture.setIcon(QtGui.QIcon.fromTheme("camera-photo"))
        self.btn_capture.setMinimumHeight(40)
        font = self.btn_capture.font()
        font.setPointSize(14)
        font.setBold(True)
        self.btn_capture.setFont(font)
        self.btn_capture.setShortcut(QtCore.Qt.Key_Space)
        self.btn_capture.clicked.connect(self._on_capture_clicked)
        self.btn_capture.setToolTip("Enter / Espaço: Multifunção dependendo do estado")

        self.btn_capture_mode = QtWidgets.QPushButton(" Modo: Nova Captura")
        self.btn_capture_mode.setIcon(QtGui.QIcon.fromTheme("view-refresh"))
        self.btn_capture_mode.setMinimumHeight(35)
        self.btn_capture_mode.clicked.connect(self._on_cycle_capture_mode)
        self.btn_capture_mode.setToolTip("Tab: Seleciona o tipo de captura")
        
        self._update_capture_button_style()
        
        capture_toolbar_layout.addWidget(self.btn_remove_last, stretch=1)
        capture_toolbar_layout.addWidget(self.btn_capture, stretch=2)
        capture_toolbar_layout.addWidget(self.btn_capture_mode, stretch=1)
        left_panel_layout.addLayout(capture_toolbar_layout)

        self.splitter.addWidget(self.thumbnail_panel)
        self.splitter.addWidget(self.left_container)
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        
        if self.splitter.count() > 1:
            self.splitter.handle(1).installEventFilter(self)

        if not self.load_project_workspace():
            self.splitter.setSizes([220, 10000])

        QtCore.QTimer.singleShot(0, self._rebalance_splitter)
        self._setup_shortcuts() 

    def _setup_shortcuts(self):
        QtWidgets.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key_Return), self).activated.connect(self._on_capture_clicked)
        QtWidgets.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key_Enter), self).activated.connect(self._on_capture_clicked)
        QtWidgets.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key_Delete), self).activated.connect(self._on_remove_last_clicked)
        QtWidgets.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key_Backspace), self).activated.connect(self._on_remove_last_clicked)
        QtWidgets.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key_Tab), self).activated.connect(self._on_cycle_capture_mode)
        
        # ✔️ ATALHOS BLINDADOS CONTRA PERDA DE FOCO
        self.sc_esc = QtWidgets.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key_Escape), self)
        self.sc_esc.setContext(QtCore.Qt.ApplicationShortcut)
        self.sc_esc.activated.connect(self._on_adjust_panels_clicked)

        self.sc_f5 = QtWidgets.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key_F5), self)
        self.sc_f5.setContext(QtCore.Qt.ApplicationShortcut)
        self.sc_f5.activated.connect(self._on_adjust_panels_clicked)
        
        # ---> NOVO: Atalho F4 para rodar a Splash Screen <---
        self.sc_f4 = QtWidgets.QShortcut(QtGui.QKeySequence(QtCore.Qt.Key_F4), self)
        self.sc_f4.setContext(QtCore.Qt.ApplicationShortcut)
        self.sc_f4.activated.connect(self.show_splash_requested.emit)

        QtWidgets.QShortcut(QtGui.QKeySequence.ZoomIn, self).activated.connect(self._on_zoom_in_clicked)
        QtWidgets.QShortcut(QtGui.QKeySequence("Ctrl++"), self).activated.connect(self._on_zoom_in_clicked)
        QtWidgets.QShortcut(QtGui.QKeySequence("+"), self).activated.connect(self._on_zoom_in_clicked)
        QtWidgets.QShortcut(QtGui.QKeySequence("="), self).activated.connect(self._on_zoom_in_clicked)
        
        QtWidgets.QShortcut(QtGui.QKeySequence.ZoomOut, self).activated.connect(self._on_zoom_out_clicked)
        QtWidgets.QShortcut(QtGui.QKeySequence("Ctrl+-"), self).activated.connect(self._on_zoom_out_clicked)
        QtWidgets.QShortcut(QtGui.QKeySequence("_"), self).activated.connect(self._on_zoom_out_clicked)
        QtWidgets.QShortcut(QtGui.QKeySequence("-"), self).activated.connect(self._on_zoom_out_clicked)
        
        QtWidgets.QShortcut(QtGui.QKeySequence("F6"), self).activated.connect(self._reset_zoom)
        QtWidgets.QShortcut(QtGui.QKeySequence("Ctrl+0"), self).activated.connect(self._reset_zoom)
        QtWidgets.QShortcut(QtGui.QKeySequence("0"), self).activated.connect(self._reset_zoom)
        
        # Atalho Agressivo de Desfazer (Impede que a QGraphicsView engula o comando)
        undo_shortcut = QtWidgets.QShortcut(QtGui.QKeySequence("Ctrl+Z"), self)
        undo_shortcut.setContext(QtCore.Qt.ApplicationShortcut)
        undo_shortcut.activated.connect(self._perform_undo)
        
        QtWidgets.QShortcut(QtGui.QKeySequence("P"), self).activated.connect(self._toggle_keep_ratio)
        QtWidgets.QShortcut(QtGui.QKeySequence("R"), self).activated.connect(self._toggle_replicate)
        
        QtWidgets.QShortcut(QtGui.QKeySequence("F3"), self).activated.connect(self.invert_requested.emit)
        QtWidgets.QShortcut(QtGui.QKeySequence("F12"), self).activated.connect(self.btn_process.click)
        QtWidgets.QShortcut(QtGui.QKeySequence("F2"), self).activated.connect(self._open_settings)
        QtWidgets.QShortcut(QtGui.QKeySequence("F1"), self).activated.connect(self._open_manual)
        
        QtWidgets.QShortcut(QtGui.QKeySequence(QtCore.Qt.CTRL | QtCore.Qt.Key_Delete), self).activated.connect(self._on_remove_last_clicked)
        QtWidgets.QShortcut(QtGui.QKeySequence(QtCore.Qt.CTRL | QtCore.Qt.Key_PageDown), self).activated.connect(lambda: self._trigger_review_action("Inserir Antes"))
        QtWidgets.QShortcut(QtGui.QKeySequence(QtCore.Qt.CTRL | QtCore.Qt.Key_PageUp), self).activated.connect(lambda: self._trigger_review_action("Inserir Depois"))
        QtWidgets.QShortcut(QtGui.QKeySequence(QtCore.Qt.CTRL | QtCore.Qt.Key_Insert), self).activated.connect(lambda: self._trigger_review_action(self.review_actions[0]))
        
        QtWidgets.QShortcut(QtGui.QKeySequence(QtCore.Qt.CTRL | QtCore.Qt.Key_Left), self).activated.connect(lambda: self._trigger_review_action("Substituir Esquerda"))
        QtWidgets.QShortcut(QtGui.QKeySequence(QtCore.Qt.CTRL | QtCore.Qt.Key_Right), self).activated.connect(lambda: self._trigger_review_action("Substituir Direita"))

    # =========================================================================
    # MECANISMO DE DESFAZER (UNDO) DE 1 NÍVEL
    # =========================================================================
    def _save_undo_snapshot(self, target_marker=None, is_draft=False, commit_draft=False):
        """Tira uma foto da estrutura atual baseada na etapa do clique do utilizador."""
        pos = "Right" if target_marker == getattr(self, 'marker_right', None) else "Left"
        main_m = self.marker_left if pos == "Left" else self.marker_right
        clips = getattr(self, 'active_clips', []) if pos == "Left" else []
        
        if commit_draft:
            # Etapa 2: Soltou o clique. Compara e se houve mudança real, oficializa o rascunho
            current_main_geom = main_m.get_geometry()
            current_clips_geom = [clip.get_geometry() for clip in clips if clip.scene()]
            self.undo_manager.commit_draft(current_main_geom, current_clips_geom)
        elif is_draft:
            # Etapa 1: Pressionou o rato. Tira uma foto cega provisória (rascunho)
            self.undo_manager.save_draft(pos, main_m, clips)
        else:
            # Botões diretos (Menu de contexto, botões). Força a foto cega a ser oficial na hora
            self.undo_manager.save_draft(pos, main_m, clips)
            self.undo_manager.snapshot = self.undo_manager.draft_snapshot
            self.undo_manager.draft_snapshot = None

    def _perform_undo(self):
        """Restaura o último estado cronológico da imagem manipulada."""
        pos, state = self.undo_manager.pop_state()
        if not state: return

        # 1. Restaura o marcador principal do lado correto
        main_m = self.marker_left if pos == "Left" else self.marker_right
        main_m.set_geometry(state["main"])

        # 2. Restaura os clipes filhos (Somente para a Esquerda / Câmera Única)
        if pos == "Left":
            self._clear_clips()
            for geom in state["clips"]:
                self._recreate_clip_from_geom(geom)

        self._save_review_crop_if_needed()
        logger.info(f"Ação desfeita na Câmera {pos}.")

    def _recreate_clip_from_geom(self, geom: dict):
        """Função utilitária isolada para reconstruir um clipe visual a partir do estado anterior."""
        opac = self.settings.get("marker_opacity", 8)
        weight = self.settings.get("marker_thickness_weight", 100)
        
        new_clip = VidyaCropMarker("Vinho", opac, weight)
        new_clip.is_single_mode = True
        new_clip.is_child_clip = True
        
        new_clip.add_clip_callback = self._add_new_clip
        new_clip.remove_clip_callback = self._remove_clip
        new_clip.make_main_callback = self._make_clip_main  # <--- INSERIR
        new_clip.duplicate_callback = self._duplicate_clip
        new_clip.toggle_ratio_callback = self._toggle_keep_ratio
        new_clip.resize_percent_callback = self._resize_crop_percent
        new_clip.save_undo_state_callback = self._save_undo_snapshot
        new_clip.reset_all_clips_callback = self._reset_crops_and_maximize
        
        new_clip.set_geometry(geom)
        
        w, h = self.current_image_dims.get("Left", (0, 0))
        if hasattr(new_clip, 'set_image_bounds'): new_clip.set_image_bounds(w, h)
        if hasattr(new_clip, 'set_keep_ratio'): new_clip.set_keep_ratio(self.settings.get("keep_crop_ratio", False))

        self.scene_left.addItem(new_clip)
        self.active_clips.append(new_clip)

    def _check_and_finish_deskew(self):
        """Se estiver no modo de apontar deskew e tiver 4 pontos, finaliza a mira."""
        if getattr(self, 'is_picking_deskew', False):
            marker = getattr(self, f"deskew_marker_{self.deskew_position.lower()}", None)
            if marker and len(marker.get_geometry()) == 4:
                self._finish_manual_deskew()
                        
    def _reset_zoom(self):
        logger.info("Ajustando visualização ao tamanho da tela (Ctrl+0).")
        self.zoom_factor = 1.0
        self._scale_views()
        self._rebalance_splitter()

    def _open_manual(self):
        manual_path = os.path.expanduser("/opt/vidya-capture/docs/Vidya Capture - Manual.pdf")
        if os.path.exists(manual_path):
            logger.info("Abrindo manual do utilizador (F1).")
            url = QtCore.QUrl.fromLocalFile(manual_path)
            QtGui.QDesktopServices.openUrl(url)
        else:
            QtWidgets.QMessageBox.warning(self, "Manual não encontrado", f"O arquivo do manual não foi localizado:\n{manual_path}")
            
    def _on_replicate_changed(self, state):
        is_checked = (state == QtCore.Qt.Checked)
        self.settings["replicate_crop"] = is_checked
        if hasattr(self, 'marker_left') and hasattr(self.marker_left, 'set_replicate_state'):
            self.marker_left.set_replicate_state(is_checked)
        if hasattr(self, 'marker_right') and hasattr(self.marker_right, 'set_replicate_state'):
            self.marker_right.set_replicate_state(is_checked)
        save_settings(self.settings)

    def _sync_crops(self, source_pos: str):
        if not getattr(self, 'chk_replicate', None) or not self.chk_replicate.isChecked(): return
        target_pos = "Right" if source_pos == "Left" else "Left"
        self._copy_crop_geometry(source_pos, target_pos, mirror=False)

    def _copy_crop_geometry(self, source_pos: str, target_pos: str, mirror: bool = False):
        if getattr(self, '_is_syncing', False) or self.is_single_mode: return
        self._is_syncing = True
        try:
            source_marker = self.marker_left if source_pos == "Left" else self.marker_right
            target_marker = self.marker_left if target_pos == "Left" else self.marker_right
            geom = source_marker.get_geometry()
            
            if mirror:
                target_w, _ = self.current_image_dims.get(target_pos, (0, 0))
                if target_w == 0:
                    scene = self.scene_left if target_pos == "Left" else self.scene_right
                    for item in scene.items():
                        if isinstance(item, QtWidgets.QGraphicsPixmapItem):
                            target_w = item.pixmap().width()
                            break
                if target_w > 0: geom["x"] = target_w - (geom["x"] + geom["width"])
            target_marker.set_geometry(geom)
        finally:
            self._is_syncing = False

    def _maximize_crop(self, target: str):
        if target in ("Left", "Both"):
            w, h = self.current_image_dims.get("Left", (0, 0))
            if w > 0 and h > 0: self.marker_left.set_geometry({"x": 0, "y": 0, "width": w, "height": h})
        if target in ("Right", "Both") and not self.is_single_mode:
            w, h = self.current_image_dims.get("Right", (0, 0))
            if w > 0 and h > 0: self.marker_right.set_geometry({"x": 0, "y": 0, "width": w, "height": h})
        self._save_review_crop_if_needed()
        
    def _resize_crop_percent(self, target_marker, percent: float):
        self._save_undo_snapshot(target_marker) # TIRA A FOTO ANTES DE REDIMENSIONAR
        side = "Right" if target_marker == getattr(self, 'marker_right', None) else "Left"
        w, h = self.current_image_dims.get(side, (0, 0))
        
        if w > 0 and h > 0:
            new_w, new_h = w * percent, h * percent
            offset_x, offset_y = (w - new_w) / 2.0, (h - new_h) / 2.0
            target_marker.set_geometry({"x": offset_x, "y": offset_y, "width": new_w, "height": new_h})

        self._save_review_crop_if_needed()

    def _reset_crops_and_maximize(self, target_marker):
        """Remove todos os quadros extras, limpa o alinhamento e expande o principal para 100%."""
        # 1. Tira uma foto do estado atual para permitir o Ctrl+Z (Undo)
        self._save_undo_snapshot(target_marker)
        
        pos = "Right" if target_marker == getattr(self, 'marker_right', None) else "Left"
        
        # 2. Remove os pontos de alinhamento manual (Deskew) da cena gráfica
        d_marker = getattr(self, f"deskew_marker_{pos.lower()}", None)
        if d_marker:
            d_marker.clear()
            
        # 3. Reseta a flag para que o texto do menu de contexto volte para "Iniciar alinhamento manual..."
        target_marker.is_deskew_active = False
        target_marker.has_deskew_points = False # <--- ADICIONE ESTA LINHA
        
        # 4. Varre a interface removendo todos os quadros filhos visuais (Clips)
        if pos == "Left" or getattr(self, 'is_single_mode', False):
            self._clear_clips()
            
        # 5. Restaura as dimensões originais nativas do quadro principal
        w, h = self.current_image_dims.get(pos, (0, 0))
        if w > 0 and h > 0:
            main_m = self.marker_left if pos == "Left" else self.marker_right
            main_m.set_geometry({"x": 0, "y": 0, "width": w, "height": h})
            
        # 6. Grava o novo estado. O _save_review_crop_if_needed detectará a ausência de pontos 
        # e removerá automaticamente a chave "manual_deskew" do arquivo JSON.
        self._save_review_crop_if_needed()
        logger.info(f"Interface, recortes múltiplos e alinhamento manual limpos com sucesso em {pos}.")

    def _cancel_manual_deskew(self, position: str):
        """Aborta a mira do alinhamento sem salvar nada e retorna a interface ao normal."""
        self.is_picking_deskew = False
        active_view = self.view_left if position == "Left" else self.view_right
        active_view.viewport().setCursor(QtCore.Qt.ArrowCursor)
        
        target_marker = self.marker_left if position == "Left" else self.marker_right
        target_marker.setAcceptHoverEvents(True)
        target_marker.setCursor(QtCore.Qt.ArrowCursor)
        target_marker.is_deskew_active = False # Devolve o menu ao estado original
        
        marker = getattr(self, f"deskew_marker_{position.lower()}", None)
        if marker:
            marker.clear()
            # Resgate: Tenta recarregar do JSON caso houvesse um alinhamento anterior válido
            json_path = getattr(self, f"review_{position.lower()}_path", None)
            if json_path:
                json_file = json_path.rsplit('.', 1)[0] + ".json"
                try:
                    import os, json
                    if os.path.exists(json_file):
                        with open(json_file, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                            if "manual_deskew" in data:
                                marker.set_geometry(data["manual_deskew"])
                except Exception:
                    pass
            
        logger.info(f"Alinhamento manual cancelado pelo utilizador na câmara {position}. Nenhuma alteração salva.")
    
    def _start_manual_deskew(self, position: str):
        """Ativa o modo de mira e prepara o marcador para receber os 4 cliques."""
        self.is_picking_deskew = True
        self.deskew_position = position
        
        active_view = self.view_left if position == "Left" else self.view_right
        active_view.viewport().setCursor(QtCore.Qt.CrossCursor)
        
        # ---> NOVA INSERÇÃO: Impede o marcador de Crop de roubar o cursor
        target_marker = self.marker_left if position == "Left" else self.marker_right
        target_marker.setAcceptHoverEvents(False)
        target_marker.setCursor(QtCore.Qt.CrossCursor)
        # ---> FIM DA INSERÇÃO
        target_marker.is_deskew_active = True # <--- NOVO: Sinaliza ao menu que a mira começou
        
        scene = self.scene_left if position == "Left" else self.scene_right
        marker_attr = f"deskew_marker_{position.lower()}"
        marker = getattr(self, marker_attr, None)
        
        if not marker:
            from gui.vidya_manual_deskew import VidyaManualDeskewMarker
            marker = VidyaManualDeskewMarker(opacity=self.settings.get("marker_opacity", 8))
            setattr(self, marker_attr, marker)
            scene.addItem(marker)
            marker.geometry_changed.connect(self._save_review_crop_if_needed)
            
        pts = marker.get_geometry()
        if len(pts) != 4:
            marker.clear()
            
        logger.info(f"Modo de marcação de Deskew Manual iniciado para a câmara {position}.")

    def _finish_manual_deskew(self):
        """Finaliza a captura de pontos e força o Crop principal para 100%."""
        self.is_picking_deskew = False
        active_view = self.view_left if self.deskew_position == "Left" else self.view_right
        active_view.viewport().setCursor(QtCore.Qt.ArrowCursor)
        
        target_marker = self.marker_left if self.deskew_position == "Left" else self.marker_right
        target_marker.setAcceptHoverEvents(True)
        target_marker.setCursor(QtCore.Qt.ArrowCursor)
        target_marker.is_deskew_active = False # <--- NOVO: Mira finalizada, retorna o menu ao estado normal
        target_marker.has_deskew_points = True # <--- ADICIONE ESTA LINHA: Avisa que a imagem agora possui pontos
        
        # ---> INÍCIO DA CORREÇÃO: Expandir para 100% sem invocar o reset destrutivo
        self._save_undo_snapshot(target_marker)
        
        # 1. Limpa os recortes filhos extras, pois o Deskew reinicia a lógica da imagem
        if self.deskew_position == "Left" or getattr(self, 'is_single_mode', False):
            self._clear_clips()
            
        # 2. Restaura as dimensões originais nativas do quadro principal
        w, h = self.current_image_dims.get(self.deskew_position, (0, 0))
        if w > 0 and h > 0:
            target_marker.set_geometry({"x": 0, "y": 0, "width": w, "height": h})
            
        self._save_review_crop_if_needed()
        # ---> FIM DA CORREÇÃO
        
        logger.info(f"Deskew manual concluído com sucesso para a câmara {self.deskew_position}.")

    def _remove_manual_deskew(self, target_marker):
        """Remove os pontos de deskew existentes e salva a remoção no JSON."""
        # 1. Tira foto do estado atual para permitir Ctrl+Z (Undo)
        self._save_undo_snapshot(target_marker)
        
        pos = "Right" if target_marker == getattr(self, 'marker_right', None) else "Left"
        d_marker = getattr(self, f"deskew_marker_{pos.lower()}", None)
        
        # 2. Limpa os pontos da interface gráfica
        if d_marker:
            d_marker.clear()
            
        # 3. Informa ao marcador que os pontos foram removidos (para resetar o menu de contexto)
        target_marker.has_deskew_points = False
        
        # 4. Força o salvamento para atualizar o JSON instantaneamente
        self._save_review_crop_if_needed()
        logger.info(f"Pontos de alinhamento manual removidos permanentemente na câmara {pos}.")
            
    def update_status_bar(self):
        import os
        working_dir = self.settings.get("working_dir", "projeto_padrao")
        # project_name = os.path.basename(working_dir) if working_dir else "Nenhum"
        project_name = working_dir if working_dir else "Nenhum"
        total_thumbnails = self.thumbnail_panel.count()
        
        self.statusBar().showMessage(f"F1: Ajuda | F4: Info | Projeto Ativo: {project_name} | Imgens carregadas: {total_thumbnails}")   

    def _on_keep_ratio_changed(self, state):
        is_checked = (state == QtCore.Qt.Checked)
        self.settings["keep_crop_ratio"] = is_checked
        save_settings(self.settings)
        if hasattr(self.marker_left, 'set_keep_ratio'): self.marker_left.set_keep_ratio(is_checked)
        if hasattr(self.marker_right, 'set_keep_ratio'): self.marker_right.set_keep_ratio(is_checked)

    def _toggle_theme(self):
        """Inverte o estado atual do tema e salva nas preferências."""
        is_dark = self.settings.get("dark_mode", False)
        self.settings["dark_mode"] = not is_dark
        save_settings(self.settings) # Preserva a escolha para a próxima inicialização
        self._apply_theme()

    def _apply_theme(self):
        """Aplica o StyleSheet na Janela Principal com base nas configurações."""
        is_dark = self.settings.get("dark_mode", False)
        
        # -> NOVO: Atualiza a letra do botão de acordo com o tema
        if hasattr(self, 'btn_theme'):
            self.btn_theme.setText(" E" if is_dark else " C")
        
        if is_dark:
            self.setStyleSheet(VidyaThemeManager.get_dark_theme())
            # Força as labels de status a usarem cores claras para contraste
            self.dynamic_label_color = "#e0e0e0" 
        else:
            self.setStyleSheet(VidyaThemeManager.get_light_theme())
            # Restaura a cor escura nativa para as labels de status
            self.dynamic_label_color = "#2c3e50"
            
        # Reavalia a interface para aplicar as novas cores nas labels dinâmicas
        self._update_adjust_button_text()
        
        # Se estiver no modo live (fora de revisão), atualiza as labels das câmeras
        if not self.is_reviewing:
            label_style = f"font-size: 11pt; font-weight: bold; color: {self.dynamic_label_color}; padding-bottom: 2px;"
            self.lbl_info_left.setStyleSheet(label_style)
            if not getattr(self, 'is_single_mode', False):
                self.lbl_info_right.setStyleSheet(label_style)
                
        # ---> ADICIONAR (ÚLTIMA LINHA): Atualiza em tempo real as etiquetas das miniaturas
        if hasattr(self, 'thumbnail_panel'):
            self.thumbnail_panel.set_last_edited_highlight(self.thumbnail_panel._last_edited_paths)
                
    def _toggle_keep_ratio(self):
        self.chk_keep_ratio.setChecked(not self.chk_keep_ratio.isChecked())

    def _toggle_replicate(self):
        if not self.is_single_mode:
            self.chk_replicate.setChecked(not self.chk_replicate.isChecked())
        
    def eventFilter(self, source, event):
        if hasattr(self, 'splitter') and self.splitter.count() > 1 and source is self.splitter.handle(1):
            if event.type() == QtCore.QEvent.MouseButtonPress and event.button() == QtCore.Qt.LeftButton:
                self._drag_splitter_active = True
                self._drag_last_x = event.globalX()
            elif event.type() == QtCore.QEvent.MouseMove and getattr(self, '_drag_splitter_active', False):
                current_x = event.globalX()
                delta_x = current_x - getattr(self, '_drag_last_x', current_x)
                self._drag_last_x = current_x
                
                if delta_x > 0:
                    right_widget = self.splitter.widget(1)
                    if right_widget.width() <= right_widget.minimumWidth() + 2:
                        self.resize(self.width() + delta_x, self.height())
                        current_sizes = self.splitter.sizes()
                        self.splitter.setSizes([current_sizes[0] + delta_x, current_sizes[1]])
                        return True 
            elif event.type() == QtCore.QEvent.MouseButtonRelease:
                self._drag_splitter_active = False
                
        # ---> INÍCIO DA INSERÇÃO: INTERCEPTADOR DE CLIQUES DO DESKEW MANUAL
        if getattr(self, 'is_picking_deskew', False):
            active_view = self.view_left if self.deskew_position == "Left" else self.view_right
            if source is active_view.viewport():
                if event.type() == QtCore.QEvent.MouseButtonPress and event.button() == QtCore.Qt.LeftButton:
                    scene_pos = active_view.mapToScene(event.pos())
                    marker = getattr(self, f"deskew_marker_{self.deskew_position.lower()}")
                    finished = marker.add_point(scene_pos)
                    if finished:
                        self._finish_manual_deskew()
                    return True # Engole o clique para não arrastar os marcadores normais de crop
        # ---> FIM DA INSERÇÃO

        if hasattr(self, 'view_left') and (source is self.view_left.viewport() or source is self.view_right.viewport()):
            if event.type() == QtCore.QEvent.Wheel:
                if event.modifiers() == QtCore.Qt.ControlModifier:
                    
                    # 1. Define o fator de escala (aumentar ou diminuir)
                    factor = 1.1 if event.angleDelta().y() > 0 else 0.9
                    self.zoom_factor *= factor # Mantém a variável global sincronizada
                    
                    # 2. Descobre em qual das views o ponteiro do mouse está
                    active_view = self.view_left if source is self.view_left.viewport() else self.view_right
                    other_view = self.view_right if active_view == self.view_left else self.view_left
                    
                    # 3. Aplica o zoom na view ativa centralizando exatamente no ponteiro do mouse
                    active_view.setTransformationAnchor(QtWidgets.QGraphicsView.AnchorUnderMouse)
                    active_view.scale(factor, factor)
                    
                    # 4. Aplica o zoom na view espelho (para que cresçam juntas), 
                    # mas centraliza no meio, já que o mouse não está sobre ela
                    other_view.setTransformationAnchor(QtWidgets.QGraphicsView.AnchorViewCenter)
                    other_view.scale(factor, factor)
                    
                    self._rebalance_splitter()
                    return True
                    
            elif event.type() == QtCore.QEvent.MouseButtonPress:
                if event.button() == QtCore.Qt.MiddleButton:
                    self._reset_zoom()
                    return True 
                return False 
                
        return super().eventFilter(source, event)

    def show_review_pair(self, left_path, right_path=None, force_reload=False):
        # --- PROTEÇÃO CONTRA DRIFT: Impede recarregar a imagem se ela já está aberta na tela ---
        if not force_reload and self.is_reviewing and getattr(self, 'review_left_path', None) == left_path and getattr(self, 'review_right_path', None) == right_path:
            return
            
        logger.info("Entrando no Modo de Revisão / Inserção.")
        if hasattr(self, 'undo_manager'): self.undo_manager.clear() # <--- LIMPA UNDO
        
        # Se for um recarregamento forçado por alteração externa (Auto Crop), 
        # não salvamos o estado da tela para não destruir os novos dados do HD.
        if not force_reload:
            self._save_review_crop_if_needed()
            
        self._clear_clips()
        
        # ---> INÍCIO DA PROTEÇÃO CONTRA DRIFT: Inicializa a memória
        if not hasattr(self, 'clean_state_geoms'): self.clean_state_geoms = {}
        if not hasattr(self, 'clean_deskew_geoms'): self.clean_deskew_geoms = {}
        # ---> FIM
        
        if not self.is_reviewing:
            self.live_marker_left_geom = self.marker_left.get_geometry()
            self.live_marker_right_geom = self.marker_right.get_geometry()
            self.is_reviewing = True
            self.current_review_action_index = 0
            
        self.lbl_info_left.setStyleSheet("font-size: 11pt; font-weight: bold; color: #c0392b; padding-bottom: 2px;")
        
        if self.is_single_mode:
            self.lbl_info_left.setText("MODO DE EDIÇÃO (ESC para voltar)")
        else:
            self.lbl_info_left.setText("MODO DE EDIÇÃO (ESC para voltar)")
            self.lbl_info_right.setStyleSheet("font-size: 11pt; font-weight: bold; color: #c0392b; padding-bottom: 2px;")
            self.lbl_info_right.setText("MODO DE EDIÇÃO (ESC para voltar)")
        
        def load_and_show(path, position, marker):
            if path and os.path.exists(path):
                with open(path, 'rb') as f:
                    self.update_frame(position, f.read(), is_live=False)
                json_path = path.rsplit('.', 1)[0] + ".json"
                if os.path.exists(json_path):
                    try:
                        with open(json_path, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                            crop = data.get("crop_geometry")
                            if crop: marker.set_geometry(crop)
                            
                            # ---> INÍCIO DA INSERÇÃO: CARREGAMENTO DE PONTOS DE DESKEW SALVOS
                            manual_pts = data.get("manual_deskew")
                            scene = self.scene_left if position == "Left" else self.scene_right
                            d_marker_attr = f"deskew_marker_{position.lower()}"
                            d_marker = getattr(self, d_marker_attr, None)
                            
                            if manual_pts:
                                if not d_marker:
                                    from gui.vidya_manual_deskew import VidyaManualDeskewMarker
                                    d_marker = VidyaManualDeskewMarker(opacity=self.settings.get("marker_opacity", 8))
                                    setattr(self, d_marker_attr, d_marker)
                                    scene.addItem(d_marker)
                                    # Garante que o sinal só é conectado ao criar o objeto
                                    d_marker.geometry_changed.connect(self._save_review_crop_if_needed)
                                d_marker.set_geometry(manual_pts)
                                marker.has_deskew_points = True # <--- ADICIONE ESTA LINHA
                            else:
                                if d_marker:
                                    d_marker.clear()
                                marker.has_deskew_points = False # <--- ADICIONE ESTA LINHA
                            # ---> FIM DA INSERÇÃO
                    except: pass
            else:
                scene = self.scene_left if position == "Left" else self.scene_right
                for item in scene.items():
                    if item != marker: scene.removeItem(item)
                    
            # ---> INÍCIO DA PROTEÇÃO: Salva uma cópia exata de como a imagem chegou do HD
            self.clean_state_geoms[position] = marker.get_geometry()
            d_marker_final = getattr(self, f"deskew_marker_{position.lower()}", None)
            self.clean_deskew_geoms[position] = d_marker_final.get_geometry() if d_marker_final else []
            # ---> FIM DA PROTEÇÃO

        load_and_show(left_path, "Left", self.marker_left)
        
        if self.is_single_mode and left_path and os.path.exists(left_path):
            import glob
            base_dir = os.path.dirname(left_path)
            name_no_ext = os.path.basename(left_path).rsplit('.', 1)[0]
            clip_files = sorted(glob.glob(os.path.join(base_dir, f"{name_no_ext}_clip_*.json")))
            
            opac = self.settings.get("marker_opacity", 8)
            weight = self.settings.get("marker_thickness_weight", 100)
            is_ratio = self.settings.get("keep_crop_ratio", False)
            w, h = self.current_image_dims.get("Left", (0, 0))

            for cf in clip_files:
                try:
                    with open(cf, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        geom = data.get("crop_geometry")
                        if geom:
                            new_clip = VidyaCropMarker("Vinho", opac, weight)
                            new_clip.is_single_mode = True
                            new_clip.is_child_clip = True
                            new_clip.add_clip_callback = self._add_new_clip
                            new_clip.remove_clip_callback = self._remove_clip
                            new_clip.make_main_callback = self._make_clip_main  # <--- INSERIR
                            
                            new_clip.duplicate_callback = self._duplicate_clip
                            new_clip.toggle_ratio_callback = self._toggle_keep_ratio
                            new_clip.resize_percent_callback = self._resize_crop_percent
                            new_clip.save_undo_state_callback = self._save_undo_snapshot # <--- ADICIONE ESTA LINHA AOS TRÊS LOCAIS
                            new_clip.reset_all_clips_callback = self._reset_crops_and_maximize
                            
                            new_clip.set_geometry(geom)
                            if hasattr(new_clip, 'set_image_bounds'): new_clip.set_image_bounds(w, h)
                            if hasattr(new_clip, 'set_keep_ratio'): new_clip.set_keep_ratio(is_ratio)
                            self.scene_left.addItem(new_clip)
                            self.active_clips.append(new_clip)
                except Exception as e:
                    logger.error(f"Erro carregando clip {cf}: {e}")
        
        if not self.is_single_mode:
            load_and_show(right_path, "Right", self.marker_right)
        
        self.review_left_path = left_path
        self.review_right_path = right_path
        self.btn_capture.setEnabled(True)
        
        self._update_review_button_style()
        
        if self.is_single_mode:
            self.btn_remove_last.setText(" Remover a imagem")
        else:
            self.btn_remove_last.setText(" Remover o par")
            
        self.btn_remove_last.setStyleSheet("color: #c0392b; font-weight: bold;")
        self._update_adjust_button_text()
        
        # Nível 1: Força a "lousa limpa" ao entrar no modo de edição
        self._reset_zoom()

    # ---> INÍCIO DA ATUALIZAÇÃO VISUAL: COR DO BOTÃO REINICIAR <---
    def _update_adjust_button_text(self):
        if self.is_reviewing:
            self.btn_adjust.setText(" Encerra")
            self.btn_adjust.setIcon(QtGui.QIcon.fromTheme("window-close"))
            self.btn_adjust.setStyleSheet("background-color: #f5b041; color: black; font-weight: bold;")
            self.thumbnail_panel.setToolTip("<b style='color: #c0392b;'>Aviso:</b> Para sair da edição, tecle Esc")
        else:
            self.btn_adjust.setText(" Reiniciar")
            self.btn_adjust.setIcon(QtGui.QIcon.fromTheme("zoom-fit-best"))
            self.btn_adjust.setStyleSheet("") # Devolve a cor original do sistema
            self.thumbnail_panel.setToolTip("<b style='color: #2980b9;'>Dica:</b> Clique nas miniaturas para editar.")
    # ---> FIM DA ATUALIZAÇÃO <---
            
    def _save_review_crop_if_needed(self):
        if not hasattr(self, 'review_left_path'):
            return
            
        if self.is_reviewing:
            paths = [(self.review_left_path, self.marker_left)]
            
            if not self.is_single_mode:
                paths.append((self.review_right_path, self.marker_right))
                
            for path, marker in paths:
                if path and os.path.exists(path):
                    
                    # ---> INÍCIO DA TRAVA DE TOLERÂNCIA GEOMÉTRICA <---
                    pos_str = "Left" if marker == self.marker_left else "Right"
                    current_geom = marker.get_geometry()
                    clean_geom = getattr(self, 'clean_state_geoms', {}).get(pos_str)
                    
                    d_marker = getattr(self, f"deskew_marker_{pos_str.lower()}", None)
                    current_deskew = d_marker.get_geometry() if d_marker else []
                    clean_deskew = getattr(self, 'clean_deskew_geoms', {}).get(pos_str, [])
                    
                    def _has_changed(g1, g2):
                        if not g1 or not g2: return True
                        try:
                            # Tolerância de 0.5 pixel para ignorar drift de arredondamento do QGraphicsView
                            for k in ["x", "y", "width", "height"]:
                                if abs(float(g1.get(k, 0)) - float(g2.get(k, 0))) > 0.5:
                                    return True
                            return False
                        except:
                            return g1 != g2

                    crop_changed = _has_changed(clean_geom, current_geom)
                    deskew_changed = (current_deskew != clean_deskew)
                    
                    # Se você só visualizou e não arrastou as bordas, aborta o salvamento e poupa o HD!
                    if not crop_changed and not deskew_changed:
                        continue 
                    # ---> FIM DA TRAVA <---
                    
                    json_path = path.rsplit('.', 1)[0] + ".json"
                    try:
                        with open(json_path, 'r+', encoding='utf-8') as f:
                            data = json.load(f)
                            data["crop_geometry"] = current_geom
                            
                            if current_deskew:
                                data["manual_deskew"] = current_deskew
                            elif "manual_deskew" in data:
                                del data["manual_deskew"]
                            
                            f.seek(0)
                            json.dump(data, f, indent=4)
                            f.truncate()
                            
                            # Atualiza a memória "limpa" para a nova posição gravada
                            self.clean_state_geoms[pos_str] = current_geom
                            self.clean_deskew_geoms[pos_str] = current_deskew
                    except Exception as e:
                        logger.error(f"Erro ao salvar alteração de recorte no JSON {json_path}: {e}")
            
            if getattr(self, 'is_single_mode', False) and getattr(self, 'review_left_path', None):
                self._save_clips_to_disk(self.review_left_path)
                    
            logger.info("Recortes atualizados e salvos automaticamente nos metadados do projeto.")
                
    def _update_review_button_style(self):
        action = self.review_actions[self.current_review_action_index]
        self.btn_capture_mode.setText(f" Ação: {action}")
        
        if action in ["Substituir Par", "Substituir Imagem"]:
            self.btn_capture.setText(" PREPARAR SUBSTITUIÇÃO")
            self.btn_capture.setStyleSheet("background-color: #f39c12; color: black; font-weight: bold;")
        elif action == "Inserir Antes":
            self.btn_capture.setText(" PREPARAR INSERÇÃO (ANTES)")
            self.btn_capture.setStyleSheet("background-color: #3498db; color: white; font-weight: bold;")
        elif action == "Inserir Depois":
            self.btn_capture.setText(" PREPARAR INSERÇÃO (DEPOIS)")
            self.btn_capture.setStyleSheet("background-color: #9b59b6; color: white; font-weight: bold;")
        elif action == "Substituir Esquerda":
            self.btn_capture.setText(" PREPARAR SUBSTITUIÇÃO (ESQ)")
            self.btn_capture.setStyleSheet("background-color: #d35400; color: white; font-weight: bold;")
        elif action == "Substituir Direita":
            self.btn_capture.setText(" PREPARAR SUBSTITUIÇÃO (DIR)")
            self.btn_capture.setStyleSheet("background-color: #d35400; color: white; font-weight: bold;")

    def _update_confirm_button_style(self):
        action = self.pending_review_action
        self.btn_capture_mode.setText(f" Ação: {action}")
        
        if action in ["Substituir Par", "Substituir Imagem"]:
            self.btn_capture.setText(" CONFIRMAR SUBSTITUIÇÃO")
            self.btn_capture.setStyleSheet("background-color: #c0392b; color: white; font-weight: bold;")
        elif action == "Inserir Antes":
            self.btn_capture.setText(" CONFIRMAR INSERÇÃO (ANTES)")
            self.btn_capture.setStyleSheet("background-color: #2980b9; color: white; font-weight: bold;")
        elif action == "Inserir Depois":
            self.btn_capture.setText(" CONFIRMAR INSERÇÃO (DEPOIS)")
            self.btn_capture.setStyleSheet("background-color: #8e44ad; color: white; font-weight: bold;")
        elif action == "Substituir Esquerda":
            self.btn_capture.setText(" CONFIRMAR SUBSTITUIÇÃO (ESQ)")
            self.btn_capture.setStyleSheet("background-color: #c0392b; color: white; font-weight: bold;")
        elif action == "Substituir Direita":
            self.btn_capture.setText(" CONFIRMAR SUBSTITUIÇÃO (DIR)")
            self.btn_capture.setStyleSheet("background-color: #c0392b; color: white; font-weight: bold;")

    def _trigger_review_action(self, action_name: str):
        if not self.is_reviewing: return
        try:
            idx = self.review_actions.index(action_name)
            self.current_review_action_index = idx
            self._update_review_button_style()
            self._on_capture_clicked()
        except ValueError:
            pass

    def _on_cycle_capture_mode(self):
        self._save_review_crop_if_needed()
        
        if self.is_reviewing:
            self.current_review_action_index = (self.current_review_action_index + 1) % len(self.review_actions)
            self._update_review_button_style()
        elif self.pending_review_action:
            self.current_review_action_index = (self.current_review_action_index + 1) % len(self.review_actions)
            self.pending_review_action = self.review_actions[self.current_review_action_index]
            self._update_confirm_button_style()
        else:
            self.current_mode_index = (self.current_mode_index + 1) % len(self.capture_modes)
            mode = self.capture_modes[self.current_mode_index]
            self.btn_capture_mode.setText(f" Modo: {mode}")
            self._update_capture_button_style()

    def _exit_review_mode(self, reset_ui=True):
        if not self.is_reviewing: return
        
        # ---> INÍCIO DA INSERÇÃO: Guarda os caminhos ANTES de sair do modo <---
        left_path = getattr(self, 'review_left_path', None)
        right_path = getattr(self, 'review_right_path', None)
        # ---> FIM DA INSERÇÃO <---
        
        self.is_reviewing = False
        self._update_adjust_button_text() 
        
        # Garante que as flags do Deskew não fiquem presas com texto errado ao sair da edição
        self.is_picking_deskew = False
        if hasattr(self, 'marker_left'): self.marker_left.is_deskew_active = False
        if hasattr(self, 'marker_right'): self.marker_right.is_deskew_active = False
        
        # ---> INÍCIO DA CORREÇÃO: Limpa pontos de Deskew ao voltar para a câmera ao vivo
        if getattr(self, 'deskew_marker_left', None):
            self.deskew_marker_left.clear()
        if getattr(self, 'deskew_marker_right', None):
            self.deskew_marker_right.clear()
        # ---> FIM DA CORREÇÃO
               
        label_style = f"font-size: 11pt; font-weight: bold; color: {getattr(self, 'dynamic_label_color', '#2c3e50')}; padding-bottom: 2px;"
        self.lbl_info_left.setStyleSheet(label_style)
        self.lbl_info_right.setStyleSheet(label_style)
        self.lbl_info_left.setText(f"{self.device_name_left}  (Retomando vídeo...)")
        self.lbl_info_right.setText(f"{self.device_name_right}  (Retomando vídeo...)")
        
        if hasattr(self, 'live_marker_left_geom'): self.marker_left.set_geometry(self.live_marker_left_geom)
        if hasattr(self, 'live_marker_right_geom'): self.marker_right.set_geometry(self.live_marker_right_geom)
        
        if self.is_single_mode:
            self.btn_remove_last.setText(" Remover última")
        else:
            self.btn_remove_last.setText(" Remover duas últimas")
            
        self.btn_remove_last.setStyleSheet("")
            
        if reset_ui:
            self.pending_review_action = None
            self.pending_replace_paths = {}
            self.btn_capture_mode.setText(f" Modo: {self.capture_modes[self.current_mode_index]}")
            self._reset_capture_button()
            self._update_capture_button_style()
        
        # ---> INÍCIO DA INSERÇÃO: Aplica a marcação amarela nas miniaturas recém editadas <---
        if left_path or right_path:
            self.thumbnail_panel.set_last_edited_highlight([left_path, right_path])
        # ---> FIM DA INSERÇÃO <---

        # Nível 1: Força a "lousa limpa" ao retornar para as câmeras ao vivo
        self._reset_zoom()

    def _on_capture_clicked(self):
        if getattr(self, 'is_picking_deskew', False):
            self._check_and_finish_deskew()
            return
            
        if self.is_reviewing:
            action = self.review_actions[self.current_review_action_index]
            left_path = getattr(self, 'review_left_path', None)
            right_path = getattr(self, 'review_right_path', None)
            
            if action == "Substituir Esquerda" or action == "Substituir Imagem":
                right_path = None
            elif action == "Substituir Direita":
                left_path = None

            self.pending_replace_paths = {"Left": left_path, "Right": right_path}
            self.pending_review_action = action
            self._exit_review_mode(reset_ui=False)
            self._update_confirm_button_style()
            return

        mode = self.capture_modes[self.current_mode_index]
        replacement_paths = {}

        if hasattr(self, 'pending_review_action') and self.pending_review_action:
            mode = self.pending_review_action
            replacement_paths = self.pending_replace_paths
            self.pending_replace_paths = {}
            self.pending_review_action = None
            self._update_capture_button_style()
            self.btn_capture_mode.setText(f" Modo: {self.capture_modes[self.current_mode_index]}")
        elif mode == "Substituir":
            if self.is_single_mode:
                if hasattr(self.thumbnail_panel, 'remove_last_single'):
                    replacement_paths = self.thumbnail_panel.remove_last_single()
                else:
                    replacement_paths = self.thumbnail_panel.remove_last_two() 
            else:
                replacement_paths = self.thumbnail_panel.remove_last_two()

        self.btn_capture.setEnabled(False)
        self.btn_capture.setText(" PROCESSANDO...")
        
        # Monta os dados de recorte
        current_geometries = {
            "Left": self.marker_left.get_geometry(),
            "Right": self.marker_right.get_geometry()
        }
        
        # INJEÇÃO DO DESKEW: Verifica se existem pontos marcados nas câmeras
        d_marker_l = getattr(self, 'deskew_marker_left', None)
        d_marker_r = getattr(self, 'deskew_marker_right', None)
        
        if d_marker_l and len(d_marker_l.get_geometry()) == 4:
            current_geometries["Left_Deskew"] = d_marker_l.get_geometry()
            
        if not self.is_single_mode and d_marker_r and len(d_marker_r.get_geometry()) == 4:
            current_geometries["Right_Deskew"] = d_marker_r.get_geometry()

        self.capture_requested.emit(mode, replacement_paths, current_geometries)
        QtCore.QTimer.singleShot(1500, self._reset_capture_button)
        
    def _delete_associated_jsons(self, image_path):
        """Limpa o JSON principal e quaisquer clipes filhos associados à imagem."""
        if not image_path: return
        import glob
        import os
        
        base_dir = os.path.dirname(image_path)
        name_no_ext = os.path.basename(image_path).rsplit('.', 1)[0]
        
        # 1. Remove o JSON principal (O arquivo órfão)
        main_json = os.path.join(base_dir, f"{name_no_ext}.json")
        if os.path.exists(main_json):
            try: os.remove(main_json)
            except: pass
            
        # 2. Remove os JSONs de recortes múltiplos (Clipes)
        for cf in glob.glob(os.path.join(base_dir, f"{name_no_ext}_clip_*.json")):
            try: os.remove(cf)
            except: pass

    def _on_remove_last_clicked(self):
        self.thumbnail_panel.clear_last_edited_highlight() # <--- NOVO
        # 1. Verifica se há miniaturas para deletar (evita exibir o pop-up à toa se a lista estiver vazia)
        if not self.is_reviewing and self.thumbnail_panel.count() == 0:
            return

        # 2. Define a mensagem apropriada de acordo com o estado atual da interface
        if self.is_reviewing:
            msg = "Tem certeza de que deseja excluir permanentemente esta imagem em edição e seus metadados?" if self.is_single_mode else "Tem certeza de que deseja excluir permanentemente este par de imagens em edição e seus metadados?"
        else:
            msg = "Tem certeza de que deseja excluir permanentemente a ÚLTIMA captura realizada e seus metadados?" if self.is_single_mode else "Tem certeza de que deseja excluir permanentemente o ÚLTIMO par capturado e seus metadados?"

        # 3. Dispara a janela de confirmação
        reply = QtWidgets.QMessageBox.question(
            self, 
            "Confirmação de Exclusão", 
            msg,
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No, 
            QtWidgets.QMessageBox.No
        )

        # 4. Se o usuário clicar em "Não", interrompe a função imediatamente
        if reply != QtWidgets.QMessageBox.Yes:
            return

        # 5. Segue com a lógica de exclusão física e de interface
        if self.is_reviewing:
            left_path = getattr(self, 'review_left_path', None)
            right_path = getattr(self, 'review_right_path', None)
            
            # ---> CORREÇÃO: Limpeza profunda dos metadados antes de remover a imagem <---
            self._delete_associated_jsons(left_path)
            self._delete_associated_jsons(right_path)
            
            if self.is_single_mode and hasattr(self.thumbnail_panel, 'remove_specific_single'):
                self.thumbnail_panel.remove_specific_single(left_path)
            else:
                self.thumbnail_panel.remove_specific_pair(left_path, right_path)
            
            self._exit_review_mode()
            self.update_status_bar()
            self._restore_previous_frames()
        else:
            # ---> CORREÇÃO: Resgata os caminhos das imagens ANTES de as remover do painel <---
            paths_to_clean = []
            c = self.thumbnail_panel.count()
            if self.is_single_mode:
                if c > 0:
                    item = self.thumbnail_panel.item(c - 1)
                    if item: paths_to_clean.append(item.data(QtCore.Qt.UserRole))
            else:
                if c > 0:
                    item1 = self.thumbnail_panel.item(c - 1)
                    if item1: paths_to_clean.append(item1.data(QtCore.Qt.UserRole))
                if c > 1:
                    item2 = self.thumbnail_panel.item(c - 2)
                    if item2: paths_to_clean.append(item2.data(QtCore.Qt.UserRole))
                    
            # Aciona a varredura para apagar os metadados
            for p in paths_to_clean:
                self._delete_associated_jsons(p)
        
            if self.is_single_mode and hasattr(self.thumbnail_panel, 'remove_last_single'):
                self.thumbnail_panel.remove_last_single()
            else:
                self.thumbnail_panel.remove_last_two()
                
            self.update_status_bar()
            self._restore_previous_frames()

    def _on_context_menu_delete(self, path):
        self.thumbnail_panel.clear_last_edited_highlight() # <--- NOVO
        
        """Intercepta a exclusão de um item específico acionado via Clique Direito."""
        if not path or not os.path.exists(path): return
        
        paths_to_delete = []
        if self.is_single_mode:
            msg = "Tem certeza de que deseja excluir permanentemente esta imagem e todos os seus recortes associados?"
            paths_to_delete.append(path)
        else:
            msg = "Tem certeza de que deseja excluir permanentemente ESTE PAR de imagens e seus metadados?"
            paths_to_delete.append(path)
            
            # Tenta espelhar a string para achar o caminho da página oposta do par
            filename = os.path.basename(path)
            try:
                expected_other = filename.replace("Left", "Right") if "Left" in filename else filename.replace("Right", "Left")
                other_path = os.path.join(os.path.dirname(path), expected_other)
                if os.path.exists(other_path):
                    paths_to_delete.append(other_path)
            except Exception:
                pass

        reply = QtWidgets.QMessageBox.question(self, "Remover Arquivos Físicos", msg,
                                               QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No, QtWidgets.QMessageBox.No)
        
        if reply == QtWidgets.QMessageBox.Yes:
            # 1. Limpa os JSONs e Clipes residuais primeiro
            for p in paths_to_delete:
                self._delete_associated_jsons(p)
                
            # 2. Chama a remoção física das imagens + miniaturas via Painel
            if self.is_single_mode:
                self.thumbnail_panel.remove_specific_single(paths_to_delete[0])
            else:
                left_path = paths_to_delete[0] if "Left" in paths_to_delete[0] else (paths_to_delete[1] if len(paths_to_delete)>1 else "")
                right_path = paths_to_delete[1] if len(paths_to_delete)>1 and "Right" in paths_to_delete[1] else (paths_to_delete[0] if "Right" in paths_to_delete[0] else "")
                self.thumbnail_panel.remove_specific_pair(left_path, right_path)

            # 3. Aborta o modo de edição caso a imagem deletada estivesse aberta no visor
            if self.is_reviewing:
                if getattr(self, 'review_left_path', None) in paths_to_delete or getattr(self, 'review_right_path', None) in paths_to_delete:
                    self._exit_review_mode()

            # 4. Atualiza GUI
            self.update_status_bar()
            self._restore_previous_frames()
                    
    def _on_adjust_panels_clicked(self):
        self.thumbnail_panel.clear_last_edited_highlight() # <--- NOVO
        
        # ---> NOVO: Salva o estado atual do splitter e da janela ANTES de reiniciar
        self.save_project_workspace()
        
        # ---> INÍCIO DA INSERÇÃO: INTERRUPÇÃO DE DESKEW INCOMPLETO (DURANTE A MIRA)
        if getattr(self, 'is_picking_deskew', False):
            marker = getattr(self, f"deskew_marker_{self.deskew_position.lower()}", None)
            if marker:
                marker.clear()
            self.is_picking_deskew = False
            active_view = self.view_left if self.deskew_position == "Left" else self.view_right
            active_view.viewport().setCursor(QtCore.Qt.ArrowCursor)
            
            # Acorda o marcador se o usuário cancelar a mira no meio
            target_marker = self.marker_left if self.deskew_position == "Left" else self.marker_right
            target_marker.setAcceptHoverEvents(True)
            target_marker.setCursor(QtCore.Qt.ArrowCursor)
            target_marker.is_deskew_active = False # <--- CORREÇÃO: Libera o menu para o estado original
            
            self._save_review_crop_if_needed()
            logger.info("Alinhamento manual cancelado pelo utilizador. Coordenadas limpas.")
            return
        # ---> FIM DA INSERÇÃO
        
        # Primeiro salvamos qualquer estado pendente e seguro
        self._save_review_crop_if_needed()
        
        # Agora sim, resetamos a interface visual, com a garantia que o disco está intacto
        if getattr(self, 'deskew_marker_left', None):
            self.deskew_marker_left.clear()
        if getattr(self, 'deskew_marker_right', None):
            self.deskew_marker_right.clear()
            
        self._exit_review_mode()
        self._exit_review_mode()
        self._clear_clips() 
        self.pending_review_action = None
        self.pending_replace_paths = {}
        self.current_mode_index = 0
        self.btn_capture_mode.setText(f" Modo: {self.capture_modes[0]}")
        self._reset_capture_button()
        self._update_capture_button_style()

        logger.info("Ajuste solicitado. Recalculando marcadores, limpando alinhamentos e abortando substituições.")
        self.zoom_factor = 1.0
        
        def get_img_size(scene):
            for item in scene.items():
                if isinstance(item, QtWidgets.QGraphicsPixmapItem):
                    return item.pixmap().width(), item.pixmap().height()
            return 0, 0

        w_left, h_left = get_img_size(self.scene_left)
        w_right, h_right = get_img_size(self.scene_right)

        if w_left > 0: self.marker_left.set_geometry({"x": 0, "y": 0, "width": w_left, "height": h_left})
        if w_right > 0: self.marker_right.set_geometry({"x": 0, "y": 0, "width": w_right, "height": h_right})

        self._scale_views()
        self.reload_requested.emit()

    def _scale_views(self):
        for view, scene in [(self.view_left, self.scene_left), (self.view_right, self.scene_right)]:
            
            # 1. Procura especificamente a imagem da câmera na cena
            img_rect = QtCore.QRectF()
            for item in scene.items():
                if isinstance(item, QtWidgets.QGraphicsPixmapItem):
                    img_rect = item.boundingRect()
                    break  # Encontrou a imagem base, interrompe a busca
            
            # 2. Se achou a imagem, centraliza usando estritamente o tamanho dela (mantendo a margem de 10%)
            if img_rect.isValid() and not img_rect.isEmpty():
                margin_w = img_rect.width() * 0.10
                margin_h = img_rect.height() * 0.10
                rect = img_rect.adjusted(-margin_w, -margin_h, margin_w, margin_h)
            else:
                # Fallback de segurança caso a cena esteja vazia
                rect = scene.sceneRect() if not scene.sceneRect().isEmpty() else scene.itemsBoundingRect()

            # 3. Aplica o enquadramento na View
            if rect.isValid():
                view.resetTransform()
                view.fitInView(rect, QtCore.Qt.KeepAspectRatio)
                view.scale(self.zoom_factor, self.zoom_factor)

    def _rebalance_splitter(self, force=False):
        if getattr(self, 'has_custom_workspace', False) and not force:
            return

        total_w = self.splitter.width()
        if total_w < 100: return

        view_w = max(self._VIEW_ABS_MIN, int(self._VIEW_BASE_W * self.zoom_factor))
        views_total = view_w * 2 + 20 

        disponivel = total_w - views_total
        thumb_w = max(self._THUMB_MIN_W, min(self._THUMB_MAX_W, disponivel))
        main_w  = total_w - thumb_w

        self.splitter.setSizes([thumb_w, main_w])

    def _on_auto_crop_requested(self, paths: list):
        if not paths: return
        
        # Import atrasado para não misturar OpenCV pesado na thread inicial da UI
        from core.vidya_crops_auto import VidyaCropsAuto
        
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
        processed_count = VidyaCropsAuto.process_images(paths)
        QtWidgets.QApplication.restoreOverrideCursor()
        
        if processed_count > 0:
            # Integração fluída: Verifica se a imagem do AutoCrop está atualmente aberta no visor
            if self.is_reviewing:
                current_review_paths = [getattr(self, 'review_left_path', None), getattr(self, 'review_right_path', None)]
                # Se alguma das imagens alvo está sendo visualizada agora, 
                #  recarregamos a interface gráfica instantaneamente
                if any(p in current_review_paths for p in paths if p is not None):
                    logger.info("Auto Crop injetou metadados na imagem ativa. Atualizando os polígonos visuais.")
                    self.show_review_pair(self.review_left_path, self.review_right_path, force_reload=True)
                    return # Foge para não mostrar o MessageBox intrusivo, a prova de sucesso é visual
                    
            # Se a imagem processada estava escondida (o usuário editava outra coisa), exibe a confirmação
            QtWidgets.QMessageBox.information(self, "Auto Crop Concluído", f"A inteligência artificial do Vidya detectou e aplicou recortes em {processed_count} imagem(ns) com sucesso!")
        else:
            QtWidgets.QMessageBox.warning(self, "Auto Crop", "O algoritmo não conseguiu distinguir documentos do fundo nestas imagens.\nTente aplicar marcadores manuais, ou selecione uma cor de fundo diferente.")
            
    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._scale_views()

    def showEvent(self, event):
        super().showEvent(event)
        self._scale_views()

    def changeEvent(self, event):
        if event.type() == QtCore.QEvent.WindowStateChange:
            if self.isMinimized(): pass
            elif self.isMaximized() or self.isActiveWindow(): self._scale_views()
        super().changeEvent(event)

    def _on_zoom_in_clicked(self):
        self.zoom_factor *= 1.1
        self._scale_views()
        self._rebalance_splitter()

    def _on_zoom_out_clicked(self):
        self.zoom_factor *= 0.9
        self._scale_views()
        self._rebalance_splitter()

    def _restore_previous_frames(self):
        self._clear_clips() 
        
        # ---> INÍCIO DA CORREÇÃO: Limpa os marcadores fantasmas da imagem deletada
        if getattr(self, 'deskew_marker_left', None):
            self.deskew_marker_left.clear()
        if getattr(self, 'deskew_marker_right', None):
            self.deskew_marker_right.clear()
        # ---> FIM DA CORREÇÃO
        
        left_path = None
        right_path = None
        
        if self.is_single_mode:
            for i in range(min(4, self.thumbnail_panel.count())):
                path = self.thumbnail_panel.item(i).data(QtCore.Qt.UserRole)
                if path and os.path.exists(path) and not left_path: 
                    left_path = path
                    break
        else:
            for i in range(min(4, self.thumbnail_panel.count())):
                path = self.thumbnail_panel.item(i).data(QtCore.Qt.UserRole)
                if path and os.path.exists(path):
                    filename = os.path.basename(path)
                    if "Left" in filename and not left_path: left_path = path
                    elif "Right" in filename and not right_path: right_path = path
                    
        if left_path:
            with open(left_path, 'rb') as f: self.update_frame("Left", f.read(), is_live=False)
        else:
            for item in self.scene_left.items():
                if item != self.marker_left: self.scene_left.removeItem(item)
                
        if right_path and not self.is_single_mode:
            with open(right_path, 'rb') as f: self.update_frame("Right", f.read(), is_live=False)
        else:
            for item in self.scene_right.items():
                if item != self.marker_right: self.scene_right.removeItem(item)
                
        self._reset_zoom()

    def _update_capture_button_style(self):
        mode = self.capture_modes[self.current_mode_index]
        if mode == "Nova Captura": self.btn_capture.setStyleSheet("background-color: #a8c6a9; color: black;")
        elif mode == "Substituir": self.btn_capture.setStyleSheet("background-color: #d35400; color: white;")
        elif mode == "Teste": self.btn_capture.setStyleSheet("background-color: #2980b9; color: white;")
        else: self.btn_capture.setStyleSheet("")
            
    def _reset_capture_button(self):
        self.btn_capture.setEnabled(True)
        self.btn_capture.setText(" CAPTURAR")

    def _open_settings(self):
        dialog = VidyaSettingsDialog(self)
        dialog.settings_saved.connect(self._apply_settings)
        
        # ---> NOVA INSERÇÃO: Escutando o pedido de Calibração IA
        dialog.calibration_requested.connect(self._launch_optuna_calibration)
        
        dialog.exec_()
        
        # ---> NOVO: Persiste as configurações de geometria da janela ao sair.
        self.save_project_workspace()

    def _launch_optuna_calibration(self, calibration_config: dict):
        working_dir = self.settings.get("working_dir")
        if not working_dir or not os.path.exists(working_dir):
            QtWidgets.QMessageBox.warning(self, "Erro", "Não há um projeto ativo válido para calibrar.")
            return

        # 1. Importações (feitas localmente para não atrasar o boot do sistema)
        from core.vidya_dataset_sampler import VidyaDatasetSampler
        from gui.vidya_ground_truth_dialog import VidyaGroundTruthDialog

        # 2. Executa o sorteio estratificado
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
        sampled_paths = VidyaDatasetSampler.generate_ground_truth_pool(
            working_dir=working_dir,
            is_single_mode=self.is_single_mode,
            num_sessions=calibration_config["sessions"],
            samples_per_session=calibration_config["samples"]
        )
        QtWidgets.QApplication.restoreOverrideCursor()

        if not sampled_paths:
            QtWidgets.QMessageBox.information(self, "Aviso", "O projeto não possui imagens suficientes para o sorteio. Faça algumas capturas primeiro.")
            return

        # 3. Lança a Interface de Marcação
        gt_dialog = VidyaGroundTruthDialog(sampled_paths, calibration_config, self.settings, self)
        
        if gt_dialog.exec_() == QtWidgets.QDialog.Accepted:
            # 4. Recupera o gabarito (Ground Truth) criado pelo operador
            ground_truth_data = gt_dialog.get_ground_truth()
            
            logger.info(f"Ground Truth coletado para {len(ground_truth_data)} imagens. Preparando Motor Optuna.")
            
            # TODO: O próximo passo acontece aqui. Iniciaremos a Thread do Optuna
            # self._start_optuna_thread(ground_truth_data, calibration_config)

    def _launch_optuna_calibration(self, calibration_config: dict):
        working_dir = self.settings.get("working_dir")
        if not working_dir or not os.path.exists(working_dir):
            QtWidgets.QMessageBox.warning(self, "Erro", "Não há um projeto ativo válido para calibrar.")
            return

        # 1. Importações (feitas localmente para não atrasar o boot do sistema)
        from core.vidya_dataset_sampler import VidyaDatasetSampler
        from gui.vidya_ground_truth_dialog import VidyaGroundTruthDialog

        # 2. Executa o sorteio estratificado
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
        sampled_paths = VidyaDatasetSampler.generate_ground_truth_pool(
            working_dir=working_dir,
            is_single_mode=self.is_single_mode,
            num_sessions=calibration_config["sessions"],
            samples_per_session=calibration_config["samples"]
        )
        QtWidgets.QApplication.restoreOverrideCursor()

        if not sampled_paths:
            QtWidgets.QMessageBox.information(self, "Aviso", "O projeto não possui imagens suficientes para o sorteio. Faça algumas capturas primeiro.")
            return

        # 3. Lança a Interface de Marcação
        gt_dialog = VidyaGroundTruthDialog(sampled_paths, calibration_config, self.settings, self)
        
        if gt_dialog.exec_() == QtWidgets.QDialog.Accepted:
            # 4. Recupera o gabarito (Ground Truth) criado pelo operador
            ground_truth_data = gt_dialog.get_ground_truth()
            
            logger.info(f"Ground Truth coletado para {len(ground_truth_data)} imagens. Preparando Motor Optuna.")
            
            # 5. Inicia a Thread e a Barra de Progresso Modal
            self._start_optuna_thread(ground_truth_data, calibration_config)

    def _start_optuna_thread(self, ground_truth_data: dict, calibration_config: dict):
        from core.vidya_optuna_tuner import VidyaOptunaTuner
        
        # Cria um escudo visual para impedir interação durante a otimização
        self.optuna_progress = QtWidgets.QProgressDialog("Inicializando Motor de IA...", "Abortar Treinamento", 0, 100, self)
        self.optuna_progress.setWindowTitle("Calibração Preditiva (Optuna)")
        self.optuna_progress.setWindowModality(QtCore.Qt.WindowModal)
        self.optuna_progress.setMinimumDuration(0)
        self.optuna_progress.setValue(0)
        
        # Instancia a Thread
        self.optuna_thread = VidyaOptunaTuner(ground_truth_data, calibration_config, self.settings)
        
        # Liga os sinais vitais
        self.optuna_thread.progress_update.connect(self._update_optuna_progress)
        self.optuna_thread.optimization_finished.connect(self._on_optuna_finished)
        self.optuna_thread.optimization_error.connect(self._on_optuna_error)
        
        # Segurança: Se o usuário abortar, tentamos matar a thread
        self.optuna_progress.canceled.connect(self.optuna_thread.terminate)
        
        # Dá a partida no motor
        self.optuna_thread.start()

    def _update_optuna_progress(self, val: int, msg: str):
        self.optuna_progress.setValue(val)
        self.optuna_progress.setLabelText(msg)

    def _on_optuna_error(self, error_msg: str):
        self.optuna_progress.close()
        QtWidgets.QMessageBox.critical(self, "Falha na Calibração", f"O motor de IA encontrou um erro crítico:\n\n{error_msg}")

    def _on_optuna_finished(self, best_params: dict):
        self.optuna_progress.close()
        
        if not best_params:
            QtWidgets.QMessageBox.warning(self, "Calibração Abortada", "A otimização não retornou parâmetros válidos.")
            return

        # 1. Injeta os parâmetros matemáticos encontrados pela IA nas preferências ativas
        self.settings.update(best_params)
        
        # 2. Força a alteração das comboboxes para o utilizador saber que a máquina assumiu o controle
        if "ac_blur" in best_params:
            self.settings["ac_preset"] = "Perfil Otimizado por IA"
            
        # 3. Persiste a alteração fisicamente no config.json
        save_settings(self.settings)
        
        # ---> INÍCIO DA INSERÇÃO: Salva os parâmetros do Optuna no project.json do lote atual <---
        working_dir = self.settings.get("working_dir")
        if working_dir and os.path.exists(working_dir):
            proj_file = os.path.join(working_dir, "project.json")
            if os.path.exists(proj_file):
                try:
                    with open(proj_file, 'r', encoding='utf-8') as f:
                        proj_data = json.load(f)
                    
                    if "optuna_params" not in proj_data:
                        proj_data["optuna_params"] = {}
                    
                    # Atualiza o manifesto do projeto com a matemática da IA
                    proj_data["optuna_params"].update(best_params)
                    
                    with open(proj_file, 'w', encoding='utf-8') as f:
                        json.dump(proj_data, f, indent=4, ensure_ascii=False)
                except Exception as e:
                    logger.error(f"Erro ao salvar parâmetros do Optuna no projeto atual: {e}")
        # ---> FIM DA INSERÇÃO <---
        
        # 4. Exibe o relatório de vitória para o operador
        msg = "<b>Calibração concluída com sucesso!</b><br><br>Os seguintes hiperparâmetros foram ajustados e travados no projeto:<br><br>"
        for k, v in best_params.items():
            # Traduz os nomes técnicos para o relatório de forma legível
            if k == "ac_blur": msg += f"• Desfoque de Fusão: <b>{v}</b><br>"
            elif k == "ac_dilate": msg += f"• Dilatação Morfológica: <b>{v}</b><br>"
            elif k == "ac_invert": msg += f"• Cálculo de Contraste: <b>{v}</b><br>"
            elif k == "ocr_denoise_h": msg += f"• Remoção de Ruído (h): <b>{v:.2f}</b><br>"
            elif k == "ocr_clahe_clip": msg += f"• Realce de Contraste (CLAHE): <b>{v:.2f}</b><br>"
            elif k == "ocr_block_size": msg += f"• Binarização (Block Size): <b>{v}</b><br>"
            elif k == "ocr_c_val": msg += f"• Binarização (C Value): <b>{v}</b><br>"
            else: msg += f"• {k}: <b>{v}</b><br>"
            
        msg += "<br><i>O Vidya utilizará esta matemática ao exportar o lote inteiro.</i>"
        
        QtWidgets.QMessageBox.information(self, "Inteligência Artificial", msg)
                    
    def _apply_settings(self, new_settings: dict, tab_name: str):
        self.settings = new_settings
        c_left = self.settings.get("marker_color_left", "Vermelho")
        c_right = self.settings.get("marker_color_right", "Verde")
        opac = self.settings.get("marker_opacity", 8)
        weight = self.settings.get("marker_thickness_weight", 100) 
        
        self.marker_left.update_color(c_left, opac, weight)
        self.marker_right.update_color(c_right, opac, weight)
        
        # --- NOVO: ATUALIZA BORDAS EM TEMPO REAL ---
        pen = self._get_border_pen()
        for pos in ["Left", "Right"]:
            if self.image_borders.get(pos) and self.image_borders[pos].scene():
                self.image_borders[pos].setPen(pen)
        
        self.thumbnail_panel.update_settings_ref(self.settings)
        self.pending_crop_reset = {"Left": True, "Right": True}
        if tab_name == "Dispositivos" or True:
            self.settings_updated.emit(self.settings)

    def _get_border_pen(self) -> QtGui.QPen:
        """Gera a QPen configurada para desenhar as bordas das imagens na cena."""
        w = self.settings.get("image_border_width", 1)
        c_name = self.settings.get("image_border_color", "Preto")
        opac = self.settings.get("image_border_opacity", 100)
        s_name = self.settings.get("image_border_style", "Contínuo")

        if w == 0:
            return QtGui.QPen(QtCore.Qt.NoPen)

        alpha = int((opac / 100.0) * 255)
        if c_name == "Branco": color = QtGui.QColor(255, 255, 255, alpha)
        elif c_name == "Cinza": color = QtGui.QColor(128, 128, 128, alpha)
        else: color = QtGui.QColor(0, 0, 0, alpha)

        pen = QtGui.QPen(color, w)
        
        if s_name == "Tracejado": pen.setStyle(QtCore.Qt.DashLine)
        elif s_name == "Pontos": pen.setStyle(QtCore.Qt.DotLine)
        else: pen.setStyle(QtCore.Qt.SolidLine)

        pen.setJoinStyle(QtCore.Qt.MiterJoin)
        return pen    
    
    def update_frame(self, position: str, frame_bytes: bytes, is_live: bool = True):
        if self.isMinimized(): return
        if self.is_reviewing and is_live: return
        if hasattr(self, 'undo_manager'): self.undo_manager.clear(position) # <--- LIMPA UNDO
        
        # ---> INÍCIO DA CORREÇÃO: Garante que o streaming de vídeo anule qualquer ponto estático
        if is_live:
            d_marker = getattr(self, f"deskew_marker_{position.lower()}", None)
            if d_marker:
                d_marker.clear()
        # ---> FIM DA CORREÇÃO

        try:
            pixmap = QtGui.QPixmap()
            if not pixmap.loadFromData(frame_bytes): return
            
            rot_setting = self.settings.get(f"rotation_{position.lower()}", "0°")
            angle = int(rot_setting.replace("°", "")) 
            
            if angle != 0 and is_live:
                transform = QtGui.QTransform().rotate(angle)
                pixmap = pixmap.transformed(transform)
                
            final_w = pixmap.width()
            final_h = pixmap.height()
            
            self.current_image_dims[position] = (final_w, final_h)
            image_ratio = final_w / final_h if final_h > 0 else 1.0
            marker = self.marker_left if position == "Left" else self.marker_right
            
            if hasattr(marker, 'set_image_ratio'): marker.set_image_ratio(image_ratio)
            if hasattr(marker, 'set_image_bounds'): marker.set_image_bounds(final_w, final_h)
            
            if not self.is_reviewing:
                if position == "Left": self.lbl_info_left.setText(f"{self.device_name_left}  ({final_w} x {final_h} px)")
                else: self.lbl_info_right.setText(f"{self.device_name_right}  ({final_w} x {final_h} px)")
                
            scene = self.scene_left if position == "Left" else self.scene_right
            
            dims_changed = False
            # Nível 2: Força o recálculo do visor se mudou o tamanho OU se estamos abrindo uma miniatura (not is_live)
            if (final_w, final_h) != self.current_image_dims.get(position) or not is_live:
                self.current_image_dims[position] = (final_w, final_h)
                dims_changed = True
                margin_w = final_w * 0.10
                margin_h = final_h * 0.10
                scene.setSceneRect(-margin_w, -margin_h, final_w + (margin_w * 2), final_h + (margin_h * 2))

            if not self.live_pixmaps[position] or self.live_pixmaps[position] not in scene.items():
                self.live_pixmaps[position] = scene.addPixmap(pixmap)
                self.live_pixmaps[position].setZValue(-1)
                self.live_pixmaps[position].setPos(0, 0)
                
                # --- NOVO: INSERE A BORDA NA CENA PELA PRIMEIRA VEZ ---
                pen = self._get_border_pen()
                self.image_borders[position] = scene.addRect(0, 0, final_w, final_h, pen)
                # ZValue = 0 garante que fique por cima da foto (-1) mas atrás dos marcadores de recorte
                self.image_borders[position].setZValue(0)
            else:
                self.live_pixmaps[position].setPixmap(pixmap)
                
                # --- NOVO: REDIMENSIONA A BORDA SE A IMAGEM ATUALIZAR ---
                if self.image_borders.get(position):
                    self.image_borders[position].setRect(0, 0, final_w, final_h)
                    self.image_borders[position].setPen(self._get_border_pen())

            if is_live and getattr(self, 'pending_crop_reset', {}).get(position, False):
                marker.set_geometry({"x": 0, "y": 0, "width": final_w, "height": final_h})
                self.pending_crop_reset[position] = False

            if dims_changed:
                self._scale_views()
            
        except Exception as e:
            logger.error(f"Falha na montagem do frame ({position}): {str(e)}")

    def enqueue_thumbnail(self, filepath: str):
        self.thumbnail_panel.clear_last_edited_highlight() # <--- NOVO
        
        self.thumbnail_panel.add_thumbnail(filepath)
        self.update_status_bar()
        
        if self.is_single_mode and getattr(self, 'active_clips', []):
            self._save_clips_to_disk(filepath)

    def _clear_clips(self):
        for clip in getattr(self, 'active_clips', []):
            if clip in self.scene_left.items():
                self.scene_left.removeItem(clip)
        self.active_clips = []

    def _add_new_clip(self):
        """Cria um novo marcador retangular ocupando o tamanho total da imagem."""
        if not self.is_single_mode: return
        self._save_undo_snapshot(self.marker_left) # <--- TIRA A FOTO ANTES DE CRIAR
        
        opac = self.settings.get("marker_opacity", 8)
        weight = self.settings.get("marker_thickness_weight", 100)
        
        new_clip = VidyaCropMarker("Vinho", opac, weight)
        new_clip.is_single_mode = True
        new_clip.is_child_clip = True
        
        # Amarração dos callbacks no novo elemento
        new_clip.add_clip_callback = self._add_new_clip
        
        new_clip.remove_clip_callback = self._remove_clip
        new_clip.make_main_callback = self._make_clip_main  # <--- INSERIR
        new_clip.duplicate_callback = self._duplicate_clip 
        new_clip.toggle_ratio_callback = self._toggle_keep_ratio
        new_clip.resize_percent_callback = self._resize_crop_percent
        new_clip.reset_all_clips_callback = self._reset_crops_and_maximize
        
        # Aplica o tamanho total da imagem nativa
        w, h = self.current_image_dims.get("Left", (0, 0))
        
        new_clip.set_geometry({
            "x": 0,
            "y": 0,
            "width": w if w > 0 else 300,
            "height": h if h > 0 else 450,
            "polygon": []  # Força fallback para as 4 arestas limpas
        })
        
        if hasattr(new_clip, 'set_image_bounds'): new_clip.set_image_bounds(w, h)
        if hasattr(new_clip, 'set_keep_ratio'): new_clip.set_keep_ratio(self.settings.get("keep_crop_ratio", False))

        self.scene_left.addItem(new_clip)
        self.active_clips.append(new_clip)
        self._save_review_crop_if_needed()

    def _duplicate_clip(self, source_marker):
        """Clona o polígono selecionado injetando offset de 10% no eixo X e Y."""
        logger.info(f"Clona o polígono selecionado injetando offset de 10% no eixo X e Y")
        if not self.is_single_mode: return
        self._save_undo_snapshot(source_marker) # <--- TIRA A FOTO ANTES DE CLONAR
        
        opac = self.settings.get("marker_opacity", 8)
        weight = self.settings.get("marker_thickness_weight", 100)
        
        new_clip = VidyaCropMarker("Vinho", opac, weight)
        new_clip.is_single_mode = True
        new_clip.is_child_clip = True
        
        new_clip.add_clip_callback = self._add_new_clip
        
        new_clip.remove_clip_callback = self._remove_clip
        new_clip.make_main_callback = self._make_clip_main  # <--- INSERIR
        new_clip.duplicate_callback = self._duplicate_clip
        new_clip.toggle_ratio_callback = self._toggle_keep_ratio
        new_clip.resize_percent_callback = self._resize_crop_percent
        new_clip.reset_all_clips_callback = self._reset_crops_and_maximize
        
        # 1. Extrai a malha geométrica COMPLETA do polígono que foi clicado.
        # É obrigatório usar get_geometry() para vir com o array "polygon" preenchido com os topos.
        geom = source_marker.get_geometry()
        
        # 2. Calcula 10% da largura e altura atuais para atuar como offset de nascimento
        offset_x = geom.get("width", 300) * 0.10
        offset_y = geom.get("height", 450) * 0.10
        
        # 3. Empurra as coordenadas matemáticas globais para baixo e para a direita
        geom["x"] += offset_x
        geom["y"] += offset_y
        
        # 4. Injeta a malha clonada no novo marcador (O sistema reconhecerá os >4 vértices automaticamente)
        new_clip.set_geometry(geom)
        
        w, h = self.current_image_dims.get("Left", (0, 0))
        if hasattr(new_clip, 'set_image_bounds'): new_clip.set_image_bounds(w, h)
        if hasattr(new_clip, 'set_keep_ratio'): new_clip.set_keep_ratio(self.settings.get("keep_crop_ratio", False))

        self.scene_left.addItem(new_clip)
        self.active_clips.append(new_clip)
        self._save_review_crop_if_needed()

    def _remove_clip(self, clip_marker):
        self._save_undo_snapshot(clip_marker) # <--- TIRA A FOTO ANTES DE DELETAR
        if clip_marker in self.active_clips:
            self.scene_left.removeItem(clip_marker)
            self.active_clips.remove(clip_marker)
            self._save_review_crop_if_needed()

    def _make_clip_main(self, clip_marker):
        """Troca a geometria do clipe secundário selecionado com o quadro principal."""
        if not self.is_single_mode: return
        
        # 1. Tira uma foto do estado atual para permitir Ctrl+Z (Undo)
        self._save_undo_snapshot(self.marker_left)
        
        # 2. Resgata as geometrias matemáticas
        clip_geom = clip_marker.get_geometry()
        main_geom = self.marker_left.get_geometry()
        
        # 3. Faz a inversão física na tela
        self.marker_left.set_geometry(clip_geom)
        clip_marker.set_geometry(main_geom)
        
        # 4. Salva no disco (HD) as novas posições
        self._save_review_crop_if_needed()
        logger.info("Quadro secundário promovido a principal com sucesso.")
        
    def _save_clips_to_disk(self, base_image_path):
        if not base_image_path or not os.path.exists(base_image_path): return
        
        base_dir = os.path.dirname(base_image_path)
        base_name = os.path.basename(base_image_path)
        name_no_ext = base_name.rsplit('.', 1)[0]
        
        import glob
        for ec in glob.glob(os.path.join(base_dir, f"{name_no_ext}_clip_*.json")):
            try: os.remove(ec)
            except: pass
        
        for idx, clip in enumerate(self.active_clips):
            clip_json_path = os.path.join(base_dir, f"{name_no_ext}_clip_{idx+1}.json")
            data = {"source_image": base_name, "crop_geometry": clip.get_geometry()}
            try:
                with open(clip_json_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=4)
            except Exception as e:
                logger.error(f"Erro ao salvar clip {clip_json_path}: {e}")

    def _toggle_maximize(self):
        if self.isMaximized(): self.showNormal()
        else: self.showMaximized()

    def _toggle_fullscreen(self):
        if self.isFullScreen(): self.showNormal()
        else: self.showFullScreen()
        
    def save_project_workspace(self):
        working_dir = self.settings.get("working_dir")
        if not working_dir or not os.path.exists(working_dir): return
        
        state = {
            "window_geometry": self.saveGeometry().toHex().data().decode(),
            "splitter_state": self.splitter.saveState().toHex().data().decode() if hasattr(self, 'splitter') else ""
        }
        try:
            with open(os.path.join(working_dir, ".vidya_workspace.json"), 'w', encoding='utf-8') as f:
                json.dump(state, f)
        except Exception as e:
            logger.error(f"Erro ao salvar workspace do projeto: {e}")

    def load_project_workspace(self) -> bool:
        working_dir = self.settings.get("working_dir")
        if not working_dir or not os.path.exists(working_dir): return False
        
        workspace_file = os.path.join(working_dir, ".vidya_workspace.json")
        if os.path.exists(workspace_file):
            try:
                with open(workspace_file, 'r', encoding='utf-8') as f:
                    state = json.load(f)
                
                if "window_geometry" in state:
                    self.restoreGeometry(QtCore.QByteArray.fromHex(state["window_geometry"].encode()))
                if "splitter_state" in state and hasattr(self, 'splitter'):
                    self.splitter.restoreState(QtCore.QByteArray.fromHex(state["splitter_state"].encode()))
                
                self.has_custom_workspace = True
                return True
            except Exception as e:
                logger.error(f"Erro ao carregar workspace do projeto: {e}")
        
        self.has_custom_workspace = False
        return False

    def closeEvent(self, event):
        logger.info("Encerrando UI. Persistindo limites geométricos e estados da janela...")
        self.settings["marker_left_geometry"] = self.marker_left.get_geometry()
        self.settings["marker_right_geometry"] = self.marker_right.get_geometry()
        
        self.save_project_workspace()
        
        if "window_geometry" in self.settings: del self.settings["window_geometry"]
        if "splitter_state" in self.settings: del self.settings["splitter_state"]
        
        save_settings(self.settings)
        self.shutdown_requested.emit()
        event.accept()
