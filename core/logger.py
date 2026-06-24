import logging
import sys
import os
from core.config import LOG_DIR, DEBUG_LEVEL

def get_logger(name: str) -> logging.Logger:
    """
    Constrói e retorna um logger customizado com 3 níveis de profundidade,
    preparado para ser executado de forma segura entre as Daemon Workers.
    """
    logger = logging.getLogger(name)
    
    # Evita duplicação de handlers se o logger já existir
    if logger.hasHandlers():
        return logger

    # Mapeamento do nível de log baseado na configuração
    level_mapping = {
        1: logging.DEBUG,   # Nível 1: Rastreamento profundo (bytes, ioctl)
        2: logging.INFO,    # Nível 2: Fluxo lógico (câmera conectada, lote gerado)
        3: logging.ERROR    # Nível 3: Falhas crônicas e exceções
    }
    
    log_level = level_mapping.get(DEBUG_LEVEL, logging.INFO)
    logger.setLevel(log_level)

    # Formatador unificado
    formatter = logging.Formatter(
        '%(asctime)s | %(levelname)-8s | [%(name)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Handler para saída no console (stdout)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    
    # Handler para persistência em arquivo de log rotativo/diário
    file_handler = logging.FileHandler(
        os.path.join(LOG_DIR, "vidya_capture.log"), 
        encoding='utf-8'
    )
    file_handler.setFormatter(formatter)

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    return logger
