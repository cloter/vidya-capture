# Arquivo: main.py
import sys
import time
import os
import glob
import json
import signal
from PyQt5 import QtWidgets, QtCore, QtGui

# sudo dpkg -i vidya-capture_0.2.25_all.deb; sudo apt --fix-broken install; sudo apt install python3-optuna; exit

# ---> VARIÁVEL GLOBAL DE pip3 install pytesseract
# (Atualizada por script externo de controle de versão)
VIDYA_VERSION = "0.2.28"
VIDYA_AUTHOR = "Cloter Migiorini Fiho"
# Injeta no ambiente para leitura em qualquer arquivo via: os.getenv("VIDYA_VERSION")
os.environ["VIDYA_VERSION"] = VIDYA_VERSION 

# ---> INÍCIO DA INSERÇÃO: TELA DE CARREGAMENTO (SPLASH SCREEN) <---
# Instancia a aplicação GUI nativa mais cedo para desenhar a tela de loading
app_instance = QtWidgets.QApplication.instance()
if not app_instance:
    app_instance = QtWidgets.QApplication(sys.argv)

class VidyaSplashScreen(QtWidgets.QSplashScreen):
    def __init__(self):
        pixmap = QtGui.QPixmap(600, 380)
        pixmap.fill(QtCore.Qt.white) # Fundo branco
        super().__init__(pixmap, QtCore.Qt.WindowStaysOnTopHint | QtCore.Qt.FramelessWindowHint)
        
        self.wait_for_esc = False # <--- NOVO: Controla se deve reter a tela até o ESC
        
        self.layout = QtWidgets.QVBoxLayout()
        self.layout.setSpacing(5)
        self.layout.addStretch()
        
        # 1. Logo centralizada no topo
        self.logo_label = QtWidgets.QLabel()
        self.logo_label.setAlignment(QtCore.Qt.AlignCenter)
        
        # O main.py está na raiz, então procuramos a pasta assets na mesma hierarquia
        icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'assets', 'vidya_capture_icon.png')
        if os.path.exists(icon_path):
            logo_pix = QtGui.QPixmap(icon_path).scaled(100, 100, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)
            self.logo_label.setPixmap(logo_pix)
        self.layout.addWidget(self.logo_label)
        
        # 2. Título Principal
        self.title = QtWidgets.QLabel("Vidya Capture")
        self.title.setStyleSheet("color: #2c3e50; font-size: 34px; font-weight: bold; font-family: sans-serif;")
        self.title.setAlignment(QtCore.Qt.AlignCenter)
        self.layout.addWidget(self.title)
        
        # 3. Bloco Horizontal: Versão (Esquerda) e Autoria (Direita)
        info_layout = QtWidgets.QHBoxLayout()
        info_layout.setContentsMargins(0, 0, 0, 0)
        
        self.version_label = QtWidgets.QLabel(f"Versão {VIDYA_VERSION}")
        self.version_label.setStyleSheet("color: #7f8c8d; font-size: 13px; font-family: sans-serif; font-weight: bold;")
        self.version_label.setAlignment(QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter)
        
        self.author_label = QtWidgets.QLabel(f"Desenvolvido por {VIDYA_AUTHOR}")
        self.author_label.setStyleSheet("color: #7f8c8d; font-size: 13px; font-family: sans-serif;")
        self.author_label.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        
        info_layout.addWidget(self.version_label)
        info_layout.addWidget(self.author_label)
        
        # Container para alinhar as infos com margens laterais
        info_container = QtWidgets.QWidget()
        info_container.setLayout(info_layout)
        info_container.setContentsMargins(80, 0, 80, 0)
        self.layout.addWidget(info_container)
        
        # ---> NOVO: Linha de Contato e Instituição (Centralizado) <---
        self.contact_label = QtWidgets.QLabel("cloterm@gmail.com - LAMUHDI.MCG.UEPG - ©2026")
        self.contact_label.setStyleSheet("color: #7f8c8d; font-size: 13px; font-family: sans-serif;")
        self.contact_label.setAlignment(QtCore.Qt.AlignCenter)
        self.layout.addWidget(self.contact_label)
        # ---> FIM DO CÓDIGO NOVO <---
        
        self.layout.addSpacing(25)
        
        # 4. Status de carregamento atual
        self.subtitle = QtWidgets.QLabel("Iniciando ambiente...")
        self.subtitle.setStyleSheet("color: #34495e; font-size: 13px; font-family: sans-serif;")
        self.subtitle.setAlignment(QtCore.Qt.AlignCenter)
        self.layout.addWidget(self.subtitle)
        
        self.layout.addSpacing(10)
        
        # 5. Barra de progresso repaginada para fundo branco
        self.progress = QtWidgets.QProgressBar()
        self.progress.setStyleSheet("""
            QProgressBar { border: 1px solid #bdc3c7; border-radius: 4px; text-align: center; color: #2c3e50; background-color: #ecf0f1; height: 16px; font-size: 11px;}
            QProgressBar::chunk { background-color: #2980b9; width: 10px; }
        """)
        self.progress.setRange(0, 100)
        
        progress_container = QtWidgets.QWidget()
        progress_layout = QtWidgets.QHBoxLayout(progress_container)
        progress_layout.setContentsMargins(50, 0, 50, 0)
        progress_layout.addWidget(self.progress)
        
        self.layout.addWidget(progress_container)
        self.layout.addStretch()
        
        central_widget = QtWidgets.QWidget()
        central_widget.setLayout(self.layout)
        
        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.addWidget(central_widget)
        
    # ---> NOVO: Intercepta a tecla ESC se a flag estiver ativa
    def keyPressEvent(self, event):
        if self.wait_for_esc and event.key() == QtCore.Qt.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)

    def update_state(self, value, text):
        self.progress.setValue(value)
        self.subtitle.setText(text)
        app_instance.processEvents() # Força a interface a atualizar antes de congelar no próximo import
        time.sleep(0.25) # <--- NOVO: Garante no mínimo 200ms de visibilidade por etapa

splash = VidyaSplashScreen()
splash.show()
app_instance.processEvents()
# ---> FIM DA INSERÇÃO <---

splash.update_state(10, "Carregando configurações base do sistema...")
from core.logger import get_logger
from core.config import load_settings, save_settings
app_instance.processEvents()

splash.update_state(30, "Carregando interface gráfica e bibliotecas visuais...")
from gui.vidya_capture_gui import VidyaMainWindow
from hardware.vidya_capture_usb_manager import VidyaCaptureUsbManager
from gui.vidya_process_dialog import VidyaProcessDialog
app_instance.processEvents()

splash.update_state(50, "Carregando conectores de hardware (Câmeras e Scanners)...")
from hardware.vidya_capture_camera_worker import VidyaCameraWorker
from hardware.vidya_capture_v4l2_worker import VidyaV4L2Worker
from hardware.vidya_capture_scanner_worker import VidyaScannerWorker
from hardware.mock_camera import MockCamera
app_instance.processEvents()

splash.update_state(70, "Carregando motores de processamento e inteligência artificial...")
from core.project_manager import VidyaProjectAuditor
from core.project_manager import VidyaSingleAuditor
from core.vidya_processor import VidyaImageProcessor
from core.vidya_processor import VidyaSingleProcessor
app_instance.processEvents()

splash.update_state(90, "Iniciando controladores principais...")
logger = get_logger("Main")

class VidyaAppController:
    def __init__(self):
        logger.info("Iniciando rotinas de boot do Vidya Capture...")
        # self.app = QtWidgets.QApplication(sys.argv)
        self.app = QtWidgets.QApplication.instance() # <--- MODIFICADO: Usa a instância criada na tela de loading
        
        # ---> INÍCIO DA TRAVA DE INSTÂNCIA ÚNICA (SUBSTITUIÇÃO) <---
        self.pid_file = os.path.expanduser("~/.vidya_capture.pid")
        current_pid = os.getpid()
        
        if os.path.exists(self.pid_file):
            try:
                with open(self.pid_file, 'r') as f:
                    old_pid = int(f.read().strip())
                
                # Testa se o processo antigo (PID) ainda está ativo no sistema operativo
                is_running = False
                try:
                    os.kill(old_pid, 0) # O sinal 0 não encerra, apenas verifica se o PID existe
                    is_running = True
                except OSError:
                    pass
                    
                if is_running:
                    msgBox = QtWidgets.QMessageBox(None)
                    msgBox.setIcon(QtWidgets.QMessageBox.Warning)
                    msgBox.setWindowTitle("Instância Duplicada")
                    msgBox.setText("O Vidya Capture já está em execução neste computador!")
                    msgBox.setInformativeText("O acesso simultâneo causará bloqueios nas portas USB e câmeras V4L. O que deseja fazer?")
                    
                    btn_kill = msgBox.addButton("Encerrar a outra e continuar", QtWidgets.QMessageBox.DestructiveRole)
                    btn_abort = msgBox.addButton("Encerrar esta", QtWidgets.QMessageBox.RejectRole)
                    msgBox.setDefaultButton(btn_abort)
                    
                    msgBox.exec_()
                    
                    if msgBox.clickedButton() == btn_kill:
                        logger.info(f"Encerrando a instância anterior (PID: {old_pid})...")
                        os.kill(old_pid, signal.SIGTERM)
                        time.sleep(1.5) # Aguarda a libertação limpa dos barramentos do hardware
                    else:
                        sys.exit(0)
            except Exception as e:
                logger.error(f"Erro ao verificar trava de instância via PID: {e}")
                
        # Regista o PID da nova instância para controle futuro
        try:
            with open(self.pid_file, 'w') as f:
                f.write(str(current_pid))
        except Exception as e:
            logger.error(f"Não foi possível salvar o arquivo PID: {e}")
        # ---> FIM DA TRAVA <---
        
        self.window = VidyaMainWindow()
        self.usb_manager = VidyaCaptureUsbManager()
        
        self.worker_left = None
        self.worker_right = None
        self.is_single_mode = False  # Flag Mestra de Topologia do Laboratório

        self.window.invert_requested.connect(self._invert_devices)
        self.window.capture_requested.connect(self._dispatch_capture)
        self.window.settings_updated.connect(self._on_project_settings_changed)
        self.window.reload_requested.connect(self._handle_reload_project)
        self.window.btn_process.clicked.connect(self._on_process_batch_clicked)
        
        # --- INÍCIO DO CÓDIGO NOVO (SINAL DE ENCERRAMENTO SEGURO) ---
        if hasattr(self.window, 'shutdown_requested'):
            self.window.shutdown_requested.connect(self._desligar_hardware_graciosamente)
        # --- FIM DO CÓDIGO NOVO ---
        
        # ---> NOVO: Conecta o sinal do F4 à função de replay da Splash Screen
        if hasattr(self.window, 'show_splash_requested'):
            self.window.show_splash_requested.connect(self._replay_splash_screen)
            
        self._load_active_project(show_summary=False)
        self._initialize_devices()
       
    def _handle_reload_project(self):
        logger.info("Solicitação de reload recebida. Sincronizando diretório...")
        if self.worker_left: self.worker_left.stop()
        if self.worker_right: self.worker_right.stop()
        self._load_active_project(show_summary=False)
        self._initialize_devices()
        logger.info("Projeto e hardware recarregados com sucesso.")        

    def _on_project_settings_changed(self, new_settings: dict):
        logger.info("Sinal de Preferências recebido no Orquestrador. Reiniciando dispositivos...")
        if self.worker_left: self.worker_left.stop()
        if self.worker_right: self.worker_right.stop()
        time.sleep(0.5)
        self._load_active_project(show_summary=True)
        self._initialize_devices()

    def _load_active_project(self, show_summary: bool = False):
        settings = load_settings()
        working_dir = settings.get("working_dir")
        
        # 1. Define o modo de operação e avisa a GUI para montar o ecrã
        self.is_single_mode = (settings.get("project_mode") == "Mesa Plana (Câmera Única)")
        if hasattr(self.window, 'apply_project_mode'):
            self.window.apply_project_mode(self.is_single_mode)
        
        if working_dir and os.path.exists(working_dir):
            proj_file = os.path.join(working_dir, "project.json")
            if os.path.exists(proj_file):
                try:
                    with open(proj_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        capture_params = data.get("capture_params", {})
                        if capture_params:
                            updated = False
                            keys_to_check = ["input_source", "rotation_left", "rotation_right", "project_mode"]
                            for key in keys_to_check:
                                if key in capture_params and settings.get(key) != capture_params[key]:
                                    settings[key] = capture_params[key]
                                    updated = True
                            if updated:
                                save_settings(settings)
                                self.window.settings = settings
                                self.is_single_mode = (settings.get("project_mode") == "Mesa Plana (Câmera Única)")
                                logger.info("Configurações de topologia restauradas a partir do projeto ativo.")
                except Exception:
                    pass
        
        # 2. Auditoria Bifurcada
        if self.is_single_mode:
            if VidyaSingleAuditor:
                report = VidyaSingleAuditor.audit_directory(working_dir)
                
                # ---> INÍCIO DA CORREÇÃO: GANCHO PARA O MODO LEGADO (CÂMERA ÚNICA) <---
                if report.get("is_legacy", False):
                    from core.project_manager import VidyaLegacyImporter
                    new_dir = VidyaLegacyImporter.run_import(self.window, working_dir, settings)
                    if new_dir:
                        settings["working_dir"] = new_dir
                        settings["rotation_left"] = "0°"
                        settings["rotation_right"] = "0°"
                        save_settings(settings)
                        self.window.settings = settings 
                        self.window.thumbnail_panel.update_settings_ref(settings)
                        working_dir = new_dir
                        
                        # Re-audita a nova pasta work_dir que agora possui os JSONs
                        report = VidyaSingleAuditor.audit_directory(working_dir)
                # ---> FIM DA CORREÇÃO <---
                
                if hasattr(self.window.thumbnail_panel, 'load_project_single'):
                    self.window.thumbnail_panel.load_project_single(report.get("valid_items", []))
            else:
                report = {"valid_items": []}
                logger.warning("VidyaSingleAuditor pendente. Ignorando auditoria de Câmera Única.")
                
        else: # MODO ORIGINAL (Berço em V)
            report = VidyaProjectAuditor.audit_directory(working_dir)
            
            if report.get("is_legacy", False):
                from core.project_manager import VidyaLegacyImporter
                new_dir = VidyaLegacyImporter.run_import(self.window, working_dir, settings)
                if new_dir:
                    settings["working_dir"] = new_dir
                    settings["rotation_left"] = "0°"
                    settings["rotation_right"] = "0°"
                    save_settings(settings)
                    self.window.settings = settings 
                    self.window.thumbnail_panel.update_settings_ref(settings)
                    working_dir = new_dir
                    report = VidyaProjectAuditor.audit_directory(working_dir)
            
            self.window.thumbnail_panel.load_project_pairs(report.get("valid_pairs", []))
            
        self.window.update_status_bar()
        
        # 3. Carregamento da última imagem na vista principal
        if self.is_single_mode:
            last_item = report.get("valid_items", [])[-1] if report.get("valid_items") else None
            if last_item and os.path.exists(last_item["image"]):
                try:
                    with open(last_item["image"], 'rb') as f:
                        self.window.update_frame("Left", f.read(), is_live=False)
                    if os.path.exists(last_item["json"]):
                        with open(last_item["json"], 'r', encoding='utf-8') as jf:
                            meta = json.load(jf)
                            if "crop_geometry" in meta and meta["crop_geometry"]:
                                self.window.marker_left.set_geometry(meta["crop_geometry"])
                                settings["marker_left_geometry"] = meta["crop_geometry"]
                except Exception as e:
                    logger.error(f"Falha ao carregar imagem única: {e}")
        else:
            last_left_path, last_left_json, last_right_path, last_right_json = None, None, None, None
            for pair in report.get("valid_pairs", []):
                img_path = pair["image"]
                if "Left" in os.path.basename(img_path): last_left_path = img_path; last_left_json = pair["json"]
                elif "Right" in os.path.basename(img_path): last_right_path = img_path; last_right_json = pair["json"]

            if last_left_path and os.path.exists(last_left_path):
                try:
                    with open(last_left_path, 'rb') as f:
                        self.window.update_frame("Left", f.read(), is_live=False)
                    if last_left_json and os.path.exists(last_left_json):
                        with open(last_left_json, 'r', encoding='utf-8') as jf:
                            meta = json.load(jf)
                            if "crop_geometry" in meta and meta["crop_geometry"]:
                                self.window.marker_left.set_geometry(meta["crop_geometry"])
                                settings["marker_left_geometry"] = meta["crop_geometry"]
                except Exception as e: logger.error(f"Falha img esq: {e}")
                    
            if last_right_path and os.path.exists(last_right_path):
                try:
                    with open(last_right_path, 'rb') as f:
                        self.window.update_frame("Right", f.read(), is_live=False)
                    if last_right_json and os.path.exists(last_right_json):
                        with open(last_right_json, 'r', encoding='utf-8') as jf:
                            meta = json.load(jf)
                            if "crop_geometry" in meta and meta["crop_geometry"]:
                                self.window.marker_right.set_geometry(meta["crop_geometry"])
                                settings["marker_right_geometry"] = meta["crop_geometry"]
                except Exception as e: logger.error(f"Falha img dir: {e}")

        save_settings(settings)

        if show_summary:
            total_count = len(report.get("valid_items", [])) if self.is_single_mode else len(report.get("valid_pairs", [])) // 2
            tipo_msg = "Imagens" if self.is_single_mode else "Pares"
            QtWidgets.QMessageBox.information(self.window, "Auditoria", f"Projeto Carregado: {total_count} {tipo_msg} identificados.")
            
        self.window.update_status_bar()

    def _refresh_thumbnails(self):
        """Força a interface a reler os ficheiros após um Deslocamento em Cascata."""
        settings = load_settings()
        working_dir = settings.get("working_dir")
        
        if working_dir and os.path.exists(working_dir):
            if self.is_single_mode and VidyaSingleAuditor:
                report = VidyaSingleAuditor.audit_directory(working_dir)
                if hasattr(self.window.thumbnail_panel, 'load_project_single'):
                    self.window.thumbnail_panel.load_project_single(report.get("valid_items", []))
            else:
                report = VidyaProjectAuditor.audit_directory(working_dir)
                self.window.thumbnail_panel.load_project_pairs(report.get("valid_pairs", []))
            self.window.update_status_bar()

    def _dispatch_capture(self, mode: str, replacement_paths: dict, crop_geometries: dict):
        import time
        batch_ts = str(int(time.time())) 
        
        worker_mode = mode

        # Mapeamento dinâmico de substituição
        if mode in ["Substituir Par", "Substituição Direcionada", "Substituir Esquerda", "Substituir Direita", "Substituir Imagem"]:
            worker_mode = "Substituir"
            valid_path = replacement_paths.get("Left") or replacement_paths.get("Right")
            if valid_path:
                try:
                    batch_ts = os.path.basename(valid_path).split('_')[2].split('.')[0]
                except: pass

        # Deslocamento em Cascata Direcionado
        elif mode in ["Inserir Antes", "Inserir Depois"]:
            worker_mode = "Nova Captura"
            settings = load_settings()
            working_dir = settings.get("working_dir")
            
            if working_dir and os.path.exists(working_dir):
                if self.is_single_mode and VidyaSingleAuditor:
                    batch_ts = VidyaSingleAuditor.execute_shift_cascade(working_dir, replacement_paths, mode)
                else:
                    batch_ts = VidyaProjectAuditor.execute_shift_cascade(working_dir, replacement_paths, mode)
            
            replacement_paths = {"Left": None, "Right": None}
            self._refresh_thumbnails()

        elif mode == "Substituir":
            pass # Fallback nativo

        # Lógica de disparo parcial / modo único
        trigger_left = True
        trigger_right = True

        if mode == "Substituir Esquerda": trigger_right = False
        elif mode == "Substituir Direita": trigger_left = False
        
        if self.is_single_mode: 
            trigger_right = False

        if self.worker_left and trigger_left: 
            self.worker_left.trigger_capture(
                mode=worker_mode, 
                target_path=replacement_paths.get("Left"), 
                crop_geometry=crop_geometries.get("Left"), 
                batch_ts=batch_ts
            )
        
        if self.worker_right and trigger_right: 
            self.worker_right.trigger_capture(
                mode=worker_mode, 
                target_path=replacement_paths.get("Right"), 
                crop_geometry=crop_geometries.get("Right"), 
                batch_ts=batch_ts
            )

    def _update_processor_progress(self, value, text):
        self.progress_dialog.setValue(value)
        self.progress_dialog.setLabelText(text)

    def _on_processor_finished(self, out_dir):
        import shutil
        import glob
        
        self.progress_dialog.close()
        
        settings = load_settings()
        export_path = settings.get("pdf_export_path", "")
        cleanup = settings.get("cleanup_after_export", False)
        
        final_message = f"Processamento concluído com sucesso e salvo na pasta do projeto:\n{out_dir}"
        pdf_files = glob.glob(os.path.join(out_dir, "*.pdf"))
        
        if pdf_files and export_path and os.path.exists(export_path):
            source_pdf = pdf_files[0]
            pdf_filename = os.path.basename(source_pdf)
            dest_pdf = os.path.join(export_path, pdf_filename)
            
            try:
                shutil.copy2(source_pdf, dest_pdf)
                
                if os.path.exists(dest_pdf) and os.path.getsize(dest_pdf) == os.path.getsize(source_pdf):
                    final_message = f"O PDF foi gerado e exportado com sucesso para:\n{dest_pdf}"
                    logger.info(f"PDF exportado de forma segura para: {dest_pdf}")
                    
                    if cleanup:
                        try:
                            shutil.rmtree(out_dir)
                            final_message += "\n\n(A pasta temporária 'out' foi removida com sucesso para libertar espaço no disco)."
                            logger.info(f"Limpeza de disco ativada. Pasta removida: {out_dir}")
                        except Exception as e:
                            logger.error(f"Falha ao apagar pasta temporária: {e}")
                            final_message += f"\n\n(Aviso: O PDF está salvo, mas ocorreu um bloqueio ao apagar a pasta 'out': {e})"
                else:
                    final_message = f"AVISO: Ocorreu uma discrepância de tamanho durante a cópia para a pasta final.\nO PDF original permanece intacto e seguro na pasta:\n{out_dir}"
                    logger.warning("Falha na validação de bytes ao exportar PDF.")
                    
            except Exception as e:
                logger.error(f"Erro inesperado ao copiar o PDF final: {e}")
                final_message = f"Erro na operação de cópia. O documento está seguro em:\n{out_dir}\nErro reportado: {str(e)}"
                
        QtWidgets.QMessageBox.information(self.window, "Processamento Concluído", final_message)

    def _on_processor_error(self, error_msg):
        self.progress_dialog.close()
        QtWidgets.QMessageBox.critical(self.window, "Erro", f"Ocorreu um erro:\n{error_msg}")
        
    def _on_process_batch_clicked(self):
        settings = load_settings()
        working_dir = settings.get("working_dir")
        
        # BIFURCAÇÃO DA LISTA DE TAREFAS
        if self.is_single_mode:
            if not VidyaSingleAuditor or not VidyaSingleProcessor:
                QtWidgets.QMessageBox.warning(self.window, "Aviso", "Classes do Modo Câmera Única não implementadas ainda.")
                return
            report = VidyaSingleAuditor.audit_directory(working_dir)
            valid_list = report.get("valid_items", [])
            tipo_erro = "imagens"
        else:
            report = VidyaProjectAuditor.audit_directory(working_dir)
            valid_list = report.get("valid_pairs", [])
            tipo_erro = "pares"
            
        if not valid_list:
            QtWidgets.QMessageBox.warning(self.window, "Aviso", f"Não há {tipo_erro} para processar.")
            return

        # Filtro de eliminação de capas vazias
        if settings.get("ignore_ends", False) and len(valid_list) > 2:
            valid_list = valid_list[1:-1]
            logger.info(f"Filtro ativado: Ignorando as extremidades do lote. Restam {len(valid_list)} itens.")

        dialog = VidyaProcessDialog(settings, self.window)
        if dialog.exec_():
            flags = dialog.get_execution_flags()
            self.progress_dialog = QtWidgets.QProgressDialog("Iniciando OpenCV...", "Cancelar", 0, 100, self.window)
            self.progress_dialog.setWindowTitle("Processamento")
            self.progress_dialog.setWindowModality(QtCore.Qt.WindowModal)
            self.progress_dialog.show()
            
            if self.is_single_mode:
                self.processor_thread = VidyaSingleProcessor(valid_list, working_dir, flags, settings)
            else:
                self.processor_thread = VidyaImageProcessor(valid_list, working_dir, flags, settings)
                
            self.processor_thread.progress_update.connect(self._update_processor_progress)
            self.processor_thread.process_finished.connect(self._on_processor_finished)
            self.processor_thread.process_error.connect(self._on_processor_error)
            self.progress_dialog.canceled.connect(self.processor_thread.terminate)
            self.processor_thread.start()

    # =========================================================================
    # MOTOR DE EXTRAÇÃO DE TOPOLOGIA FÍSICA E NOMES
    # =========================================================================
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

    def _get_device_friendly_name(self, source: str, signature: str, settings: dict) -> str:
        if not signature: return "Nenhum"
        custom_names = settings.get("custom_device_names", {})
        if signature in custom_names: return custom_names[signature]
        if source == "Classe Mock": return "Câmera Simulada"
        elif source == "Câmeras": return f"DSLR/PTP"
        elif source == "Scanners": return f"Scanner SANE"
        return signature

    def _initialize_devices(self):
        settings = load_settings()
        source = settings.get("input_source", "Câmeras")
        target_working_dir = settings.get("working_dir")
        is_inverted = settings.get("devices_inverted", False)

        port_left = None
        port_right = None
        signature_left = None
        signature_right = None
        worker_class = MockCamera

        logger.info(f"Inicializando hardware de captura. Origem: {source} | Modo Simples: {self.is_single_mode}")

        if source == "Câmeras":
            ports = self.usb_manager.detect_cameras()
            worker_class = VidyaCameraWorker
            if len(ports) > 0: port_left = ports[0]; signature_left = ports[0]
            if len(ports) > 1: port_right = ports[1]; signature_right = ports[1]

        elif source == "V4L":
            worker_class = VidyaV4L2Worker
            current_v4l = sorted(glob.glob('/dev/video*'))
            current_map = {self._get_v4l_signature(path): path for path in current_v4l}
            
            saved_signatures = settings.get("v4l_devices", [])
            if not saved_signatures:
                if len(current_v4l) > 0: port_left = current_v4l[0]; signature_left = self._get_v4l_signature(port_left)
                if len(current_v4l) > 1: port_right = current_v4l[1]; signature_right = self._get_v4l_signature(port_right)
            else:
                if len(saved_signatures) > 0:
                    signature_left = saved_signatures[0]
                    port_left = current_map.get(signature_left) 
                if len(saved_signatures) > 1:
                    signature_right = saved_signatures[1]
                    port_right = current_map.get(signature_right)

        elif source == "Scanners":
            worker_class = VidyaScannerWorker 
            ports = settings.get("scanner_devices", [])
            if not ports:
                import sane
                sane.init()
                devices = sane.get_devices()
                ports = [dev[0] for dev in devices] 
                sane.exit()

            if len(ports) > 0: port_left = ports[0]; signature_left = ports[0]
            if len(ports) > 1: port_right = ports[1]; signature_right = ports[1]

        elif source == "Classe Mock":
            worker_class = MockCamera
            port_left = "Mock_L"; signature_left = "Mock_L"
            port_right = "Mock_R"; signature_right = "Mock_R"

        # Interceção de segurança para o Modo Mesa Plana
        if self.is_single_mode:
            port_right = None
            signature_right = None
            is_inverted = False  

        name_left = self._get_device_friendly_name(source, signature_left, settings)
        name_right = self._get_device_friendly_name(source, signature_right, settings)

        if self.is_single_mode:
            name_right = "Desativado (Modo Câmera Única)"

        if is_inverted:
            port_left, port_right = port_right, port_left
            name_left, name_right = name_right, name_left

        self.window.set_device_names(name_left, name_right)

        if port_left:
            self.worker_left = worker_class(port_address=port_left, position="Left")
        else:
            logger.warning(f"Dispositivo {signature_left or 'Left'} não encontrado hoje. Fallback para Mock.")
            self.worker_left = MockCamera(position="Left")

        # Inicia e amarra apenas o que é estritamente necessário
        self.worker_left.working_dir = target_working_dir
        self.worker_left.settings = settings
        self.worker_left.frame_ready.connect(lambda frame: self.window.update_frame("Left", frame))
        self.worker_left.capture_complete.connect(self.window.enqueue_thumbnail)
        self.worker_left.start()

        if port_right and not self.is_single_mode:
            self.worker_right = worker_class(port_address=port_right, position="Right")
            self.worker_right.working_dir = target_working_dir
            self.worker_right.settings = settings
            self.worker_right.frame_ready.connect(lambda frame: self.window.update_frame("Right", frame))
            self.worker_right.capture_complete.connect(self.window.enqueue_thumbnail)
            self.worker_right.start()
        elif not self.is_single_mode:
            logger.warning(f"Dispositivo {signature_right or 'Right'} não encontrado hoje. Fallback para Mock.")
            self.worker_right = MockCamera(position="Right")
            self.worker_right.start()
        else:
            self.worker_right = None

    def _invert_devices(self):
        if self.is_single_mode:
            return # Inverter não tem efeito em câmera única

        self.window.btn_invert.setEnabled(False)
        if self.worker_left: self.worker_left.stop()
        if self.worker_right: self.worker_right.stop()
        time.sleep(1) 
        settings = load_settings()
        settings["devices_inverted"] = not settings.get("devices_inverted", False)
        save_settings(settings)
        self._initialize_devices()
        self.window.btn_invert.setEnabled(True)
        
    # =========================================================================
    # MOTOR DE ENCERRAMENTO SEGURO (PREVENÇÃO DE CORE DUMP V4L)
    # =========================================================================
    def _desligar_hardware_graciosamente(self):
        try:
            logger.info("Selando os dispositivos de captura para evitar ruturas no sistema operativo...")
            
            # --- Encerramento Câmera Única / Esquerda ---
            if hasattr(self, 'worker_left') and self.worker_left is not None:
                # 1. Corta a comunicação do sinal de imagem para a GUI
                try:
                    self.worker_left.disconnect()
                except Exception:
                    pass
                
                # 2. Tenta parar o ciclo de leitura da thread
                if hasattr(self.worker_left, 'stop'):
                    self.worker_left.stop()
                elif hasattr(self.worker_left, 'running'):
                    self.worker_left.running = False
                    
                # 3. Força a junção da thread com um timeout estrito de 1.5s
                if hasattr(self.worker_left, 'wait'):
                    self.worker_left.wait(1500) 

            # --- Encerramento Câmera Dupla / Direita ---
            if hasattr(self, 'worker_right') and self.worker_right is not None:
                try:
                    self.worker_right.disconnect()
                except Exception:
                    pass
                
                if hasattr(self.worker_right, 'stop'):
                    self.worker_right.stop()
                elif hasattr(self.worker_right, 'running'):
                    self.worker_right.running = False
                    
                if hasattr(self.worker_right, 'wait'):
                    self.worker_right.wait(1500)

        except Exception as e:
            # Captura absoluta de qualquer exceção para blindar o PyQt
            logger.error(f"Erro silenciado durante o desligamento do hardware: {e}")

    def _replay_splash_screen(self):
        """Re-instancia e roda a splash screen rapidamente ao pressionar F4."""
        logger.info("Reexibindo a Splash Screen (F4)...")
        
        # Bloqueia a janela principal temporariamente para evitar cliques acidentais
        self.window.setEnabled(False) 
        
        replay_splash = VidyaSplashScreen()
        replay_splash.wait_for_esc = True # <--- NOVO: Ativa a retenção por teclado
        replay_splash.show()
        
        # Simula um carregamento rápido apenas para demonstração/créditos
        etapas = [
            (20, "Revisando configurações base..."),
            (40, "Verificando bibliotecas visuais..."),
            (60, "Sincronizando hardware..."),
            (80, "Verificando motores de inteligência artificial..."),
            (100, "ESC para voltar")
        ]
        
        for val, texto in etapas:
            replay_splash.update_state(val, texto)
            
        # ---> NOVO: Em vez de time.sleep(), criamos um loop local de eventos 
        # que processa o teclado e só encerra quando a Splash Screen for fechada.
        loop = QtCore.QEventLoop()
        old_close = replay_splash.closeEvent
        replay_splash.closeEvent = lambda event: [old_close(event), loop.quit()]
        
        loop.exec_() # Segura a execução reativamente aqui até o ESC ser teclado
        
        replay_splash.finish(self.window)
        
        # Libera a janela principal
        self.window.setEnabled(True)
        
    # =========================================================================
    # EXECUÇÃO PRINCIPAL
    # =========================================================================
    def run(self):
        splash.update_state(100, "Pronto!")
        time.sleep(0.5) # Breve pausa visual para o utilizador perceber o 100%
        self.window.show()
        splash.finish(self.window) # Esconde a tela de carregamento e passa o foco para a GUI
        sys.exit(self.app.exec_())


if __name__ == "__main__":
    controller = VidyaAppController()
    controller.run()
