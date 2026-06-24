# Arquivo: gui/vidya_theme_manager.py

class VidyaThemeManager:
    @staticmethod
    def get_dark_theme() -> str:
        """Retorna o QSS para o modo escuro padrão do aplicativo."""
        return """
        QMainWindow, QWidget {
            background-color: #2b2b2b;
            color: #e0e0e0;
        }
        QPushButton {
            background-color: #3c3f41;
            color: #e0e0e0;
            border: 1px solid #555555;
            border-radius: 4px;
            padding: 5px;
        }
        QPushButton:hover {
            background-color: #4b4d4f;
        }
        QPushButton:pressed {
            background-color: #5c5e60;
        }
        /* Preserva os botões que já possuem fundo colorido (via property ou nome) */
        QPushButton#btn_process {
            background-color: #1976D2; 
            color: white;
        }
        QLabel {
            color: #e0e0e0;
        }
        QGraphicsView {
            background-color: #1e1e1e;
            border: 1px solid #3c3f41;
        }
        QSplitter::handle {
            background-color: #3c3f41;
        }
        QCheckBox {
            color: #e0e0e0;
        }
        """

    @staticmethod
    def get_light_theme() -> str:
        """Retorna uma string vazia para restaurar o tema nativo do sistema operacional."""
        return ""
