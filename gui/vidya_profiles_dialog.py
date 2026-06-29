# Arquivo: gui/vidya_profiles_dialog.py

from PyQt5 import QtWidgets, QtCore, QtGui
import copy

class VidyaProfilesDialog(QtWidgets.QDialog):
    def __init__(self, current_settings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Perfis Globais de Digitalização (Acervo)")
        self.resize(450, 350)
        
        self.current_settings = current_settings
        
        # Inicializa o dicionário de perfis na memória caso ainda não exista
        if "profiles_acervo" not in self.current_settings:
            self.current_settings["profiles_acervo"] = {}
            
        self.profiles = self.current_settings["profiles_acervo"]
        self.selected_profile_data = None
        
        self._setup_ui()
        self._load_list()

    def _setup_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        
        lbl_info = QtWidgets.QLabel(
            "<b>Gerenciador de Perfis (Presets)</b><br>"
            "<small>Salve o estado completo desta janela (Câmeras, Auto-Crop, OCR, Custódia, etc.) "
            "para alternar rapidamente as configurações dependendo do tipo de acervo físico.</small>"
        )
        lbl_info.setWordWrap(True)
        layout.addWidget(lbl_info)
        
        self.list_profiles = QtWidgets.QListWidget()
        self.list_profiles.setAlternatingRowColors(True)
        layout.addWidget(self.list_profiles)
        
        # --- Botões de Gerenciamento ---
        btn_mgmt_layout = QtWidgets.QHBoxLayout()
        
        self.btn_new = QtWidgets.QPushButton(" Criar Perfil (Estado Atual)")
        self.btn_new.setIcon(QtGui.QIcon.fromTheme("document-new"))
        self.btn_new.clicked.connect(self._create_profile)
        
        # ---> INSERIR AQUI: Novo botão de atualização
        self.btn_update = QtWidgets.QPushButton(" Atualizar Perfil")
        self.btn_update.setIcon(QtGui.QIcon.fromTheme("document-save"))
        self.btn_update.clicked.connect(self._update_profile)
        # -----------------------------------------------
        
        self.btn_delete = QtWidgets.QPushButton(" Remover Perfil")
        self.btn_delete.setIcon(QtGui.QIcon.fromTheme("edit-delete"))
        self.btn_delete.clicked.connect(self._delete_profile)
        
        btn_mgmt_layout.addWidget(self.btn_new)
        btn_mgmt_layout.addWidget(self.btn_update) # <--- Adiciona no layout
        btn_mgmt_layout.addWidget(self.btn_delete)
        btn_mgmt_layout.addStretch()
        layout.addLayout(btn_mgmt_layout)
        
        # --- Botões da Dialog (Rodapé) ---
        box_layout = QtWidgets.QHBoxLayout()
        
        self.btn_load = QtWidgets.QPushButton(" Carregar Perfil Selecionado")
        self.btn_load.setIcon(QtGui.QIcon.fromTheme("document-open"))
        self.btn_load.setStyleSheet("font-weight: bold;")
        self.btn_load.clicked.connect(self._load_profile)
        
        self.btn_cancel = QtWidgets.QPushButton("Cancelar")
        self.btn_cancel.clicked.connect(self.reject)
        
        box_layout.addStretch()
        box_layout.addWidget(self.btn_cancel)
        box_layout.addWidget(self.btn_load)
        
        layout.addLayout(box_layout)

    def _load_list(self):
        self.list_profiles.clear()
        for name in sorted(self.profiles.keys()):
            self.list_profiles.addItem(name)

    def _create_profile(self):
        name, ok = QtWidgets.QInputDialog.getText(
            self, "Novo Perfil", 
            "Digite o nome para o perfil de acervo\n(ex: 'Manuscritos Séc XIX' ou 'Fotos P/B'):"
        )
        if ok and name.strip():
            name = name.strip()
            
            # Cria um snapshot imutável das configurações atuais
            profile_data = copy.deepcopy(self.current_settings)
            
            # BLINDAGEM: Remove as chaves estritamente ligadas a projetos e diretórios
            keys_to_exclude = [
                "profiles_acervo", "working_dir", "recent_projects", 
                "pdf_export_path", "project_mode", "project_integrity_check"
            ]
            for key in keys_to_exclude:
                if key in profile_data:
                    del profile_data[key]
            
            self.profiles[name] = profile_data
            self.current_settings["profiles_acervo"] = self.profiles
            self._load_list()
            
            QtWidgets.QMessageBox.information(self, "Sucesso", f"Perfil '{name}' salvo com sucesso (sem metadados de projeto)!")

    def _update_profile(self):
        """Sobrescreve o perfil selecionado com as configurações atuais da tela, blindando os projetos."""
        item = self.list_profiles.currentItem()
        
        if not item:
            QtWidgets.QMessageBox.warning(
                self, "Aviso", 
                "Selecione um perfil na lista primeiro para poder atualizá-lo."
            )
            return

        name = item.text()
        reply = QtWidgets.QMessageBox.question(
            self, "Confirmar Atualização", 
            f"Atenção: Isso apagará os dados antigos do perfil '{name}'.\n\n"
            "Deseja sobrescrevê-lo com as configurações de imagem/hardware atuais?", 
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
        )
        
        if reply == QtWidgets.QMessageBox.Yes:
            # Tira uma nova "foto" (snapshot) do estado atual do programa
            profile_data = copy.deepcopy(self.current_settings)
            
            # BLINDAGEM: Remove as chaves estritamente ligadas a projetos e diretórios
            keys_to_exclude = [
                "profiles_acervo", "working_dir", "recent_projects", 
                "pdf_export_path", "project_mode", "project_integrity_check"
            ]
            for key in keys_to_exclude:
                if key in profile_data:
                    del profile_data[key]
            
            # Sobrescreve os dados na memória
            self.profiles[name] = profile_data
            self.current_settings["profiles_acervo"] = self.profiles
            
            QtWidgets.QMessageBox.information(
                self, "Sucesso", 
                f"Perfil '{name}' atualizado com as novas calibragens!"
            )

    def _delete_profile(self):
        item = self.list_profiles.currentItem()
        if item:
            name = item.text()
            reply = QtWidgets.QMessageBox.question(
                self, "Remover Perfil", 
                f"Tem certeza que deseja apagar permanentemente o perfil '{name}'?", 
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
            )
            if reply == QtWidgets.QMessageBox.Yes:
                del self.profiles[name]
                self.current_settings["profiles_acervo"] = self.profiles
                self._load_list()
        else:
            QtWidgets.QMessageBox.warning(self, "Aviso", "Selecione um perfil para remover.")
            
    def _load_profile(self):
        item = self.list_profiles.currentItem()
        if item:
            name = item.text()
            self.selected_profile_data = copy.deepcopy(self.profiles[name])
            self.accept()
        else:
            QtWidgets.QMessageBox.warning(self, "Aviso", "Selecione um perfil na lista primeiro.")
            
    def get_selected_profile(self):
        return self.selected_profile_data
