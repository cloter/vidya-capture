# Arquivo: hardware/vidya_capture_usb_manager.py

import gphoto2 as gp
from core.logger import get_logger

logger = get_logger("UsbManager")

class VidyaCaptureUsbManager:
    """
    Gerencia resiliência de barramento e timeouts das portas físicas (IOCTL / unbind).
    """
    def __init__(self):
        logger.debug("Inicializando gerenciador USB.")

    def detect_cameras(self) -> list:
        """
        Retorna a lista de portas das câmeras detectadas pelo OS.
        Exemplo de retorno: ['usb:001,004', 'usb:001,005']
        """
        logger.info("Varrendo barramento USB em busca de câmeras...")
        ports = []
        
        try:
            # Método robusto e compatível com as versões mais recentes do gphoto2
            port_info_list = gp.PortInfoList()
            port_info_list.load()
            
            abilities_list = gp.CameraAbilitiesList()
            abilities_list.load()
            
            # Executa a varredura cruzando as portas físicas com os drivers conhecidos
            camera_list = abilities_list.detect(port_info_list)
            
            # O retorno de detect() é iterável, devolvendo (Nome da Câmera, Endereço da Porta)
            for name, addr in camera_list:
                ports.append(addr)
                
        except Exception as e:
            logger.error(f"Erro de baixo nível ao interrogar barramento gphoto2: {str(e)}")

        if not ports:
            logger.warning("Nenhuma câmera detectada no barramento.")
        else:
            logger.info(f"{len(ports)} câmera(s) detectada(s): {ports}")
            
        return ports

    def reset_port(self, bus_id: str):
        """ Placeholder para a lógica de IOCTL USBDEVFS_RESET """
        logger.info(f"Executando soft reset no barramento USB: {bus_id}")
        pass
