# Arquivo: core/config.py
import os
import json

PROJECT_NAME = "Vidya Capture"
VERSION = "0.2.0"
DEBUG_LEVEL = 1 

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_DIR = os.path.join(BASE_DIR, "logs")
TEMP_DIR = os.path.join(BASE_DIR, "temp")
SETTINGS_FILE = os.path.join(BASE_DIR, "settings.json")

os.makedirs(LOG_DIR, exist_ok=True)
os.makedirs(TEMP_DIR, exist_ok=True)

COLOR_MAP = {
    "Vermelho": "#FF0000",
    "Verde": "#00FF00",
    "Azul": "#0000FF",
    "Ciano": "#00FFFF",
    "Magenta": "#FF00FF",
    "Preto": "#000000",
    "Branco": "#FFFFFF",
    "Cinza": "#808080"
}

def _get_default_working_dir() -> str:
    """Localiza a pasta Documentos do utilizador de forma inteligente (Suporta PT e EN)."""
    home = os.path.expanduser("~")
    docs_pt = os.path.join(home, "Documentos")
    docs_en = os.path.join(home, "Documents")
    
    if os.path.exists(docs_pt):
        base_docs = docs_pt
    elif os.path.exists(docs_en):
        base_docs = docs_en
    else:
        # Fallback de segurança absoluto: grava direto na Home do utilizador
        base_docs = home 
        
    return os.path.join(base_docs, "projeto_padrao")

def load_settings() -> dict:
    defaults = {
        "cameras_inverted": False,
        "marker_color_left": "Vermelho",
        "marker_color_right": "Verde",
        # ---> UTILIZA A NOVA FUNÇÃO AQUI <---
        "working_dir": _get_default_working_dir(),
        "rotation_left": "0°",
        "rotation_right": "0°",
        "image_format": "JPG",
        "jpg_quality": 95,
        "png_compression": 6,
        "tiff_compression": "Sem compressão",
        "proc_crop": True,
        "proc_deskew": True,
        "proc_dewarp": False,
        "proc_pdf": True,
        "deskew_aggressiveness": 1.0, 
        "dewarp_aggressiveness": 1.0,
        "custom_device_names": {},
        "force_max_resolution": True,   # Fallback padrão
        "v4l2_advanced_config": {},     # Nova chave para guardar os nós customizados
        "marker_opacity": 8,            # <--- ADICIONE ESTA LINHA (8% de opacidade padrão)
        "marker_thickness_weight": 100  # <--- ADICIONE ESTA LINHA (100% de intensidade por padrão)
    }
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                saved = json.load(f)
                defaults.update(saved)
        except Exception:
            pass
            
    os.makedirs(defaults["working_dir"], exist_ok=True)
    return defaults

def save_settings(settings: dict):
    with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
        json.dump(settings, f, indent=4)
