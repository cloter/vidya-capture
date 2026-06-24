# Arquivo: core/project_manager.py

import os
import json
import time
from datetime import datetime
import platform
import socket
import getpass
from PIL import Image, ExifTags, ImageOps # <--- ADICIONADO: ImageOps
from PyQt5 import QtWidgets, QtCore, QtGui
from core.logger import get_logger
from core.config import load_settings # <--- NOVO: Leitura de preferências
import glob
import hashlib # <--- NOVO: Importação para a Cadeia de Custódia

logger = get_logger("ProjectManager")
single_logger = get_logger("SingleAuditor")

# =========================================================================
# NOVA FUNÇÃO GLOBAL: CÁLCULO DE HASH FÍSICO (ANTI-FRAUDE)
# =========================================================================
def calculate_file_hash(filepath: str) -> str:
    """Calcula o SHA-256 do arquivo físico no disco em blocos (poupa RAM em TIFFs pesados)."""
    sha256_hash = hashlib.sha256()
    try:
        with open(filepath, "rb") as f:
            for byte_block in iter(lambda: f.read(65536), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()
    except Exception as e:
        logger.error(f"Erro ao calcular hash de {filepath}: {e}")
        return ""

class VidyaProjectAuditor:
    """
    Motor analítico para verificação de integridade estrita e detecção de lotes legados.
    """
    @staticmethod
    def audit_directory(directory_path: str) -> dict:
        logger.info(f"Iniciando auditoria rigorosa no repositório: {directory_path}")
        
        settings = load_settings()
        verificar_hash = settings.get("project_integrity_check", "Com verificação de integridade") == "Com verificação de integridade"
        if not verificar_hash:
            logger.info("Verificação de integridade por Hash ignorada pelas preferências do utilizador.")
        report = {
            "total_images": 0,
            "total_jsons": 0,
            "valid_pairs": [],
            "orphaned_images": [],
            "orphaned_jsons": [],
            "left_pages": 0,
            "right_pages": 0,
            "is_legacy": False
        }
        
        if not os.path.exists(directory_path):
            return report

        all_files = os.listdir(directory_path)
        image_extensions = ('.jpg', '.jpeg', '.cr2', '.png', '.tif', '.tiff')
        
        images = [f for f in all_files if f.lower().endswith(image_extensions)]
        jsons = [f for f in all_files if f.lower().endswith('.json')]
        
        report["total_images"] = len(images)
        report["total_jsons"] = len(jsons)

        for img in images:
            base_name = img.rsplit('.', 1)[0]
            expected_json = f"{base_name}.json"
            
            full_img_path = os.path.join(directory_path, img)
            full_json_path = os.path.join(directory_path, expected_json)
            
            if expected_json in jsons and os.path.exists(full_json_path):
                try:
                    with open(full_json_path, 'r', encoding='utf-8') as f:
                        meta = json.load(f)
                        timestamp = meta.get("timestamp", os.path.getmtime(full_img_path))
                    
                    # ---> INÍCIO: VALIDAÇÃO CRIPTOGRÁFICA (ANTI-FRAUDE) <---
                    stored_hash = meta.get("preservation", {}).get("sha256_raw_fixity")
                    if stored_hash and verificar_hash: # <--- CONDICIONADO AQUI
                        disk_hash = calculate_file_hash(full_img_path)
                        if disk_hash != stored_hash:
                            logger.critical(f"CADEIA DE CUSTÓDIA QUEBRADA! O arquivo {img} foi adulterado. Rejeitando imagem.")
                            report["orphaned_images"].append(full_img_path)
                            continue # Aborta a inclusão deste ficheiro corrompido!
                    # ---> FIM: VALIDAÇÃO CRIPTOGRÁFICA <---

                    report["valid_pairs"].append({
                        "image": full_img_path,
                        "json": full_json_path,
                        "timestamp": timestamp
                    })
                    
                    if "Left" in img: report["left_pages"] += 1
                    elif "Right" in img: report["right_pages"] += 1
                        
                except Exception as e:
                    logger.error(f"Rejeitando imagem {img}. JSON corrompido: {e}")
                    report["orphaned_images"].append(full_img_path)
            else:
                report["orphaned_images"].append(full_img_path)

        for jsn in jsons:
            base_name = jsn.rsplit('.', 1)[0]
            has_img = any(img.rsplit('.', 1)[0] == base_name for img in images)
            if not has_img:
                report["orphaned_jsons"].append(os.path.join(directory_path, jsn))

        report["valid_pairs"].sort(key=lambda x: (int(x.get("timestamp", 0)), 0 if "Left" in x["image"] else 1))
        
        if report["total_images"] > 0 and len(report["valid_pairs"]) == 0:
            report["is_legacy"] = True
            logger.warning("Repositório não possui estrutura Vidya. Identificado como Lote Legado.")
        else:
            logger.info(
                f"Auditoria concluída. Pares válidos blindados: {len(report['valid_pairs'])}. "
                f"Imagens rejeitadas (órfãs/corrompidas): {len(report['orphaned_images'])}."
            )
        
        return report

    @staticmethod
    def execute_shift_cascade(working_dir: str, reference_paths: dict, action: str) -> str:
        """Abre espaço de 10s no projeto empurrando arquivos sucessores."""
        ref_path = reference_paths.get("Left") or reference_paths.get("Right")
        if not ref_path: return str(int(time.time()))

        try:
            base_name = os.path.basename(ref_path)
            ref_ts = int(base_name.split('_')[2].split('.')[0])
        except Exception:
            return str(int(time.time()))

        target_ts = ref_ts if action == "Inserir Antes" else ref_ts + 10

        report = VidyaProjectAuditor.audit_directory(working_dir)
        valid_pairs = report["valid_pairs"]

        pairs_by_ts = {}
        for pair in valid_pairs:
            try:
                ts = int(pair.get("timestamp", 0))
                if ts >= target_ts:
                    if ts not in pairs_by_ts:
                        pairs_by_ts[ts] = []
                    pairs_by_ts[ts].append(pair)
            except: pass

        sorted_ts = sorted(pairs_by_ts.keys(), reverse=True)

        for ts in sorted_ts:
            new_ts = ts + 10
            new_ts_str = str(new_ts)
            for item in pairs_by_ts[ts]:
                old_img = item["image"]
                old_json = item["json"]

                img_dir = os.path.dirname(old_img)
                old_img_base = os.path.basename(old_img)
                old_json_base = os.path.basename(old_json)

                new_img_base = old_img_base.replace(str(ts), new_ts_str)
                new_json_base = old_json_base.replace(str(ts), new_ts_str)

                new_img = os.path.join(img_dir, new_img_base)
                new_json = os.path.join(img_dir, new_json_base)

                if os.path.exists(old_img):
                    os.rename(old_img, new_img)
                    
                    # ---> NOVA INSERÇÃO: Renomeia o proxy na pasta .thumbnails (Página Dupla)
                    thumb_dir = os.path.join(img_dir, ".thumbnails")
                    old_thumb = os.path.join(thumb_dir, f"{old_img_base.rsplit('.', 1)[0]}.jpg")
                    new_thumb = os.path.join(thumb_dir, f"{new_img_base.rsplit('.', 1)[0]}.jpg")
                    if os.path.exists(old_thumb):
                        os.rename(old_thumb, new_thumb)
                    # ---> FIM DA INSERÇÃO
                    
                if os.path.exists(old_json):
                    try:
                        with open(old_json, 'r', encoding='utf-8') as f:
                            meta = json.load(f)
                        meta["timestamp"] = new_ts_str
                        with open(old_json, 'w', encoding='utf-8') as f:
                            json.dump(meta, f, indent=4)
                    except Exception as e:
                        logger.error(f"Falha ao atualizar JSON interno {old_json}: {e}")
                    os.rename(old_json, new_json)

        logger.info(f"Deslocamento em Cascata executado. Brecha de Tempo libertada: {target_ts}")
        return str(target_ts)


class VidyaSingleAuditor:
    """
    Auditor especializado para projetos de Câmera Única (Mesa Plana).
    """
    @staticmethod
    def audit_directory(working_dir: str) -> dict:
        if not working_dir or not os.path.exists(working_dir):
            return {"valid_items": [], "is_legacy": False}

        settings = load_settings()
        verificar_hash = settings.get("project_integrity_check", "Com verificação de integridade") == "Com verificação de integridade"

        extensions = ('*.jpg', '*.jpeg', '*.png', '*.tiff', '*.tif')
        image_files = []
        for ext in extensions:
            image_files.extend(glob.glob(os.path.join(working_dir, ext)))
            image_files.extend(glob.glob(os.path.join(working_dir, ext.upper())))

        valid_items = []
        total_raw_images = 0 # <--- Rastreador de imagens brutas
        
        for img_path in image_files:
            filename = os.path.basename(img_path)
            
            if filename.startswith('.') or "processed" in filename.lower() or filename.startswith('Proc_') or filename.startswith('Orig_'):
                continue

            total_raw_images += 1
            json_path = img_path.rsplit('.', 1)[0] + '.json'
            
            # ---> CORREÇÃO 1: Se não tem JSON sidecar, não é uma captura processada pelo Vidya
            if not os.path.exists(json_path):
                continue
                
            ts = int(os.path.getmtime(img_path))
            is_corrupted = False

            try:
                with open(json_path, 'r', encoding='utf-8') as f:
                    meta = json.load(f)
                    ts = int(meta.get("timestamp", ts))
                    
                # Validação Cadeia de Custódia
                stored_hash = meta.get("preservation", {}).get("sha256_raw_fixity")
                if stored_hash and verificar_hash: # <--- CONDICIONADO AQUI
                    disk_hash = calculate_file_hash(img_path)
                    if disk_hash != stored_hash:
                        single_logger.critical(f"CADEIA DE CUSTÓDIA QUEBRADA! O arquivo {filename} foi adulterado.")
                        is_corrupted = True
            except Exception as e:
                single_logger.error(f"Falha ao ler JSON {json_path}: {e}")
                is_corrupted = True
        
            if is_corrupted:
                continue
                
            valid_items.append({
                "image": img_path,
                "json": json_path,
                "timestamp": ts
            })
            
            # Rastreador de Clipes
            base_name_no_ext = os.path.basename(img_path).rsplit('.', 1)[0]
            clip_pattern = os.path.join(working_dir, f"{base_name_no_ext}_clip_*.json")
            for clip_json in glob.glob(clip_pattern):
                valid_items.append({
                    "image": img_path,
                    "json": clip_json,
                    "timestamp": ts,
                    "is_clip": True
                })

        valid_items.sort(key=lambda x: x["timestamp"])
        for item in valid_items:
            del item["timestamp"]

        # ---> CORREÇÃO 2: Disparo Seguro do Gatilho Legado <---
        is_legacy = False
        if total_raw_images > 0 and len(valid_items) == 0:
            is_legacy = True
            single_logger.warning("Repositório possui imagens brutas mas não possui arquivos JSON. Identificado como Lote Legado.")

        single_logger.info(f"Auditoria Câmera Única concluída: {len(valid_items)} imagens válidas encontradas.")
        return {"valid_items": valid_items, "is_legacy": is_legacy}

    @staticmethod
    def execute_shift_cascade(working_dir: str, replacement_paths: dict, mode: str) -> str:
        # [A lógica de cascata permanece intacta como estava no ficheiro original]
        target_path = replacement_paths.get("Left")
        if not target_path or not os.path.exists(target_path): return str(int(time.time()))

        report = VidyaSingleAuditor.audit_directory(working_dir)
        valid_items = report.get("valid_items", [])
        
        target_index = -1
        for i, item in enumerate(valid_items):
            if item["image"] == target_path:
                target_index = i; break
                
        if target_index == -1: return str(int(time.time()))

        shift_start_index = target_index if mode == "Inserir Antes" else target_index + 1
        target_filename = os.path.basename(target_path)
        try: base_ts = int(target_filename.split('_')[2].split('.')[0])
        except Exception: base_ts = int(time.time())

        if mode == "Inserir Depois" and shift_start_index >= len(valid_items): return str(base_ts + 10)

        SHIFT_AMOUNT = 20
        
        for i in range(len(valid_items) - 1, shift_start_index - 1, -1):
            item = valid_items[i]
            img_path = item["image"]
            json_path = item["json"]
            old_filename = os.path.basename(img_path)
            try:
                parts = old_filename.split('_')
                old_ts = int(parts[2].split('.')[0])
                new_ts = old_ts + SHIFT_AMOUNT
                new_img_name = old_filename.replace(str(old_ts), str(new_ts))
                new_img_path = os.path.join(working_dir, new_img_name)
                os.rename(img_path, new_img_path)
                
                # ---> NOVA INSERÇÃO: Renomeia o proxy na pasta .thumbnails (Câmera Única)
                thumb_dir = os.path.join(working_dir, ".thumbnails")
                old_thumb = os.path.join(thumb_dir, f"{old_filename.rsplit('.', 1)[0]}.jpg")
                new_thumb = os.path.join(thumb_dir, f"{new_img_name.rsplit('.', 1)[0]}.jpg")
                if os.path.exists(old_thumb):
                    os.rename(old_thumb, new_thumb)
                # ---> FIM DA INSERÇÃO
                
                if os.path.exists(json_path):
                    old_json_name = os.path.basename(json_path)
                    new_json_name = old_json_name.replace(str(old_ts), str(new_ts))
                    new_json_path = os.path.join(working_dir, new_json_name)
                    os.rename(json_path, new_json_path)
                    
                clip_pattern = os.path.join(working_dir, f"{old_filename.rsplit('.', 1)[0]}_clip_*.json")
                for clip_file in glob.glob(clip_pattern):
                    try:
                        old_clip_name = os.path.basename(clip_file)
                        new_clip_name = old_clip_name.replace(str(old_ts), str(new_ts))
                        new_clip_path = os.path.join(working_dir, new_clip_name)
                        os.rename(clip_file, new_clip_path)
                    except Exception as e: single_logger.error(f"Falha cascata de clip {clip_file}: {e}")
            except Exception as e:
                single_logger.error(f"Falha ao renomear item em cascata {old_filename}: {e}")

        if mode == "Inserir Antes": new_capture_ts = base_ts
        else: new_capture_ts = base_ts + (SHIFT_AMOUNT // 2)
        return str(new_capture_ts)
        
class LegacyImportDialog(QtWidgets.QDialog):
    def __init__(self, source_dir: str, settings: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Assistente de Ingestão de Projeto Legado")
        self.resize(550, 450)
        self.source_dir = source_dir
        self.settings = settings
        self.is_single_mode = (self.settings.get("project_mode") == "Mesa Plana (Câmera Única)")
        
        layout = QtWidgets.QVBoxLayout(self)
        
        modo_texto = "Câmera Única (Mesa Plana)" if self.is_single_mode else "Página Dupla (Berço em V)"
        lbl_info = QtWidgets.QLabel(f"O Vidya Capture detetou imagens em bruto. Elas serão importadas para a topologia de <b>{modo_texto}</b> num subdiretório seguro chamado <b>'work_dir'</b>.")
        lbl_info.setWordWrap(True)
        layout.addWidget(lbl_info)
        
        grp_settings = QtWidgets.QGroupBox("Ordenação e Formato Físico")
        lo_settings = QtWidgets.QFormLayout(grp_settings)
        
        self.cb_sort = QtWidgets.QComboBox()
        self.cb_sort.addItems(["Nome do Arquivo (Ordem Alfabética)", "Data de Criação (Timestamp do SO)"])
        self.cb_first = QtWidgets.QComboBox()
        self.cb_first.addItems(["Esquerda (Anverso)", "Direita (Verso)"])
        
        lo_settings.addRow("Ordenar Lote por:", self.cb_sort)
        
        # Oculta a exigência de posição inicial se for câmera única
        if not self.is_single_mode:
            lo_settings.addRow("A 1ª imagem da lista é a página:", self.cb_first)
            
        layout.addWidget(grp_settings)
        
        grp_meta = QtWidgets.QGroupBox("Confirmação de Metadados (Dublin Core)")
        lo_meta = QtWidgets.QFormLayout(grp_meta)
        
        self.le_title = QtWidgets.QLineEdit()
        self.le_desc = QtWidgets.QLineEdit()
        self.le_pub = QtWidgets.QLineEdit()
        self.le_col = QtWidgets.QLineEdit()
        self.le_creator = QtWidgets.QLineEdit()
        
        try: user = getpass.getuser()
        except Exception: user = "Operador"
        self.le_creator.setText(user)
        
        lo_meta.addRow("Nome do Projeto:", self.le_title)
        lo_meta.addRow("Descrição:", self.le_desc)
        lo_meta.addRow("Editor/Instituição:", self.le_pub)
        lo_meta.addRow("Fundo/Coleção:", self.le_col)
        lo_meta.addRow("Operador (Criador):", self.le_creator)
        layout.addWidget(grp_meta)
        
        btns = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)
        
        self._prefill_from_existing_project()
        
    def _prefill_from_existing_project(self):
        proj_file = os.path.join(self.source_dir, "project.json")
        if os.path.exists(proj_file):
            try:
                with open(proj_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    meta = data.get("metadata", {})
                    self.le_title.setText(meta.get("dcterms:title", ""))
                    self.le_desc.setText(meta.get("dcterms:description", ""))
                    self.le_pub.setText(meta.get("dcterms:publisher", ""))
                    self.le_col.setText(meta.get("schema:collection", ""))
                    creator = meta.get("dcterms:creator", "")
                    if creator: self.le_creator.setText(creator)
            except Exception as e: logger.error(f"Erro ao preencher metadados legados: {e}")
            
    def get_config(self):
        return {
            "sort_by": self.cb_sort.currentText(),
            "first_page": self.cb_first.currentText(),
            "meta_title": self.le_title.text().strip(),
            "meta_desc": self.le_desc.text().strip(),
            "meta_publisher": self.le_pub.text().strip(),
            "meta_collection": self.le_col.text().strip(),
            "meta_creator": self.le_creator.text().strip()
        }

class VidyaExifExtractor:
    """Utilitário seguro para extração e sanitização de metadados EXIF."""
    @staticmethod
    def extract(img_obj) -> dict:
        exif_data = {}
        try:
            raw_exif = img_obj._getexif()
            if raw_exif:
                for tag_id, value in raw_exif.items():
                    tag_name = ExifTags.TAGS.get(tag_id, tag_id)
                    # Filtro de segurança: Ignora dados binários pesados (como MakerNote) 
                    # que causariam erro fatal na hora de salvar o JSON.
                    if tag_name == 'MakerNote' or isinstance(value, bytes):
                        continue
                    # Converte tudo para string para garantir a serialização
                    exif_data[str(tag_name)] = str(value)
        except Exception as e:
            # Falha silenciosa intencional. Se não houver EXIF, segue o jogo.
            logger.debug(f"Nenhum dado EXIF extraído ou falha na leitura: {e}")
            
        return exif_data

class LegacyImportWorker(QtCore.QThread):
    progress = QtCore.pyqtSignal(int, str)
    finished = QtCore.pyqtSignal(str)
    error = QtCore.pyqtSignal(str)

    def __init__(self, source_dir, work_dir, files, config, settings):
        super().__init__()
        self.source_dir = source_dir
        self.work_dir = work_dir
        self.files = files
        self.config = config
        self.settings = settings
        self.is_single_mode = (self.settings.get("project_mode") == "Mesa Plana (Câmera Única)")

    def run(self):
        try:
            # 1. Ordenação Base do Lote
            if "Data" in self.config["sort_by"]: 
                self.files.sort(key=lambda x: os.path.getmtime(x))
            else: 
                self.files.sort()
                
            base_ts = int(os.path.getmtime(self.files[0])) if self.files else int(time.time())
            fmt = self.settings.get("image_format", "JPG").upper()
            ext = "tif" if fmt == "TIFF" else fmt.lower()
            
            # 2. Despacho Polimórfico (O coração da refatoração)
            if self.is_single_mode:
                self._process_single_mode(base_ts, fmt, ext)
            else:
                self._process_dual_mode(base_ts, fmt, ext)
            
            # 3. Empacotamento Seguro de Metadados
            self._generate_manifest()
            
            self.progress.emit(100, "Ingestão Concluída!")
            self.finished.emit(self.work_dir)
            
        except Exception as e:
            self.error.emit(str(e))

    def _process_dual_mode(self, base_ts: int, fmt: str, ext: str):
        """Lógica intocada de Berço em V: Força agrupamento de 2 em 2 com timestamps iguais."""
        total = len(self.files)
        for idx, f in enumerate(self.files):
            self.progress.emit(int((idx/total)*100), f"Convertendo Par {os.path.basename(f)}...")
            
            is_even = (idx % 2 == 0)
            if "Esquerda" in self.config.get("first_page", "Esquerda"): 
                side = "Left" if is_even else "Right"
            else: 
                side = "Right" if is_even else "Left"
                
            pair_index = idx // 2
            current_ts = str(base_ts + (pair_index * 10))
            
            self._convert_and_save_image(f, side, current_ts, fmt, ext)

    def _process_single_mode(self, base_ts: int, fmt: str, ext: str):
        """Nova Lógica Mesa Plana: Timestamps incrementam para cada arquivo e não formam pares."""
        total = len(self.files)
        for idx, f in enumerate(self.files):
            self.progress.emit(int((idx/total)*100), f"Convertendo Imagem {os.path.basename(f)}...")
            
            side = "Left" # No modo simples, a infraestrutura âncora é sempre a Left
            current_ts = str(base_ts + (idx * 10)) # Salto isolado de tempo para cada imagem
            
            self._convert_and_save_image(f, side, current_ts, fmt, ext)

    def _convert_and_save_image(self, original_file: str, side: str, current_ts: str, fmt: str, ext: str):
        """Rotina padronizada de compressão e gravação de Crop Geométrico (DRY)."""
        out_name = f"Temp_{side}_{current_ts}.{ext}"
        out_path = os.path.join(self.work_dir, out_name)
        
        img = Image.open(original_file)
        
        # ---> NOVA INSERÇÃO: Captura do EXIF antes de manipular a imagem
        exif_dict = VidyaExifExtractor.extract(img)
        # ---> FIM DA INSERÇÃO
        
        # ROTACIONAR FISICAMENTE BASEADO NO EXIF
        img = ImageOps.exif_transpose(img)
        
        if fmt == "JPG" and img.mode in ("RGBA", "P"): 
            img = img.convert('RGB')
        img_w, img_h = img.size
        
        save_kwargs = {}
        if fmt == "JPG":
            save_kwargs["format"] = "JPEG"
            save_kwargs["quality"] = int(self.settings.get("jpg_quality", 95))
        elif fmt == "PNG":
            save_kwargs["format"] = "PNG"
            save_kwargs["compress_level"] = int(self.settings.get("png_compression", 6))
        elif fmt == "TIFF":
            save_kwargs["format"] = "TIFF"
            comp = self.settings.get("tiff_compression", "Sem compressão")
            if "LZW" in comp: save_kwargs["compression"] = "tiff_lzw"
            elif "ZIP" in comp: save_kwargs["compression"] = "tiff_adobe_deflate"
            elif "JPEG" in comp: save_kwargs["compression"] = "tiff_jpeg"
            
        img.save(out_path, **save_kwargs)
        
        try:
            thumb_dir = os.path.join(self.work_dir, ".thumbnails")
            os.makedirs(thumb_dir, exist_ok=True)
            
            thumb_img = img.copy()
            thumb_img.thumbnail((154, 232))
            if thumb_img.mode in ("RGBA", "P"):
                thumb_img = thumb_img.convert('RGB')
                
            # --- CORREÇÃO: Força o arquivo físico a ser escrito com extensão .jpg ---
            name_no_ext = out_name.rsplit('.', 1)[0]
            thumb_img.save(os.path.join(thumb_dir, f"{name_no_ext}.jpg"), "JPEG", quality=70, optimize=True)
            thumb_img.close()
        except Exception as e:
            logger.error(f"Erro ao criar proxy em lote durante a ingestão: {e}")
            
        img.close()
        
        sidecar = {
            "timestamp": current_ts,
            "position": side,
            "crop_geometry": {"x": 0, "y": 0, "width": img_w, "height": img_h},
            "exif_metadata": exif_dict  # <--- NOVA INSERÇÃO: Injeta o dicionário (vazio ou preenchido)
        }
        with open(os.path.join(self.work_dir, f"Temp_{side}_{current_ts}.json"), 'w', encoding='utf-8') as jf:
            json.dump(sidecar, jf, indent=4)

    def _generate_manifest(self):
        """Injeta metadados essenciais e bloqueia a topologia no project.json."""
        self.progress.emit(99, "Gerando Manifesto do Projeto (project.json)...")
        proj_file = os.path.join(self.work_dir, "project.json")
        gui_env = os.environ.get('XDG_CURRENT_DESKTOP') or os.environ.get('DESKTOP_SESSION') or "Desconhecido"
        
        manifest = {
            "metadata": {
                "dcterms:title": self.config["meta_title"],
                "dcterms:description": self.config["meta_desc"],
                "dcterms:created": datetime.now().isoformat(timespec='seconds'),
                "dcterms:publisher": self.config["meta_publisher"],
                "dcterms:creator": self.config["meta_creator"],
                "schema:collection": self.config["meta_collection"],
                "imported_legacy_data": True
            },
            "provenance": {
                "hostname": socket.gethostname(),
                "os_name": platform.system(),
                "os_version": platform.release(),
                "cpu": platform.processor(),
                "gui_environment": gui_env
            },
            "capture_params": {
                # Esta chave é vital para que a interface trave o modo correto na próxima abertura
                "project_mode": self.settings.get("project_mode", "Berço em V (Página Dupla)")
            },
            "files": [] 
        }
        with open(proj_file, 'w', encoding='utf-8') as pf:
            json.dump(manifest, pf, indent=4, ensure_ascii=False)


class VidyaLegacyImporter:
    @staticmethod
    def run_import(parent_widget, source_dir, settings):
        image_exts = ('.jpg', '.jpeg', '.png', '.tif', '.tiff')
        images = [os.path.join(source_dir, f) for f in os.listdir(source_dir) if f.lower().endswith(image_exts)]
        if not images: return None
        
        is_single = (settings.get("project_mode") == "Mesa Plana (Câmera Única)")
        modo_str = "Câmera Única" if is_single else "Berço em V"
        
        reply = QtWidgets.QMessageBox.question(
            parent_widget, "Projeto Legado Detectado", 
            f"Foram encontradas {len(images)} imagens brutas sem metadados estruturados.\nDeseja importar o lote para o modo '{modo_str}'?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
        )
        if reply != QtWidgets.QMessageBox.Yes: return None
        
        # A injeção das settings no Dialogo é o que permite adaptar a interface
        dialog = LegacyImportDialog(source_dir, settings, parent_widget)
        if not dialog.exec_(): return None
        
        config = dialog.get_config()
        work_dir = os.path.join(source_dir, "work_dir")
        os.makedirs(work_dir, exist_ok=True)
        
        progress = QtWidgets.QProgressDialog("Preparando arquivos...", "Cancelar", 0, 100, parent_widget)
        progress.setWindowTitle("Ingestão de Lote")
        progress.setWindowModality(QtCore.Qt.WindowModal)
        progress.show()
        
        worker = LegacyImportWorker(source_dir, work_dir, images, config, settings)
        worker.progress.connect(lambda v, t: (progress.setValue(v), progress.setLabelText(t)))
        
        loop = QtCore.QEventLoop()
        final_dir = None
        
        def on_finished(out_dir):
            nonlocal final_dir
            final_dir = out_dir
            loop.quit()
            
        def on_error(msg):
            QtWidgets.QMessageBox.critical(parent_widget, "Erro", f"Falha na importação:\n{msg}")
            loop.quit()
            
        worker.finished.connect(on_finished)
        worker.error.connect(on_error)
        progress.canceled.connect(worker.terminate)
        progress.canceled.connect(loop.quit)
        worker.start()
        loop.exec_()
        progress.close()
        
        return final_dir
