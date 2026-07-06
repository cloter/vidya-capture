# Arquivo: gui/vidya_settings_dialog.py

from PyQt5 import QtWidgets, QtCore, QtGui
import glob
import os
import json
import platform
import socket
import getpass
from datetime import datetime
from core.config import COLOR_MAP, load_settings, save_settings
from hardware.vidya_v4l2_scanner import V4L2AdvancedScanner
from gui.vidya_profiles_dialog import VidyaProfilesDialog
from core.vidya_fisheye_calibration import FisheyeCalibrationWorker, VidyaFisheyePreviewWindow

class V4L2AdvancedDialog(QtWidgets.QDialog):
    def __init__(self, scan_data, current_config, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Detecção Avançada V4L2")
        self.resize(550, 400)
        self.scan_data = scan_data
        self.combos = {} 
        self._setup_ui(current_config)
        
    def _setup_ui(self, current_config):
        layout = QtWidgets.QVBoxLayout(self)
        info = QtWidgets.QLabel("<b>Configuração de Hardware USB:</b><br><small>Force o codec e a resolução para evitar gargalos no barramento. Escolha 'Automático' para o comportamento padrão.</small>")
        layout.addWidget(info)
        
        form_layout = QtWidgets.QFormLayout()
        
        for node, info_data in self.scan_data.items():
            if not info_data.get("formatos_suportados"):
                continue

            combo = QtWidgets.QComboBox()
            combo.addItem("Automático (Padrão)", userData=None)
            
            idx = 1
            match_idx = 0
            for fmt in info_data["formatos_suportados"]:
                codec = fmt["codec"]
                for res in fmt["resolucoes"]:
                    label = f"{codec} - {res}"
                    combo.addItem(label, userData={"codec": codec, "res": res})
                    
                    saved = current_config.get(node)
                    if saved and saved.get("codec") == codec and f"{saved.get('width')}x{saved.get('height')}" == res:
                        match_idx = idx
                    idx += 1
            
            combo.setCurrentIndex(match_idx)
            self.combos[node] = combo
            
            dev_name = info_data.get("nome_dispositivo", "Câmera")
            bus = info_data.get("barramento_usb", "")
            form_layout.addRow(f"{dev_name}\n({node} | {bus}):", combo)
            
        layout.addLayout(form_layout)
        
        btn_box = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        layout.addStretch()
        layout.addWidget(btn_box)
        
    def get_selected_config(self):
        config = {}
        for node, combo in self.combos.items():
            data = combo.currentData()
            if data:
                w, h = data["res"].split("x")
                config[node] = {
                    "codec": data["codec"],
                    "width": int(w),
                    "height": int(h)
                }
        return config

class VidyaSettingsDialog(QtWidgets.QDialog):
    settings_saved = QtCore.pyqtSignal(dict, str)   # (settings, tab_name)
    # ---> INSERIR AQUI: Sinal para disparar a nova GUI do Optuna
    calibration_requested = QtCore.pyqtSignal(dict) # Envia as configs de amostragem

    def __init__(self, parent=None):
        super().__init__(parent)
        self.preview_window = None  # <--- INSERIR ESTA LINHA AQUI
        self.setWindowTitle("Preferências - Vidya Capture")
        self.resize(920, 580) 
        self.settings = load_settings()
        self._setup_ui()
        
    # ---> INSERIR AQUI: Regras de Exclusividade Mútua <---
    def _on_use_rectify_toggled(self, checked):
        if checked and hasattr(self, 'chk_use_simulated'):
            self.chk_use_simulated.setChecked(False)

    def _on_use_simulated_toggled(self, checked):
        if checked and hasattr(self, 'chk_use_rectify'):
            self.chk_use_rectify.setChecked(False)
    # ------------------------------------------------------

    def _setup_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        self.tabs = QtWidgets.QTabWidget()
        layout.addWidget(self.tabs)
        
        self.tabs.currentChanged.connect(self._on_tab_changed)
        self.current_tab_name = self.tabs.tabText(self.tabs.currentIndex())
        
        self._build_project_tab()
        self._build_source_tab()    
        self._build_preview_tab()
        self._build_images_tab()
        self._build_rectify_tab()
        self._build_simulate_tab() 
        self._build_markers_tab()
        self._build_ocr_tab()
        self._build_optuna_tab()
        self._build_custody_tab()
        self._build_process_tab()

        btn_layout = QtWidgets.QHBoxLayout()
        btn_save = QtWidgets.QPushButton("Aplicar")
        btn_cancel = QtWidgets.QPushButton("Cancelar")
        
        # ---> INSERIR: Instanciação do Botão de Perfis
        btn_profiles = QtWidgets.QPushButton("Perfis de Acervo")
        btn_profiles.setIcon(QtGui.QIcon.fromTheme("document-properties"))
        btn_profiles.clicked.connect(self._open_profiles_dialog)
        # ----------------------------------------------------
        
        btn_save.setIcon(QtGui.QIcon.fromTheme("document-save"))
        btn_cancel.setIcon(QtGui.QIcon.fromTheme("process-stop"))
        
        btn_save.clicked.connect(self._save_and_close)
        btn_cancel.clicked.connect(self.reject)
        
        btn_layout.addStretch()
        btn_layout.addWidget(btn_cancel)
        btn_layout.addWidget(btn_profiles) # <--- Posicionado entre Cancelar e Aplicar
        btn_layout.addWidget(btn_save)
        layout.addLayout(btn_layout)
        
        self._load_project_metadata(self.combo_path.currentText())
        
        # Chamada síncrona para garantir que a UI SANE abre no estado correto
        if hasattr(self, 'combo_project_mode'):
            self._toggle_scanner_options(self.combo_project_mode.currentText())

    def _on_tab_changed(self, index):
        self.current_tab_name = self.tabs.tabText(index)

    def _get_v4l_signature(self, dev_path: str) -> str:
        try:
            dev_id = os.path.basename(dev_path)
            name = "V4L Device"
            sysfs_name = f"/sys/class/video4linux/{dev_id}/name"
            if os.path.exists(sysfs_name):
                with open(sysfs_name, 'r', encoding='utf-8') as f:
                    name = f.read().strip()
                    
            sysfs_device = f"/sys/class/video4linux/{dev_id}/device"
            usb_id = "Porta Desconhecida"
            if os.path.exists(sysfs_device):
                real_path = os.path.realpath(sysfs_device)
                usb_id = os.path.basename(real_path)
                
            index_val = dev_id.replace("video", "")
            sysfs_index = f"/sys/class/video4linux/{dev_id}/index"
            if os.path.exists(sysfs_index):
                with open(sysfs_index, 'r', encoding='utf-8') as f:
                    index_val = f.read().strip()
                
            return f"{name} [USB {usb_id} - Nó {index_val}]"
        except Exception:
            return dev_path

    def _show_rename_menu(self, pos, list_widget):
        item = list_widget.itemAt(pos)
        if not item: return
            
        menu = QtWidgets.QMenu(self)
        action_rename = menu.addAction("Renomear Dispositivo...")
        action_rename.setIcon(QtGui.QIcon.fromTheme("insert-text"))
        action_restore = menu.addAction("Restaurar Nome Original")
        action_restore.setIcon(QtGui.QIcon.fromTheme("edit-undo"))
        
        action = menu.exec_(list_widget.mapToGlobal(pos))
        signature = item.data(QtCore.Qt.UserRole)
        if not signature: return

        if action == action_rename:
            current_name = item.text().split("  —  ")[-1] if "  —  " in item.text() else item.text().split("  [")[0]
            new_name, ok = QtWidgets.QInputDialog.getText(
                self, "Renomear Dispositivo", 
                f"Digite um apelido (alias) para:\n{signature}", 
                QtWidgets.QLineEdit.Normal, current_name
            )
            if ok and new_name.strip():
                custom_names = self.settings.get("custom_device_names", {})
                custom_names[signature] = new_name.strip()
                self.settings["custom_device_names"] = custom_names
                item.setText(new_name.strip())

        elif action == action_restore:
            custom_names = self.settings.get("custom_device_names", {})
            if signature in custom_names:
                del custom_names[signature]
                self.settings["custom_device_names"] = custom_names
                item.setText(signature)

    def _build_source_tab(self):
        tab = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(tab)

        source_label = QtWidgets.QLabel("<b>Controle e Escolha dos Dispositivos de Captura</b><br><small>As opções são: Câmeras DSLR, Video for Linux 2 ou Scanners SANE</small>")
        source_label.setWordWrap(True)
        layout.addWidget(source_label)        
        
        form_layout = QtWidgets.QFormLayout()
        self.combo_source = QtWidgets.QComboBox()
        self.combo_source.addItems(["Câmeras", "V4L", "Scanners", "Classe Mock"])
        self.combo_source.setCurrentText(self.settings.get("input_source", "Câmeras"))
        self.combo_source.currentTextChanged.connect(self._on_source_changed)
        form_layout.addRow("Dispositivo de Origem:", self.combo_source)
        layout.addLayout(form_layout)
        
        custom_names = self.settings.get("custom_device_names", {})

        self.container_v4l = QtWidgets.QWidget()
        v4l_layout = QtWidgets.QVBoxLayout(self.container_v4l)
        v4l_layout.setContentsMargins(0, 10, 0, 0)
        lbl_v4l = QtWidgets.QLabel("<b>Dispositivos V4L detectados:</b><br><small>Arraste para <b>Reordenar</b>. Clique com o botão direito para <b>Renomear</b>.</small>")
        
        self.list_v4l = QtWidgets.QListWidget()
        self.list_v4l.setDragDropMode(QtWidgets.QAbstractItemView.InternalMove)
        self.list_v4l.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.list_v4l.setContextMenuPolicy(QtCore.Qt.CustomContextMenu) 
        self.list_v4l.customContextMenuRequested.connect(lambda pos: self._show_rename_menu(pos, self.list_v4l))
        
        v4l_saved_signatures = self.settings.get("v4l_devices", [])
        current_v4l_paths = sorted(glob.glob('/dev/video*'))
        current_signatures = [self._get_v4l_signature(p) for p in current_v4l_paths]
        
        for sig in v4l_saved_signatures:
            if sig in current_signatures:
                display_name = custom_names.get(sig, sig)
                item = QtWidgets.QListWidgetItem(display_name)
                item.setData(QtCore.Qt.UserRole, sig) 
                self.list_v4l.addItem(item)
                current_signatures.remove(sig)
                
        for sig in current_signatures:
            display_name = custom_names.get(sig, sig)
            item = QtWidgets.QListWidgetItem(display_name)
            item.setData(QtCore.Qt.UserRole, sig) 
            self.list_v4l.addItem(item)
        
        btn_layout_v4l = QtWidgets.QHBoxLayout()
        btn_reload_v4l = QtWidgets.QPushButton(" Varredura Rápida")
        btn_reload_v4l.setIcon(QtGui.QIcon.fromTheme("view-refresh"))
        btn_reload_v4l.clicked.connect(self._reload_v4l_devices)
        
        btn_adv_v4l = QtWidgets.QPushButton(" Detecção Avançada")
        btn_adv_v4l.setIcon(QtGui.QIcon.fromTheme("system-search"))
        btn_adv_v4l.clicked.connect(self._open_advanced_v4l_scan)
        
        btn_layout_v4l.addWidget(btn_reload_v4l)
        btn_layout_v4l.addWidget(btn_adv_v4l)
        
        v4l_layout.addWidget(lbl_v4l)
        v4l_layout.addWidget(self.list_v4l)
        v4l_layout.addLayout(btn_layout_v4l)
        
        self.container_scanner = QtWidgets.QWidget()
        scanner_layout = QtWidgets.QVBoxLayout(self.container_scanner)
        scanner_layout.setContentsMargins(0, 10, 0, 0)
        lbl_scanner = QtWidgets.QLabel("<b>Scanners de Mesa / Rede</b><br><small>Arraste para reordenar. <b>Clique com o botão direito para Renomear.</b></small>")
        
        self.list_scanner = QtWidgets.QListWidget()
        self.list_scanner.setDragDropMode(QtWidgets.QAbstractItemView.InternalMove)
        self.list_scanner.setContextMenuPolicy(QtCore.Qt.CustomContextMenu) 
        self.list_scanner.customContextMenuRequested.connect(lambda pos: self._show_rename_menu(pos, self.list_scanner))
        
        scanner_devs = self.settings.get("scanner_devices", [])
        for uri in scanner_devs:
            display_name = custom_names.get(uri, uri)
            item = QtWidgets.QListWidgetItem(display_name)
            item.setData(QtCore.Qt.UserRole, uri)
            self.list_scanner.addItem(item)
            
        btn_reload_scanner = QtWidgets.QPushButton(" Buscar Scanners (SANE)")
        btn_reload_scanner.setIcon(QtGui.QIcon.fromTheme("scanner"))
        btn_reload_scanner.clicked.connect(self._reload_scanner_devices)
        
        scanner_layout.addWidget(lbl_scanner)
        scanner_layout.addWidget(self.list_scanner)
        scanner_layout.addWidget(btn_reload_scanner) 

        # =========================================================================
        # CONFIGURAÇÃO SANE PROFISSIONAL (MANTIDA NO HARDWARE)
        # =========================================================================
        self.grp_sane_opts = QtWidgets.QGroupBox("Parâmetros de Digitalização (Scanner SANE)")
        font_sane = self.grp_sane_opts.font(); font_sane.setBold(True); self.grp_sane_opts.setFont(font_sane)
        self.grp_sane_opts.setStyleSheet("QLabel, QComboBox, QSlider { font-weight: normal; }")
        lyt_sane = QtWidgets.QFormLayout(self.grp_sane_opts)

        self.combo_scanner_dpi = QtWidgets.QComboBox()
        self.combo_scanner_dpi.addItems(["150", "300", "400", "600", "1200"])
        self.combo_scanner_dpi.setCurrentText(str(self.settings.get("scanner_dpi", "300")))

        self.combo_scanner_mode = QtWidgets.QComboBox()
        self.combo_scanner_mode.addItems(["Color", "Gray", "Lineart"])
        self.combo_scanner_mode.setCurrentText(self.settings.get("scanner_color_mode", "Color"))

        self.combo_scanner_source = QtWidgets.QComboBox()
        self.combo_scanner_source.addItems(["Flatbed", "Automatic Document Feeder", "ADF Front", "ADF Back"])
        self.combo_scanner_source.setCurrentText(self.settings.get("scanner_source", "Flatbed"))

        self.combo_scanner_paper = QtWidgets.QComboBox()
        self.combo_scanner_paper.addItems(["Máximo do Vidro", "A4 (210x297mm)", "A3 (297x420mm)", "A2 (420x594mm)", "US Letter", "US Legal"])
        self.combo_scanner_paper.setCurrentText(self.settings.get("scanner_paper_size", "Máximo do Vidro"))

        def create_bc_slider(val):
            s = QtWidgets.QSlider(QtCore.Qt.Horizontal)
            s.setRange(-100, 100)
            s.setValue(int(val))
            s.setTickPosition(QtWidgets.QSlider.TicksBelow)
            s.setTickInterval(25)
            return s
        
        self.slider_scanner_brightness = create_bc_slider(self.settings.get("scanner_brightness", 0))
        self.slider_scanner_contrast = create_bc_slider(self.settings.get("scanner_contrast", 0))
        
        self.lbl_s_bright = QtWidgets.QLabel(f"{self.slider_scanner_brightness.value()}")
        self.lbl_s_bright.setMinimumWidth(30)
        self.slider_scanner_brightness.valueChanged.connect(lambda v: self.lbl_s_bright.setText(str(v)))
        
        self.lbl_s_contrast = QtWidgets.QLabel(f"{self.slider_scanner_contrast.value()}")
        self.lbl_s_contrast.setMinimumWidth(30)
        self.slider_scanner_contrast.valueChanged.connect(lambda v: self.lbl_s_contrast.setText(str(v)))

        lyt_b = QtWidgets.QHBoxLayout(); lyt_b.addWidget(self.lbl_s_bright); lyt_b.addWidget(self.slider_scanner_brightness)
        lyt_c = QtWidgets.QHBoxLayout(); lyt_c.addWidget(self.lbl_s_contrast); lyt_c.addWidget(self.slider_scanner_contrast)

        lyt_sane.addRow("Resolução (DPI):", self.combo_scanner_dpi)
        lyt_sane.addRow("Modo de Cor:", self.combo_scanner_mode)
        lyt_sane.addRow("Alimentação:", self.combo_scanner_source)
        lyt_sane.addRow("Formato da Página:", self.combo_scanner_paper)
        lyt_sane.addRow("Brilho (Hardware):", lyt_b)
        lyt_sane.addRow("Contraste (Hardware):", lyt_c)

        self.lbl_sane_warning = QtWidgets.QLabel("<small style='color:#c0392b;'><b>Aviso:</b> O suporte avançado SANE requer que o projeto esteja no modo <b>Mesa Plana (Câmera Única)</b>.</small>")
        self.lbl_sane_warning.setWordWrap(True)
        lyt_sane.addRow(self.lbl_sane_warning)

        scanner_layout.addWidget(self.grp_sane_opts)

        layout.addWidget(self.container_v4l)
        layout.addWidget(self.container_scanner)
        layout.addStretch()
        
        self.tabs.addTab(tab, "Dispositivos")
        self._on_source_changed(self.combo_source.currentText())

    def _toggle_scanner_options(self, mode_text: str):
        if hasattr(self, 'grp_sane_opts'):
            is_single = ("Única" in mode_text or "Plana" in mode_text)
            self.grp_sane_opts.setEnabled(is_single)
            self.lbl_sane_warning.setVisible(not is_single)

    def _reload_scanner_devices(self):
        self.list_scanner.clear()
        custom_names = self.settings.get("custom_device_names", {})
        try:
            import sane
            sane.init()
            devices = sane.get_devices()
            for dev in devices:
                dev_uri = dev[0] 
                display_name = custom_names.get(dev_uri, dev_uri)
                item = QtWidgets.QListWidgetItem(display_name)
                item.setData(QtCore.Qt.UserRole, dev_uri)
                self.list_scanner.addItem(item)
            sane.exit()
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "Erro SANE", f"Falha ao buscar scanners: {str(e)}")
            
    def _open_advanced_v4l_scan(self):
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
        scan_data = V4L2AdvancedScanner.scan()
        QtWidgets.QApplication.restoreOverrideCursor()
        
        if "error" in scan_data:
            QtWidgets.QMessageBox.warning(self, "Erro no V4L2", scan_data["error"])
            return
            
        current_cfg = self.settings.get("v4l2_advanced_config", {})
        dialog = V4L2AdvancedDialog(scan_data, current_cfg, self)
        
        if dialog.exec_() == QtWidgets.QDialog.Accepted:
            self.settings["v4l2_advanced_config"] = dialog.get_selected_config()
            self._reload_v4l_devices() 

    def _reload_v4l_devices(self):
        self.list_v4l.clear()
        custom_names = self.settings.get("custom_device_names", {})
        adv_cfg = self.settings.get("v4l2_advanced_config", {})
        devices = sorted(glob.glob('/dev/video*'))
        
        for dev_path in devices:
            sig = self._get_v4l_signature(dev_path)
            display_name = custom_names.get(sig, sig)
            
            if dev_path in adv_cfg:
                cfg = adv_cfg[dev_path]
                display_name += f"  [{cfg['codec']} {cfg['width']}x{cfg['height']}]"
                
            item = QtWidgets.QListWidgetItem(display_name)
            item.setData(QtCore.Qt.UserRole, sig)
            self.list_v4l.addItem(item)

    def _on_source_changed(self, source: str):
        self.container_v4l.setVisible(source == "V4L")
        self.container_scanner.setVisible(source == "Scanners")

    def _reset_post_capture_defaults(self):
        self.slider_post_brightness.setValue(0)
        self.slider_post_contrast.setValue(0)
        
        self.combo_format.setCurrentText("PNG")
        self.spin_png_compression.setValue(6)
        
        # Outros formatos (Padrões de segurança)
        self.spin_jpg_quality.setValue(95)
        self.combo_tiff_compression.setCurrentText("Sem compressão")        

        self._reset_bg_defaults()

    def _build_images_tab(self):
        tab = QtWidgets.QWidget()
        self.images_form_layout = QtWidgets.QFormLayout(tab)
        
        # =========================================================================
        # 1. INTELIGÊNCIA DE RECORTE AUTOMÁTICO (AUTO CROP) - AGORA NO TOPO
        # =========================================================================
        grp_autocrop = QtWidgets.QGroupBox("Inteligência de Recorte Automático (Auto Crop)")
        f_ac = grp_autocrop.font(); f_ac.setBold(True); grp_autocrop.setFont(f_ac)
        grp_autocrop.setStyleSheet("QLabel, QComboBox, QSlider, QSpinBox { font-weight: normal; }")
        lyt_ac = QtWidgets.QFormLayout(grp_autocrop)

        self.combo_ac_preset = QtWidgets.QComboBox()
        self.combo_ac_preset.addItems([
            "Padrão de Fábrica", 
            "Fundo um Pouco Escuro", 
            "Fundo Muito Escuro", 
            "Fundo um Pouco Claro", 
            "Fundo Muito Claro", 
            "Customizado"
        ])
        
        def create_ac_slider(min_val, max_val, default_val):
            s = QtWidgets.QSlider(QtCore.Qt.Horizontal)
            s.setRange(min_val, max_val)
            s.setValue(int(default_val))
            s.setTickPosition(QtWidgets.QSlider.TicksBelow)
            return s

        self.slider_ac_blur = create_ac_slider(3, 31, self.settings.get("ac_blur", 11))
        self.slider_ac_blur.setSingleStep(2)
        self.slider_ac_dilate = create_ac_slider(0, 10, self.settings.get("ac_dilate", 2))
        
        # Escala multiplicada por 100 (1500 = 15.00%)
        val_pad = int(float(self.settings.get("ac_pad", 3.0)) * 100)
        self.slider_ac_pad = create_ac_slider(0, 1500, val_pad) 
        self.slider_ac_pad.setSingleStep(25)
        self.slider_ac_pad.setPageStep(100)
        self.slider_ac_pad.setTickInterval(100)
        
        # Escala multiplicada por 100 (1000 = 10.00%)
        val_area = int(float(self.settings.get("ac_min_area", 1.5)) * 100)
        self.slider_ac_area = create_ac_slider(25, 1000, val_area) 
        self.slider_ac_area.setSingleStep(25)
        self.slider_ac_area.setPageStep(100)
        self.slider_ac_area.setTickInterval(100)

        self.lbl_ac_blur = QtWidgets.QLabel(str(self.slider_ac_blur.value()))
        self.lbl_ac_dilate = QtWidgets.QLabel(str(self.slider_ac_dilate.value()))
        self.lbl_ac_pad = QtWidgets.QLabel(f"{self.slider_ac_pad.value() / 100.0:.2f}%")
        self.lbl_ac_area = QtWidgets.QLabel(f"{self.slider_ac_area.value() / 100.0:.2f}%")

        self.combo_ac_invert = QtWidgets.QComboBox()
        self.combo_ac_invert.addItems(["Automático", "Forçar Fundo Preto", "Forçar Fundo Branco"])
        self.combo_ac_invert.setCurrentText(self.settings.get("ac_invert", "Automático"))

        self.spin_ac_max = QtWidgets.QSpinBox()
        self.spin_ac_max.setRange(0, 50)
        self.spin_ac_max.setSpecialValueText("Ilimitado")
        self.spin_ac_max.setValue(int(self.settings.get("ac_max_crops", 0)))

        def wrap_slider(lbl, sld):
            h = QtWidgets.QHBoxLayout()
            lbl.setMinimumWidth(35)
            h.addWidget(lbl)
            h.addWidget(sld)
            return h

        lyt_ac.addRow("Perfil de Detecção:", self.combo_ac_preset)
        lyt_ac.addRow("Desfoque de Fusão (Ímpar):", wrap_slider(self.lbl_ac_blur, self.slider_ac_blur))
        lyt_ac.addRow("Dilatação de Fissuras:", wrap_slider(self.lbl_ac_dilate, self.slider_ac_dilate))
        lyt_ac.addRow("Margem de Segurança:", wrap_slider(self.lbl_ac_pad, self.slider_ac_pad))
        lyt_ac.addRow("Área Mínima do Recorte:", wrap_slider(self.lbl_ac_area, self.slider_ac_area))
        
        # --- NOVA ORGANIZAÇÃO DO LAYOUT (Na mesma linha) ---
        lyt_inline_ac = QtWidgets.QHBoxLayout()
        
        # 1. Cálculo de Contraste
        lbl_contraste = QtWidgets.QLabel("Cálculo de Contraste:")
        lyt_inline_ac.addWidget(lbl_contraste)
        lyt_inline_ac.addWidget(self.combo_ac_invert)
        
        lyt_inline_ac.addSpacing(30) # Respiro visual entre os blocos
        
        # 2. Número Máximo de Quadros
        lbl_max_crops = QtWidgets.QLabel("Número Máximo de Quadros:")
        lyt_inline_ac.addWidget(lbl_max_crops)
        lyt_inline_ac.addWidget(self.spin_ac_max)
        
        # Adiciona a linha combinada ao layout do grupo Auto Crop
        lyt_ac.addRow(lyt_inline_ac)
        
        # ---> INSERIR AQUI: Controle de cor estática para os recortes
        lyt_ac_bg = QtWidgets.QHBoxLayout()
        
        self.chk_ac_custom_bg = QtWidgets.QCheckBox("Usar cor de fundo customizada para os recortes")
        self.chk_ac_custom_bg.setChecked(self.settings.get("ac_use_custom_bg", False))
        
        lbl_ac_bg_color = QtWidgets.QLabel("Cor de fundo:")
        
        self.combo_ac_bg_color = QtWidgets.QComboBox()
        self.combo_ac_bg_color.addItems(["Preto", "Branco", "Cinza"])
        
        saved_ac_bg = self.settings.get("ac_bg_color", "Preto")
        if saved_ac_bg not in ["Preto", "Branco", "Cinza"]:
            self.combo_ac_bg_color.addItem(saved_ac_bg)
            
        self.combo_ac_bg_color.addItem("Customizado...")
        
        self.combo_ac_bg_color.blockSignals(True)
        self.combo_ac_bg_color.setCurrentText(saved_ac_bg)
        self.combo_ac_bg_color.blockSignals(False)
        
        self.combo_ac_bg_color.currentTextChanged.connect(self._on_ac_bg_color_changed)
        
        # Lógica visual: ativa/desativa os componentes dinamicamente
        self.combo_ac_bg_color.setEnabled(self.chk_ac_custom_bg.isChecked())
        lbl_ac_bg_color.setEnabled(self.chk_ac_custom_bg.isChecked())
        
        self.chk_ac_custom_bg.toggled.connect(self.combo_ac_bg_color.setEnabled)
        self.chk_ac_custom_bg.toggled.connect(lbl_ac_bg_color.setEnabled)
        
        lyt_ac_bg.addWidget(self.chk_ac_custom_bg)
        lyt_ac_bg.addSpacing(15)
        lyt_ac_bg.addWidget(lbl_ac_bg_color)
        lyt_ac_bg.addWidget(self.combo_ac_bg_color)
        lyt_ac_bg.addStretch()

        lyt_ac.addRow(lyt_ac_bg)

        self.images_form_layout.addRow(grp_autocrop)
        
        # Funções para forçar o slider a travar sempre em múltiplos de 25 (0.25%) 
        def snap_and_update_pad(v):
            snapped = round(v / 25.0) * 25
            if snapped != v:
                self.slider_ac_pad.blockSignals(True)
                self.slider_ac_pad.setValue(snapped)
                self.slider_ac_pad.blockSignals(False)
            self.lbl_ac_pad.setText(f"{snapped / 100.0:.2f}%")
            self._on_ac_customized()

        def snap_and_update_area(v):
            snapped = round(v / 25.0) * 25
            if snapped != v:
                self.slider_ac_area.blockSignals(True)
                self.slider_ac_area.setValue(snapped)
                self.slider_ac_area.blockSignals(False)
            self.lbl_ac_area.setText(f"{snapped / 100.0:.2f}%")
            self._on_ac_customized()

        self.slider_ac_blur.valueChanged.connect(lambda v: self.lbl_ac_blur.setText(str(v if v % 2 != 0 else v + 1)))
        self.slider_ac_dilate.valueChanged.connect(lambda v: self.lbl_ac_dilate.setText(str(v)))
        self.slider_ac_blur.valueChanged.connect(self._on_ac_customized)
        self.slider_ac_dilate.valueChanged.connect(self._on_ac_customized)
        
        self.slider_ac_pad.valueChanged.connect(snap_and_update_pad)
        self.slider_ac_area.valueChanged.connect(snap_and_update_area)

        self.combo_ac_preset.currentTextChanged.connect(self._on_ac_preset_changed)

        saved_preset = self.settings.get("ac_preset", "Padrão de Fábrica")
        self.combo_ac_preset.blockSignals(True)
        self.combo_ac_preset.setCurrentText(saved_preset)
        self.combo_ac_preset.blockSignals(False)
        
        # =========================================================================
        # INSERÇÃO: CONTROLE DE COR DE FUNDO (COM OPÇÃO TRANSPARENTE)
        # =========================================================================
        grp_bg_control = QtWidgets.QGroupBox("Controle de Cor de Fundo")
        f_bg = grp_bg_control.font(); f_bg.setBold(True); grp_bg_control.setFont(f_bg)
        grp_bg_control.setStyleSheet("QLabel, QComboBox, QSlider, QCheckBox { font-weight: normal; }")
        lyt_bg = QtWidgets.QFormLayout(grp_bg_control)

        self.chk_bg_detect = QtWidgets.QCheckBox("Detectar e converter a cor de fundo")
        self.chk_bg_detect.setChecked(self.settings.get("bg_detect_enabled", False))

        self.slider_bg_sens = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.slider_bg_sens.setRange(-50, 50)
        self.slider_bg_sens.setValue(int(self.settings.get("bg_detect_sensitivity", 0)))
        self.slider_bg_sens.setTickPosition(QtWidgets.QSlider.TicksBelow)
        self.slider_bg_sens.setTickInterval(10)

        self.lbl_bg_sens_val = QtWidgets.QLabel(f"+{self.slider_bg_sens.value()}" if self.slider_bg_sens.value() > 0 else str(self.slider_bg_sens.value()))
        self.lbl_bg_sens_val.setMinimumWidth(35)
        self.slider_bg_sens.valueChanged.connect(lambda v: self.lbl_bg_sens_val.setText(f"+{v}" if v > 0 else str(v)))

        self.combo_bg_color = QtWidgets.QComboBox()
        # ---> LISTA ATUALIZADA AQUI <---
        self.combo_bg_color.addItems(["Preto", "Branco", "Cinza", "Transparente"])
        
        saved_bg_color = self.settings.get("bg_replace_color", "Preto")
        # ---> VERIFICAÇÃO ATUALIZADA AQUI <---
        if saved_bg_color not in ["Preto", "Branco", "Cinza", "Transparente"]:
            self.combo_bg_color.addItem(saved_bg_color)
            
        self.combo_bg_color.addItem("Customizado...")
        
        self.combo_bg_color.blockSignals(True)
        self.combo_bg_color.setCurrentText(saved_bg_color)
        self.combo_bg_color.blockSignals(False)
        
        self.combo_bg_color.currentTextChanged.connect(self._on_bg_color_changed)

        # --- NOVA ORGANIZAÇÃO DO LAYOUT (Na mesma linha) ---
        lyt_bg.addRow(self.chk_bg_detect)
        
        lyt_inline = QtWidgets.QHBoxLayout()

        # 1. Substituir cor
        lbl_cor = QtWidgets.QLabel("Substituir cor do fundo por:")
        lyt_inline.addWidget(lbl_cor)
        lyt_inline.addWidget(self.combo_bg_color)
        
        lyt_inline.addSpacing(30) # Respiro visual entre os blocos

        # 2. Sensibilidade
        lbl_sens = QtWidgets.QLabel("Sensibilidade da detecção:")
        lyt_inline.addWidget(lbl_sens)
        lyt_inline.addWidget(self.lbl_bg_sens_val)
        lyt_inline.addWidget(self.slider_bg_sens)

        # Adiciona a linha combinada ao layout do grupo
        lyt_bg.addRow(lyt_inline)

        self.images_form_layout.addRow(grp_bg_control)
        # =========================================================================

        # =========================================================================
        # 2. FORMATO E QUALIDADE DAS IMAGENS DE SAÍDA - EM BAIXO
        # =========================================================================
        images_label = QtWidgets.QLabel("<b>Formato e Qualidade das Imagens de Saída</b><br><small>Ajuste para uma boa relação de tamanho e qualidade do PDF final</small>")
        images_label.setWordWrap(True)
        self.images_form_layout.addRow(images_label)
        
        self.combo_format = QtWidgets.QComboBox()
        self.combo_format.addItems(["JPG", "PNG", "TIFF"])
        self.combo_format.setCurrentText(self.settings.get("image_format", "JPG"))
        self.combo_format.currentTextChanged.connect(self._on_image_format_changed)
        
        # --- NOVA ORGANIZAÇÃO DO LAYOUT (50% / 50%) ---
        lyt_format_inline = QtWidgets.QHBoxLayout()
        
        # ---------------------------------------------------------
        # Container da Esquerda (Ocupará 50% do espaço)
        # ---------------------------------------------------------
        self.widget_format_left = QtWidgets.QWidget()
        lyt_left = QtWidgets.QHBoxLayout(self.widget_format_left)
        lyt_left.setContentsMargins(0, 0, 15, 0) # Margem direita para não colar no meio
        
        lbl_formato = QtWidgets.QLabel("Formato de Saída:")
        lyt_left.addWidget(lbl_formato)
        lyt_left.addWidget(self.combo_format)
        
        # ---------------------------------------------------------
        # Container da Direita (Ocupará os outros 50% do espaço)
        # ---------------------------------------------------------
        self.widget_format_right = QtWidgets.QWidget()
        lyt_right = QtWidgets.QHBoxLayout(self.widget_format_right)
        lyt_right.setContentsMargins(15, 0, 0, 0) # Margem esquerda para espaçar
        
        # Container dinâmico para JPG
        self.widget_jpg = QtWidgets.QWidget()
        lyt_jpg = QtWidgets.QHBoxLayout(self.widget_jpg)
        lyt_jpg.setContentsMargins(0, 0, 0, 0)
        lbl_jpg = QtWidgets.QLabel("Qualidade JPG:")
        self.spin_jpg_quality = QtWidgets.QSpinBox()
        self.spin_jpg_quality.setRange(50, 100)
        self.spin_jpg_quality.setValue(int(self.settings.get("jpg_quality", 95)))
        self.spin_jpg_quality.setSuffix("%")
        lyt_jpg.addWidget(lbl_jpg)
        lyt_jpg.addWidget(self.spin_jpg_quality)
        
        # Container dinâmico para PNG
        self.widget_png = QtWidgets.QWidget()
        lyt_png = QtWidgets.QHBoxLayout(self.widget_png)
        lyt_png.setContentsMargins(0, 0, 0, 0)
        lbl_png = QtWidgets.QLabel("Nível Compressão PNG:")
        self.spin_png_compression = QtWidgets.QSpinBox()
        self.spin_png_compression.setRange(4, 9)
        self.spin_png_compression.setValue(int(self.settings.get("png_compression", 6)))
        lyt_png.addWidget(lbl_png)
        lyt_png.addWidget(self.spin_png_compression)
        
        # Container dinâmico para TIFF
        self.widget_tiff = QtWidgets.QWidget()
        lyt_tiff = QtWidgets.QHBoxLayout(self.widget_tiff)
        lyt_tiff.setContentsMargins(0, 0, 0, 0)
        lbl_tiff = QtWidgets.QLabel("Compressão TIFF:")
        self.combo_tiff_compression = QtWidgets.QComboBox()
        self.combo_tiff_compression.addItems(["Sem compressão", "Compressão lossless LZW", "Compressão lossless ZIP", "Compressão JPEG"])
        self.combo_tiff_compression.setCurrentText(self.settings.get("tiff_compression", "Sem compressão"))
        lyt_tiff.addWidget(lbl_tiff)
        lyt_tiff.addWidget(self.combo_tiff_compression)
        
        # Adiciona todos os layouts dinâmicos no container da direita
        lyt_right.addWidget(self.widget_jpg)
        lyt_right.addWidget(self.widget_png)
        lyt_right.addWidget(self.widget_tiff)
        
        # ---------------------------------------------------------
        # Montagem Final: Adiciona esquerda e direita com "stretch=1"
        # ---------------------------------------------------------
        lyt_format_inline.addWidget(self.widget_format_left, 1)
        lyt_format_inline.addWidget(self.widget_format_right, 1)
        
        self.images_form_layout.addRow(lyt_format_inline)
        # =========================================================================
        
        # =========================================================================
        # 3. CONTROLE DA IMAGEM CAPTURADA (POST-PROCESSING) + BOTÃO RESTAURAR
        # =========================================================================
        post_label = QtWidgets.QLabel("<b>Controle da Imagem Capturada</b><br><small>Ajustes numéricos aplicados via software após o clique de qualquer equipamento.</small>")
        post_label.setWordWrap(True)
        self.images_form_layout.addRow(post_label)
        
        def create_post_slider(default_val):
            s = QtWidgets.QSlider(QtCore.Qt.Horizontal)
            s.setRange(-50, 50)
            s.setValue(int(default_val))
            s.setTickPosition(QtWidgets.QSlider.TicksBelow)
            s.setTickInterval(10)
            return s
            
        self.slider_post_brightness = create_post_slider(self.settings.get("post_brightness", 0))
        self.slider_post_contrast = create_post_slider(self.settings.get("post_contrast", 0))
        
        def format_pct(v):
            return f"+{v}%" if v > 0 else f"{v}%"
            
        self.lbl_post_bright = QtWidgets.QLabel(format_pct(self.slider_post_brightness.value()))
        self.lbl_post_bright.setMinimumWidth(45)
        self.slider_post_brightness.valueChanged.connect(lambda v: self.lbl_post_bright.setText(format_pct(v)))
        
        self.lbl_post_contrast = QtWidgets.QLabel(format_pct(self.slider_post_contrast.value()))
        self.lbl_post_contrast.setMinimumWidth(45)
        self.slider_post_contrast.valueChanged.connect(lambda v: self.lbl_post_contrast.setText(format_pct(v)))
        
        lyt_pb = QtWidgets.QHBoxLayout()
        lyt_pb.addWidget(self.lbl_post_bright)
        lyt_pb.addWidget(self.slider_post_brightness)
        
        lyt_pc = QtWidgets.QHBoxLayout()
        lyt_pc.addWidget(self.lbl_post_contrast)
        lyt_pc.addWidget(self.slider_post_contrast)
        
        # ---> NOVA ORGANIZAÇÃO DO LAYOUT (Na mesma linha) <---
        lyt_inline_post = QtWidgets.QHBoxLayout()
        
        lbl_brilho = QtWidgets.QLabel("Brilho:")
        lyt_inline_post.addWidget(lbl_brilho)
        lyt_inline_post.addLayout(lyt_pb)
        
        lyt_inline_post.addSpacing(30) # Respiro visual entre os blocos
        
        lbl_contraste = QtWidgets.QLabel("Contraste:")
        lyt_inline_post.addWidget(lbl_contraste)
        lyt_inline_post.addLayout(lyt_pc)
        
        btn_reset_post = QtWidgets.QPushButton(" Restaurar padrões de fábrica")
        btn_reset_post.setIcon(QtGui.QIcon.fromTheme("edit-clear"))
        btn_reset_post.clicked.connect(self._reset_post_capture_defaults)
        
        lyt_btn_post = QtWidgets.QHBoxLayout()
        lyt_btn_post.addStretch()
        lyt_btn_post.addWidget(btn_reset_post)
        
        # Adiciona a linha combinada (Brilho + Contraste) ao form layout principal
        self.images_form_layout.addRow(lyt_inline_post)
        self.images_form_layout.addRow("", lyt_btn_post)

        self.tabs.addTab(tab, "Imagens")
        self._on_image_format_changed(self.combo_format.currentText())

    def _on_ac_bg_color_changed(self, text):
        """Abre o seletor nativo do Qt para a cor de fundo do Auto Crop (sem canal Alpha)."""
        if text == "Customizado...":
            initial_color = QtGui.QColor(QtCore.Qt.black)
            current_saved = self.settings.get("ac_bg_color", "Preto")
            
            if current_saved.startswith("#"):
                initial_color = QtGui.QColor(current_saved)
            elif current_saved == "Branco":
                initial_color = QtGui.QColor(QtCore.Qt.white)
            elif current_saved == "Cinza":
                initial_color = QtGui.QColor(QtCore.Qt.gray)

            # Usa o seletor padrão (sem o ShowAlphaChannel, já que para o recorte precisamos de RGB sólido)
            color = QtWidgets.QColorDialog.getColor(
                initial_color, 
                self, 
                "Escolher cor de fundo para o Auto Crop"
            )
            
            if color.isValid():
                hex_val = color.name().upper()
                
                if self.combo_ac_bg_color.findText(hex_val) == -1:
                    idx = self.combo_ac_bg_color.count() - 1
                    self.combo_ac_bg_color.insertItem(idx, hex_val)
                
                self.combo_ac_bg_color.blockSignals(True)
                self.combo_ac_bg_color.setCurrentText(hex_val)
                self.combo_ac_bg_color.blockSignals(False)
                
                self.settings["ac_bg_color"] = hex_val 
            else:
                self.combo_ac_bg_color.blockSignals(True)
                self.combo_ac_bg_color.setCurrentText(self.settings.get("ac_bg_color", "Preto"))
                self.combo_ac_bg_color.blockSignals(False)
                
    def _on_bg_color_changed(self, text):
        if text == "Customizado...":
            initial_color = QtGui.QColor(QtCore.Qt.black)
            current_saved = self.settings.get("bg_replace_color", "Preto")
            
            if current_saved.startswith("#"):
                initial_color = QtGui.QColor(current_saved)
            elif current_saved == "Branco":
                initial_color = QtGui.QColor(QtCore.Qt.white)
            elif current_saved == "Cinza":
                initial_color = QtGui.QColor(QtCore.Qt.gray)
            elif current_saved == "Transparente":
                initial_color = QtGui.QColor(QtCore.Qt.transparent)

            # Abre o seletor nativo do Qt com suporte a canal Alpha (Transparência)
            color = QtWidgets.QColorDialog.getColor(
                initial_color, 
                self, 
                "Escolher cor de fundo customizada",
                QtWidgets.QColorDialog.ShowAlphaChannel
            )
            
            if color.isValid():
                # Usa formato hexadecimal com Alpha (ex: #AARRGGBB) se não for totalmente opaco, ou padrão #RRGGBB
                if color.alpha() < 255:
                    hex_val = color.name(QtGui.QColor.HexArgb).upper()
                else:
                    hex_val = color.name().upper()
                
                if self.combo_bg_color.findText(hex_val) == -1:
                    idx = self.combo_bg_color.count() - 1
                    self.combo_bg_color.insertItem(idx, hex_val)
                
                self.combo_bg_color.blockSignals(True)
                self.combo_bg_color.setCurrentText(hex_val)
                self.combo_bg_color.blockSignals(False)
                
                self.settings["bg_replace_color"] = hex_val 
            else:
                self.combo_bg_color.blockSignals(True)
                self.combo_bg_color.setCurrentText(self.settings.get("bg_replace_color", "Preto"))
                self.combo_bg_color.blockSignals(False)
                
    def _on_image_format_changed(self, fmt):
        if hasattr(self, 'widget_jpg'):
            self.widget_jpg.setVisible(fmt == "JPG")
        if hasattr(self, 'widget_png'):
            self.widget_png.setVisible(fmt == "PNG")
        if hasattr(self, 'widget_tiff'):
            self.widget_tiff.setVisible(fmt == "TIFF")

    def _safe_set_combo(self, combo, text):
        """Verifica se o texto existe no QComboBox. Se não, insere antes de 'Customizado...'."""
        if combo.findText(text) == -1:
            idx = max(0, combo.count() - 1)
            combo.insertItem(idx, text)
        combo.blockSignals(True)
        combo.setCurrentText(text)
        combo.blockSignals(False)

    def _sync_settings_to_ui(self):
        """Lê self.settings e atualiza o estado de todos os widgets visuais da tela."""
        # --- Aba Dispositivos ---
        if hasattr(self, 'combo_source'):
            self.combo_source.setCurrentText(self.settings.get("input_source", "Câmeras"))
        if hasattr(self, 'combo_scanner_dpi'):
            self.combo_scanner_dpi.setCurrentText(str(self.settings.get("scanner_dpi", "300")))
            self.combo_scanner_mode.setCurrentText(self.settings.get("scanner_color_mode", "Color"))
            self.combo_scanner_source.setCurrentText(self.settings.get("scanner_source", "Flatbed"))
            self.combo_scanner_paper.setCurrentText(self.settings.get("scanner_paper_size", "Máximo do Vidro"))
            self.slider_scanner_brightness.setValue(self.settings.get("scanner_brightness", 0))
            self.slider_scanner_contrast.setValue(self.settings.get("scanner_contrast", 0))

        # --- Aba Imagens (Auto-Crop e Fundo) ---
        if hasattr(self, 'combo_ac_preset'):
            self.combo_ac_preset.blockSignals(True)
            self.combo_ac_preset.setCurrentText(self.settings.get("ac_preset", "Padrão de Fábrica"))
            self.combo_ac_preset.blockSignals(False)
            
            self.slider_ac_blur.setValue(self.settings.get("ac_blur", 11))
            self.slider_ac_dilate.setValue(self.settings.get("ac_dilate", 2))
            self.slider_ac_pad.setValue(int(float(self.settings.get("ac_pad", 3.0)) * 100))
            self.slider_ac_area.setValue(int(float(self.settings.get("ac_min_area", 1.5)) * 100))
            self.combo_ac_invert.setCurrentText(self.settings.get("ac_invert", "Automático"))
            self.spin_ac_max.setValue(int(self.settings.get("ac_max_crops", 0)))
            
            self.chk_ac_custom_bg.setChecked(self.settings.get("ac_use_custom_bg", False))
            self._safe_set_combo(self.combo_ac_bg_color, self.settings.get("ac_bg_color", "Preto"))

            self.chk_bg_detect.setChecked(self.settings.get("bg_detect_enabled", False))
            self.slider_bg_sens.setValue(int(self.settings.get("bg_detect_sensitivity", 0)))
            self._safe_set_combo(self.combo_bg_color, self.settings.get("bg_replace_color", "Preto"))

        # --- Aba Imagens (Formatos e Post) ---
        if hasattr(self, 'combo_format'):
            self.combo_format.setCurrentText(self.settings.get("image_format", "JPG"))
            self.spin_jpg_quality.setValue(int(self.settings.get("jpg_quality", 95)))
            self.spin_png_compression.setValue(int(self.settings.get("png_compression", 6)))
            self.combo_tiff_compression.setCurrentText(self.settings.get("tiff_compression", "Sem compressão"))
            
            self.slider_post_brightness.setValue(self.settings.get("post_brightness", 0))
            self.slider_post_contrast.setValue(self.settings.get("post_contrast", 0))

        # --- Aba Marcadores ---
        if hasattr(self, 'combo_left'):
            self.combo_left.setCurrentText(self.settings.get("marker_color_left", "Vermelho"))
            self.combo_right.setCurrentText(self.settings.get("marker_color_right", "Verde"))
            self._safe_set_combo(self.combo_fill_color, self.settings.get("marker_fill_color", "Transparente"))
            
            self.slider_opacity.setValue(int(self.settings.get("marker_opacity", 8)))
            self.slider_weight.setValue(int(self.settings.get("marker_thickness_weight", 100)))
            
            self.spin_border_width.setValue(int(self.settings.get("image_border_width", 1)))
            self.combo_border_color.setCurrentText(self.settings.get("image_border_color", "Preto"))
            self.slider_border_opacity.setValue(int(self.settings.get("image_border_opacity", 100)))
            self.combo_border_style.setCurrentText(self.settings.get("image_border_style", "Contínuo"))

        # --- Aba Orientação ---
        if hasattr(self, 'combo_rot_left'):
            self.combo_rot_left.setCurrentText(self.settings.get("rotation_left", "0°"))
            self.combo_rot_right.setCurrentText(self.settings.get("rotation_right", "0°"))

        # --- Aba Processar ---
        if hasattr(self, 'chk_crop'):
            self.chk_crop.setChecked(self.settings.get("proc_crop", True))
            self.chk_contour_deskew.setChecked(self.settings.get("proc_contour_deskew", False))
            self.chk_deskew.setChecked(self.settings.get("proc_deskew", True))
            self.chk_dewarp.setChecked(self.settings.get("proc_dewarp", False))
            self.chk_pdf.setChecked(self.settings.get("proc_pdf", True))
            self.chk_ignore_ends.setChecked(self.settings.get("ignore_ends", False))
            
            self.slider_deskew_agg.setValue(int(self.settings.get("deskew_aggressiveness", 1.0) * 100))
            self.slider_dewarp_agg.setValue(int(self.settings.get("dewarp_aggressiveness", 1.0) * 100))
            
            pdf_src = self.settings.get("pdf_source", "tratadas")
            if pdf_src == "entrada": self.rb_entrada.setChecked(True)
            elif pdf_src == "originais": self.rb_originais.setChecked(True)
            else: self.rb_tratadas.setChecked(True)
            
            self.chk_cleanup.setChecked(self.settings.get("cleanup_after_export", False))

        # --- Aba OCR ---
        if hasattr(self, 'chk_proc_ocr'):
            self.chk_proc_ocr.setChecked(self.settings.get("proc_ocr", False))
            self.chk_ocr_preprocess.setChecked(self.settings.get("ocr_preprocess", True))
            self.chk_manual_opencv.setChecked(self.settings.get("manual_opencv_configs", False))
            self.slider_cor_papel.setValue(self.settings.get("ocr_cor_papel", 20))
            self.slider_int_impr.setValue(self.settings.get("ocr_int_impressao", 80))
            self.slider_tam_manchas.setValue(self.settings.get("ocr_tam_manchas", 10))
            self.slider_prof_manchas.setValue(self.settings.get("ocr_prof_manchas", 0))
            self.combo_ocr_lang.setCurrentText(self.settings.get("ocr_lang", "por+eng"))
            self.spin_ocr_jobs.setValue(int(self.settings.get("ocr_jobs", 2)))
            self.chk_ocr_sidecar.setChecked(self.settings.get("ocr_sidecar", False))

        # --- Aba Custódia ---
        if hasattr(self, 'chk_hash_capture'):
            self.chk_hash_capture.setChecked(self.settings.get("custody_calc_hash_on_capture", False))
            self.chk_premis.setChecked(self.settings.get("custody_log_premis", True))
            self.chk_bagit.setChecked(self.settings.get("custody_export_bagit", False))
            self.chk_tsv.setChecked(self.settings.get("custody_export_tsv", False))
            self.chk_tsv_hash.setChecked(self.settings.get("custody_tsv_include_hash", False))
            self.chk_tsv_ocr.setChecked(self.settings.get("custody_tsv_include_ocr", False))
            self.combo_tsv_granularity.setCurrentText(self.settings.get("custody_tsv_granularity", "2. Registo por Imagem (Ao nível da Página)"))

        # --- Aba Calibração (Optuna) ---
        if hasattr(self, 'spin_opt_sessions'):
            self.spin_opt_sessions.setValue(int(self.settings.get("optuna_sessions", 3)))
            self.spin_opt_samples.setValue(int(self.settings.get("optuna_samples", 3)))
            
            saved_trials = self.settings.get("optuna_trials", 150)
            idx = self.combo_opt_trials.findData(saved_trials)
            if idx >= 0: self.combo_opt_trials.setCurrentIndex(idx)
            
            # ---> INÍCIO DA CORREÇÃO: Sincronizar as labels da IA na tela
            if hasattr(self, 'lbl_ai_blur'):
                # val_blur = self.settings.get("ac_blur", 11)
                # val_dilate = self.settings.get("ac_dilate", 2)
                val_denoise = self.settings.get("ocr_denoise_h", 0.0)
                val_clahe = self.settings.get("ocr_clahe_clip", 1.0)
                val_block = self.settings.get("ocr_block_size", 11)
                val_c = self.settings.get("ocr_c_val", 2)

                # self.lbl_ai_blur.setText(f"Crop-Blur: {val_blur}  ")
                # self.lbl_ai_dilate.setText(f"Crop-Dilate: {val_dilate}  ")
                self.lbl_ai_denoise.setText(f"Denoise: {val_denoise:.2f}  ")
                self.lbl_ai_clahe.setText(f"CLAHE: {val_clahe:.2f}  ")
                self.lbl_ai_block.setText(f"Bloco: {val_block}  ")
                self.lbl_ai_c.setText(f"Valor C: {val_c}  ")
            # ---> FIM DA CORREÇÃO

        # --- Aba Retificar (Fish-eye) ---
        if hasattr(self, 'chk_use_rectify'):
            self.chk_use_rectify.setChecked(self.settings.get("use_fisheye_rectification", False))
            
            # Sincroniza a lista de strings com as chaves mestres do dicionário pai
            self.combo_checker_profile.blockSignals(True)
            self.combo_checker_profile.clear()
            profiles_db = self.settings.get("fisheye_profiles", {})
            self.combo_checker_profile.addItems(list(profiles_db.keys()))
            
            last_profile = self.settings.get("last_fisheye_profile", "")
            last_angle = self.settings.get("last_fisheye_angle", 180)
            
            if last_profile and self.combo_checker_profile.findText(last_profile) != -1:
                self.combo_checker_profile.setCurrentText(last_profile)
            else:
                if self.combo_checker_profile.count() > 0:
                    self.combo_checker_profile.setCurrentIndex(0)
            
            self.spin_checker_angle.blockSignals(True)
            self.spin_checker_angle.setValue(last_angle)
            self.spin_checker_angle.blockSignals(False)

            self.combo_checker_profile.blockSignals(False)

            # Agora sim, dispara uma única vez
            self._load_rectify_profile_metadata(self.combo_checker_profile.currentText())
            
        if hasattr(self, 'chk_use_simulated'):
            self.chk_use_simulated.setChecked(self.settings.get("use_simulated_rectification", False))

                            
    def _on_ac_preset_changed(self, preset_name):
        presets = {
            # Formato: [blur, dilate, pad (%), min_area (%), invert_mode]
            "Padrão de Fábrica":     [11, 2, 3.0, 1.5, "Automático"],
            "Fundo um Pouco Escuro": [9,  1, 2.0, 1.0, "Forçar Fundo Preto"],
            "Fundo Muito Escuro":    [21, 4, 4.0, 2.5, "Forçar Fundo Preto"],
            "Fundo um Pouco Claro":  [9,  1, 2.0, 1.0, "Forçar Fundo Branco"],
            "Fundo Muito Claro":     [25, 5, 3.0, 2.0, "Forçar Fundo Branco"]
        }
        
        if preset_name in presets:
            vals = presets[preset_name]
            
            self.slider_ac_blur.blockSignals(True)
            self.slider_ac_dilate.blockSignals(True)
            self.slider_ac_pad.blockSignals(True)
            self.slider_ac_area.blockSignals(True)
            self.combo_ac_invert.blockSignals(True)
            
            self.slider_ac_blur.setValue(vals[0]); self.lbl_ac_blur.setText(str(vals[0]))
            self.slider_ac_dilate.setValue(vals[1]); self.lbl_ac_dilate.setText(str(vals[1]))
            self.slider_ac_pad.setValue(int(vals[2] * 100)); self.lbl_ac_pad.setText(f"{vals[2]:.2f}%")
            self.slider_ac_area.setValue(int(vals[3] * 100)); self.lbl_ac_area.setText(f"{vals[3]:.2f}%")         
            self.combo_ac_invert.setCurrentText(vals[4])
            
            self.slider_ac_blur.blockSignals(False)
            self.slider_ac_dilate.blockSignals(False)
            self.slider_ac_pad.blockSignals(False)
            self.slider_ac_area.blockSignals(False)
            self.combo_ac_invert.blockSignals(False)

    def _on_ac_customized(self, *args):
        if self.combo_ac_preset.currentText() != "Customizado":
            self.combo_ac_preset.blockSignals(True)
            self.combo_ac_preset.setCurrentText("Customizado")
            self.combo_ac_preset.blockSignals(False)

    def _build_project_tab(self):
        tab = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(tab)
        info_label = QtWidgets.QLabel("<b>Pasta de Trabalho Ativa<bb><br></b><small>Todas as capturas e metadados JSON serão centralizados neste diretório</small>")
        info_label.setWordWrap(True)
        layout.addWidget(info_label)
        
        path_layout = QtWidgets.QHBoxLayout()
        
        self.combo_path = QtWidgets.QComboBox()
        self.combo_path.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        
        recent_projects = self.settings.get("recent_projects", [])
        current_dir = self.settings.get("working_dir", "")
        
        if current_dir and current_dir not in recent_projects:
            recent_projects.insert(0, current_dir)
            
        self.combo_path.addItems(recent_projects)
        self.combo_path.setCurrentText(current_dir)
        self.combo_path.currentTextChanged.connect(self._load_project_metadata)
        
        btn_browse = QtWidgets.QPushButton("Selecionar/Importar/Criar")
        btn_browse.setIcon(QtGui.QIcon.fromTheme("folder-new"))
        btn_browse.clicked.connect(self._on_browse_directory)
        
        path_layout.addWidget(self.combo_path)
        path_layout.addWidget(btn_browse)
        layout.addLayout(path_layout)
        
        mode_label = QtWidgets.QLabel("<br><b>Modo de Operação do Projeto</b><br><small>Atenção: O modo define a topologia de captura e não pode ser alterado após a criação do lote.</small>")
        mode_label.setWordWrap(True)
        layout.addWidget(mode_label)

        self.combo_project_mode = QtWidgets.QComboBox()
        self.combo_project_mode.addItems(["Berço em V (Página Dupla)", "Mesa Plana (Câmera Única)"])
        self.combo_project_mode.setCurrentText(self.settings.get("project_mode", "Berço em V (Página Dupla)"))
        self.combo_project_mode.currentTextChanged.connect(self._toggle_scanner_options)
        layout.addWidget(self.combo_project_mode)
        
        integ_label = QtWidgets.QLabel("<br><b>Verificação de Integridade dos Arquivos</b><br><small>Aviso: Desativar acelera o carregamento, mas ignora alertas de adulteração física.</small>")
        integ_label.setWordWrap(True)
        layout.addWidget(integ_label)

        self.combo_integrity_check = QtWidgets.QComboBox()
        self.combo_integrity_check.addItems(["Com verificação de integridade", "Sem verificação de integridade"])
        self.combo_integrity_check.setCurrentText(self.settings.get("project_integrity_check", "Com verificação de integridade"))
        layout.addWidget(self.combo_integrity_check)

        meta_label = QtWidgets.QLabel("<br><b>Metadados Descritivos do Projeto</b><br><small>Os metadados inseridos aqui serão gravados no PDF/A final</small>")
        meta_label.setWordWrap(True)
        layout.addWidget(meta_label)
        
        meta_frame = QtWidgets.QFrame()
        meta_frame.setFrameShape(QtWidgets.QFrame.StyledPanel)
        meta_frame.setFrameShadow(QtWidgets.QFrame.Plain)

        meta_layout = QtWidgets.QFormLayout(meta_frame)

        self.line_proj_title = QtWidgets.QLineEdit()
        self.line_proj_desc = QtWidgets.QLineEdit()

        self.lbl_proj_created = QtWidgets.QLabel()
        self.lbl_proj_created.setStyleSheet(
            "color: #7f8c8d; font-style: italic;"
        )

        self.line_proj_publisher = QtWidgets.QLineEdit()
        self.line_proj_collection = QtWidgets.QLineEdit()
        self.line_proj_creator = QtWidgets.QLineEdit()

        meta_layout.addRow("Nome do Projeto:", self.line_proj_title)
        meta_layout.addRow("Descrição:", self.line_proj_desc)
        meta_layout.addRow("Data de Criação:", self.lbl_proj_created)
        meta_layout.addRow("Editor/Instituição:", self.line_proj_publisher)
        meta_layout.addRow("Fundo/Coleção:", self.line_proj_collection)
        meta_layout.addRow("Operador (Criador):", self.line_proj_creator)

        layout.addWidget(meta_frame)
        layout.addStretch()
        self.tabs.addTab(tab, "Projeto")

    def _load_project_metadata(self, dir_path):
        self.line_proj_title.setText("")
        self.line_proj_desc.setText("")
        self.line_proj_publisher.setText("")
        self.line_proj_collection.setText("")
        
        try:
            default_user = getpass.getuser()
        except Exception:
            default_user = "Operador"
            
        self.line_proj_creator.setText(default_user)
        self.lbl_proj_created.setText("Será gerada automaticamente ao salvar")
        
        if hasattr(self, 'combo_project_mode'):
            self.combo_project_mode.setEnabled(True)
            self.combo_project_mode.setToolTip("Selecione o modo de captura para este novo projeto.")

        if not dir_path or not os.path.exists(dir_path):
            return

        proj_file = os.path.join(dir_path, "project.json")
        if os.path.exists(proj_file):
            try:
                with open(proj_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    meta = data.get("metadata", {})
                    self.line_proj_title.setText(meta.get("dcterms:title", ""))
                    self.line_proj_desc.setText(meta.get("dcterms:description", ""))
                    self.line_proj_publisher.setText(meta.get("dcterms:publisher", ""))
                    self.line_proj_collection.setText(meta.get("schema:collection", ""))
                    self.line_proj_creator.setText(meta.get("dcterms:creator", default_user))
                    
                    created = meta.get("dcterms:created", "")
                    if created: self.lbl_proj_created.setText(created)
                        
                    ocr_params = data.get("ocr_params", {})
                    if ocr_params and hasattr(self, 'chk_proc_ocr'):
                        self.chk_proc_ocr.setChecked(ocr_params.get("proc_ocr", self.settings.get("proc_ocr", False)))
                        self.chk_ocr_preprocess.setChecked(ocr_params.get("ocr_preprocess", self.settings.get("ocr_preprocess", True)))
                        self.slider_cor_papel.setValue(ocr_params.get("ocr_cor_papel", self.settings.get("ocr_cor_papel", 20)))
                        self.slider_int_impr.setValue(ocr_params.get("ocr_int_impressao", self.settings.get("ocr_int_impressao", 80)))
                        self.slider_tam_manchas.setValue(ocr_params.get("ocr_tam_manchas", self.settings.get("ocr_tam_manchas", 10)))
                        self.slider_prof_manchas.setValue(ocr_params.get("ocr_prof_manchas", self.settings.get("ocr_prof_manchas", 0)))
                        self.combo_ocr_lang.setCurrentText(ocr_params.get("ocr_lang", self.settings.get("ocr_lang", "por+eng")))
                        self.spin_ocr_jobs.setValue(ocr_params.get("ocr_jobs", self.settings.get("ocr_jobs", 2)))
                        self.chk_ocr_sidecar.setChecked(ocr_params.get("ocr_sidecar", self.settings.get("ocr_sidecar", False)))

                    capture_params = data.get("capture_params", {})
                    if capture_params:
                        if hasattr(self, 'combo_source'):
                            self.combo_source.setCurrentText(capture_params.get("input_source", self.settings.get("input_source", "Câmeras")))
                        if hasattr(self, 'combo_project_mode'):
                            if hasattr(self, 'combo_integrity_check'):
                                self.combo_integrity_check.setCurrentText(capture_params.get("project_integrity_check", self.settings.get("project_integrity_check", "Com verificação de integridade")))
                            proj_mode = capture_params.get("project_mode")
                            if proj_mode:
                                self.combo_project_mode.setCurrentText(proj_mode)
                                self.combo_project_mode.setEnabled(False) 
                                self.combo_project_mode.setToolTip("O modo de operação não pode ser alterado num projeto já existente.")
                                self._toggle_scanner_options(proj_mode) 
                        if hasattr(self, 'combo_rot_left'):
                            self.combo_rot_left.setCurrentText(capture_params.get("rotation_left", self.settings.get("rotation_left", "0°")))
                        if hasattr(self, 'combo_rot_right'):
                            self.combo_rot_right.setCurrentText(capture_params.get("rotation_right", self.settings.get("rotation_right", "0°")))
                            
                    custody_params = data.get("custody_params", {})
                    if custody_params and hasattr(self, 'chk_hash_capture'):
                        self.chk_hash_capture.setChecked(custody_params.get("calc_hash_on_capture", self.settings.get("custody_calc_hash_on_capture", False)))
                        self.chk_premis.setChecked(custody_params.get("log_premis", self.settings.get("custody_log_premis", True)))
                        self.chk_bagit.setChecked(custody_params.get("export_bagit", self.settings.get("custody_export_bagit", False)))
                        self.chk_tsv.setChecked(custody_params.get("export_tsv", self.settings.get("custody_export_tsv", False)))
                        self.chk_tsv_hash.setChecked(custody_params.get("tsv_include_hash", self.settings.get("custody_tsv_include_hash", False)))
                        self.chk_tsv_ocr.setChecked(custody_params.get("tsv_include_ocr", self.settings.get("custody_tsv_include_ocr", False)))
                        granularity = custody_params.get("tsv_granularity")
                        if granularity:
                            self.combo_tsv_granularity.setCurrentText(granularity)

            except Exception:
                pass 

    def _save_project_metadata(self, dir_path):
        if not dir_path: return
        os.makedirs(dir_path, exist_ok=True)
        
        proj_file = os.path.join(dir_path, "project.json")
        data = {}
        
        if os.path.exists(proj_file):
            try:
                with open(proj_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            except:
                pass
                
        if "metadata" not in data: data["metadata"] = {}
        if "provenance" not in data: data["provenance"] = {}
        if "files" not in data: data["files"] = []
        
        created = data["metadata"].get("dcterms:created")
        if not created:
            created = datetime.now().isoformat(timespec='seconds')
            
        data["metadata"].update({
            "dcterms:title": self.line_proj_title.text().strip(),
            "dcterms:description": self.line_proj_desc.text().strip(),
            "dcterms:created": created,
            "dcterms:publisher": self.line_proj_publisher.text().strip(),
            "dcterms:creator": self.line_proj_creator.text().strip(),
            "schema:collection": self.line_proj_collection.text().strip()
        })
        
        gui_env = os.environ.get('XDG_CURRENT_DESKTOP') or os.environ.get('DESKTOP_SESSION') or "Desconhecido"
        data["provenance"].update({
            "hostname": socket.gethostname(),
            "os_name": platform.system(),
            "os_version": platform.release(),
            "cpu": platform.processor(),
            "gui_environment": gui_env
        })
        
        if hasattr(self, 'chk_proc_ocr'):
            data["ocr_params"] = {
                "proc_ocr": self.chk_proc_ocr.isChecked(),
                "ocr_preprocess": self.chk_ocr_preprocess.isChecked(),
                "ocr_cor_papel": self.slider_cor_papel.value(),
                "ocr_int_impressao": self.slider_int_impr.value(),
                "ocr_tam_manchas": self.slider_tam_manchas.value(),
                "ocr_prof_manchas": self.slider_prof_manchas.value(),
                "ocr_lang": self.combo_ocr_lang.currentText(),
                "ocr_jobs": self.spin_ocr_jobs.value(),
                "ocr_sidecar": self.chk_ocr_sidecar.isChecked()
            }
            
            # ---> INÍCIO DA INSERÇÃO: Sincroniza a memória da IA com o manifesto do projeto <---
            optuna_keys = ["ac_blur", "ac_dilate", "ac_invert", "ocr_denoise_h", "ocr_clahe_clip", "ocr_block_size", "ocr_c_val", "search_space_mode"]
            optuna_data = {}
            for k in optuna_keys:
                if k in self.settings:
                    optuna_data[k] = self.settings[k]
                    
            if optuna_data:
                data["optuna_params"] = optuna_data
            # ---> FIM DA INSERÇÃO <---
            
        if hasattr(self, 'combo_source'):
            data["capture_params"] = {
                "input_source": self.combo_source.currentText(),
                "rotation_left": self.combo_rot_left.currentText(),
                "rotation_right": self.combo_rot_right.currentText(),
                "project_mode": self.combo_project_mode.currentText(),
                "project_integrity_check": self.combo_integrity_check.currentText() 
            }
            
        if hasattr(self, 'chk_hash_capture'):
            data["custody_params"] = {
                "calc_hash_on_capture": self.chk_hash_capture.isChecked(),
                "log_premis": self.chk_premis.isChecked(),
                "export_bagit": self.chk_bagit.isChecked(),
                "export_tsv": self.chk_tsv.isChecked(),
                "tsv_include_hash": self.chk_tsv_hash.isChecked(),
                "tsv_include_ocr": self.chk_tsv_ocr.isChecked(),
                "tsv_granularity": self.combo_tsv_granularity.currentText()
            }
        
        try:
            with open(proj_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
        except Exception:
            pass

    def _on_browse_directory(self):
        current_dir = self.combo_path.currentText()
        selected_dir = QtWidgets.QFileDialog.getExistingDirectory(
            self,
            "Selecionar ou Criar Pasta",
            current_dir,
            QtWidgets.QFileDialog.ShowDirsOnly
        )
        if selected_dir:
            idx = self.combo_path.findText(selected_dir)
            if idx >= 0:
                self.combo_path.setCurrentIndex(idx)
            else:
                self.combo_path.insertItem(0, selected_dir)
                self.combo_path.setCurrentIndex(0)

    def _on_browse_export_dir(self):
        current_dir = self.line_export_path.text()
        selected_dir = QtWidgets.QFileDialog.getExistingDirectory(
            self, 
            "Selecionar Pasta de Destino para o PDF Final", 
            current_dir, 
            QtWidgets.QFileDialog.ShowDirsOnly
        )
        if selected_dir:
            self.line_export_path.setText(selected_dir)

    def _build_process_tab(self):
        tab = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(tab)
        
        batch_title = QtWidgets.QLabel("<b>Ações para Executar em Lote</b><br><small>Selecione os algoritmos padrão que rodarão na exportação do projeto</small>")
        batch_title.setWordWrap(True)
        layout.addWidget(batch_title)
        
        grp_geom = QtWidgets.QFrame()
        grp_geom.setFrameShape(QtWidgets.QFrame.StyledPanel)
        lyt_geom = QtWidgets.QVBoxLayout(grp_geom)
        
        self.chk_crop = QtWidgets.QCheckBox("Cortar (Crop)")
        self.chk_crop.setChecked(self.settings.get("proc_crop", True))
        
        # ---> NOVO LOCAL: Checkbox do Deskew de Contorno movido para cima <---
        self.chk_contour_deskew = QtWidgets.QCheckBox("Alinhamento Horizontal de Imagens/Fotos")
        self.chk_contour_deskew.setChecked(self.settings.get("proc_contour_deskew", False))
        self.chk_contour_deskew.setToolTip("Alinha a imagem baseando-se no contorno estrutural externo (borda do objeto/papel).")
        
        self.chk_deskew = QtWidgets.QCheckBox("Alinhamento de Imagens com Texto")
        self.chk_deskew.setChecked(self.settings.get("proc_deskew", True))
        
        self.chk_dewarp = QtWidgets.QCheckBox("Planificação Geométrica")
        self.chk_dewarp.setChecked(self.settings.get("proc_dewarp", False))
        
        self.chk_pdf = QtWidgets.QCheckBox("Produzir PDF Unificado no Final")
        self.chk_pdf.setChecked(self.settings.get("proc_pdf", True))
        
        self.chk_ignore_ends = QtWidgets.QCheckBox("Ignorar primeira e última imagens (capas vazias no berço em V)")
        self.chk_ignore_ends.setChecked(self.settings.get("ignore_ends", False))
        self.chk_ignore_ends.setToolTip("Se marcado, o sistema não processará nem incluirá no PDF a primeira e a última foto do lote.")
        
        def create_agg_slider(default_val):
            slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
            slider.setRange(50, 150)
            slider.setValue(int(default_val * 100))
            slider.setTickPosition(QtWidgets.QSlider.TicksBelow)
            slider.setTickInterval(10)
            return slider

        self.slider_deskew_agg = create_agg_slider(self.settings.get("deskew_aggressiveness", 1.0))
        self.slider_dewarp_agg = create_agg_slider(self.settings.get("dewarp_aggressiveness", 1.0))

        self.lbl_deskew_val = QtWidgets.QLabel(f"<b>{self.slider_deskew_agg.value()}%</b>")
        self.lbl_dewarp_val = QtWidgets.QLabel(f"<b>{self.slider_dewarp_agg.value()}%</b>")
        self.lbl_deskew_val.setMinimumWidth(40)
        self.lbl_dewarp_val.setMinimumWidth(40)

        self.slider_deskew_agg.valueChanged.connect(lambda v: self.lbl_deskew_val.setText(f"<b>{v}%</b>"))
        self.slider_dewarp_agg.valueChanged.connect(lambda v: self.lbl_dewarp_val.setText(f"<b>{v}%</b>"))

        def toggle_deskew(state):
            self.slider_deskew_agg.setEnabled(state)
            self.lbl_deskew_val.setEnabled(state)
            
        def toggle_dewarp(state):
            self.slider_dewarp_agg.setEnabled(state)
            self.lbl_dewarp_val.setEnabled(state)

        toggle_deskew(self.chk_deskew.isChecked())
        toggle_dewarp(self.chk_dewarp.isChecked())
        self.chk_deskew.toggled.connect(toggle_deskew)
        self.chk_dewarp.toggled.connect(toggle_dewarp)
        
        lyt_geom.addWidget(self.chk_crop)
        
        # ---> INSERIDO AQUI: Fica acima do "Alinhamento de Imagens com Texto" (que está no grid abaixo) <---
        lyt_geom.addWidget(self.chk_contour_deskew)
        
        # ---> INÍCIO DA CORREÇÃO: ALINHAMENTO EM GRADE <---
        grid_geom = QtWidgets.QGridLayout()
        grid_geom.setContentsMargins(0, 0, 0, 0) # Remove margens extras do grid
        grid_geom.setHorizontalSpacing(15)       # Espaçamento entre texto, % e slider
        
        # Linha 0 (Deskew)
        grid_geom.addWidget(self.chk_deskew, 0, 0)
        grid_geom.addWidget(self.lbl_deskew_val, 0, 1)
        grid_geom.addWidget(self.slider_deskew_agg, 0, 2)
        
        # Linha 1 (Dewarp)
        grid_geom.addWidget(self.chk_dewarp, 1, 0)
        grid_geom.addWidget(self.lbl_dewarp_val, 1, 1)
        grid_geom.addWidget(self.slider_dewarp_agg, 1, 2)
        
        # Força os sliders (coluna 2) a se expandirem de forma idêntica
        grid_geom.setColumnStretch(2, 1)
        
        lyt_geom.addLayout(grid_geom)
        # ---> FIM DA CORREÇÃO <---

        lyt_geom.addWidget(self.chk_pdf)
        
        lyt_geom.addWidget(self.chk_ignore_ends) 
        layout.addWidget(grp_geom)
            
        grp_pdf_source = QtWidgets.QGroupBox("Fonte de Imagens para o PDF Final")
        font_pdf = grp_pdf_source.font()
        font_pdf.setBold(True)
        grp_pdf_source.setFont(font_pdf)
        grp_pdf_source.setStyleSheet("QRadioButton { font-weight: normal; }")
        lyt_pdf = QtWidgets.QVBoxLayout(grp_pdf_source)
        
        self.rb_entrada = QtWidgets.QRadioButton("1. Imagens de Entrada")
        self.rb_entrada.setToolTip("Fotos em bruto, diretamente da câmara (inclui fundo da mesa). Ficheiro muito pesado.")
        
        self.rb_originais = QtWidgets.QRadioButton("2. Imagens Originais")
        self.rb_originais.setToolTip("Fotos com geometria corrigida (Crop/Deskew/Dewarp), mantendo as cores intactas.")
        
        self.rb_tratadas = QtWidgets.QRadioButton("3. Imagens Tratadas")
        self.rb_tratadas.setToolTip("Fotos limpas e binarizadas. Ideal para PDFs leves e focados no texto.")
        
        pdf_src = self.settings.get("pdf_source", "tratadas")
        if pdf_src == "entrada": self.rb_entrada.setChecked(True)
        elif pdf_src == "originais": self.rb_originais.setChecked(True)
        else: self.rb_tratadas.setChecked(True)
        
        lyt_pdf.addWidget(self.rb_entrada)
        lyt_pdf.addWidget(self.rb_originais)
        lyt_pdf.addWidget(self.rb_tratadas)
        layout.addWidget(grp_pdf_source)
        
        grp_export = QtWidgets.QGroupBox("Destino Final do PDF e Limpeza")
        font_exp = grp_export.font()
        font_exp.setBold(True)
        grp_export.setFont(font_exp)
        grp_export.setStyleSheet("QLabel, QLineEdit, QPushButton, QCheckBox { font-weight: normal; }")
        lyt_export = QtWidgets.QVBoxLayout(grp_export)

        lbl_export_info = QtWidgets.QLabel("<small style='color:gray;'>Selecione a pasta para onde o PDF será copiado automaticamente após a geração.</small>")
        lbl_export_info.setWordWrap(True)

        path_layout = QtWidgets.QHBoxLayout()
        self.line_export_path = QtWidgets.QLineEdit()
        self.line_export_path.setReadOnly(True)
        self.line_export_path.setText(self.settings.get("pdf_export_path", ""))

        btn_browse_export = QtWidgets.QPushButton(" Escolher Pasta...")
        btn_browse_export.setIcon(QtGui.QIcon.fromTheme("folder-open"))
        btn_browse_export.clicked.connect(self._on_browse_export_dir)

        path_layout.addWidget(self.line_export_path)
        path_layout.addWidget(btn_browse_export)

        self.chk_cleanup = QtWidgets.QCheckBox("Depois de copiar o PDF com sucesso, remover todos os arquivos temporários (Pasta 'out')")
        self.chk_cleanup.setChecked(self.settings.get("cleanup_after_export", False))
        self.chk_cleanup.setStyleSheet("color: #c0392b; font-weight: bold;")

        lyt_export.addWidget(lbl_export_info)
        lyt_export.addLayout(path_layout)
        lyt_export.addWidget(self.chk_cleanup)
        layout.addWidget(grp_export)

        btn_reset_process = QtWidgets.QPushButton(" Restaurar padrões de fábrica")
        btn_reset_process.setIcon(QtGui.QIcon.fromTheme("edit-clear"))
        btn_reset_process.clicked.connect(self._reset_process_defaults)
        
        reset_layout = QtWidgets.QHBoxLayout()
        reset_layout.addStretch()
        reset_layout.addWidget(btn_reset_process)
        layout.addLayout(reset_layout)
                    
        layout.addStretch()
        self.tabs.addTab(tab, "Processar")

    def _build_rectify_tab(self):
        tab = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(tab)
        
        info_label = QtWidgets.QLabel(
            "<b>Retificação de Câmeras Fish-eye (Grande Angular)</b><br>"
            "<small>Gerencie perfis de calibração para remover a distorção de lentes grande angulares "
            "baseando-se em amostras de tabuleiros de xadrez (checkerboard).</small>"
        )
        info_label.setWordWrap(True)
        layout.addWidget(info_label)
        
        # Controle Mestre
        self.chk_use_rectify = QtWidgets.QCheckBox("Usar retificação de grande angular")
        self.chk_use_rectify.setChecked(self.settings.get("use_fisheye_rectification", False))
        font_chk = self.chk_use_rectify.font()
        font_chk.setBold(True)
        self.chk_use_rectify.setFont(font_chk)
        layout.addWidget(self.chk_use_rectify)
        
        # Grupo de Parâmetros
        self.grp_rectify = QtWidgets.QGroupBox("Parâmetros de Calibração (Checkerboard)")
        lyt_rectify = QtWidgets.QFormLayout(self.grp_rectify)
        
        # Linha do Perfil (Combobox + Botões de Ação)
        profile_layout = QtWidgets.QHBoxLayout()
        self.combo_checker_profile = QtWidgets.QComboBox()
        self.combo_checker_profile.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        
        btn_new_profile = QtWidgets.QPushButton("Novo")
        btn_new_profile.setIcon(QtGui.QIcon.fromTheme("list-add"))
        btn_new_profile.clicked.connect(self._on_new_rectify_profile)
        
        btn_del_profile = QtWidgets.QPushButton("Excluir")
        btn_del_profile.setIcon(QtGui.QIcon.fromTheme("list-remove"))
        btn_del_profile.clicked.connect(self._on_delete_rectify_profile)
        
        profile_layout.addWidget(self.combo_checker_profile)
        profile_layout.addWidget(btn_new_profile)
        profile_layout.addWidget(btn_del_profile)
        
        self.spin_checker_angle = QtWidgets.QSpinBox()
        self.spin_checker_angle.setRange(45, 180)
        self.spin_checker_angle.setSuffix("°")
        
        self.spin_checker_x = QtWidgets.QSpinBox()
        self.spin_checker_x.setRange(2, 20)
        
        self.spin_checker_y = QtWidgets.QSpinBox()
        self.spin_checker_y.setRange(2, 20)
        
        self.spin_checker_size = QtWidgets.QSpinBox()
        self.spin_checker_size.setRange(100, 1000)
        self.spin_checker_size.setSingleStep(10)
        self.spin_checker_size.setSuffix(" mm")
        
        # Caminho das imagens de calibração
        path_layout = QtWidgets.QHBoxLayout()
        self.line_checker_path = QtWidgets.QLineEdit()
        self.line_checker_path.setReadOnly(True)
        
        btn_browse_checker = QtWidgets.QPushButton(" Escolher Pasta...")
        btn_browse_checker.setIcon(QtGui.QIcon.fromTheme("folder-open"))
        btn_browse_checker.clicked.connect(self._on_browse_checker_path)
        
        path_layout.addWidget(self.line_checker_path)
        path_layout.addWidget(btn_browse_checker)
        
        lyt_rectify.addRow("Perfil de Calibração:", profile_layout)
        lyt_rectify.addRow("Angular da câmera (Ângulo de visão):", self.spin_checker_angle)
        lyt_rectify.addRow("Linhas horizontais (Interseções internas):", self.spin_checker_x)
        lyt_rectify.addRow("Colunas verticais (Interseções internas):", self.spin_checker_y)
        lyt_rectify.addRow("Tamanho do quadro (Quadrado do xadrez):", self.spin_checker_size)
        lyt_rectify.addRow("Pasta com imagens de calibração:", path_layout)
        
        layout.addWidget(self.grp_rectify)
        
        # ---> INSERIR AQUI: Nova área "Controle de Calibração"
        self.grp_exec_calib = QtWidgets.QGroupBox("Ações de Calibração")
        lyt_exec_calib = QtWidgets.QVBoxLayout(self.grp_exec_calib)
        
        self.lbl_calib_status = QtWidgets.QLabel("Status: Aguardando execução...")
        self.lbl_calib_status.setStyleSheet("color: #7f8c8d; font-style: italic;")
        self.lbl_calib_status.setWordWrap(True)
        
        # ---> INSERIR AQUI: A barra de progresso
        self.progress_calib = QtWidgets.QProgressBar()
        self.progress_calib.setValue(0)
        self.progress_calib.setVisible(False) # Escondida até o processo começar
        
        # ---> CORREÇÃO: Adicionado o prefixo 'self.' no botão
        self.btn_exec_calib = QtWidgets.QPushButton(" Executar Calibração da Lente")
        self.btn_exec_calib.setIcon(QtGui.QIcon.fromTheme("system-run"))
        self.btn_exec_calib.setStyleSheet("background-color: #2196F3; color: white; font-weight: bold; padding: 6px;")
        
        # Conexão com o método que iniciará a Thread
        self.btn_exec_calib.clicked.connect(self._start_fisheye_calibration)
        
        lyt_exec_calib.addWidget(self.lbl_calib_status)
        lyt_exec_calib.addWidget(self.btn_exec_calib)
        
        layout.addWidget(self.grp_exec_calib)
        
        # Oculta este grupo se o checkbox mestre de retificação estiver desmarcado
        self.grp_exec_calib.setEnabled(self.chk_use_rectify.isChecked())
        self.chk_use_rectify.toggled.connect(self.grp_exec_calib.setEnabled)
        # ---> FIM DA INSERÇÃO
                
        layout.addStretch()
        
        # ---> INÍCIO DA CORREÇÃO: Carregar os dados na interface assim que a aba é construída <---
        profiles_db = self.settings.get("fisheye_profiles", {})
        self.combo_checker_profile.addItems(list(profiles_db.keys()))
        
        last_profile = self.settings.get("last_fisheye_profile", "")
        last_angle = self.settings.get("last_fisheye_angle", 180)
        
        self.combo_checker_profile.blockSignals(True)
        if last_profile and self.combo_checker_profile.findText(last_profile) != -1:
            self.combo_checker_profile.setCurrentText(last_profile)
        elif self.combo_checker_profile.count() > 0:
            self.combo_checker_profile.setCurrentIndex(0)
        self.combo_checker_profile.blockSignals(False)
        
        self.spin_checker_angle.blockSignals(True)
        self.spin_checker_angle.setValue(last_angle)
        self.spin_checker_angle.blockSignals(False)
        
        # Força o preenchimento dos campos (X, Y, Size, Path) com base no perfil selecionado acima
        self._load_rectify_profile_metadata(self.combo_checker_profile.currentText())
        # ---> FIM DA CORREÇÃO <---
        
        # Conexões de monitoramento: Mudou o perfil ou mudou o angular -> recarrega os campos específicos
        self.combo_checker_profile.currentTextChanged.connect(self._load_rectify_profile_metadata)
        self.spin_checker_angle.valueChanged.connect(self._on_angle_changed)
        
        # Lógica de ativação/desativação visual dependente do Checkbox mestre
        self.grp_rectify.setEnabled(self.chk_use_rectify.isChecked())
        self.chk_use_rectify.toggled.connect(self.grp_rectify.setEnabled)
        
        self.chk_use_rectify.toggled.connect(self._on_use_rectify_toggled)
        
        self.tabs.addTab(tab, "Retificar")

    # E adicione este método na classe:
    def _on_angle_changed(self, new_angle):
        profile_name = self.combo_checker_profile.currentText()
        if profile_name:
            # Salva o estado atual da tela na memória temporária ANTES de limpar a interface
            # Obs: Você precisaria rastrear o "ângulo anterior" para salvar corretamente, 
            # ou instruir o usuário de que mudanças não aplicadas são perdidas ao navegar.
            self._load_rectify_profile_metadata(profile_name)

    def _on_new_rectify_profile(self):
        """Prompt síncrono para criação de uma nova chave de perfil."""
        name, ok = QtWidgets.QInputDialog.getText(
            self, "Novo Perfil de Retificação", 
            "Digite o nome de identificação para o novo perfil:"
        )
        if ok and name.strip():
            name = name.strip()
            if self.combo_checker_profile.findText(name) == -1:
                self.combo_checker_profile.addItem(name)
            self.combo_checker_profile.setCurrentText(name)

    def _on_delete_rectify_profile(self):
        """Remove o perfil da memória volátil, apaga os arquivos de calibração do disco e limpa o combobox."""
        current_profile = self.combo_checker_profile.currentText()
        if not current_profile:
            return
            
        reply = QtWidgets.QMessageBox.question(
            self, "Excluir Perfil de Calibração",
            f"Tem certeza que deseja remover o perfil '{current_profile}' e excluir seus arquivos de calibração permanentemente do disco?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
        )
        
        if reply == QtWidgets.QMessageBox.Yes:
            profiles_db = self.settings.get("fisheye_profiles", {})
            if current_profile in profiles_db:
                
                # ---> INÍCIO DA EXCLUSÃO FÍSICA DOS ARQUIVOS <---
                profile_settings = profiles_db[current_profile].get("settings", {})
                for key, value in profile_settings.items():
                    # Verifica se o valor armazenado é uma string (caminho) e aponta para um arquivo .npy
                    if isinstance(value, str) and value.endswith(".npy"):
                        if os.path.exists(value):
                            try:
                                os.remove(value)
                                print(f"[Vidya] Arquivo de calibração removido com sucesso: {value}")
                            except Exception as e:
                                print(f"[Vidya] Erro ao remover arquivo de calibração {value}: {e}")
                # ---> FIM DA EXCLUSÃO FÍSICA <---

                # Agora sim, apaga o perfil da memória
                del profiles_db[current_profile]
                self.settings["fisheye_profiles"] = profiles_db
            
            # Remove da interface visual
            idx = self.combo_checker_profile.currentIndex()
            self.combo_checker_profile.removeItem(idx)
            
            # Atualiza o último perfil usado, se necessário
            if self.settings.get("last_fisheye_profile") == current_profile:
                self.settings["last_fisheye_profile"] = self.combo_checker_profile.currentText()

    def _load_rectify_profile_metadata(self, profile_name):
        """Busca na árvore JSON e popula os widgets para o par Perfil + Angulação."""
        if not profile_name:
            self.spin_checker_x.setValue(9)
            self.spin_checker_y.setValue(6)
            self.spin_checker_size.setValue(150)
            self.line_checker_path.setText("")
            return
            
        angle = self.spin_checker_angle.value()
        angle_key = f"angle_{angle}"
        profiles_db = self.settings.get("fisheye_profiles", {})
        
        # Padrões de Fallback caso o nó ou sub-nó específico não existam
        val_x, val_y, val_size, val_path = 9, 6, 150, ""
        
        if profile_name in profiles_db:
            cameras_dict = profiles_db[profile_name].get("cameras", {})
            if angle_key in cameras_dict:
                config = cameras_dict[angle_key]
                val_x = config.get("checker_x", 9)
                val_y = config.get("checker_y", 6)
                val_size = config.get("checker_size", 150)
                val_path = config.get("checker_path", "")
                
        # Blindagem de Sinais para evitar disparos recursivos durante atualização forçada da UI
        self.spin_checker_x.blockSignals(True)
        self.spin_checker_y.blockSignals(True)
        self.spin_checker_size.blockSignals(True)
        
        self.spin_checker_x.setValue(val_x)
        self.spin_checker_y.setValue(val_y)
        self.spin_checker_size.setValue(val_size)
        self.line_checker_path.setText(val_path)
        
        self.spin_checker_x.blockSignals(False)
        self.spin_checker_y.blockSignals(False)
        self.spin_checker_size.blockSignals(False)


    def _start_fisheye_calibration(self):
        profile_name = self.combo_checker_profile.currentText().strip()
        images_dir = self.line_checker_path.text().strip()
        
        if not profile_name or not images_dir or not os.path.isdir(images_dir):
            QtWidgets.QMessageBox.warning(self, "Atenção", "Certifique-se de escolher um perfil e uma pasta de imagens válida.")
            return

        # Trava a interface para evitar cliques acidentais durante o cálculo
        self.btn_exec_calib.setEnabled(False)
        self.grp_rectify.setEnabled(False)
        
        self.progress_calib.setRange(0, 100)
        self.progress_calib.setValue(0)
        self.progress_calib.setVisible(True)
        
        # Pega a pasta de instalação para salvar as matrizes (mesmo nível do main.py)
        # Ajuste "base_install" se a sua pasta raiz do Vidya estiver mapeada de outra forma
        base_install = os.path.dirname(os.path.abspath(__file__)) 
        base_install = os.path.dirname(base_install) # Sobe um nível de 'gui' para a raiz

        # Instancia e configura o Worker
        self.calib_worker = FisheyeCalibrationWorker(
            profile_name=profile_name,
            angle=self.spin_checker_angle.value(),
            checker_x=self.spin_checker_x.value(),
            checker_y=self.spin_checker_y.value(),
            square_size=self.spin_checker_size.value(),
            images_dir=images_dir,
            base_install_path=base_install
        )
        
        # Conecta os sinais da Thread aos elementos da UI
        self.calib_worker.progress_text.connect(self.lbl_calib_status.setText)
        self.calib_worker.progress_value.connect(self._update_calib_progress)
        self.calib_worker.finished.connect(self._on_fisheye_calibration_finished)
        
        # Inicia o processamento em background
        self.calib_worker.start()

    def _update_calib_progress(self, val):
        """Se receber -1, a barra entra no modo infinito visual (vai e vem)"""
        if val == -1:
            self.progress_calib.setRange(0, 0)
        else:
            self.progress_calib.setRange(0, 100)
            self.progress_calib.setValue(val)

    def _on_fisheye_calibration_finished(self, success, result_data, message):
        # Destrava a interface
        self.btn_exec_calib.setEnabled(True)
        self.grp_rectify.setEnabled(True)
        self.progress_calib.setVisible(False)
        self.lbl_calib_status.setText(f"Status: {message}")
        
        if success:
            QtWidgets.QMessageBox.information(self, "Sucesso", message)
            
            # Injeta as chaves resultantes dentro de 'settings' no JSON da memória
            profile_name = self.combo_checker_profile.currentText().strip()
            
            if "fisheye_profiles" not in self.settings:
                self.settings["fisheye_profiles"] = {}
                
            if "settings" not in self.settings["fisheye_profiles"][profile_name]:
                self.settings["fisheye_profiles"][profile_name]["settings"] = {}
                
            # Adiciona/Atualiza a matriz calculada ao dicionário dinâmico
            self.settings["fisheye_profiles"][profile_name]["settings"].update(result_data)
            
        else:
            QtWidgets.QMessageBox.critical(self, "Erro na Calibração", message)
            
    def _on_browse_checker_path(self):
        current_dir = self.line_checker_path.text()
        selected_dir = QtWidgets.QFileDialog.getExistingDirectory(
            self, 
            "Selecionar Pasta com Imagens do Checkerboard", 
            current_dir, 
            QtWidgets.QFileDialog.ShowDirsOnly
        )
        if selected_dir:
            self.line_checker_path.setText(selected_dir)

    def _build_simulate_tab(self):
        tab = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(tab)
        
        info_label = QtWidgets.QLabel(
            "<b>Calibração Simétrica Paramétrica (Simulação)</b><br>"
            "<small>Ajuste os parâmetros matemáticos da lente visualmente utilizando uma única foto de referência. </small>"
        )
        info_label.setWordWrap(True)
        layout.addWidget(info_label)
        
        # ---> INSERIR AQUI: O Checkbox Mestre da Simulação <---
        self.chk_use_simulated = QtWidgets.QCheckBox("Usar calibração simulada na importação das imagens")
        self.chk_use_simulated.setChecked(self.settings.get("use_simulated_rectification", False))
        font_chk_sim = self.chk_use_simulated.font()
        font_chk_sim.setBold(True)
        self.chk_use_simulated.setFont(font_chk_sim)
        layout.addWidget(self.chk_use_simulated)
        # ------------------------------------------------------
        
        # --- ÁREA 1: GESTÃO DE PERFIL ---
        self.grp_sim_profile = QtWidgets.QGroupBox("1. Perfil de Simulação")
        lyt_sim_profile = QtWidgets.QFormLayout(self.grp_sim_profile)
        
        profile_layout = QtWidgets.QHBoxLayout()
        self.combo_sim_profile = QtWidgets.QComboBox()
        self.combo_sim_profile.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        
        btn_new_sim = QtWidgets.QPushButton("Novo")
        btn_new_sim.setIcon(QtGui.QIcon.fromTheme("list-add"))
        btn_new_sim.clicked.connect(self._on_new_sim_profile)
        
        btn_del_sim = QtWidgets.QPushButton("Excluir")
        btn_del_sim.setIcon(QtGui.QIcon.fromTheme("list-remove"))
        btn_del_sim.clicked.connect(self._on_delete_sim_profile)
        
        profile_layout.addWidget(self.combo_sim_profile)
        profile_layout.addWidget(btn_new_sim)
        profile_layout.addWidget(btn_del_sim)
        
        lyt_sim_profile.addRow("Perfil Ativo:", profile_layout)
        layout.addWidget(self.grp_sim_profile)
        
        # --- ÁREA 2: LABORATÓRIO E IMAGEM DE REFERÊNCIA ---
        self.grp_sim_lab = QtWidgets.QGroupBox("2. Imagem de Referência (Laboratório)")
        lyt_sim_lab = QtWidgets.QFormLayout(self.grp_sim_lab)
        
        path_layout = QtWidgets.QHBoxLayout()
        self.line_sim_image = QtWidgets.QLineEdit()
        self.line_sim_image.setReadOnly(True)
        self.line_sim_image.setPlaceholderText("Nenhuma imagem selecionada...")
        
        btn_browse_sim = QtWidgets.QPushButton(" Abrir Imagem...")
        btn_browse_sim.setIcon(QtGui.QIcon.fromTheme("image-x-generic"))
        btn_browse_sim.clicked.connect(self._on_browse_sim_image)
        
        path_layout.addWidget(self.line_sim_image)
        path_layout.addWidget(btn_browse_sim)
        
        dim_layout = QtWidgets.QHBoxLayout()
        self.spin_sim_width = QtWidgets.QSpinBox()
        self.spin_sim_width.setRange(0, 10000)
        self.spin_sim_width.setReadOnly(True)
        self.spin_sim_width.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons)
        self.spin_sim_width.setSuffix(" px")
        
        self.spin_sim_height = QtWidgets.QSpinBox()
        self.spin_sim_height.setRange(0, 10000)
        self.spin_sim_height.setReadOnly(True)
        self.spin_sim_height.setButtonSymbols(QtWidgets.QAbstractSpinBox.NoButtons)
        self.spin_sim_height.setSuffix(" px")
        
        dim_layout.addWidget(QtWidgets.QLabel("Largura:"))
        dim_layout.addWidget(self.spin_sim_width)
        dim_layout.addWidget(QtWidgets.QLabel("Altura:"))
        dim_layout.addWidget(self.spin_sim_height)
        dim_layout.addStretch()
        
        lyt_sim_lab.addRow("Foto de Teste:", path_layout)
        lyt_sim_lab.addRow("Resolução Detectada:", dim_layout)
        
        # lbl_sim_warning = QtWidgets.QLabel("<small style='color: gray;'>A resolução deve corresponder exatamente à resolução real de captura da câmera.</small>")
        # lyt_sim_lab.addRow("", lbl_sim_warning)
        
        layout.addWidget(self.grp_sim_lab)
        layout.addStretch()
        
        # --- ÁREA 3: MATRIZ INTRÍNSECA (GEOMETRIA K) ---
        self.grp_sim_k = QtWidgets.QGroupBox("3. Geometria Óptica (Matriz K)")
        lyt_sim_k = QtWidgets.QFormLayout(self.grp_sim_k)
        
        def create_sim_slider(min_val, max_val, default_val):
            s = QtWidgets.QSlider(QtCore.Qt.Horizontal)
            s.setRange(min_val, max_val)
            s.setValue(int(default_val))
            s.setTickPosition(QtWidgets.QSlider.TicksBelow)
            return s
            
        self.slider_sim_fov = create_sim_slider(30, 220, 170)
        self.slider_sim_pan = create_sim_slider(-500, 500, 0)
        self.slider_sim_tilt = create_sim_slider(-500, 500, 0)
        
        self.lbl_sim_fov = QtWidgets.QLabel(f"{self.slider_sim_fov.value()}°")
        self.lbl_sim_pan = QtWidgets.QLabel(f"{self.slider_sim_pan.value()} px")
        self.lbl_sim_tilt = QtWidgets.QLabel(f"{self.slider_sim_tilt.value()} px")
        
        self.slider_sim_fov.valueChanged.connect(lambda v: self.lbl_sim_fov.setText(f"{v}°"))
        self.slider_sim_pan.valueChanged.connect(lambda v: self.lbl_sim_pan.setText(f"{v} px"))
        self.slider_sim_tilt.valueChanged.connect(lambda v: self.lbl_sim_tilt.setText(f"{v} px"))
        
        def wrap_sim_slider(lbl, sld):
            h = QtWidgets.QHBoxLayout()
            lbl.setMinimumWidth(55)
            h.addWidget(lbl)
            h.addWidget(sld)
            return h

        lyt_sim_k.addRow("Ângulo Diagonal (FOV):", wrap_sim_slider(self.lbl_sim_fov, self.slider_sim_fov))
        lyt_sim_k.addRow("Deslocamento X (Pan):", wrap_sim_slider(self.lbl_sim_pan, self.slider_sim_pan))
        lyt_sim_k.addRow("Deslocamento Y (Tilt):", wrap_sim_slider(self.lbl_sim_tilt, self.slider_sim_tilt))
        
        layout.addWidget(self.grp_sim_k)
        
        # --- ÁREA 4: MATRIZ DE DISTORÇÃO (D) ---
        self.grp_sim_d = QtWidgets.QGroupBox("4. Distorção da Lente (Matriz D)")
        lyt_sim_d = QtWidgets.QFormLayout(self.grp_sim_d)
        
        # Sliders multiplicados por 1000 para permitir casas decimais finas (ex: 150 = 0.150)
        self.slider_sim_k1 = create_sim_slider(-1000, 1000, 0)
        self.slider_sim_k2 = create_sim_slider(-1000, 1000, 0)
        
        self.lbl_sim_k1 = QtWidgets.QLabel(f"{self.slider_sim_k1.value() / 1000.0:.3f}")
        self.lbl_sim_k2 = QtWidgets.QLabel(f"{self.slider_sim_k2.value() / 1000.0:.3f}")
        
        self.slider_sim_k1.valueChanged.connect(lambda v: self.lbl_sim_k1.setText(f"{v / 1000.0:.3f}"))
        self.slider_sim_k2.valueChanged.connect(lambda v: self.lbl_sim_k2.setText(f"{v / 1000.0:.3f}"))
        
        lyt_sim_d.addRow("Curvatura de Barril (k1):", wrap_sim_slider(self.lbl_sim_k1, self.slider_sim_k1))
        lyt_sim_d.addRow("Refinamento de Borda (k2):", wrap_sim_slider(self.lbl_sim_k2, self.slider_sim_k2))
        
        layout.addWidget(self.grp_sim_d)
        
        # --- ÁREA 5: AÇÕES ---
        self.grp_sim_actions = QtWidgets.QGroupBox("5. Execução")
        lyt_sim_actions = QtWidgets.QHBoxLayout(self.grp_sim_actions)
        
        self.btn_sim_preview = QtWidgets.QPushButton("  Preview em Tempo Real")
        self.btn_sim_preview.setIcon(QtGui.QIcon.fromTheme("video-display"))
        self.btn_sim_preview.setStyleSheet("background-color: #e67e22; color: white; font-weight: bold; padding: 6px;")
        
        self.btn_sim_save = QtWidgets.QPushButton("  Salvar Matrizes Simuladas")
        self.btn_sim_save.setIcon(QtGui.QIcon.fromTheme("document-save"))
        self.btn_sim_save.setStyleSheet("background-color: #8e44ad; color: white; font-weight: bold; padding: 6px;")
        
        # ---> INSERIR AQUI: Novo Botão de Ajustes de Fábrica <---
        self.btn_sim_reset = QtWidgets.QPushButton("  Ajustes de Fábrica")
        self.btn_sim_reset.setIcon(QtGui.QIcon.fromTheme("edit-clear"))
        self.btn_sim_reset.setStyleSheet("background-color: #7f8c8d; color: white; font-weight: bold; padding: 6px;") # Cor cinzenta
        
        # O botão do preview ficará inativo nesta etapa até carregar a imagem.
        self.btn_sim_preview.setEnabled(False) 
        self.btn_sim_preview.clicked.connect(self._open_sim_preview_window)
        self.btn_sim_save.clicked.connect(self._save_simulated_matrices)
        self.btn_sim_reset.clicked.connect(self._reset_sim_defaults) # Conecta à função de reset
        
        lyt_sim_actions.addWidget(self.btn_sim_preview)
        lyt_sim_actions.addWidget(self.btn_sim_save)
        lyt_sim_actions.addWidget(self.btn_sim_reset) # Adiciona à mesma linha
        
        layout.addWidget(self.grp_sim_actions)
        
        # Carregamento Inicial
        sim_db = self.settings.get("fisheye_sim_profiles", {})
        self.combo_sim_profile.addItems(list(sim_db.keys()))
        
        last_sim_profile = self.settings.get("last_sim_profile", "")
        if last_sim_profile and self.combo_sim_profile.findText(last_sim_profile) != -1:
            self.combo_sim_profile.setCurrentText(last_sim_profile)
            
        self._load_sim_profile_data(self.combo_sim_profile.currentText())
        self.combo_sim_profile.currentTextChanged.connect(self._load_sim_profile_data)
        
        # ---> INSERIR AQUI: Lógica visual dependente do Checkbox mestre <---
        self.grp_sim_profile.setEnabled(self.chk_use_simulated.isChecked())
        self.grp_sim_lab.setEnabled(self.chk_use_simulated.isChecked())
        self.grp_sim_k.setEnabled(self.chk_use_simulated.isChecked())
        self.grp_sim_d.setEnabled(self.chk_use_simulated.isChecked())
        self.grp_sim_actions.setEnabled(self.chk_use_simulated.isChecked())
        
        self.chk_use_simulated.toggled.connect(self.grp_sim_profile.setEnabled)
        self.chk_use_simulated.toggled.connect(self.grp_sim_lab.setEnabled)
        self.chk_use_simulated.toggled.connect(self.grp_sim_k.setEnabled)
        self.chk_use_simulated.toggled.connect(self.grp_sim_d.setEnabled)
        self.chk_use_simulated.toggled.connect(self.grp_sim_actions.setEnabled)
        
        self.chk_use_simulated.toggled.connect(self._on_use_simulated_toggled) # Liga exclusividade mútua
        # ------------------------------------------------------------------
        
        self.tabs.addTab(tab, "Simular")

    def _reset_sim_defaults(self):
        """Restaura os valores matemáticos originais da simulação sem remover a imagem de teste."""
        if hasattr(self, 'slider_sim_fov'):
            # O setValue() aciona automaticamente o signal 'valueChanged', 
            # o que atualiza os rótulos de texto e a janela de preview em tempo real.
            self.slider_sim_fov.setValue(170)
            self.slider_sim_pan.setValue(0)
            self.slider_sim_tilt.setValue(0)
            self.slider_sim_k1.setValue(0)
            self.slider_sim_k2.setValue(0)
            
    def _on_new_sim_profile(self):
        name, ok = QtWidgets.QInputDialog.getText(
            self, "Novo Perfil Simulado", 
            "Digite o nome para este perfil de simulação de lente:"
        )
        if ok and name.strip():
            name = name.strip()
            if self.combo_sim_profile.findText(name) == -1:
                self.combo_sim_profile.addItem(name)
            self.combo_sim_profile.setCurrentText(name)

    def _on_delete_sim_profile(self):
        current = self.combo_sim_profile.currentText()
        if not current: return
            
        reply = QtWidgets.QMessageBox.question(
            self, "Excluir Perfil Simulado", 
            f"Tem certeza que deseja remover o perfil de simulação '{current}' e apagar seus arquivos físicos (.npy)?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
        )
        if reply == QtWidgets.QMessageBox.Yes:
            # 1. Remove da memória de Simulação (Sliders)
            sim_db = self.settings.get("fisheye_sim_profiles", {})
            if current in sim_db:
                del sim_db[current]
                self.settings["fisheye_sim_profiles"] = sim_db

            # 2. Localiza o "clone" na memória principal, exclui os arquivos físicos e a chave
            profiles_db = self.settings.get("fisheye_profiles", {})
            if current in profiles_db:
                profile_settings = profiles_db[current].get("settings", {})
                for key, value in profile_settings.items():
                    if isinstance(value, str) and value.endswith(".npy"):
                        if os.path.exists(value):
                            try:
                                os.remove(value)
                                print(f"[Vidya] Arquivo de simulação removido: {value}")
                            except Exception as e:
                                print(f"[Vidya] Erro ao remover arquivo {value}: {e}")
                
                # Apaga a chave injetada da árvore principal
                del profiles_db[current]
                self.settings["fisheye_profiles"] = profiles_db

            # 3. Limpa a Interface Visual
            self.combo_sim_profile.removeItem(self.combo_sim_profile.currentIndex())
            self.line_sim_image.clear()
            self.spin_sim_width.setValue(0)
            self.spin_sim_height.setValue(0)

    def _load_sim_profile_data(self, profile_name):
        if not profile_name: return
        sim_db = self.settings.get("fisheye_sim_profiles", {})
        data = sim_db.get(profile_name, {})
        
        self.line_sim_image.setText(data.get("image_path", ""))
        self.spin_sim_width.setValue(data.get("width", 0))
        self.spin_sim_height.setValue(data.get("height", 0))
        
        # ---> INSERIR AQUI: Carregamento dos valores paramétricos
        if hasattr(self, 'slider_sim_fov'):
            self.slider_sim_fov.setValue(data.get("sim_fov", 170))
            self.slider_sim_pan.setValue(data.get("sim_pan", 0))
            self.slider_sim_tilt.setValue(data.get("sim_tilt", 0))
            self.slider_sim_k1.setValue(data.get("sim_k1", 0))
            self.slider_sim_k2.setValue(data.get("sim_k2", 0))
            
        # ---> INSERIR ESTAS LINHAS NO FINAL DO MÉTODO:
        if hasattr(self, 'btn_sim_preview'):
            has_image = bool(self.line_sim_image.text().strip())
            self.btn_sim_preview.setEnabled(has_image)

    def _open_sim_preview_window(self):
        image_path = self.line_sim_image.text()
        if not image_path or not os.path.exists(image_path):
            QtWidgets.QMessageBox.warning(self, "Aviso", "O caminho da imagem é inválido.")
            return
            
        # Se a janela já existir e estiver aberta, foca nela
        if self.preview_window is not None and self.preview_window.isVisible():
            self.preview_window.activateWindow()
            return
            
        # Instancia a nova janela flutuante passando a imagem
        self.preview_window = VidyaFisheyePreviewWindow(image_path, self)
        
        # Conecta os sliders ao método de atualização
        self.slider_sim_fov.valueChanged.connect(self._update_live_preview)
        self.slider_sim_pan.valueChanged.connect(self._update_live_preview)
        self.slider_sim_tilt.valueChanged.connect(self._update_live_preview)
        self.slider_sim_k1.valueChanged.connect(self._update_live_preview)
        self.slider_sim_k2.valueChanged.connect(self._update_live_preview)
        
        # Mostra a janela (Não-modal, o utilizador ainda pode clicar nos sliders)
        self.preview_window.show()
        
        # Força a primeira renderização para a janela não abrir em branco
        self._update_live_preview()

    def _update_live_preview(self):
        """Envia o estado atual dos sliders para a janela de Preview (se ela estiver aberta)."""
        if self.preview_window is not None and self.preview_window.isVisible():
            self.preview_window.update_preview(
                fov_deg=self.slider_sim_fov.value(),
                pan_orig=self.slider_sim_pan.value(),
                tilt_orig=self.slider_sim_tilt.value(),
                k1_raw=self.slider_sim_k1.value(),
                k2_raw=self.slider_sim_k2.value()
            )

    def _on_browse_sim_image(self):
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Selecionar Imagem de Referência", "", 
            "Imagens (*.jpg *.jpeg *.png *.tif *.tiff)"
        )
        if file_path:
            import cv2
            img = cv2.imread(file_path)
            if img is not None:
                h, w = img.shape[:2]
                self.line_sim_image.setText(file_path)
                self.spin_sim_width.setValue(w)
                self.spin_sim_height.setValue(h)
                
                # ---> INSERIR ESTA LINHA: Habilita o botão do preview
                if hasattr(self, 'btn_sim_preview'):
                    self.btn_sim_preview.setEnabled(True)
            else:
                QtWidgets.QMessageBox.warning(self, "Erro", "Não foi possível ler a imagem selecionada.")
                    
    def _build_markers_tab(self):
        tab = QtWidgets.QWidget()
        layout = QtWidgets.QFormLayout(tab)
        
        self.combo_left = QtWidgets.QComboBox()
        self.combo_right = QtWidgets.QComboBox()
        colors = list(COLOR_MAP.keys())
        self.combo_left.addItems(colors)
        self.combo_right.addItems(colors)
        self.combo_left.setCurrentText(self.settings.get("marker_color_left", "Vermelho"))
        self.combo_right.setCurrentText(self.settings.get("marker_color_right", "Verde"))

        # --- CÓDIGO ATUALIZADO ---
        self.combo_fill_color = QtWidgets.QComboBox()
        self.combo_fill_color.addItems(["Preto", "Branco", "Transparente"])
        
        # Recupera a cor salva. Se for um HEX customizado, adiciona na lista para visualização
        saved_fill = self.settings.get("marker_fill_color", "Transparente")
        if saved_fill not in ["Preto", "Branco", "Transparente"]:
            self.combo_fill_color.addItem(saved_fill)
            
        self.combo_fill_color.addItem("Customizado...")
        
        # Bloqueia os sinais temporariamente para não abrir o ColorPicker ao carregar a janela
        self.combo_fill_color.blockSignals(True)
        self.combo_fill_color.setCurrentText(saved_fill)
        self.combo_fill_color.blockSignals(False)
        
        # Conecta o sinal de mudança para disparar o nosso seletor
        self.combo_fill_color.currentTextChanged.connect(self._on_fill_color_changed)
        # -------------------------
        
        self.slider_opacity = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.slider_opacity.setRange(0, 100)
        self.slider_opacity.setValue(int(self.settings.get("marker_opacity", 8)))
        self.slider_opacity.setTickPosition(QtWidgets.QSlider.TicksBelow)
        self.slider_opacity.setTickInterval(10)
        
        self.lbl_opacity_val = QtWidgets.QLabel(f"<b>{self.slider_opacity.value()}%</b>")
        self.slider_opacity.valueChanged.connect(lambda v: self.lbl_opacity_val.setText(f"<b>{v}%</b>"))
        
        opacity_layout = QtWidgets.QHBoxLayout()
        opacity_layout.addWidget(self.lbl_opacity_val)
        opacity_layout.addWidget(self.slider_opacity)
        
        self.slider_weight = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.slider_weight.setRange(0, 200) 
        self.slider_weight.setValue(int(self.settings.get("marker_thickness_weight", 100)))
        self.slider_weight.setTickPosition(QtWidgets.QSlider.TicksBelow)
        self.slider_weight.setTickInterval(20)
        
        self.lbl_weight_val = QtWidgets.QLabel(f"<b>{self.slider_weight.value()}%</b>")
        self.slider_weight.valueChanged.connect(lambda v: self.lbl_weight_val.setText(f"<b>{v}%</b>"))
        
        weight_layout = QtWidgets.QHBoxLayout()
        weight_layout.addWidget(self.lbl_weight_val)
        weight_layout.addWidget(self.slider_weight)
        
        markers_label = QtWidgets.QLabel("<b>Transparência e Largura dos Marcadores</b><br><small>Ajuste estes controles para a melhor visualização dos marcadores de recorte</small>")
        markers_label.setWordWrap(True)
        layout.addRow(markers_label)
        
        layout.addRow("Cor do Marcador Esquerdo:", self.combo_left)
        layout.addRow("Cor do Marcador Direito:", self.combo_right)
        layout.addRow("Cor de Preenchimento de Recorte:", self.combo_fill_color) 
        layout.addRow("Opacidade do Fundo:", opacity_layout)
        # ... código existente ...
        layout.addRow("Espessura da Borda Dinâmica:", weight_layout) 
        
        # --- NOVO: CONTROLE DE BORDAS DAS IMAGENS ---
        lbl_bordas = QtWidgets.QLabel("<br><b>Bordas nas Visualização das Imagens</b>")
        layout.addRow(lbl_bordas)

        self.spin_border_width = QtWidgets.QSpinBox()
        self.spin_border_width.setRange(0, 20)
        self.spin_border_width.setValue(int(self.settings.get("image_border_width", 1)))
        self.spin_border_width.setSuffix(" px")

        self.combo_border_color = QtWidgets.QComboBox()
        self.combo_border_color.addItems(["Preto", "Branco", "Cinza"])
        self.combo_border_color.setCurrentText(self.settings.get("image_border_color", "Preto"))

        self.slider_border_opacity = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.slider_border_opacity.setRange(0, 100)
        self.slider_border_opacity.setValue(int(self.settings.get("image_border_opacity", 100)))
        self.slider_border_opacity.setTickPosition(QtWidgets.QSlider.TicksBelow)
        self.slider_border_opacity.setTickInterval(10)

        self.lbl_border_opacity_val = QtWidgets.QLabel(f"<b>{self.slider_border_opacity.value()}%</b>")
        self.slider_border_opacity.valueChanged.connect(lambda v: self.lbl_border_opacity_val.setText(f"<b>{v}%</b>"))

        border_opacity_layout = QtWidgets.QHBoxLayout()
        border_opacity_layout.addWidget(self.lbl_border_opacity_val)
        border_opacity_layout.addWidget(self.slider_border_opacity)

        self.combo_border_style = QtWidgets.QComboBox()
        self.combo_border_style.addItems(["Contínuo", "Tracejado", "Pontos"])
        self.combo_border_style.setCurrentText(self.settings.get("image_border_style", "Contínuo"))

        layout.addRow("Largura das Bordas:", self.spin_border_width)
        layout.addRow("Cor da Borda:", self.combo_border_color)
        layout.addRow("Opacidade:", border_opacity_layout)
        layout.addRow("Traço:", self.combo_border_style)
        
        # --- NOVO: BOTÃO RESTAURAR PADRÕES DE FÁBRICA ---
        btn_reset_markers = QtWidgets.QPushButton(" Restaurar padrões de fábrica")
        btn_reset_markers.setIcon(QtGui.QIcon.fromTheme("edit-clear"))
        btn_reset_markers.clicked.connect(self._reset_markers_defaults)
        
        reset_layout = QtWidgets.QHBoxLayout()
        reset_layout.addStretch()
        reset_layout.addWidget(btn_reset_markers)
        layout.addRow(reset_layout)
        # ------------------------------------------------
        
        self.tabs.addTab(tab, "Marcadores")

    def _build_preview_tab(self):
        tab = QtWidgets.QWidget()
        layout = QtWidgets.QFormLayout(tab)
        
        self.combo_rot_left = QtWidgets.QComboBox()
        self.combo_rot_right = QtWidgets.QComboBox()
        rotations = ["0°", "90°", "180°", "270°"]
        self.combo_rot_left.addItems(rotations)
        self.combo_rot_right.addItems(rotations)
        self.combo_rot_left.setCurrentText(self.settings.get("rotation_left", "0°"))
        self.combo_rot_right.setCurrentText(self.settings.get("rotation_right", "0°"))
        
        rotation_label = QtWidgets.QLabel("<b>Rotação das câmeras ou sensores</b><br><small>Para book scanners com berço em V, é necessário alterar a rotação das imagens.</small>")
        rotation_label.setWordWrap(True)
        layout.addRow(rotation_label)
        layout.setSpacing(10) 
        
        layout.addRow("Rotação do Sensor Esquerdo:", self.combo_rot_left)
        layout.addRow("Rotação do Sensor Direito:", self.combo_rot_right)
        self.tabs.addTab(tab, "Orientação")

    def _on_fill_color_changed(self, text):
        if text == "Customizado...":
            # Tenta usar a cor customizada atual como ponto de partida no ColorPicker (se houver)
            initial_color = QtGui.QColor(QtCore.Qt.white)
            current_saved = self.settings.get("marker_fill_color", "Transparente")
            if current_saved.startswith("#"):
                initial_color = QtGui.QColor(current_saved)

            # Abre o seletor nativo de cores do Qt
            color = QtWidgets.QColorDialog.getColor(initial_color, self, "Escolher cor de preenchimento")
            
            if color.isValid():
                hex_val = color.name().upper() # Extrai no formato #RRGGBB
                
                # Se a cor escolhida ainda não estiver na lista, insere antes de "Customizado..."
                if self.combo_fill_color.findText(hex_val) == -1:
                    idx = self.combo_fill_color.count() - 1
                    self.combo_fill_color.insertItem(idx, hex_val)
                
                # Define a nova cor como texto atual silenciosamente (sem re-disparar o sinal)
                self.combo_fill_color.blockSignals(True)
                self.combo_fill_color.setCurrentText(hex_val)
                self.combo_fill_color.blockSignals(False)
                
                # Salva provisoriamente em memória
                self.settings["marker_fill_color"] = hex_val 
            else:
                # O usuário clicou em Cancelar (fechou a janela). Volta para a seleção anterior.
                self.combo_fill_color.blockSignals(True)
                self.combo_fill_color.setCurrentText(self.settings.get("marker_fill_color", "Transparente"))
                self.combo_fill_color.blockSignals(False)
                
    def _create_ocr_slider(self, default_value: int) -> QtWidgets.QSlider:
        slider = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        slider.setRange(0, 100)
        slider.setValue(int(default_value))
        slider.setTickPosition(QtWidgets.QSlider.TicksBelow)
        slider.setTickInterval(10)
        return slider

    def _reset_bg_defaults(self):
        """Restaura os padrões de fábrica específicos da detecção de fundo."""
        self.chk_bg_detect.setChecked(False)
        self.slider_bg_sens.setValue(0)
        
        # Bloqueia sinais temporariamente para evitar loops ou abertura indesejada de paletas
        self.combo_bg_color.blockSignals(True)
        self.combo_bg_color.setCurrentText("Branco")
        self.combo_bg_color.blockSignals(False)
           
    def _reset_markers_defaults(self):
        """Restaura os padrões de fábrica específicos da aba de Marcadores e Bordas."""
        # Configurações dos Marcadores de Recorte
        self.combo_left.setCurrentText("Vermelho")
        self.combo_right.setCurrentText("Verde")
        self.combo_fill_color.setCurrentText("Transparente")
        
        self.slider_opacity.setValue(3)
        self.lbl_opacity_val.setText("<b>3%</b>")
        
        self.slider_weight.setValue(100)
        self.lbl_weight_val.setText("<b>100%</b>")
        
        # Configurações de Visualização das Bordas da Imagem
        if hasattr(self, 'spin_border_width'):
            self.spin_border_width.setValue(3)
            
        if hasattr(self, 'combo_border_color'):
            self.combo_border_color.setCurrentText("Preto")
            
        if hasattr(self, 'slider_border_opacity'):
            self.slider_border_opacity.setValue(50)
            self.lbl_border_opacity_val.setText("<b>50%</b>")
            
        if hasattr(self, 'combo_border_style'):
            self.combo_border_style.setCurrentText("Pontos")
            
    def _update_ocr_jobs_color(self, value):
        """Muda a cor da fonte do número de núcleos com base na carga do processador e no tema atual."""
        is_dark = self.settings.get("dark_mode", False)
        
        # Avaliação de Carga: Se for menor ou igual aos núcleos físicos, é seguro (Verde)
        if value <= getattr(self, 'physical_cores', 2):
            color = "#a8e6cf" if is_dark else "#27ae60"  # Verde Claro (Tema Escuro) / Verde Padrão (Tema Claro)
        else:
            # Se entrar na área das Threads lógicas (Hyper-threading), alerta (Vermelho)
            color = "#ff8b94" if is_dark else "#c0392b"  # Vermelho Claro (Tema Escuro) / Vermelho Padrão (Tema Claro)
            
        self.spin_ocr_jobs.setStyleSheet(f"color: {color}; font-weight: bold;")
                  
    def _reset_ocr_defaults(self):
        self.chk_proc_ocr.setChecked(False)
        self.chk_ocr_preprocess.setChecked(True)
        self.chk_manual_opencv.setChecked(False) # <--- INSERIR AQUI
        self.slider_cor_papel.setValue(20)
        self.slider_int_impr.setValue(80)
        self.slider_tam_manchas.setValue(10)
        self.slider_prof_manchas.setValue(10)
        self.combo_ocr_lang.setCurrentText("por")
        self.spin_ocr_jobs.setValue(2)
        self.chk_ocr_sidecar.setChecked(False)
        
    def _reset_process_defaults(self):
        self.chk_crop.setChecked(True)
        self.chk_deskew.setChecked(True)
        self.chk_dewarp.setChecked(True)
        self.chk_contour_deskew.setChecked(False)
        self.chk_pdf.setChecked(True)
        self.chk_ignore_ends.setChecked(False)
        self.rb_originais.setChecked(True)
        self.slider_deskew_agg.setValue(100)
        self.slider_dewarp_agg.setValue(100)
        self.line_export_path.setText("")
        self.chk_cleanup.setChecked(False)
        
    def _reset_custody_defaults(self):
        self.chk_hash_capture.setChecked(True)
        self.chk_premis.setChecked(True)
        self.chk_bagit.setChecked(False)
        self.chk_tsv.setChecked(True)
        self.chk_tsv_hash.setChecked(True)
        self.chk_tsv_ocr.setChecked(False)
        self.combo_tsv_granularity.setCurrentIndex(1) 

    def _build_custody_tab(self):
        tab = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(tab)

        grp_fix = QtWidgets.QGroupBox("Garantia de Fixidez e Origem")
        f_fix = grp_fix.font(); f_fix.setBold(True); grp_fix.setFont(f_fix)
        grp_fix.setStyleSheet("QCheckBox, QLabel { font-weight: normal; }")
        lyt_fix = QtWidgets.QVBoxLayout(grp_fix)
        
        self.chk_hash_capture = QtWidgets.QCheckBox("Calcular e selar Hash SHA-256 no momento da captura")
        self.chk_hash_capture.setChecked(self.settings.get("custody_calc_hash_on_capture", False))
        lbl_fix = QtWidgets.QLabel("<small style='color:gray;'>Gera prova criptográfica em tempo real. Pode atrasar ligeiramente as capturas em discos lentos.</small>")
        lbl_fix.setWordWrap(True); lbl_fix.setContentsMargins(20, 0, 0, 5)
        
        lyt_fix.addWidget(self.chk_hash_capture)
        lyt_fix.addWidget(lbl_fix)
        layout.addWidget(grp_fix)

        grp_premis = QtWidgets.QGroupBox("Rastreabilidade de Transformações (Padrão PREMIS)")
        f_premis = grp_premis.font(); f_premis.setBold(True); grp_premis.setFont(f_premis)
        grp_premis.setStyleSheet("QCheckBox, QLabel { font-weight: normal; }")
        lyt_premis = QtWidgets.QVBoxLayout(grp_premis)

        self.chk_premis = QtWidgets.QCheckBox("Registar eventos de processamento no manifesto do projeto")
        self.chk_premis.setChecked(self.settings.get("custody_log_premis", True))
        lbl_premis = QtWidgets.QLabel("<small style='color:gray;'>Anexa ao project.json o histórico arquivístico das alterações feitas (Deskew, Dewarp, OCR, etc).</small>")
        lbl_premis.setWordWrap(True); lbl_premis.setContentsMargins(20, 0, 0, 5)
        
        lyt_premis.addWidget(self.chk_premis)
        lyt_premis.addWidget(lbl_premis)
        layout.addWidget(grp_premis)

        grp_dist = QtWidgets.QGroupBox("Estruturas de Distribuição e Repositório")
        f_dist = grp_dist.font(); f_dist.setBold(True); grp_dist.setFont(f_dist)
        grp_dist.setStyleSheet("QCheckBox, QLabel, QComboBox { font-weight: normal; }")
        lyt_dist = QtWidgets.QVBoxLayout(grp_dist)

        self.chk_bagit = QtWidgets.QCheckBox("Empacotar pasta de saída no padrão internacional BagIt")
        self.chk_bagit.setChecked(self.settings.get("custody_export_bagit", False))
        lbl_bagit = QtWidgets.QLabel("<small style='color:gray;'>Gera manifestos de integridade e a hierarquia exigida pelo AtoM, Archivematica e DSpace.</small>")
        lbl_bagit.setWordWrap(True); lbl_bagit.setContentsMargins(20, 0, 0, 10)
        
        self.chk_tsv = QtWidgets.QCheckBox("Exportar metadados tabulares para sistemas externos (.TSV)")
        self.chk_tsv.setChecked(self.settings.get("custody_export_tsv", False))
        lbl_tsv = QtWidgets.QLabel("<small style='color:gray;'>Gera um ficheiro TSV (Tab Separated Values) para importação em Omeka S, Tainacan ou análise em Excel.</small>")
        lbl_tsv.setWordWrap(True); lbl_tsv.setContentsMargins(20, 0, 0, 5)

        self.wdg_tsv_opts = QtWidgets.QWidget()
        lyt_tsv_opts = QtWidgets.QVBoxLayout(self.wdg_tsv_opts)
        lyt_tsv_opts.setContentsMargins(40, 0, 0, 5) 

        self.chk_tsv_hash = QtWidgets.QCheckBox("Incluir coluna de integridade (Hashes SHA-256)")
        self.chk_tsv_hash.setChecked(self.settings.get("custody_tsv_include_hash", False))
        
        self.chk_tsv_ocr = QtWidgets.QCheckBox("Incluir coluna com o texto integral (OCR)")
        self.chk_tsv_ocr.setChecked(self.settings.get("custody_tsv_include_ocr", False))

        lyt_gran = QtWidgets.QHBoxLayout()
        lyt_gran.addWidget(QtWidgets.QLabel("Granularidade:"))
        self.combo_tsv_granularity = QtWidgets.QComboBox()
        self.combo_tsv_granularity.addItems(["1. Registo Global (Ao nível do Livro)", "2. Registo por Imagem (Ao nível da Página)"])
        saved_gran = self.settings.get("custody_tsv_granularity", "2. Registo por Imagem (Ao nível da Página)")
        self.combo_tsv_granularity.setCurrentText(saved_gran)
        lyt_gran.addWidget(self.combo_tsv_granularity)
        lyt_gran.addStretch()

        lyt_tsv_opts.addWidget(self.chk_tsv_hash)
        lyt_tsv_opts.addWidget(self.chk_tsv_ocr)
        lyt_tsv_opts.addLayout(lyt_gran)

        self.chk_tsv.toggled.connect(self.wdg_tsv_opts.setEnabled)
        self.wdg_tsv_opts.setEnabled(self.chk_tsv.isChecked())

        lyt_dist.addWidget(self.chk_bagit)
        lyt_dist.addWidget(lbl_bagit)
        lyt_dist.addWidget(self.chk_tsv)
        lyt_dist.addWidget(lbl_tsv)
        lyt_dist.addWidget(self.wdg_tsv_opts)

        layout.addWidget(grp_dist)

        btn_reset = QtWidgets.QPushButton(" Restaurar padrões de fábrica")
        btn_reset.setIcon(QtGui.QIcon.fromTheme("edit-clear"))
        btn_reset.clicked.connect(self._reset_custody_defaults)
        
        reset_layout = QtWidgets.QHBoxLayout()
        reset_layout.addStretch()
        reset_layout.addWidget(btn_reset)
        layout.addLayout(reset_layout)

        layout.addStretch()
        self.tabs.addTab(tab, "Custódia")        

    def _build_optuna_tab(self):
        tab = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(tab)

        info_label = QtWidgets.QLabel(
            "<b>Calibração Preditiva por Inteligência Artificial (Tuning)</b><br>"
            "<small>O sistema sorteará amostras do projeto atual. Você fará a marcação ideal nestas amostras "
            "e a IA testará milhares de parâmetros para encontrar a matemática perfeita para o resto do lote.</small>"
        )
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        # --- GRUPO 1: AMOSTRAGEM ESTRATIFICADA ---
        grp_sample = QtWidgets.QGroupBox("1. Estratégia de Amostragem (Sorteio)")
        f_sample = grp_sample.font(); f_sample.setBold(True); grp_sample.setFont(f_sample)
        grp_sample.setStyleSheet("QLabel, QSpinBox { font-weight: normal; }")
        lyt_sample = QtWidgets.QFormLayout(grp_sample)

        self.spin_opt_sessions = QtWidgets.QSpinBox()
        self.spin_opt_sessions.setRange(2, 10)
        self.spin_opt_sessions.setValue(int(self.settings.get("optuna_sessions", 3)))
        self.spin_opt_sessions.setToolTip("Divide a linha do tempo do lote em X blocos (Manhã, Tarde, etc).")

        self.spin_opt_samples = QtWidgets.QSpinBox()
        self.spin_opt_samples.setRange(1, 5)
        self.spin_opt_samples.setValue(int(self.settings.get("optuna_samples", 3)))
        self.spin_opt_samples.setToolTip("Quantas imagens serão pescadas dentro de cada bloco de tempo.")

        self.lbl_opt_total = QtWidgets.QLabel()
        self.lbl_opt_total.setStyleSheet("color: #2980b9; font-weight: bold; font-size: 11pt;")
        
        lyt_sample.addRow("Sessões Temporais (Divisões):", self.spin_opt_sessions)
        lyt_sample.addRow("Amostras por Sessão:", self.spin_opt_samples)
        lyt_sample.addRow("Total do Ground Truth:", self.lbl_opt_total)
        layout.addWidget(grp_sample)

        # --- GRUPO 2: ESFORÇO DA MÁQUINA (Antigo Grupo 3) ---
        grp_effort = QtWidgets.QGroupBox("2. Esforço Computacional")
        f_effort = grp_effort.font(); f_effort.setBold(True); grp_effort.setFont(f_effort)
        grp_effort.setStyleSheet("QComboBox, QLabel { font-weight: normal; }")
        lyt_effort = QtWidgets.QFormLayout(grp_effort)

        self.combo_opt_trials = QtWidgets.QComboBox()
        self.combo_opt_trials.addItem("Relâmpago (5 iterações)", 10)
        self.combo_opt_trials.addItem("Rápido (50 iterações)", 50)
        self.combo_opt_trials.addItem("Equilibrado (150 iterações)", 150)
        self.combo_opt_trials.addItem("Profundo (300 iterações)", 300)
        
        self.combo_opt_trials.setToolTip("Mais iterações geram parâmetros melhores, mas exigem mais tempo de CPU.")
       
        # Seleciona o salvo ou o Equilibrado como padrão
        saved_trials = self.settings.get("optuna_trials", 150)
        idx = self.combo_opt_trials.findData(saved_trials)
        if idx >= 0: self.combo_opt_trials.setCurrentIndex(idx)

        lyt_effort.addRow("Tentativas da IA (Trials):", self.combo_opt_trials)
        layout.addWidget(grp_effort)

        # --- GRUPO 3: VALORES CALCULADOS PELA IA (Antigo Grupo 4) ---
        grp_ai_calc = QtWidgets.QGroupBox("3. Valores Otimizados pela IA (Atuais)")
        f_ai = grp_ai_calc.font(); f_ai.setBold(True); grp_ai_calc.setFont(f_ai)
        grp_ai_calc.setStyleSheet("QLabel { font-weight: normal; }")
        lyt_ai = QtWidgets.QVBoxLayout(grp_ai_calc)
        
        # [O restante do código do Grupo Valores Calculados continua intacto abaixo disto...]

        # Resgata os últimos valores otimizados salvos (ou os padrões de fábrica)
        # val_blur = self.settings.get("ac_blur", 11)
        # val_dilate = self.settings.get("ac_dilate", 2)
        val_denoise = self.settings.get("ocr_denoise_h", 0.0)
        val_clahe = self.settings.get("ocr_clahe_clip", 1.0)
        val_block = self.settings.get("ocr_block_size", 11)
        val_c = self.settings.get("ocr_c_val", 2)

        # Instanciação das labels contendo Nome: Valor
        # self.lbl_ai_blur = QtWidgets.QLabel(f"Crop-Blur: {val_blur}  ")
        # self.lbl_ai_dilate = QtWidgets.QLabel(f"Crop-Dilate: {val_dilate}  ")
        self.lbl_ai_denoise = QtWidgets.QLabel(f"Denoise: {val_denoise:.2f}  ")
        self.lbl_ai_clahe = QtWidgets.QLabel(f"CLAHE: {val_clahe:.2f}  ")
        self.lbl_ai_block = QtWidgets.QLabel(f"Bloco: {val_block}  ")
        self.lbl_ai_c = QtWidgets.QLabel(f"Valor C: {val_c}  ")

        # Aplica o mesmo estilo azul monoespaçado da aba OCR
        calc_style = "color: #2980b9; font-family: monospace; font-weight: bold; font-size: 10pt;"
        for lbl in [self.lbl_ai_denoise, self.lbl_ai_clahe, self.lbl_ai_block, self.lbl_ai_c]:
            lbl.setStyleSheet(calc_style)

        # Alinhamento horizontal garantindo que todos fiquem na mesma linha
        lyt_ai_row = QtWidgets.QHBoxLayout()
        lyt_ai_row.setContentsMargins(0, 5, 0, 0)
        # lyt_ai_row.addWidget(self.lbl_ai_blur)
        # lyt_ai_row.addWidget(self.lbl_ai_dilate)
        lyt_ai_row.addWidget(self.lbl_ai_denoise)
        lyt_ai_row.addWidget(self.lbl_ai_clahe)
        lyt_ai_row.addWidget(self.lbl_ai_block)
        lyt_ai_row.addWidget(self.lbl_ai_c)
        lyt_ai_row.addStretch() # Empurra os itens para a esquerda, mantendo o espaçamento uniforme

        lyt_ai.addLayout(lyt_ai_row)
        layout.addWidget(grp_ai_calc)
        
        # --- GRUPO 4: MODO DE OPERAÇÃO (ESPAÇO DE BUSCA) ---
        grp_mode = QtWidgets.QGroupBox("4. Modo de Operação")
        f_mode = grp_mode.font(); f_mode.setBold(True); grp_mode.setFont(f_mode)
        grp_mode.setStyleSheet("QComboBox, QLabel { font-weight: normal; }")
        lyt_mode = QtWidgets.QFormLayout(grp_mode)

        self.combo_opt_mode = QtWidgets.QComboBox()
        self.combo_opt_mode.addItems(["Básico", "Avançado"])
        
        # Resgata o valor salvo (padrão é Básico)
        saved_mode = self.settings.get("search_space_mode", "Básico")
        self.combo_opt_mode.setCurrentText(saved_mode)

        lbl_mode_info = QtWidgets.QLabel("<small style='color:gray;'><b>Básico:</b> Otimiza apenas 4 parâmetros (Mais rápido e seguro, ideal para a maioria dos casos).<br><b>Avançado:</b> Otimiza até 12 parâmetros, incluindo resizing e morfologia (Experimental, exige mais CPU).</small>")
        lbl_mode_info.setWordWrap(True)

        lyt_mode.addRow("Complexidade da IA:", self.combo_opt_mode)
        lyt_mode.addRow("", lbl_mode_info)
        
        layout.addWidget(grp_mode)
        
        # --- BOTÃO DE AÇÃO ---
        btn_layout = QtWidgets.QHBoxLayout()
        self.btn_start_optuna = QtWidgets.QPushButton("  Extrair Amostras e Iniciar Treinamento")
        self.btn_start_optuna.setIcon(QtGui.QIcon.fromTheme("system-run"))
        self.btn_start_optuna.setStyleSheet("background-color: #2196F3; color: white; font-weight: bold; padding: 8px; font-size: 11pt;")
        self.btn_start_optuna.clicked.connect(self._on_start_optuna_clicked)
        
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_start_optuna)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        layout.addStretch()
        self.tabs.addTab(tab, "Calibração (IA)")

        # Conectar sinais para atualizar o Label Total
        self.spin_opt_sessions.valueChanged.connect(self._update_optuna_total)
        self.spin_opt_samples.valueChanged.connect(self._update_optuna_total)
        self._update_optuna_total()

    def _update_optuna_total(self):
        """Atualiza dinamicamente o número total de amostras (X * Y)."""
        x = self.spin_opt_sessions.value()
        y = self.spin_opt_samples.value()
        total = x * y
        self.lbl_opt_total.setText(f"{total} imagens serão sorteadas")
        self.btn_start_optuna.setEnabled(True)

    def _on_start_optuna_clicked(self):
        """Salva as configurações atuais e emite o sinal para abrir a GUI de marcação."""
        
        # Monta o dicionário de configuração da calibração fixando os alvos nos bastidores
        calibration_config = {
            "sessions": self.spin_opt_sessions.value(),
            "samples": self.spin_opt_samples.value(),
            "target_crop": False,  # <--- Fixado para não otimizar crop
            "target_ocr": True,    # <--- Fixado para focar sempre no OCR
            "trials": self.combo_opt_trials.currentData(),
            "search_space_mode": self.combo_opt_mode.currentText() # <--- ADICIONAR ESTA LINHA
        }

        # Salva o estado provisório na memória antes de fechar a janela
        self.settings["optuna_sessions"] = calibration_config["sessions"]
        self.settings["optuna_samples"] = calibration_config["samples"]
        self.settings["optuna_target_crop"] = calibration_config["target_crop"]
        self.settings["optuna_target_ocr"] = calibration_config["target_ocr"]
        self.settings["optuna_trials"] = calibration_config["trials"]
        self.settings["search_space_mode"] = calibration_config["search_space_mode"] # <--- ADICIONAR ESTA LINHA

        # Como esta ação interrompe o fluxo normal (não é apenas 'Aplicar'), 
        # acionamos a rotina padrão de salvar tudo e emitimos o sinal que abrirá a GUI do Optuna.
        self._save_and_close()
        
        # Emite o sinal instruindo o VidyaMainWindow a lançar o assistente!
        self.calibration_requested.emit(calibration_config)

    def _build_ocr_tab(self):
        tab = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(tab)
        
        self.chk_proc_ocr = QtWidgets.QCheckBox("Habilitar Extração de Texto (Tesseract 5 + PDF/A)")
        self.chk_proc_ocr.setChecked(self.settings.get("proc_ocr", False))
        font = self.chk_proc_ocr.font()
        font.setBold(True)
        self.chk_proc_ocr.setFont(font)
        layout.addWidget(self.chk_proc_ocr)

        grp_cv2 = QtWidgets.QGroupBox("Pré-processamento (Binarização OpenCV)")
        font_cv2 = grp_cv2.font()
        font_cv2.setBold(True)
        grp_cv2.setFont(font_cv2)
        grp_cv2.setStyleSheet("QLabel, QComboBox, QLineEdit, QSpinBox, QSlider, QCheckBox, QPushButton { font-weight: normal; }")
        
        lyt_cv2 = QtWidgets.QFormLayout(grp_cv2)
        
        self.chk_ocr_preprocess = QtWidgets.QCheckBox("Ativar filtros de realce antes do OCR")
        self.chk_ocr_preprocess.setChecked(self.settings.get("ocr_preprocess", True))
        
        self.slider_cor_papel = self._create_ocr_slider(self.settings.get("ocr_cor_papel", 20))
        self.slider_int_impr = self._create_ocr_slider(self.settings.get("ocr_int_impressao", 80))
        self.slider_tam_manchas = self._create_ocr_slider(self.settings.get("ocr_tam_manchas", 10))
        self.slider_prof_manchas = self._create_ocr_slider(self.settings.get("ocr_prof_manchas", 0))

        # ---> INÍCIO DA ALTERAÇÃO: LABELS DOS PARÂMETROS CALCULADOS (MESMA LINHA) <---
        self.lbl_calc_desfoque = QtWidgets.QLabel("Desfoque: 0.00")
        self.lbl_calc_expansao = QtWidgets.QLabel("Expansão: 0.00")
        self.lbl_calc_bloco = QtWidgets.QLabel("Bloco: 0")
        self.lbl_calc_valor_c = QtWidgets.QLabel("Valor C: 0")

        # Mantém a fonte monoespaçada e a estilização visual coerente
        calc_style = "color: #2980b9; font-family: monospace; font-weight: bold; font-size: 10pt;"
        self.lbl_calc_desfoque.setStyleSheet(calc_style)
        self.lbl_calc_expansao.setStyleSheet(calc_style)
        self.lbl_calc_bloco.setStyleSheet(calc_style)
        self.lbl_calc_valor_c.setStyleSheet(calc_style)

        # Alinhamento horizontal em uma única linha
        lyt_calc = QtWidgets.QHBoxLayout()
        lyt_calc.setContentsMargins(0, 5, 0, 0)
        lyt_calc.addWidget(self.lbl_calc_desfoque)
        lyt_calc.addWidget(self.lbl_calc_expansao)
        lyt_calc.addWidget(self.lbl_calc_bloco)
        lyt_calc.addWidget(self.lbl_calc_valor_c)
        
        wdg_calc_container = QtWidgets.QWidget()
        wdg_calc_container.setLayout(lyt_calc)

        # Conexão dos sliders para atualização em tempo real
        self.slider_cor_papel.valueChanged.connect(self._update_ocr_calculated_params)
        self.slider_int_impr.valueChanged.connect(self._update_ocr_calculated_params)
        self.slider_tam_manchas.valueChanged.connect(self._update_ocr_calculated_params)
        self.slider_prof_manchas.valueChanged.connect(self._update_ocr_calculated_params)
        # ---> FIM DA ALTERAÇÃO <---        

        lbl_style = "font-size: 8pt; color: gray;"
        lyt_cv2.addRow(self.chk_ocr_preprocess)
        lyt_cv2.addRow(QtWidgets.QLabel("Cor do Papel<br><span style='%s'>Claro (0) → Escuro (100)</span>" % lbl_style), self.slider_cor_papel)
        lyt_cv2.addRow(QtWidgets.QLabel("Intensidade Impressão<br><span style='%s'>Fraca (0) → Forte (100)</span>" % lbl_style), self.slider_int_impr)
        lyt_cv2.addRow(QtWidgets.QLabel("Tamanho Manchas<br><span style='%s'>Pequenas (0) → Grandes (100)</span>" % lbl_style), self.slider_tam_manchas)
        lyt_cv2.addRow(QtWidgets.QLabel("Profundidade Manchas<br><span style='%s'>Superficiais (0) → Densas (100)</span>" % lbl_style), self.slider_prof_manchas)
        
        lyt_cv2.addRow(wdg_calc_container)
        
        # 2. INSERÇÃO: Checkbox de Força Manual totalmente alinhado à esquerda
        self.chk_manual_opencv = QtWidgets.QCheckBox("Forçar o OpenCV usar estes valores")
        self.chk_manual_opencv.setChecked(self.settings.get("manual_opencv_configs", False))
        lyt_cv2.addRow(self.chk_manual_opencv)
        
        self._update_ocr_calculated_params()
        
        layout.addWidget(grp_cv2)

        grp_tess = QtWidgets.QGroupBox("Motor OCRmyPDF (Tesseract)")
        font_tess = grp_tess.font()
        font_tess.setBold(True)
        grp_tess.setFont(font_tess)
        grp_tess.setStyleSheet("QLabel, QComboBox, QLineEdit, QSpinBox, QCheckBox, QPushButton { font-weight: normal; }")
        
        lyt_tess = QtWidgets.QFormLayout(grp_tess)
        
        self.combo_ocr_lang = QtWidgets.QComboBox()
        self.combo_ocr_lang.addItems(["por", "eng", "spa", "por+eng", "por+eng+spa"])
        self.combo_ocr_lang.setCurrentText(self.settings.get("ocr_lang", "por+eng"))
        
        # ---> INÍCIO: DETECÇÃO DE HARDWARE E LIMITES DINÂMICOS
        try:
            import psutil
            self.physical_cores = psutil.cpu_count(logical=False) or os.cpu_count()
            self.logical_threads = psutil.cpu_count(logical=True) or os.cpu_count()
        except ImportError:
            # Fallback nativo caso psutil não esteja instalado
            self.logical_threads = os.cpu_count() or 4
            self.physical_cores = max(1, self.logical_threads // 2)

        self.spin_ocr_jobs = QtWidgets.QSpinBox()
        self.spin_ocr_jobs.setRange(1, self.logical_threads)
        self.spin_ocr_jobs.setValue(int(self.settings.get("ocr_jobs", 2)))
        self.spin_ocr_jobs.setToolTip(f"Recomendado: até {self.physical_cores} (Núcleos Físicos). Limite de {self.logical_threads} (Threads).")
        
        # Conecta a lógica de cores em tempo real e aplica a cor inicial
        self.spin_ocr_jobs.valueChanged.connect(self._update_ocr_jobs_color)
        self._update_ocr_jobs_color(self.spin_ocr_jobs.value())
        # ---> FIM
        
        self.chk_ocr_sidecar = QtWidgets.QCheckBox("Gerar TXT Separado (.txt)")
        self.chk_ocr_sidecar.setChecked(self.settings.get("ocr_sidecar", False))
        
        lyt_tess.addRow("Idiomas Base:", self.combo_ocr_lang)
        lyt_tess.addRow("Núcleos CPU (Jobs):", self.spin_ocr_jobs)
        lyt_tess.addRow("Arquivamento Extra:", self.chk_ocr_sidecar)
        
        layout.addWidget(grp_tess)
        
        btn_reset_ocr = QtWidgets.QPushButton(" Restaurar padrões de fábrica")
        btn_reset_ocr.setIcon(QtGui.QIcon.fromTheme("edit-clear"))
        btn_reset_ocr.clicked.connect(self._reset_ocr_defaults)
        
        reset_layout = QtWidgets.QHBoxLayout()
        reset_layout.addStretch()
        reset_layout.addWidget(btn_reset_ocr)
        layout.addLayout(reset_layout)
        
        layout.addStretch()
        self.tabs.addTab(tab, "OCR")

    def _update_ocr_calculated_params(self, *args):
        """Calcula e exibe em tempo real os parâmetros matemáticos que serão passados para o OpenCV"""
        escurecimento = self.slider_cor_papel.value()
        intensidade = self.slider_int_impr.value()
        extensao = self.slider_tam_manchas.value()
        profundidade = self.slider_prof_manchas.value()

        # Desfoque (denoise_h)
        h_base = (extensao * 0.15) + (profundidade * 0.05)
        if intensidade < 50:
            denoise_h = h_base * (intensidade / 50.0)
        else:
            denoise_h = h_base
        denoise_h = min(denoise_h, 20.0)

        # Expansão (clahe_clip)
        clahe_base = 1.0 + (escurecimento * 0.03)
        if intensidade < 60:
            contrast_clip = clahe_base + ((60 - intensidade) * 0.05)
        else:
            contrast_clip = clahe_base
        contrast_clip = min(contrast_clip, 6.0)

        # Bloco (block_size)
        raw_block = int(11 + (extensao * 0.4))
        block_size = raw_block + 1 if raw_block % 2 == 0 else raw_block

        # Valor C (c_final)
        c_base = 8 + (escurecimento * 0.05) + (profundidade * 0.1)
        if intensidade < 70:
            c_final = c_base - ((70 - intensidade) * 0.15)
        else:
            c_final = c_base
        c_final = int(max(2, min(c_final, 25)))

        # Atualiza a interface gráfica, limitando os floats a 2 casas decimais para manter a legibilidade
        self.lbl_calc_desfoque.setText(f"Desfoque: {denoise_h:.2f}")
        self.lbl_calc_expansao.setText(f"Expansão: {contrast_clip:.2f}")
        self.lbl_calc_bloco.setText(f"Bloco: {block_size}")
        self.lbl_calc_valor_c.setText(f"Valor C: {c_final}")
        
    def _sync_ui_to_settings(self):
        tab_name = self.current_tab_name
        
        self.settings["input_source"] = self.combo_source.currentText()
        self.settings["project_mode"] = self.combo_project_mode.currentText() 
        self.settings["project_integrity_check"] = self.combo_integrity_check.currentText()
        
        v4l_list = []
        for i in range(self.list_v4l.count()):
            sig = self.list_v4l.item(i).data(QtCore.Qt.UserRole)
            if sig: v4l_list.append(sig)
        self.settings["v4l_devices"] = v4l_list
        
        scanner_list = []
        for i in range(self.list_scanner.count()):
            uri = self.list_scanner.item(i).data(QtCore.Qt.UserRole)
            if uri: scanner_list.append(uri)
        self.settings["scanner_devices"] = scanner_list
        
        if hasattr(self, 'combo_scanner_dpi'):
            self.settings["scanner_dpi"] = int(self.combo_scanner_dpi.currentText())
            self.settings["scanner_color_mode"] = self.combo_scanner_mode.currentText()
            self.settings["scanner_source"] = self.combo_scanner_source.currentText()
            self.settings["scanner_paper_size"] = self.combo_scanner_paper.currentText()
            self.settings["scanner_brightness"] = self.slider_scanner_brightness.value()
            self.settings["scanner_contrast"] = self.slider_scanner_contrast.value()
        
        current_working_dir = self.combo_path.currentText()
        self.settings["working_dir"] = current_working_dir
        
        recentes = self.settings.get("recent_projects", [])
        if current_working_dir in recentes: recentes.remove(current_working_dir) 
        if current_working_dir: recentes.insert(0, current_working_dir) 
        self.settings["recent_projects"] = recentes[:20] 
        
        self.settings["marker_color_left"] = self.combo_left.currentText()
        self.settings["marker_opacity"] = self.slider_opacity.value()
        self.settings["marker_thickness_weight"] = self.slider_weight.value()
        self.settings["marker_color_right"] = self.combo_right.currentText()
        self.settings["marker_fill_color"] = self.combo_fill_color.currentText()
        
        # --- NOVO: SALVAR CONFIGURAÇÕES DE BORDAS ---
        self.settings["image_border_width"] = self.spin_border_width.value()
        self.settings["image_border_color"] = self.combo_border_color.currentText()
        self.settings["image_border_opacity"] = self.slider_border_opacity.value()
        self.settings["image_border_style"] = self.combo_border_style.currentText()
        
        self.settings["rotation_left"] = self.combo_rot_left.currentText()
        self.settings["rotation_right"] = self.combo_rot_right.currentText()
        
        self.settings["image_format"] = self.combo_format.currentText()
        self.settings["jpg_quality"] = self.spin_jpg_quality.value()
        self.settings["png_compression"] = self.spin_png_compression.value()
        self.settings["tiff_compression"] = self.combo_tiff_compression.currentText()
        
        # ---> GRAVAÇÃO: CONTROLE DE IMAGEM CAPTURADA
        if hasattr(self, 'slider_post_brightness'):
            self.settings["post_brightness"] = self.slider_post_brightness.value()
            self.settings["post_contrast"] = self.slider_post_contrast.value()
        
        if hasattr(self, 'combo_ac_preset'):
            self.settings["ac_preset"] = self.combo_ac_preset.currentText()
            blur_val = self.slider_ac_blur.value()
            self.settings["ac_blur"] = blur_val if blur_val % 2 != 0 else blur_val + 1
            self.settings["ac_dilate"] = self.slider_ac_dilate.value()
            self.settings["ac_pad"] = self.slider_ac_pad.value() / 100.0
            self.settings["ac_min_area"] = self.slider_ac_area.value() / 100.0
            self.settings["ac_invert"] = self.combo_ac_invert.currentText()
            self.settings["ac_max_crops"] = self.spin_ac_max.value()
            
            # ---> INSERIR AQUI: Persistência da cor customizada do Auto Crop
            self.settings["ac_use_custom_bg"] = self.chk_ac_custom_bg.isChecked()
            self.settings["ac_bg_color"] = self.combo_ac_bg_color.currentText()
            # ----------------------------------------------------------------
            
            # ---> INSERIR AQUI: Salvar o estado da remoção de fundo <---
            self.settings["bg_detect_enabled"] = self.chk_bg_detect.isChecked()
            self.settings["bg_detect_sensitivity"] = self.slider_bg_sens.value()
            self.settings["bg_replace_color"] = self.combo_bg_color.currentText()
            # ------------------------------------------------------------
        
        self.settings["proc_crop"] = self.chk_crop.isChecked()
        self.settings["proc_deskew"] = self.chk_deskew.isChecked()
        self.settings["proc_dewarp"] = self.chk_dewarp.isChecked()
        self.settings["proc_contour_deskew"] = self.chk_contour_deskew.isChecked()
        self.settings["proc_pdf"] = self.chk_pdf.isChecked()
        self.settings["ignore_ends"] = self.chk_ignore_ends.isChecked() 

        self.settings["deskew_aggressiveness"] = self.slider_deskew_agg.value() / 100.0
        self.settings["dewarp_aggressiveness"] = self.slider_dewarp_agg.value() / 100.0
                
        if self.rb_entrada.isChecked(): self.settings["pdf_source"] = "entrada"
        elif self.rb_originais.isChecked(): self.settings["pdf_source"] = "originais"
        else: self.settings["pdf_source"] = "tratadas"
        
        self.settings["pdf_export_path"] = self.line_export_path.text()
        self.settings["cleanup_after_export"] = self.chk_cleanup.isChecked()
        
        self.settings["proc_ocr"] = self.chk_proc_ocr.isChecked()
        self.settings["ocr_preprocess"] = self.chk_ocr_preprocess.isChecked()
        self.settings["manual_opencv_configs"] = self.chk_manual_opencv.isChecked() # <--- INSERIR AQUI
        self.settings["ocr_cor_papel"] = self.slider_cor_papel.value()
        self.settings["ocr_int_impressao"] = self.slider_int_impr.value()
        self.settings["ocr_tam_manchas"] = self.slider_tam_manchas.value()
        self.settings["ocr_prof_manchas"] = self.slider_prof_manchas.value()
        self.settings["ocr_lang"] = self.combo_ocr_lang.currentText()
        self.settings["ocr_jobs"] = self.spin_ocr_jobs.value()
        self.settings["ocr_sidecar"] = self.chk_ocr_sidecar.isChecked()
        
        if hasattr(self, 'chk_hash_capture'):
            self.settings["custody_calc_hash_on_capture"] = self.chk_hash_capture.isChecked()
            self.settings["custody_log_premis"] = self.chk_premis.isChecked()
            self.settings["custody_export_bagit"] = self.chk_bagit.isChecked()
            self.settings["custody_export_tsv"] = self.chk_tsv.isChecked()
            self.settings["custody_tsv_include_hash"] = self.chk_tsv_hash.isChecked()
            self.settings["custody_tsv_include_ocr"] = self.chk_tsv_ocr.isChecked()
            self.settings["custody_tsv_granularity"] = self.combo_tsv_granularity.currentText()
        
        # ---> INSERIR AQUI: Salvar estado dos componentes da aba do Optuna
        if hasattr(self, 'spin_opt_sessions'):
            self.settings["optuna_sessions"] = self.spin_opt_sessions.value()
            self.settings["optuna_samples"] = self.spin_opt_samples.value()
            self.settings["optuna_target_crop"] = False
            self.settings["optuna_target_ocr"] = True
            self.settings["optuna_trials"] = self.combo_opt_trials.currentData()
            
            # ---> ADICIONAR ESTA LINHA:
            if hasattr(self, 'combo_opt_mode'):
                self.settings["search_space_mode"] = self.combo_opt_mode.currentText()
                self.combo_opt_mode.setCurrentText(self.settings.get("search_space_mode", "Básico"))
        
        # --- Salvar dados da aba Retificar (Fish-eye) ---
        if hasattr(self, 'chk_use_rectify'):
            use_rectify = self.chk_use_rectify.isChecked()
            self.settings["use_fisheye_rectification"] = use_rectify
            
            profile_name = self.combo_checker_profile.currentText().strip()
            if profile_name:
                angle = self.spin_checker_angle.value()
                angle_key = f"angle_{angle}"
                
                # Armazena referências rápidas para a reabertura do diálogo
                self.settings["last_fisheye_profile"] = profile_name
                self.settings["last_fisheye_angle"] = angle
                
                # Inicialização segura da árvore hierárquica
                if "fisheye_profiles" not in self.settings:
                    self.settings["fisheye_profiles"] = {}
                    
                if profile_name not in self.settings["fisheye_profiles"]:
                    self.settings["fisheye_profiles"][profile_name] = {
                        "cameras": {},
                        "settings": {}
                    }
                    
                # Injeção modular dos metadados sob o nó dinâmico do angular
                self.settings["fisheye_profiles"][profile_name]["cameras"][angle_key] = {
                    "checker_x": self.spin_checker_x.value(),
                    "checker_y": self.spin_checker_y.value(),
                    "checker_size": self.spin_checker_size.value(),
                    "checker_path": self.line_checker_path.text()
                }

        # --- Salvar dados da aba Simular (Fish-eye Paramétrico) ---
        if hasattr(self, 'combo_sim_profile'):
            sim_profile = self.combo_sim_profile.currentText().strip()
            if sim_profile:
                self.settings["last_sim_profile"] = sim_profile
                
                if "fisheye_sim_profiles" not in self.settings:
                    self.settings["fisheye_sim_profiles"] = {}
                    
                if sim_profile not in self.settings["fisheye_sim_profiles"]:
                    self.settings["fisheye_sim_profiles"][sim_profile] = {}
                    
                self.settings["fisheye_sim_profiles"][sim_profile].update({
                    "image_path": self.line_sim_image.text(),
                    "width": self.spin_sim_width.value(),
                    "height": self.spin_sim_height.value(),
                    "sim_fov": self.slider_sim_fov.value(),
                    "sim_pan": self.slider_sim_pan.value(),
                    "sim_tilt": self.slider_sim_tilt.value(),
                    "sim_k1": self.slider_sim_k1.value(),
                    "sim_k2": self.slider_sim_k2.value()
                })
                
        # --- Salvar dados da aba Simular (Fish-eye Paramétrico) ---
        if hasattr(self, 'chk_use_simulated'):
            self.settings["use_simulated_rectification"] = self.chk_use_simulated.isChecked()
            
        self._save_project_metadata(current_working_dir)
        
        # save_settings(self.settings)
        # self.settings_saved.emit(self.settings, tab_name)
        # self.accept()

    def _save_simulated_matrices(self):
        profile_name = self.combo_sim_profile.currentText().strip()
        w = self.spin_sim_width.value()
        h = self.spin_sim_height.value()
        
        if not profile_name or w == 0 or h == 0:
            QtWidgets.QMessageBox.warning(self, "Atenção", "Selecione um perfil e carregue uma imagem de referência primeiro.")
            return
            
        import math
        import numpy as np
        
        # Obter valores da interface
        fov_deg = self.slider_sim_fov.value()
        pan = self.slider_sim_pan.value()
        tilt = self.slider_sim_tilt.value()
        
        k1 = self.slider_sim_k1.value() / 1000.0
        k2 = self.slider_sim_k2.value() / 1000.0
        
        # 1. Matemática do Centro Ótico
        cx = (w / 2.0) + pan
        cy = (h / 2.0) + tilt
        
        # 2. Matemática da Distância Focal (Modelo Equidistante)
        diag_px = math.hypot(w, h)
        fov_rad = math.radians(fov_deg)
        focal_length = diag_px / fov_rad if fov_rad > 0 else diag_px
        
        # 3. Montagem das Matrizes do OpenCV
        K = np.array([
            [focal_length, 0, cx],
            [0, focal_length, cy],
            [0, 0, 1]
        ], dtype=np.float64)
        
        D = np.array([[k1], [k2], [0.0], [0.0]], dtype=np.float64)
        
        # 4. Gravação Física no Diretório
        base_install = os.path.dirname(os.path.abspath(__file__)) 
        base_install = os.path.dirname(base_install)
        calib_dir = os.path.join(base_install, "calibrations")
        os.makedirs(calib_dir, exist_ok=True)
        
        safe_profile_name = "".join([c if c.isalnum() else "_" for c in profile_name])
        
        # Note que registamos a "angular" no nome do ficheiro usando o FOV escolhido pelo utilizador
        k_filename = f"fisheye_K_{safe_profile_name}_angle_{fov_deg}.npy"
        d_filename = f"fisheye_D_{safe_profile_name}_angle_{fov_deg}.npy"
        
        k_path = os.path.join(calib_dir, k_filename)
        d_path = os.path.join(calib_dir, d_filename)
        
        np.save(k_path, K)
        np.save(d_path, D)
        
        # 5. Injeção Silenciosa na Aba "Retificar" (Para ficar disponível globalmente)
        if "fisheye_profiles" not in self.settings:
            self.settings["fisheye_profiles"] = {}
        if profile_name not in self.settings["fisheye_profiles"]:
            self.settings["fisheye_profiles"][profile_name] = {"cameras": {}, "settings": {}}
            
        result_data = {
            f"angle_{fov_deg}_K": k_path,
            f"angle_{fov_deg}_D": d_path,
            f"angle_{fov_deg}_rms": 0.0, # RMS simulado é tecnicamente erro 0, pois é pura matemática
            f"angle_{fov_deg}_resolution": [w, h]
        }
        
        self.settings["fisheye_profiles"][profile_name]["settings"].update(result_data)
        
        # Grava os valores atuais dos sliders de simulação para a memória também
        self._sync_ui_to_settings()
        
        QtWidgets.QMessageBox.information(
            self, 
            "Sucesso Paramétrico", 
            f"As matrizes sintéticas para o FOV de {fov_deg}° foram gravadas com sucesso!\n\n"
            f"O Vidya Capture reconhecerá estes parâmetros automaticamente durante a importação "
            f"quando o perfil '{profile_name}' for selecionado."
        )
        
    def _save_and_close(self):
        """Método encapsulado que sincroniza a UI, salva no disco e fecha."""
        tab_name = self.current_tab_name
        self._sync_ui_to_settings() # Coleta tudo que está na tela
        
        save_settings(self.settings)
        self.settings_saved.emit(self.settings, tab_name)
        self.accept()

    def _open_profiles_dialog(self):
        """Abre o gerenciador de perfis garantindo que a memória está atualizada com a UI."""
        self._sync_ui_to_settings()
        
        dialog = VidyaProfilesDialog(self.settings, self)
        
        if dialog.exec_() == QtWidgets.QDialog.Accepted:
            selected_profile = dialog.get_selected_profile()
            if selected_profile:
                # BLINDAGEM INVERSA: Chaves que NUNCA devem ser alteradas ao carregar um perfil
                keys_to_exclude = [
                    "profiles_acervo", "working_dir", "recent_projects", 
                    "pdf_export_path", "project_mode", "project_integrity_check"
                ]
                
                # Injeta os valores do perfil na memória principal, ignorando as chaves de projeto
                for key, value in selected_profile.items():
                    if key not in keys_to_exclude:
                        self.settings[key] = value
                
                # ---> NOVA LÓGICA: Sincroniza a memória com a interface sem fechar a janela
                self._sync_settings_to_ui()
                
                QtWidgets.QMessageBox.information(
                    self, "Perfil Carregado (Modo de Revisão)",
                    "O perfil de acervo foi carregado na interface!\n\n"
                    "As novas configurações já estão visíveis nas abas. Revise os valores e clique em 'Aplicar' para efetivar as mudanças."
                )  
        
