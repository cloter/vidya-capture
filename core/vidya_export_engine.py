# Arquivo: core/vidya_export_engine.py

import os
import glob
import csv
import json
import shutil
import hashlib
from datetime import datetime
from core.logger import get_logger

logger = get_logger("ExportEngine")

class VidyaTSVExporter:
    """
    Motor especializado na extração e mapeamento de metadados arquivísticos 
    e resultados de OCR para matrizes tabulares (TSV), prontas para ingestão 
    em repositórios como Omeka S, Tainacan e DSpace.
    """
    def __init__(self, working_dir: str, out_dir: str, manifest_data: dict, settings: dict, pdf_input_list: list):
        self.working_dir = working_dir
        self.out_dir = out_dir
        self.manifest_data = manifest_data
        self.settings = settings
        self.pdf_input_list = pdf_input_list # A lista exata de ficheiros que entraram no PDF
        
        self.metadata = self.manifest_data.get("metadata", {})
        self.premis = self.manifest_data.get("premis:events", [])
        
        # ---> CORREÇÃO: Variável movida para cá, buscando com self.manifest_data
        self.project_name = self.manifest_data.get("project_name", os.path.basename(self.working_dir))
        
    def generate_tsv(self):
        granularity = self.settings.get("custody_tsv_granularity", "2.")
        
        # Gera o timestamp real de forma independente e imune ao formato do nome da imagem
        timestamp_str = datetime.now().strftime("%y%m%d-%H%M%S")
        
        tsv_filename = f"{self.project_name}_{timestamp_str}_Metadados.tsv"
        tsv_path = os.path.join(self.out_dir, tsv_filename)
        
        try:
            if "1." in granularity or "Global" in granularity:
                self._generate_global_tsv(tsv_path)
            else:
                self._generate_page_tsv(tsv_path)
            logger.info(f"Arquivo TSV gerado com sucesso: {tsv_path}")

            # =========================================================
            # NOVO: COPIAR O TSV PARA A PASTA DE DESTINO FINAL
            # =========================================================
            export_path = self.settings.get("pdf_export_path", "")
            if export_path and os.path.exists(export_path):
                import shutil
                final_tsv_path = os.path.join(export_path, tsv_filename)
                shutil.copy2(tsv_path, final_tsv_path)
                logger.info(f"Metadados TSV copiados para o destino final: {final_tsv_path}")

        except Exception as e:
            logger.error(f"Falha ao gerar TSV de metadados: {e}")

    def _get_base_metadata(self) -> dict:
        """Extrai os metadados descritivos padrão do Dublin Core."""
        return {
            "dcterms:title": self.metadata.get("dcterms:title", ""),
            "dcterms:creator": self.metadata.get("dcterms:creator", ""),
            "dcterms:description": self.metadata.get("dcterms:description", ""),
            "dcterms:publisher": self.metadata.get("dcterms:publisher", ""),
            "schema:collection": self.metadata.get("schema:collection", "")
        }

    def _get_ocr_text_pages(self) -> list:
        """Lê o TXT bruto e fatia o texto página a página usando o delimitador Form Feed."""
        txt_files = glob.glob(os.path.join(self.out_dir, "*_Texto_Bruto.txt"))
        if not txt_files:
            return []
        
        latest_txt = max(txt_files, key=os.path.getmtime)
        try:
            with open(latest_txt, 'r', encoding='utf-8') as f:
                content = f.read()
            # O Tesseract divide as páginas fisicamente com o caractere \x0c
            pages = [p.strip() for p in content.split('\x0c')]
            return pages
        except Exception as e:
            logger.error(f"Erro ao fatiar o texto OCR: {e}")
            return []

    def _find_image_hash(self, img_path: str, img_name: str) -> str:
        """Busca o Hash da imagem no PREMIS central, no sidecar ou calcula na hora."""
        # 1. Tenta encontrar o hash nos eventos de transformação (Imagens Tratadas)
        for evt in self.premis:
            if evt.get("linkingObjectIdentifierValue") == img_name:
                return evt.get("resultingObjectHash", "")
                
        # 2. Fallback 1: Se for imagem crua ("Entrada"), o Hash está no sidecar .json
        json_path = img_path.rsplit('.', 1)[0] + '.json'
        if os.path.exists(json_path):
            try:
                with open(json_path, 'r', encoding='utf-8') as f:
                    sidecar = json.load(f)
                    hash_val = sidecar.get("preservation", {}).get("sha256_raw_fixity", "")
                    if hash_val: return hash_val
            except:
                pass
                
        # 3. Fallback Absoluto: Se não achou (ex: modo "Originais"), calcula na hora
        if os.path.exists(img_path):
            try:
                with open(img_path, 'rb') as f:
                    return hashlib.sha256(f.read()).hexdigest()
            except Exception as e:
                logger.error(f"Falha ao calcular hash de emergência para {img_name}: {e}")

        return "Hash Indisponível"

    def _generate_global_tsv(self, filepath: str):
        """Modo 1: Uma única linha representando todo o projeto/livro."""
        include_hash = self.settings.get("custody_tsv_include_hash", False)
        include_ocr = self.settings.get("custody_tsv_include_ocr", False)

        # Cabeçalhos baseados em ontologias padronizadas
        headers = ["dcterms:title", "dcterms:creator", "dcterms:description", "dcterms:publisher", "schema:collection"]
        if include_hash: headers.append("vidya:sha256_pdfa_fixity")
        if include_ocr: headers.append("vidya:full_text")

        base_meta = self._get_base_metadata()
        row = [
            base_meta["dcterms:title"], base_meta["dcterms:creator"], 
            base_meta["dcterms:description"], base_meta["dcterms:publisher"], 
            base_meta["schema:collection"]
        ]

        # Injeta o Hash do PDF/A inteiro
        if include_hash:
            pdf_hash = "Hash Indisponível"
            for evt in reversed(self.premis):
                # Alterado de "PDFA.pdf" para buscar qualquer coisa que termine em .pdf
                if evt.get("eventType") == "creation" and str(evt.get("linkingObjectIdentifierValue", "")).endswith(".pdf"):
                    pdf_hash = evt.get("resultingObjectHash", "")
                    break
            row.append(pdf_hash)

        # Injeta o texto do livro inteiro numa única célula
        if include_ocr:
            pages = self._get_ocr_text_pages()
            full_text = "\n\n".join(pages).strip()
            row.append(full_text)

        # Gravação blindada via módulo nativo CSV (configurado para TSV)
        with open(filepath, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f, delimiter='\t', quoting=csv.QUOTE_MINIMAL)
            writer.writerow(headers)
            writer.writerow(row)

    def _get_exif_from_sidecar(self, img_path: str) -> dict:
        """Localiza o sidecar JSON original e extrai o bloco exif_metadata de forma segura."""
        base_name = os.path.basename(img_path)
        
        # Remove os prefixos operacionais do motor OpenCV para achar o nome original do ficheiro
        if base_name.startswith("Proc_"):
            base_name = base_name[5:]
        elif base_name.startswith("Orig_"):
            base_name = base_name[5:]
            
        name_no_ext, _ = os.path.splitext(base_name)
        json_path = os.path.join(self.working_dir, f"{name_no_ext}.json")
        
        if os.path.exists(json_path):
            try:
                with open(json_path, 'r', encoding='utf-8') as f:
                    sidecar = json.load(f)
                    return sidecar.get("exif_metadata", {})
            except Exception as e:
                logger.debug(f"Falha ao ler metadados EXIF do sidecar {json_path}: {e}")
                
        return {}

    def _generate_page_tsv(self, filepath: str):
        """Modo 2: Uma linha para cada página processada com inclusão de metadados técnicos EXIF."""
        include_hash = self.settings.get("custody_tsv_include_hash", False)
        include_ocr = self.settings.get("custody_tsv_include_ocr", False)

        # 1. Ampliação dos cabeçalhos para suportar o mapeamento arquivístico
        headers = [
            "dcterms:title", 
            "vidya:filename", 
            "dcterms:creator", 
            "dcterms:description", 
            "dcterms:publisher", 
            "schema:collection",
            "vidya:camera_model",    # <-- NOVO
            "vidya:capture_date"     # <-- NOVO
        ]
        if include_hash: headers.append("vidya:sha256_image_fixity")
        if include_ocr: headers.append("vidya:page_text")

        base_meta = self._get_base_metadata()
        pages_text = self._get_ocr_text_pages() if include_ocr else []

        with open(filepath, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f, delimiter='\t', quoting=csv.QUOTE_MINIMAL)
            writer.writerow(headers)

            for idx, img_path in enumerate(self.pdf_input_list):
                img_name = os.path.basename(img_path)
                
                base_title = base_meta["dcterms:title"] or "Documento"
                page_title = f"{base_title} - Página {idx + 1}"
                
                # 2. Extração segura dos metadados técnicos do sidecar
                exif_dict = self._get_exif_from_sidecar(img_path)
                camera_model = exif_dict.get("Model", "Não disponível")
                
                # Tenta obter a data original da foto; se não houver, tenta a data de modificação do EXIF
                capture_date = exif_dict.get("DateTimeOriginal", exif_dict.get("DateTime", "Não disponível"))
                
                # 3. Montagem da linha com o alinhamento estrito dos novos campos
                row = [
                    page_title,
                    img_name,
                    base_meta["dcterms:creator"],
                    base_meta["dcterms:description"],
                    base_meta["dcterms:publisher"],
                    base_meta["schema:collection"],
                    camera_model,  # <-- NOVO
                    capture_date   # <-- NOVO
                ]

                if include_hash:
                    img_hash = self._find_image_hash(img_path, img_name)
                    row.append(img_hash)

                if include_ocr:
                    page_text = pages_text[idx] if idx < len(pages_text) else ""
                    row.append(page_text.strip())

                writer.writerow(row)
                
# ===================================================================================
# MOTOR BAGIT (RFC 8493) - EMPACOTAMENTO DE PRESERVAÇÃO
# ===================================================================================
class VidyaBagItPackager:
    """
    Motor de empacotamento que estrutura o projeto no formato internacional BagIt.
    Gera topologia de Arquivo Permanente (AIP/SIP) e manifestos criptográficos.
    """
    def __init__(self, working_dir: str, out_dir: str, manifest_data: dict, settings: dict, progress_callback=None):
        self.working_dir = working_dir
        self.out_dir = out_dir
        self.manifest_data = manifest_data
        self.settings = settings
        self.progress_callback = progress_callback
        # self.project_name = os.path.basename(self.working_dir)
        # Faça isso dentro do __init__ do VidyaTSVExporter e do VidyaBagItPackager
        self.project_name = manifest_data.get("project_name", os.path.basename(self.working_dir))

    def _emit(self, msg):
        if self.progress_callback:
            self.progress_callback(msg)
        logger.info(msg)

    def create_bag(self):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        bag_name = f"{self.project_name}_BagIt_{timestamp}"
        
        # ---> CORREÇÃO: O BagIt vai diretamente e exclusivamente para a pasta 'out'
        bag_dir = os.path.join(self.out_dir, bag_name)
        
        # Topologia de Preservação Estruturada (O "Cofre" do BagIt)
        data_dir = os.path.join(bag_dir, "data")
        raw_dir = os.path.join(data_dir, "RAW_Master")
        deriv_dir = os.path.join(data_dir, "Derivatives")
        meta_dir = os.path.join(data_dir, "Metadata")
        access_dir = os.path.join(data_dir, "Access")
        
        for d in [raw_dir, deriv_dir, meta_dir, access_dir]:
            os.makedirs(d, exist_ok=True)
            
        payload_manifest = {}
        total_bytes = 0
        total_files = 0
        
        # Função interna ultrarrápida: Copia e Hashea na mesma passagem de disco
        def copy_and_hash(src, dest, rel_path):
            nonlocal total_bytes, total_files
            if not os.path.exists(src): return
            sha256 = hashlib.sha256()
            size = 0
            with open(src, 'rb') as fsrc, open(dest, 'wb') as fdst:
                for chunk in iter(lambda: fsrc.read(65536), b""):
                    fdst.write(chunk)
                    sha256.update(chunk)
                    size += len(chunk)
            shutil.copystat(src, dest) # Preserva data de criação/modificação original
            payload_manifest[rel_path] = sha256.hexdigest()
            total_bytes += size
            total_files += 1

        # 1. Empacotar Arquivos RAW (Negativos Digitais)
        self._emit("BagIt: Empacotando arquivos RAW (Master)...")
        for f in os.listdir(self.working_dir):
            if (f.startswith("Temp_") or f.endswith(".json")) and "project.json" not in f and "BagIt" not in f:
                src = os.path.join(self.working_dir, f)
                if os.path.isfile(src):
                    copy_and_hash(src, os.path.join(raw_dir, f), f"data/RAW_Master/{f}")

        # 2. Empacotar Derivados e PDF de Acesso
        self._emit("BagIt: Empacotando Derivados e PDF de Acesso...")
        if os.path.exists(self.out_dir):
            for f in os.listdir(self.out_dir):
                src = os.path.join(self.out_dir, f)
                if not os.path.isfile(src): continue
                
                if f.endswith(".pdf"):
                    copy_and_hash(src, os.path.join(access_dir, f), f"data/Access/{f}")
                elif f.startswith("Proc_") or f.startswith("Orig_"):
                    copy_and_hash(src, os.path.join(deriv_dir, f), f"data/Derivatives/{f}")
                elif f.endswith(".tsv") or f.endswith(".txt") or f.endswith(".ps"):
                    copy_and_hash(src, os.path.join(meta_dir, f), f"data/Metadata/{f}")
                    
        # 3. Empacotar o Manifesto do Projeto (Dublin Core + PREMIS)
        proj_json = os.path.join(self.working_dir, "project.json")
        if os.path.exists(proj_json):
            copy_and_hash(proj_json, os.path.join(meta_dir, "project.json"), "data/Metadata/project.json")
            
        # 4. Escrever manifest-sha256.txt (A Alma do BagIt)
        self._emit("BagIt: Gerando Manifestos Criptográficos...")
        manifest_path = os.path.join(bag_dir, "manifest-sha256.txt")
        with open(manifest_path, 'w', encoding='utf-8') as f:
            for rel_path, file_hash in payload_manifest.items():
                f.write(f"{file_hash}  {rel_path}\n")
                
        # 5. Escrever bagit.txt
        bagit_txt_path = os.path.join(bag_dir, "bagit.txt")
        with open(bagit_txt_path, 'w', encoding='utf-8') as f:
            f.write("BagIt-Version: 0.97\n")
            f.write("Tag-File-Character-Encoding: UTF-8\n")
            
        # 6. Escrever bag-info.txt (Metadados Institucionais)
        bag_info_path = os.path.join(bag_dir, "bag-info.txt")
        meta = self.manifest_data.get("metadata", {})
        with open(bag_info_path, 'w', encoding='utf-8') as f:
            f.write("Source-Organization: Vidya Capture Framework\n")
            f.write("Organization-Address: LAMUHDI - Museu Campos Gerais (UEPG)\n")
            f.write(f"Contact-Name: {meta.get('dcterms:creator', 'Operador')}\n")
            f.write(f"External-Description: {meta.get('dcterms:description', 'Digitalização de Acervo')}\n")
            f.write(f"External-Identifier: {meta.get('dcterms:title', self.project_name)}\n")
            f.write(f"Bagging-Date: {datetime.now().strftime('%Y-%m-%d')}\n")
            f.write(f"Payload-Oxum: {total_bytes}.{total_files}\n") # Formato estrito: bytes.quantidade
            
        # 7. Escrever tagmanifest-sha256.txt (Hash dos Hashes)
        tagmanifest_path = os.path.join(bag_dir, "tagmanifest-sha256.txt")
        with open(tagmanifest_path, 'w', encoding='utf-8') as f:
            for tag_file in ["bagit.txt", "bag-info.txt", "manifest-sha256.txt"]:
                tp = os.path.join(bag_dir, tag_file)
                if os.path.exists(tp):
                    with open(tp, 'rb') as tf:
                        thash = hashlib.sha256(tf.read()).hexdigest()
                    f.write(f"{thash}  {tag_file}\n")
                    
        self._emit("BagIt: Pacote Arquivístico concluído e selado!")
