# Arquivo: core/vidya_processor.py

import os
import json
import time
from datetime import datetime, timezone
import cv2
import numpy as np
from PIL import Image
from PyQt5 import QtCore
import hashlib 
import shutil
from core.logger import get_logger

logger = get_logger("BatchProcessor")

class VidyaImageProcessor(QtCore.QThread):
    """Worker Thread para processamento Duplo (Berço em V), PDF/A e motor OCR."""
    progress_update = QtCore.pyqtSignal(int, str)
    process_finished = QtCore.pyqtSignal(str)
    process_error = QtCore.pyqtSignal(str)

    def __init__(self, valid_pairs: list, working_dir: str, flags: dict, settings: dict):
        super().__init__()
        self.valid_pairs = valid_pairs
        self.working_dir = working_dir
        self.flags = flags
        self.settings = settings
        
        self.out_dir = os.path.join(self.working_dir, "out")
        os.makedirs(self.out_dir, exist_ok=True)

    def _get_ocr_parameters(self, manifest_data: dict):
        """
        Lê os parâmetros de OCR do projeto (prioridade), depois das configs globais, 
        ou calcula a heurística dos sliders (Fallback).
        """
        # 1. OPTUNA NO PROJETO: Se a IA calibrou este lote, use a matemática perfeita absoluta
        proj_optuna = manifest_data.get("optuna_params", {})
        if "ocr_denoise_h" in proj_optuna:
            return (
                float(proj_optuna["ocr_denoise_h"]),
                float(proj_optuna["ocr_clahe_clip"]),
                int(proj_optuna["ocr_block_size"]),
                int(proj_optuna["ocr_c_val"])
            )
            
        # 2. OPTUNA GLOBAL: Se não calibrou o lote, mas tem calibração no sistema (Fallback 1)
        if "ocr_denoise_h" in self.settings:
            return (
                float(self.settings["ocr_denoise_h"]),
                float(self.settings["ocr_clahe_clip"]),
                int(self.settings["ocr_block_size"]),
                int(self.settings["ocr_c_val"])
            )

        # 3. HEURÍSTICA: Se não tem IA, lê as notas dos Sliders e converte em matriz OpenCV
        # (Prioriza o Slider salvo no projeto. Se não houver, usa o Slider global do sistema)
        proj_ocr = manifest_data.get("ocr_params", {})
        
        escurecimento = proj_ocr.get("ocr_cor_papel", self.settings.get("ocr_cor_papel", 20))
        intensidade = proj_ocr.get("ocr_int_impressao", self.settings.get("ocr_int_impressao", 80))
        extensao = proj_ocr.get("ocr_tam_manchas", self.settings.get("ocr_tam_manchas", 10))
        profundidade = proj_ocr.get("ocr_prof_manchas", self.settings.get("ocr_prof_manchas", 0))

        # --- A Matemática de Tradução (Mantida) ---
        h_base = (extensao * 0.15) + (profundidade * 0.05)
        if intensidade < 50:
            denoise_h = h_base * (intensidade / 50.0)
        else:
            denoise_h = h_base
        denoise_h = min(denoise_h, 20.0)

        clahe_base = 1.0 + (escurecimento * 0.03)
        if intensidade < 60:
            contrast_clip = clahe_base + ((60 - intensidade) * 0.05)
        else:
            contrast_clip = clahe_base
        contrast_clip = min(contrast_clip, 6.0)

        raw_block = int(19 + (extensao * 0.4))
        block_size = raw_block + 1 if raw_block % 2 == 0 else raw_block

        c_base = 8 + (escurecimento * 0.05) + (profundidade * 0.1)
        if intensidade < 70:
            c_final = c_base - ((70 - intensidade) * 0.15)
        else:
            c_final = c_base
        c_final = int(max(2, min(c_final, 25)))

        return denoise_h, contrast_clip, block_size, c_final

    def _create_premis_event(self, event_type: str, detail: str, agent: str, obj_id: str, obj_hash: str = None) -> dict:
        event = {
            "eventType": event_type,
            "eventDateTime": datetime.now(timezone.utc).isoformat()[:19] + "Z", 
            "eventDetail": detail,
            "linkingAgentIdentifierValue": agent,
            "linkingObjectIdentifierValue": obj_id
        }
        if obj_hash:
            event["resultingObjectHash"] = obj_hash
        return event

    def _cleanup_old_exports(self, project_name):
        export_path = self.settings.get("pdf_export_path", "")
        
        if export_path and os.path.exists(export_path):
            for f_name in os.listdir(export_path):
                full_path = os.path.join(export_path, f_name)
                if f_name.startswith(f"{project_name}-") and (f_name.endswith(".pdf") or f_name.endswith("_Texto_Bruto.txt")):
                    try: os.remove(full_path)
                    except: pass
                elif f_name.endswith("_Metadados.tsv"):
                    base = f_name.replace("_Metadados.tsv", "")
                    if base.rsplit('_', 1)[0] == project_name:
                        try: os.remove(full_path)
                        except: pass
                elif "_BagIt_" in f_name and os.path.isdir(full_path):
                    if f_name.split("_BagIt_")[0] == project_name:
                        try: shutil.rmtree(full_path)
                        except: pass

        for f_name in os.listdir(self.working_dir):
            full_path = os.path.join(self.working_dir, f_name)
            if "_BagIt_" in f_name and os.path.isdir(full_path):
                if f_name.split("_BagIt_")[0] == project_name:
                    try: shutil.rmtree(full_path)
                    except: pass
                    
        if os.path.exists(self.out_dir):
            for f_name in os.listdir(self.out_dir):
                full_path = os.path.join(self.out_dir, f_name)
                if f_name.lower().endswith(".pdf") or f_name.endswith("_Texto_Bruto.txt") or f_name.endswith("_Metadados.tsv"):
                    try: os.remove(full_path)
                    except: pass

    def _get_encode_params(self):
        """Traduz as preferências do usuário para matrizes de compressão do OpenCV."""
        fmt = self.settings.get("image_format", "JPG")
        params = []
        ext = ".jpg"
        
        if fmt == "JPG":
            q = int(self.settings.get("jpg_quality", 95))
            params = [int(cv2.IMWRITE_JPEG_QUALITY), q]
            ext = ".jpg"
        elif fmt == "PNG":
            c = int(self.settings.get("png_compression", 6))
            params = [int(cv2.IMWRITE_PNG_COMPRESSION), c]
            ext = ".png"
        elif fmt == "TIFF":
            t_comp = self.settings.get("tiff_compression", "Sem compressão")
            val = 1 
            if "LZW" in t_comp: val = 5
            elif "ZIP" in t_comp: val = 8
            elif "JPEG" in t_comp: val = 7
            params = [int(cv2.IMWRITE_TIFF_COMPRESSION), val]
            ext = ".tiff"
            
        return ext, params
        
    def run(self):
        try:
            # ---> INÍCIO DA PURGA PREVENTIVA DA PASTA 'out' <---
            self.progress_update.emit(0, "Limpando cache de processamento anterior...")
            if os.path.exists(self.out_dir):
                for f_name in os.listdir(self.out_dir):
                    full_path = os.path.join(self.out_dir, f_name)
                    try:
                        if os.path.isfile(full_path) or os.path.islink(full_path):
                            os.remove(full_path)
                        elif os.path.isdir(full_path):
                            shutil.rmtree(full_path)
                    except Exception as e:
                        logger.warning(f"Aviso: Não foi possível remover lixo residual '{f_name}': {e}")
            # ---> FIM DA PURGA PREVENTIVA <---
            
            total_files = len(self.valid_pairs)
            processed_images = []
            original_geom_images = []
            
            premis_events = [] 
            log_premis = self.settings.get("custody_log_premis", True)
            
            deskew_agg = float(self.settings.get("deskew_aggressiveness", 1.0))
            dewarp_agg = float(self.settings.get("dewarp_aggressiveness", 1.0))
            pdf_source = self.settings.get("pdf_source", "tratadas")

            do_ocr_prep = self.flags.get("ocr") and self.settings.get("ocr_preprocess", True)
            if do_ocr_prep:
                den_h, clahe_clip, block_s, c_val = self._calculate_ocr_heuristics()

            target_ext, encode_params = self._get_encode_params() # <--- BUSCA OS PARÂMETROS

            # =========================================================================
            # 1. PROCESSAMENTO DE IMAGENS (OpenCV)
            # =========================================================================
            for idx, pair in enumerate(self.valid_pairs):
                img_path = pair["image"]
                json_path = pair["json"]
                
                # Substitui a extensão herdada da câmara pela escolhida pelo utilizador
                base_name = os.path.basename(img_path) # <--- INCLUA ESTA LINHA
                name_no_ext, _ = os.path.splitext(base_name) # <--- USE base_name AQUI
                target_name = f"{name_no_ext}{target_ext}"
                
                self.progress_update.emit(int((idx / total_files) * 85), f"Processando: {target_name}")
                
                img = cv2.imread(img_path)
                if img is None: continue

                applied_transforms = []

                homographics_run = False
                # ---> INÍCIO DA INSERÇÃO: DESKEW MANUAL E AUTOMÁTICO <---
                if os.path.exists(json_path) and self.flags.get("crop"):
                    try:
                        with open(json_path, 'r', encoding='utf-8') as f:
                            meta_deskew = json.load(f)
                        manual_pts = meta_deskew.get("manual_deskew", [])
                        
                        # Se houver 4 pontos válidos, aplica a Retificação de Perspectiva
                        if manual_pts and len(manual_pts) == 4:
                            pts = np.array([[p["x"], p["y"]] for p in manual_pts], dtype="float32")
                            
                            # Algoritmo de Ordenação: Garante TL, TR, BR, BL independente da ordem do clique
                            s = pts.sum(axis=1)
                            diff = np.diff(pts, axis=1)
                            rect = np.zeros((4, 2), dtype="float32")
                            rect[0] = pts[np.argmin(s)]       # Top-Left
                            rect[2] = pts[np.argmax(s)]       # Bottom-Right
                            rect[1] = pts[np.argmin(diff)]    # Top-Right
                            rect[3] = pts[np.argmax(diff)]    # Bottom-Left
                            
                            # Captura as dimensões da imagem (antes da retificação)
                            orig_h, orig_w = img.shape[:2]
                            
                            # Mapeia os pontos selecionados para os extremos das dimensões originais
                            dst = np.array([
                                [0, 0],
                                [orig_w - 1, 0],
                                [orig_w - 1, orig_h - 1],
                                [0, orig_h - 1]], dtype="float32")
                                
                            M = cv2.getPerspectiveTransform(rect, dst)
                            # Retifica a imagem forçando a saída nas mesmas dimensões originais
                            img = cv2.warpPerspective(img, M, (orig_w, orig_h))
                            homographics_run = True
                            applied_transforms.append("Crop Manual (Homografia 4 Pontos para Dimensões Originais)")
                    except Exception as e:
                        logger.error(f"Erro no Crop Manual em {base_name}: {e}")             
                
                # ---> INÍCIO DA INSERÇÃO: LÓGICA DE CROP PARA CÂMERA DUPLA <---
                if self.flags.get("crop") and not homographics_run:
                    try:
                        if os.path.exists(json_path):
                            with open(json_path, 'r', encoding='utf-8') as f:
                                meta = json.load(f)
                            geom = meta.get("crop_geometry", {})
                            if geom:
                                # Otimização Numérica (Bounding Box)
                                x = int(geom.get("x", 0)); y = int(geom.get("y", 0))
                                w = int(geom.get("width", img.shape[1])); h = int(geom.get("height", img.shape[0]))
                                x = max(0, x); y = max(0, y)
                                w = min(w, img.shape[1] - x); h = min(h, img.shape[0] - y)
                                img = img[y:y+h, x:x+w]
                                applied_transforms.append("Crop Geométrico (Retangular)")
                                
                                # Máscara Poligonal Vetorial
                                polygon_data = geom.get("polygon", [])
                                if polygon_data and len(polygon_data) > 2:
                                    fill_pref = self.settings.get("marker_fill_color", "Transparente")
                                    pts = np.array([[int(p["x"]), int(p["y"])] for p in polygon_data], dtype=np.int32)
                                    mask = np.zeros(img.shape[:2], dtype=np.uint8)
                                    cv2.fillPoly(mask, [pts], 255)
                                    
                                    if fill_pref == "Transparente":
                                        img = cv2.cvtColor(img, cv2.COLOR_BGR2BGRA)
                                        img[mask == 0] = (0, 0, 0, 0)
                                    elif fill_pref == "Branco":
                                        img[mask == 0] = (255, 255, 255)
                                    elif fill_pref == "Preto":
                                        img[mask == 0] = (0, 0, 0)
                                    elif fill_pref.startswith("#") and len(fill_pref) == 7:
                                        # Converte HEX (#RRGGBB) para Tupla BGR nativa do OpenCV
                                        try:
                                            r = int(fill_pref[1:3], 16)
                                            g = int(fill_pref[3:5], 16)
                                            b = int(fill_pref[5:7], 16)
                                            
                                            if img.shape[2] == 4:
                                                img[mask == 0] = (b, g, r, 255) # Com canal Alpha
                                            else:
                                                img[mask == 0] = (b, g, r) # Padrão BGR
                                        except ValueError:
                                            img[mask == 0] = (0, 0, 0) # Fallback para preto
                                    else: 
                                        img[mask == 0] = (0, 0, 0) # Fallback padrão
                                        
                                    applied_transforms.append(f"Crop Poligonal Dinâmico (Fundo: {fill_pref})")
                    except Exception as e: logger.error(f"Erro no Crop em {base_name}: {e}")
                    # ---> FIM DA INSERÇÃO <---

                if self.flags.get("deskew"):
                    try:
                        from core.vidya_deskew import VidyaDeskewer
                        deskewer = VidyaDeskewer(max_angle=15.0)
                        img, final_angle, changed = deskewer.deskew(img, aggressiveness=deskew_agg)
                        if changed: applied_transforms.append(f"Deskew (Agg: {deskew_agg})")
                    except Exception as e: 
                        logger.error(f"Erro na execução do Deskew em {base_name}: {e}")
                # ---> FIM DA INSERÇÃO <---

                if self.flags.get("dewarp"):
                    try:
                        self.progress_update.emit(int((idx / total_files) * 85), f"Calculando malha de Dewarp: {base_name}")
                        from core.vidya_dewarp import VidyaPageDewarper                       
                        dewarper = VidyaPageDewarper(aggressiveness=dewarp_agg)
                        flattened_img, success = dewarper.flatten(img)
                        if success:
                            img = flattened_img
                            applied_transforms.append(f"Dewarp Planificação (Agg: {dewarp_agg})")
                    except Exception as e:
                        logger.error(f"Erro na execução do Dewarp em {base_name}: {e}")
                        
                original_state_img = img.copy()
                if pdf_source == "originais":
                    orig_path = os.path.join(self.out_dir, f"Orig_{target_name}")
                    cv2.imwrite(orig_path, original_state_img, encode_params) # <--- INJETA PARÂMETROS
                    original_geom_images.append(orig_path)

                if do_ocr_prep:
                    try:
                        if len(img.shape) == 3: 
                            if img.shape[2] == 4: # Blindagem para Imagens com Canal Alpha (Transparência)
                                alpha = img[:, :, 3] / 255.0
                                bgr = img[:, :, :3]
                                white_bg = np.ones_like(bgr, dtype=np.uint8) * 255
                                blended = (bgr * alpha[:, :, None] + white_bg * (1 - alpha[:, :, None])).astype(np.uint8)
                                gray = cv2.cvtColor(blended, cv2.COLOR_BGR2GRAY)
                            else:
                                gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
                        else: 
                            gray = img
                            
                        if den_h > 0.5: gray = cv2.fastNlMeansDenoising(gray, None, float(den_h), 7, 21)
                        clahe = cv2.createCLAHE(clipLimit=float(clahe_clip), tileGridSize=(8,8))
                        gray = clahe.apply(gray)
                        img = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, block_s, c_val)
                        img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
                        applied_transforms.append("Binarização Adaptativa OpenCV")
                    except Exception as e: logger.error(f"Erro na binarização: {e}")

                out_path = os.path.join(self.out_dir, f"Proc_{target_name}")
                cv2.imwrite(out_path, img, encode_params) # <--- INJETA PARÂMETROS E NOVA EXTENSÃO
                processed_images.append(out_path)

                if log_premis:
                    try:
                        with open(out_path, "rb") as f:
                            file_hash = hashlib.sha256(f.read()).hexdigest()
                        
                        detail_str = "Transformações aplicadas: " + ", ".join(applied_transforms) if applied_transforms else "Compressão de Imagem sem alterações geométricas"
                        
                        evt = self._create_premis_event(
                            event_type="transformation",
                            detail=detail_str,
                            agent="Vidya Capture CV-Engine",
                            obj_id=f"Proc_{target_name}", # <--- NOME ATUALIZADO NO PREMIS
                            obj_hash=file_hash
                        )
                        premis_events.append(evt)
                    except Exception as e:
                        logger.error(f"Falha ao gerar Hash PREMIS para {base_name}: {e}")

            # =========================================================================
            # 2. CARREGAMENTO CENTRALIZADO DO MANIFESTO
            # =========================================================================
            project_manifest_path = os.path.join(self.working_dir, "project.json")
            manifest_data = {}
            
            if os.path.exists(project_manifest_path):
                try:
                    with open(project_manifest_path, 'r', encoding='utf-8') as f:
                        manifest_data = json.load(f)
                except Exception as e:
                    logger.error(f"Falha ao carregar manifesto central: {e}")

            # --- NOVA LÓGICA DE NOMEAÇÃO ---
            folder_name = os.path.basename(self.working_dir)
            
            # 1. Busca prioritariamente o título salvo pela GUI no padrão Dublin Core
            project_name = manifest_data.get("metadata", {}).get("dcterms:title", "").strip()
            
            # 2. Fallback de segurança para configurações legadas ou nome da pasta
            if not project_name:
                project_name = manifest_data.get("project_name", self.settings.get("project_name", folder_name))
            
            # 3. Sanitiza a string para evitar quebra de I/O na gravação de PDFs, TSVs e BagIt
            import re
            safe_project_name = re.sub(r'[\\/*?:"<>|]', "", project_name).strip()
            
            # Injeta o nome oficial sanitizado de volta no manifesto para os exportadores downstream
            manifest_data["project_name"] = safe_project_name
            # -------------------------------

            pdf_input_list = [] # Declarado aqui para garantir escopo

            # =========================================================================
            # 3. MOTOR DE PRESERVAÇÃO PDF/A E OCR (DELEGAÇÃO)
            # =========================================================================
            if (self.flags.get("pdf") or self.flags.get("ocr")):
                timestamp_str = datetime.now().strftime("%y%m%d-%H%M%S")
                
                self.progress_update.emit(86, "Limpando exportações anteriores do projeto...")
                self._cleanup_old_exports(project_name)

                if pdf_source == "entrada":
                    pdf_input_list = [p["image"] for p in self.valid_pairs]
                elif pdf_source == "originais":
                    pdf_input_list = original_geom_images
                else:
                    pdf_input_list = processed_images
                    
                if not pdf_input_list:
                    raise ValueError("A lista de imagens selecionada para gerar o PDF está vazia.")

                self.progress_update.emit(89, "Invocando Motor Arquivístico PDF/A...")
                
                pdf_target = None
                try:
                    from core.pdfa_generator import VidyaPDFAEngine
                    pdf_engine = VidyaPDFAEngine(
                        pdf_input_list, self.out_dir, project_name, timestamp_str,
                        manifest_data, self.settings, self.flags
                    )
                    
                    pdf_target, agent_used = pdf_engine.compile_pdfa(
                        progress_callback=lambda msg: self.progress_update.emit(91, msg)
                    )
                    
                    self._log_pdf_creation(premis_events, pdf_target, agent_used)
                except Exception as e:
                    logger.error(f"Falha de delegação para o motor PDF/A: {e}")

                # ---> CÓPIA DO PDF PARA O DESTINO FINAL <---
                export_path = self.settings.get("pdf_export_path", "")
                if export_path and os.path.exists(export_path) and pdf_target and os.path.exists(pdf_target):
                    self.progress_update.emit(97, "Copiando PDF de acesso para o destino final...")
                    try: shutil.copy2(pdf_target, os.path.join(export_path, os.path.basename(pdf_target)))
                    except Exception as e: logger.error(f"Erro ao copiar PDF: {e}")
                    
                    if self.settings.get("ocr_sidecar", False):
                        txt_path = os.path.join(self.out_dir, f"{project_name}-{timestamp_str}_Texto_Bruto.txt")
                        if os.path.exists(txt_path):
                            try: shutil.copy2(txt_path, os.path.join(export_path, os.path.basename(txt_path)))
                            except: pass

            # =========================================================================
            # 4. FECHO DA CADEIA DE CUSTÓDIA: SELAGEM NO MANIFESTO (PREMIS)
            # =========================================================================
            if log_premis and premis_events:
                self.progress_update.emit(98, "Selando Cadeia de Custódia (Padrão PREMIS)...")
                if "premis:events" not in manifest_data:
                    manifest_data["premis:events"] = []
                    
                manifest_data["premis:events"].extend(premis_events)
                try:
                    with open(project_manifest_path, 'w', encoding='utf-8') as f:
                        json.dump(manifest_data, f, indent=4, ensure_ascii=False)
                except Exception as e:
                    logger.error(f"Falha arquivística ao selar PREMIS no project.json: {e}")            
          
            # =========================================================================
            # 5. CUSTÓDIA: EXPORTAÇÃO TSV
            # =========================================================================
            if self.flags.get("tsv", self.settings.get("custody_export_tsv", False)):
                self.progress_update.emit(99, "Gerando matriz tabular de metadados (TSV)...")
                try:
                    from core.vidya_export_engine import VidyaTSVExporter
                    exporter = VidyaTSVExporter(self.working_dir, self.out_dir, manifest_data, self.settings, pdf_input_list)
                    exporter.generate_tsv()
                except Exception as e:
                    logger.error(f"Falha ao acionar o motor de exportação TSV: {e}")

            # =========================================================================
            # 6. CUSTÓDIA: EMPACOTAMENTO BAGIT
            # =========================================================================
            if self.flags.get("bagit", self.settings.get("custody_export_bagit", False)):
                self.progress_update.emit(99, "Empacotando projeto no padrão BagIt (Pode demorar)...")
                try:
                    from core.vidya_export_engine import VidyaBagItPackager
                    packager = VidyaBagItPackager(
                        self.working_dir, self.out_dir, manifest_data, self.settings, 
                        progress_callback=lambda msg: self.progress_update.emit(99, msg)
                    )
                    packager.create_bag()
                except Exception as e:
                    logger.error(f"Falha ao gerar pacote BagIt: {e}")

            # =========================================================================
            # 7. LIMPEZA FINAL DA PASTA OUT (APENAS RESÍDUOS INÚTEIS)
            # =========================================================================
            self.progress_update.emit(99, "Limpando arquivos originais temporários...")
            for f_name in os.listdir(self.out_dir):
                if f_name.startswith("Orig_"):
                    try: os.remove(os.path.join(self.out_dir, f_name))
                    except Exception as e: logger.warning(f"Não foi possível remover a imagem original {f_name}: {e}")

            self.progress_update.emit(100, "Concluído!")
            time.sleep(0.3) 
            self.process_finished.emit(self.out_dir)

        except Exception as e:
            logger.error(f"Falha crítica no processamento: {str(e)}")
            self.process_error.emit(str(e))

    def _log_pdf_creation(self, event_list, pdf_path, agent):
        """Função auxiliar para capturar a assinatura do PDF final."""
        if not self.settings.get("custody_log_premis", True) or not pdf_path or not os.path.exists(pdf_path): return
        try:
            with open(pdf_path, "rb") as f:
                pdf_hash = hashlib.sha256(f.read()).hexdigest()
            evt = self._create_premis_event(
                event_type="creation",
                detail="Geração de derivado de acesso e envelopamento de metadados XMP.",
                agent=agent,
                obj_id=os.path.basename(pdf_path),
                obj_hash=pdf_hash
            )
            event_list.append(evt)
        except Exception as e:
            logger.error(f"Erro ao hashear o PDF final {pdf_path}: {e}")

# ===================================================================================
# PROCESSADOR LINEAR PARA CÂMERA ÚNICA (Idêntico rigor arquivístico)
# ===================================================================================
class VidyaSingleProcessor(QtCore.QThread):
    """Worker Thread para processamento Linear (Câmera Única), PDF/A e motor OCR."""
    progress_update = QtCore.pyqtSignal(int, str)
    process_finished = QtCore.pyqtSignal(str)
    process_error = QtCore.pyqtSignal(str)

    def __init__(self, valid_items: list, working_dir: str, flags: dict, settings: dict):
        super().__init__()
        self.valid_items = valid_items  
        self.working_dir = working_dir
        self.flags = flags
        self.settings = settings
        
        self.out_dir = os.path.join(self.working_dir, "out")
        os.makedirs(self.out_dir, exist_ok=True)

    def _get_ocr_parameters(self, manifest_data: dict):
        """
        Lê os parâmetros de OCR do projeto (prioridade), depois das configs globais, 
        ou calcula a heurística dos sliders (Fallback).
        """
        # 1. OPTUNA NO PROJETO: Se a IA calibrou este lote, use a matemática perfeita absoluta
        proj_optuna = manifest_data.get("optuna_params", {})
        if "ocr_denoise_h" in proj_optuna:
            return (
                float(proj_optuna["ocr_denoise_h"]),
                float(proj_optuna["ocr_clahe_clip"]),
                int(proj_optuna["ocr_block_size"]),
                int(proj_optuna["ocr_c_val"])
            )
            
        # 2. OPTUNA GLOBAL: Se não calibrou o lote, mas tem calibração no sistema (Fallback 1)
        if "ocr_denoise_h" in self.settings:
            return (
                float(self.settings["ocr_denoise_h"]),
                float(self.settings["ocr_clahe_clip"]),
                int(self.settings["ocr_block_size"]),
                int(self.settings["ocr_c_val"])
            )

        # 3. HEURÍSTICA: Se não tem IA, lê as notas dos Sliders e converte em matriz OpenCV
        # (Prioriza o Slider salvo no projeto. Se não houver, usa o Slider global do sistema)
        proj_ocr = manifest_data.get("ocr_params", {})
        
        escurecimento = proj_ocr.get("ocr_cor_papel", self.settings.get("ocr_cor_papel", 20))
        intensidade = proj_ocr.get("ocr_int_impressao", self.settings.get("ocr_int_impressao", 80))
        extensao = proj_ocr.get("ocr_tam_manchas", self.settings.get("ocr_tam_manchas", 10))
        profundidade = proj_ocr.get("ocr_prof_manchas", self.settings.get("ocr_prof_manchas", 0))

        # --- A Matemática de Tradução (Mantida) ---
        h_base = (extensao * 0.15) + (profundidade * 0.05)
        if intensidade < 50:
            denoise_h = h_base * (intensidade / 50.0)
        else:
            denoise_h = h_base
        denoise_h = min(denoise_h, 20.0)

        clahe_base = 1.0 + (escurecimento * 0.03)
        if intensidade < 60:
            contrast_clip = clahe_base + ((60 - intensidade) * 0.05)
        else:
            contrast_clip = clahe_base
        contrast_clip = min(contrast_clip, 6.0)

        raw_block = int(19 + (extensao * 0.4))
        block_size = raw_block + 1 if raw_block % 2 == 0 else raw_block

        c_base = 8 + (escurecimento * 0.05) + (profundidade * 0.1)
        if intensidade < 70:
            c_final = c_base - ((70 - intensidade) * 0.15)
        else:
            c_final = c_base
        c_final = int(max(2, min(c_final, 25)))

        return denoise_h, contrast_clip, block_size, c_final

    def _create_premis_event(self, event_type: str, detail: str, agent: str, obj_id: str, obj_hash: str = None) -> dict:
        event = {
            "eventType": event_type,
            "eventDateTime": datetime.now(timezone.utc).isoformat()[:19] + "Z", 
            "eventDetail": detail,
            "linkingAgentIdentifierValue": agent,
            "linkingObjectIdentifierValue": obj_id
        }
        if obj_hash: event["resultingObjectHash"] = obj_hash
        return event

    def _cleanup_old_exports(self, project_name):
        export_path = self.settings.get("pdf_export_path", "")
        if export_path and os.path.exists(export_path):
            for f_name in os.listdir(export_path):
                full_path = os.path.join(export_path, f_name)
                if f_name.startswith(f"{project_name}-") and (f_name.endswith(".pdf") or f_name.endswith("_Texto_Bruto.txt")):
                    try: os.remove(full_path)
                    except: pass
                elif f_name.endswith("_Metadados.tsv"):
                    base = f_name.replace("_Metadados.tsv", "")
                    if base.rsplit('_', 1)[0] == project_name:
                        try: os.remove(full_path)
                        except: pass
                elif "_BagIt_" in f_name and os.path.isdir(full_path):
                    if f_name.split("_BagIt_")[0] == project_name:
                        try: shutil.rmtree(full_path)
                        except: pass

        for f_name in os.listdir(self.working_dir):
            full_path = os.path.join(self.working_dir, f_name)
            if "_BagIt_" in f_name and os.path.isdir(full_path):
                if f_name.split("_BagIt_")[0] == project_name:
                    try: shutil.rmtree(full_path)
                    except: pass
                    
        if os.path.exists(self.out_dir):
            for f_name in os.listdir(self.out_dir):
                full_path = os.path.join(self.out_dir, f_name)
                if f_name.lower().endswith(".pdf") or f_name.endswith("_Texto_Bruto.txt") or f_name.endswith("_Metadados.tsv"):
                    try: os.remove(full_path)
                    except: pass

    def _get_encode_params(self):
        fmt = self.settings.get("image_format", "JPG")
        params = []
        ext = ".jpg"
        if fmt == "JPG":
            q = int(self.settings.get("jpg_quality", 95))
            params = [int(cv2.IMWRITE_JPEG_QUALITY), q]
            ext = ".jpg"
        elif fmt == "PNG":
            c = int(self.settings.get("png_compression", 6))
            params = [int(cv2.IMWRITE_PNG_COMPRESSION), c]
            ext = ".png"
        elif fmt == "TIFF":
            t_comp = self.settings.get("tiff_compression", "Sem compressão")
            val = 1 
            if "LZW" in t_comp: val = 5
            elif "ZIP" in t_comp: val = 8
            elif "JPEG" in t_comp: val = 7
            params = [int(cv2.IMWRITE_TIFF_COMPRESSION), val]
            ext = ".tiff"
        return ext, params
        
    def run(self):
        try:
            # ---> INÍCIO DA PURGA PREVENTIVA DA PASTA 'out' <---
            self.progress_update.emit(0, "Limpando cache de processamento anterior...")
            if os.path.exists(self.out_dir):
                for f_name in os.listdir(self.out_dir):
                    full_path = os.path.join(self.out_dir, f_name)
                    try:
                        if os.path.isfile(full_path) or os.path.islink(full_path):
                            os.remove(full_path)
                        elif os.path.isdir(full_path):
                            shutil.rmtree(full_path)
                    except Exception as e:
                        logger.warning(f"Aviso: Não foi possível remover lixo residual '{f_name}': {e}")
            # ---> FIM DA PURGA PREVENTIVA <---
            
            # ---> INÍCIO DA CORREÇÃO: CARREGAR O MANIFESTO ANTES DE INICIAR O LOOP <---
            project_manifest_path = os.path.join(self.working_dir, "project.json")
            manifest_data = {}
            if os.path.exists(project_manifest_path):
                try:
                    with open(project_manifest_path, 'r', encoding='utf-8') as f:
                        manifest_data = json.load(f)
                except Exception as e:
                    logger.error(f"Falha ao carregar manifesto central: {e}")
            # ---> FIM DA CORREÇÃO <---
            
            total_files = len(self.valid_items)
            processed_images = []
            original_geom_images = []
            
            premis_events = [] 
            log_premis = self.settings.get("custody_log_premis", True)
            
            deskew_agg = float(self.settings.get("deskew_aggressiveness", 1.0))
            dewarp_agg = float(self.settings.get("dewarp_aggressiveness", 1.0))
            pdf_source = self.settings.get("pdf_source", "tratadas")

            # ---> AQUI INVOCAMOS O NOVO MÉTODO PASSANDO O MANIFESTO DO PROJETO <---
            do_ocr_prep = self.flags.get("ocr") and self.settings.get("ocr_preprocess", True)
            if do_ocr_prep:
                den_h, clahe_clip, block_s, c_val = self._get_ocr_parameters(manifest_data)

            target_ext, encode_params = self._get_encode_params()

            # =========================================================================
            # 1. PROCESSAMENTO DE IMAGENS (OpenCV)
            # =========================================================================
            for idx, item in enumerate(self.valid_items):
                img_path = item["image"]
                json_path = item["json"]
                is_clip = item.get("is_clip", False) 
                
                # Substitui a extensão herdada da câmara pela escolhida pelo utilizador
                base_name = os.path.basename(img_path) # <--- INCLUA ESTA LINHA
                name_no_ext, _ = os.path.splitext(base_name) # <--- USE base_name AQUI
                target_name = f"{name_no_ext}{target_ext}"
                
                if is_clip:
                    json_name = os.path.basename(json_path).replace(".json", "")
                    clip_suffix = json_name.replace(name_no_ext, "")
                    target_name = f"{name_no_ext}{clip_suffix}{target_ext}"
                else:
                    target_name = f"{name_no_ext}{target_ext}"
                
                self.progress_update.emit(int((idx / total_files) * 85), f"Processando Câmera Única: {target_name}")
                
                img = cv2.imread(img_path)
                if img is None: continue

                applied_transforms = []

                # ---> INÍCIO DA INSERÇÃO: DESKEW MANUAL E AUTOMÁTICO <---
                homographics_run = False
                if os.path.exists(json_path) and self.flags.get("crop"):
                    try:
                        with open(json_path, 'r', encoding='utf-8') as f:
                            meta_deskew = json.load(f)
                        manual_pts = meta_deskew.get("manual_deskew", [])
                        
                        # Se houver 4 pontos válidos, aplica a Retificação de Perspectiva
                        if manual_pts and len(manual_pts) == 4:
                            pts = np.array([[p["x"], p["y"]] for p in manual_pts], dtype="float32")
                            
                            # Algoritmo de Ordenação: Garante TL, TR, BR, BL independente da ordem do clique
                            s = pts.sum(axis=1)
                            diff = np.diff(pts, axis=1)
                            rect = np.zeros((4, 2), dtype="float32")
                            rect[0] = pts[np.argmin(s)]       # Top-Left
                            rect[2] = pts[np.argmax(s)]       # Bottom-Right
                            rect[1] = pts[np.argmin(diff)]    # Top-Right
                            rect[3] = pts[np.argmax(diff)]    # Bottom-Left
                            
                            # Captura as dimensões da imagem (antes da retificação)
                            orig_h, orig_w = img.shape[:2]
                            
                            # Mapeia os pontos selecionados para os extremos das dimensões originais
                            dst = np.array([
                                [0, 0],
                                [orig_w - 1, 0],
                                [orig_w - 1, orig_h - 1],
                                [0, orig_h - 1]], dtype="float32")
                                
                            M = cv2.getPerspectiveTransform(rect, dst)
                            # Retifica a imagem forçando a saída nas mesmas dimensões originais
                            img = cv2.warpPerspective(img, M, (orig_w, orig_h))
                            homographics_run = True
                            applied_transforms.append("Crop Manual (Homografia 4 Pontos para Dimensões Originais)")
                    except Exception as e:
                        logger.error(f"Erro no Crop Manual em {base_name}: {e}")


                if self.flags.get("crop") and not homographics_run:
                    try:
                        if os.path.exists(json_path):
                            with open(json_path, 'r', encoding='utf-8') as f:
                                meta = json.load(f)
                            geom = meta.get("crop_geometry", {})
                            if geom:
                                # Passo 1: Otimização Numérica (Bounding Box)
                                x = int(geom.get("x", 0)); y = int(geom.get("y", 0))
                                w = int(geom.get("width", img.shape[1])); h = int(geom.get("height", img.shape[0]))
                                x = max(0, x); y = max(0, y)
                                w = min(w, img.shape[1] - x); h = min(h, img.shape[0] - y)
                                img = img[y:y+h, x:x+w]
                                applied_transforms.append("Crop Geométrico (Retangular)")
                                
                                # Passo 2: Máscara Poligonal Vetorial
                                polygon_data = geom.get("polygon", [])
                                if polygon_data and len(polygon_data) > 2:
                                    fill_pref = self.settings.get("marker_fill_color", "Transparente")
                                    
                                    pts = np.array([[int(p["x"]), int(p["y"])] for p in polygon_data], dtype=np.int32)
                                    mask = np.zeros(img.shape[:2], dtype=np.uint8)
                                    cv2.fillPoly(mask, [pts], 255)
                                    
                                    if fill_pref == "Transparente":
                                        img = cv2.cvtColor(img, cv2.COLOR_BGR2BGRA)
                                        img[mask == 0] = (0, 0, 0, 0)
                                    elif fill_pref == "Branco":
                                        img[mask == 0] = (255, 255, 255)
                                    elif fill_pref == "Preto":
                                        img[mask == 0] = (0, 0, 0)
                                    elif fill_pref.startswith("#") and len(fill_pref) == 7:
                                        try:
                                            r = int(fill_pref[1:3], 16)
                                            g = int(fill_pref[3:5], 16)
                                            b = int(fill_pref[5:7], 16)
                                            
                                            if img.shape[2] == 4:
                                                img[mask == 0] = (b, g, r, 255)
                                            else:
                                                img[mask == 0] = (b, g, r)
                                        except ValueError:
                                            img[mask == 0] = (0, 0, 0)
                                    else:
                                        img[mask == 0] = (0, 0, 0)
                                        
                                    applied_transforms.append(f"Crop Poligonal Dinâmico (Fundo: {fill_pref})")

                                if is_clip: applied_transforms.append("Recorte de Múltiplos Quadros")
                    except Exception as e: logger.error(f"Erro no Crop: {e}")

                if self.flags.get("deskew"):
                    try:
                        from core.vidya_deskew import VidyaDeskewer
                        deskewer = VidyaDeskewer(max_angle=15.0)
                        img, final_angle, changed = deskewer.deskew(img, aggressiveness=deskew_agg)
                        if changed: applied_transforms.append(f"Deskew (Agg: {deskew_agg})")
                    except Exception as e: 
                        logger.error(f"Erro na execução do Deskew em {base_name}: {e}")
                # ---> FIM DA INSERÇÃO <---
                        
                if self.flags.get("dewarp"):
                    try:
                        self.progress_update.emit(int((idx / total_files) * 85), f"Calculando malha de Dewarp: {base_name}")
                        from core.vidya_dewarp import VidyaPageDewarper                       
                        dewarper = VidyaPageDewarper(aggressiveness=dewarp_agg)
                        flattened_img, success = dewarper.flatten(img)
                        if success:
                            img = flattened_img
                            applied_transforms.append(f"Dewarp Planificação (Agg: {dewarp_agg})")
                    except Exception as e: logger.error(f"Erro na execução do Dewarp em {base_name}: {e}")
                        
                original_state_img = img.copy()
                if pdf_source == "originais":
                    orig_path = os.path.join(self.out_dir, f"Orig_{target_name}")
                    cv2.imwrite(orig_path, original_state_img, encode_params)
                    original_geom_images.append(orig_path)

                if do_ocr_prep:
                    try:
                        if len(img.shape) == 3:
                            if img.shape[2] == 4: # Blindagem para Imagens com Canal Alpha (Transparência)
                                alpha = img[:, :, 3] / 255.0
                                bgr = img[:, :, :3]
                                white_bg = np.ones_like(bgr, dtype=np.uint8) * 255
                                blended = (bgr * alpha[:, :, None] + white_bg * (1 - alpha[:, :, None])).astype(np.uint8)
                                gray = cv2.cvtColor(blended, cv2.COLOR_BGR2GRAY)
                            else:
                                gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
                        else: 
                            gray = img
                            
                        if den_h > 0.5: gray = cv2.fastNlMeansDenoising(gray, None, float(den_h), 7, 21)
                        clahe = cv2.createCLAHE(clipLimit=float(clahe_clip), tileGridSize=(8,8))
                        gray = clahe.apply(gray)
                        img = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, block_s, c_val)
                        img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
                        applied_transforms.append("Binarização Adaptativa OpenCV")
                    except Exception as e: logger.error(f"Erro na binarização: {e}")

                out_path = os.path.join(self.out_dir, f"Proc_{target_name}")
                cv2.imwrite(out_path, img, encode_params)
                processed_images.append(out_path)

                if log_premis:
                    try:
                        with open(out_path, "rb") as f:
                            file_hash = hashlib.sha256(f.read()).hexdigest()
                        detail_str = "Transformações aplicadas: " + ", ".join(applied_transforms) if applied_transforms else "Compressão de Imagem sem alterações geométricas"
                        evt = self._create_premis_event(
                            event_type="transformation", detail=detail_str, agent="Vidya Capture CV-Engine",
                            obj_id=f"Proc_{target_name}", obj_hash=file_hash
                        )
                        premis_events.append(evt)
                    except Exception as e: logger.error(f"Falha ao gerar Hash PREMIS para {base_name}: {e}")

            # =========================================================================
            # 2. CARREGAMENTO CENTRALIZADO DO MANIFESTO
            # =========================================================================
            project_manifest_path = os.path.join(self.working_dir, "project.json")
            manifest_data = {}
            
            if os.path.exists(project_manifest_path):
                try:
                    with open(project_manifest_path, 'r', encoding='utf-8') as f:
                        manifest_data = json.load(f)
                except: pass

            # --- NOVA LÓGICA DE NOMEAÇÃO ---
            folder_name = os.path.basename(self.working_dir)
            
            project_name = manifest_data.get("metadata", {}).get("dcterms:title", "").strip()
            if not project_name:
                project_name = manifest_data.get("project_name", self.settings.get("project_name", folder_name))
                
            import re
            safe_project_name = re.sub(r'[\\/*?:"<>|]', "", project_name).strip()
            
            manifest_data["project_name"] = safe_project_name
            # -------------------------------

            pdf_input_list = []

            # =========================================================================
            # 3. MOTOR DE PRESERVAÇÃO PDF/A E OCR (DELEGAÇÃO)
            # =========================================================================
            if (self.flags.get("pdf") or self.flags.get("ocr")):
                timestamp_str = datetime.now().strftime("%y%m%d-%H%M%S")
                
                self.progress_update.emit(86, "Limpando exportações anteriores do projeto...")
                self._cleanup_old_exports(project_name)

                if pdf_source == "entrada": pdf_input_list = [p["image"] for p in self.valid_items]
                elif pdf_source == "originais": pdf_input_list = original_geom_images
                else: pdf_input_list = processed_images
                    
                if not pdf_input_list: raise ValueError("A lista de imagens selecionada para gerar o PDF está vazia.")

                self.progress_update.emit(89, "Invocando Motor Arquivístico PDF/A...")
                
                pdf_target = None
                try:
                    from core.pdfa_generator import VidyaPDFAEngine
                    pdf_engine = VidyaPDFAEngine(
                        pdf_input_list, self.out_dir, project_name, timestamp_str,
                        manifest_data, self.settings, self.flags
                    )
                    
                    pdf_target, agent_used = pdf_engine.compile_pdfa(
                        progress_callback=lambda msg: self.progress_update.emit(91, msg)
                    )
                    
                    self._log_pdf_creation(premis_events, pdf_target, agent_used)
                except Exception as e:
                    logger.error(f"Falha de delegação para o motor PDF/A: {e}")

                # ---> CÓPIA DO PDF PARA O DESTINO FINAL <---
                export_path = self.settings.get("pdf_export_path", "")
                if export_path and os.path.exists(export_path) and pdf_target and os.path.exists(pdf_target):
                    self.progress_update.emit(97, "Copiando PDF de acesso para o destino final...")
                    try: shutil.copy2(pdf_target, os.path.join(export_path, os.path.basename(pdf_target)))
                    except Exception as e: logger.error(f"Erro ao copiar PDF: {e}")
                    
                    if self.settings.get("ocr_sidecar", False):
                        txt_path = os.path.join(self.out_dir, f"{project_name}-{timestamp_str}_Texto_Bruto.txt")
                        if os.path.exists(txt_path):
                            try: shutil.copy2(txt_path, os.path.join(export_path, os.path.basename(txt_path)))
                            except: pass

            # =========================================================================
            # 4. FECHO DA CADEIA DE CUSTÓDIA: SELAGEM NO MANIFESTO (PREMIS)
            # =========================================================================
            if log_premis and premis_events:
                self.progress_update.emit(98, "Selando Cadeia de Custódia (Padrão PREMIS)...")
                if "premis:events" not in manifest_data: manifest_data["premis:events"] = []
                manifest_data["premis:events"].extend(premis_events)
                try:
                    with open(project_manifest_path, 'w', encoding='utf-8') as f:
                        json.dump(manifest_data, f, indent=4, ensure_ascii=False)
                except Exception as e: logger.error(f"Falha ao selar PREMIS: {e}")            
          
            # =========================================================================
            # 5. CUSTÓDIA: EXPORTAÇÃO TSV
            # =========================================================================
            if self.flags.get("tsv", self.settings.get("custody_export_tsv", False)):
                try:
                    from core.vidya_export_engine import VidyaTSVExporter
                    exporter = VidyaTSVExporter(self.working_dir, self.out_dir, manifest_data, self.settings, pdf_input_list)
                    exporter.generate_tsv()
                except Exception as e: logger.error(f"Falha na exportação TSV: {e}")

            # =========================================================================
            # 6. CUSTÓDIA: EMPACOTAMENTO BAGIT
            # =========================================================================
            if self.flags.get("bagit", self.settings.get("custody_export_bagit", False)):
                try:
                    from core.vidya_export_engine import VidyaBagItPackager
                    packager = VidyaBagItPackager(
                        self.working_dir, self.out_dir, manifest_data, self.settings, 
                        progress_callback=lambda msg: self.progress_update.emit(99, msg)
                    )
                    packager.create_bag()
                except Exception as e: logger.error(f"Falha ao gerar BagIt: {e}")

            # =========================================================================
            # 7. LIMPEZA FINAL DA PASTA OUT (APENAS RESÍDUOS INÚTEIS)
            # =========================================================================
            self.progress_update.emit(99, "Limpando arquivos originais temporários...")
            for f_name in os.listdir(self.out_dir):
                if f_name.startswith("Orig_"):
                    try: os.remove(os.path.join(self.out_dir, f_name))
                    except: pass

            self.progress_update.emit(100, "Concluído!")
            time.sleep(0.3) 
            self.process_finished.emit(self.out_dir)

        except Exception as e:
            logger.error(f"Falha crítica no processamento: {str(e)}")
            self.process_error.emit(str(e))

    def _log_pdf_creation(self, event_list, pdf_path, agent):
        if not self.settings.get("custody_log_premis", True) or not pdf_path or not os.path.exists(pdf_path): return
        try:
            with open(pdf_path, "rb") as f: pdf_hash = hashlib.sha256(f.read()).hexdigest()
            evt = self._create_premis_event(
                event_type="creation", detail="Geração de derivado de acesso e envelopamento XMP.", 
                agent=agent, obj_id=os.path.basename(pdf_path), obj_hash=pdf_hash
            )
            event_list.append(evt)
        except Exception as e: logger.error(f"Erro ao hashear o PDF final: {e}")
