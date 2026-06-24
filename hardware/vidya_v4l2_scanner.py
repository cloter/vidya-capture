# Arquivo: hardware/v4l2_scanner.py

import subprocess
import re

class V4L2AdvancedScanner:
    @staticmethod
    def scan() -> dict:
        devices_info = {}
        
        try:
            list_output = subprocess.check_output(['v4l2-ctl', '--list-devices'], text=True)
        except FileNotFoundError:
            return {"error": "O utilitário 'v4l2-ctl' não foi encontrado. Instale o pacote 'v4l-utils'."}
        except Exception as e:
            return {"error": f"Falha ao executar v4l2-ctl: {str(e)}"}

        current_device_name = None
        current_bus = None

        # 1. Mapeia os dispositivos e seus nós
        for line in list_output.split('\n'):
            line = line.strip()
            if not line:
                continue
            
            if not line.startswith('/dev/'):
                current_device_name = line.strip(':')
                bus_match = re.search(r'\((usb-[^)]+)\)', current_device_name)
                current_bus = bus_match.group(1) if bus_match else "Desconhecido"
                current_device_name = re.sub(r'\s*\(usb-[^)]+\)', '', current_device_name)
            
            elif line.startswith('/dev/video'):
                node = line
                if node not in devices_info:
                    devices_info[node] = {
                        "nome_dispositivo": current_device_name,
                        "barramento_usb": current_bus,
                        "formatos_suportados": []
                    }

        # 2. Varre as resoluções de cada nó encontrado
        for node, info in devices_info.items():
            try:
                formats_output = subprocess.check_output(['v4l2-ctl', '-d', node, '--list-formats-ext'], text=True)
                
                current_format = None
                for f_line in formats_output.split('\n'):
                    f_line = f_line.strip()
                    
                    if f_line.startswith('[') and "]:" in f_line:
                        match = re.search(r"'([^']+)'", f_line)
                        if match:
                            current_format = match.group(1)
                            info["formatos_suportados"].append({
                                "codec": current_format,
                                "resolucoes": []
                            })
                    
                    elif f_line.startswith('Size:') and current_format:
                        res_match = re.search(r'Size:.* (\d+x\d+)', f_line)
                        if res_match:
                            resolucao = res_match.group(1)
                            if resolucao not in info["formatos_suportados"][-1]["resolucoes"]:
                                info["formatos_suportados"][-1]["resolucoes"].append(resolucao)

            except subprocess.CalledProcessError:
                pass # Ignora nós de metadados que falham no list-formats

        return devices_info
