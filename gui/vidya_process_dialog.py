# Arquivo: gui/vidya_process_dialog.py

from PyQt5 import QtWidgets, QtGui, QtCore

class VidyaProcessDialog(QtWidgets.QDialog):
    """
    Janela de confirmação final que aparece antes do início do processamento em lote.
    Permite ativar/desativar etapas (Crop, Deskew, PDF, OCR) on-the-fly.
    """
    def __init__(self, settings: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Processamento em Lote")
        self.setMinimumWidth(350)
        self.settings = settings
        self._setup_ui()

    def _setup_ui(self):
        layout = QtWidgets.QVBoxLayout(self)
        
        lbl_info = QtWidgets.QLabel("Selecione as etapas que deseja executar neste lote:")
        layout.addWidget(lbl_info)
        
        # 1. Grupo de Processamento Geométrico (OpenCV)
        grp_img = QtWidgets.QGroupBox("1. Tratamento de Imagem")
        lyt_img = QtWidgets.QVBoxLayout(grp_img)
        
        self.chk_crop = QtWidgets.QCheckBox("Cortar (Crop)")
        self.chk_crop.setChecked(self.settings.get("proc_crop", True))
        
        # ---> INSERIR AQUI: Novo checkbox de contorno <---
        self.chk_contour_deskew = QtWidgets.QCheckBox("Alinhamento Físico (Deskew de Contorno/Fotos)")
        self.chk_contour_deskew.setChecked(self.settings.get("proc_contour_deskew", False))
        self.chk_contour_deskew.setToolTip("Alinha a imagem baseando-se no contorno do papel. Ideal para fotos ou documentos sem texto.")
        
        # ---> ALTERAR AQUI: Deixar o deskew de texto mais explicativo <---
        self.chk_deskew = QtWidgets.QCheckBox("Alinhamento de Conteúdo (Deskew de Texto)")
        self.chk_deskew.setChecked(self.settings.get("proc_deskew", True))
        self.chk_deskew.setToolTip("Alinha baseado na inclinação das linhas de texto.")
        
        self.chk_dewarp = QtWidgets.QCheckBox("Planificação geométrica (Dewarp)")
        self.chk_dewarp.setChecked(self.settings.get("proc_dewarp", False))
        
        self.chk_ocr = QtWidgets.QCheckBox("Aplicar OCR (Tesseract + PDF/A)")
        self.chk_ocr.setChecked(self.settings.get("proc_ocr", False))
        
        lyt_img.addWidget(self.chk_crop)
        lyt_img.addWidget(self.chk_contour_deskew)
        lyt_img.addWidget(self.chk_deskew)
        lyt_img.addWidget(self.chk_dewarp)
        lyt_img.addWidget(self.chk_ocr)

        layout.addWidget(grp_img)
        
        # 2. Grupo de Fechamento e Preservação
        grp_out = QtWidgets.QGroupBox("2. Fechamento e Preservação")
        lyt_out = QtWidgets.QVBoxLayout(grp_out)

        self.chk_pdf = QtWidgets.QCheckBox("Produzir PDF Unificado")
        self.chk_pdf.setChecked(self.settings.get("proc_pdf", True))
        
        self.chk_override_tsv = QtWidgets.QCheckBox("Criar TSV (Matriz Tabular de Metadados)")
        self.chk_override_tsv.setChecked(self.settings.get("custody_export_tsv", False))

        self.chk_override_bagit = QtWidgets.QCheckBox("Construir BagIt (Pacote de Preservação)")
        self.chk_override_bagit.setChecked(self.settings.get("custody_export_bagit", False))

        lyt_out.addWidget(self.chk_pdf)
        lyt_out.addWidget(self.chk_override_tsv)
        lyt_out.addWidget(self.chk_override_bagit)

        layout.addWidget(grp_out)

        # Botões de Ação
        btns = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        
        # Deixa o botão de confirmação com um texto claro
        btns.button(QtWidgets.QDialogButtonBox.Ok).setText("Iniciar Processamento")
        
        layout.addWidget(btns)

    def get_execution_flags(self) -> dict:
        """
        Retorna um dicionário com as opções finais escolhidas pelo operador.
        Este dicionário alimenta a classe VidyaImageProcessor em vidya_processor.py.
        """
        return {
            "crop": self.chk_crop.isChecked(),
            "contour_deskew": self.chk_contour_deskew.isChecked(), # ---> INSERIDO AQUI
            "deskew": self.chk_deskew.isChecked(),
            "dewarp": self.chk_dewarp.isChecked(),
            "pdf": self.chk_pdf.isChecked(),
            "ocr": self.chk_ocr.isChecked(),
            "tsv": self.chk_override_tsv.isChecked(),
            "bagit": self.chk_override_bagit.isChecked()
        }
