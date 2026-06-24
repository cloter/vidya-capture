# Arquivo: core/pdfa_generator.py

import os
import subprocess
from PIL import Image
from core.logger import get_logger

logger = get_logger("PDFAGenerator")

class VidyaPDFAEngine:
    """
    Motor especialista na compilação de matrizes de imagem para a norma ISO 19005 (PDF/A).
    Atua de forma síncrona, encapsulando os binários ocrmypdf e ghostscript.
    """
    def __init__(self, pdf_input_list: list, out_dir: str, project_name: str, timestamp_str: str, manifest_data: dict, settings: dict, flags: dict):
        self.pdf_input_list = pdf_input_list
        self.out_dir = out_dir
        self.project_name = project_name
        self.timestamp_str = timestamp_str
        self.manifest_data = manifest_data
        self.settings = settings
        self.flags = flags

    def _escape_ps_string(self, text: str) -> str:
        if not text: return ""
        return str(text).replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)')

    def compile_pdfa(self, progress_callback):
        """Compila o PDF e retorna um tuplo: (caminho_final, agente_utilizado)."""
        raw_pdf_path = os.path.join(self.out_dir, "temp_raw_archive.pdf")
        final_pdfa_path = os.path.join(self.out_dir, f"{self.project_name}-{self.timestamp_str}_PDFA.pdf")
        fallback_pdf_path = os.path.join(self.out_dir, f"{self.project_name}-{self.timestamp_str}_Comum.pdf")
        
        # 1. Agrupamento em Matriz Bruta
        pil_images = [Image.open(p).convert("RGB") for p in self.pdf_input_list]
        if pil_images:
            pil_images[0].save(raw_pdf_path, save_all=True, append_images=pil_images[1:], resolution=150.0)
        for img in pil_images: img.close()

        # 2. Extração de Metadados Dublin Core
        meta = self.manifest_data.get("metadata", {})
        title = meta.get("dcterms:title", "Projeto Vidya")
        creator = meta.get("dcterms:creator", "Operador")
        description = meta.get("dcterms:description", "")
        publisher = meta.get("dcterms:publisher", "")
        
        proc_hist = self.manifest_data.get("processing_history", {})
        if proc_hist:
            d_app = "Ativo" if proc_hist.get("deskew_applied") else "Inativo"
            d_agg = int(proc_hist.get("deskew_aggressiveness_multiplier", 1.0) * 100)
            w_app = "Ativo" if proc_hist.get("dewarp_applied") else "Inativo"
            w_agg = int(proc_hist.get("dewarp_aggressiveness_multiplier", 1.0) * 100)
            o_app = "Ativo" if self.flags.get("ocr") else "Inativo"
            hist_str = f"[Historico de Processamento: Deskew={d_app}({d_agg}%); Dewarp={w_app}({w_agg}%); OCR={o_app}]"
            description = f"{description} | {hist_str}" if description else hist_str

        # =========================================================================
        # CAMINHO A: TESSERACT 5 (OCRMYPDF) - Preferencial para Preservação
        # =========================================================================
        if self.flags.get("ocr"):
            progress_callback("Iniciando Motor Tesseract 5 (Pode demorar)...")
            ocr_cmd = [
                "ocrmypdf", "--output-type", "pdfa-2",
                "--jobs", str(self.settings.get("ocr_jobs", 2)),
                "-l", self.settings.get("ocr_lang", "por+eng"),
                "--title", title, "--author", creator,
                "--subject", description, "--keywords", publisher,
                "--force-ocr"
            ]
            
            if self.settings.get("ocr_sidecar", False):
                txt_path = os.path.join(self.out_dir, f"{self.project_name}-{self.timestamp_str}_Texto_Bruto.txt")
                ocr_cmd.extend(["--sidecar", txt_path])
                
            ocr_cmd.extend([raw_pdf_path, final_pdfa_path])
            
            try:
                custom_env = os.environ.copy()
                custom_env["OMP_THREAD_LIMIT"] = "1"
                
                process = subprocess.run(
                    ocr_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL, env=custom_env, check=False
                )
                
                if os.path.exists(raw_pdf_path): os.remove(raw_pdf_path)
                
                if process.returncode == 0:
                    return final_pdfa_path, "Tesseract 5 OCR (ocrmypdf)"
                else:
                    logger.warning(f"O ocrmypdf finalizou com código de aviso {process.returncode}.")
                    if os.path.exists(final_pdfa_path): os.rename(final_pdfa_path, fallback_pdf_path)
                    return fallback_pdf_path, "Tesseract 5 OCR (Falha de Validação PDF/A)"
            except Exception as e:
                logger.error(f"Falha de sistema ao invocar OCR: {e}")
                if os.path.exists(raw_pdf_path): os.rename(raw_pdf_path, fallback_pdf_path)
                return fallback_pdf_path, "Tesseract 5 OCR (Falha Crítica)"

        # =========================================================================
        # CAMINHO B: GHOSTSCRIPT (ISO 19005 STRCIT MODE)
        # =========================================================================
        else:
            progress_callback("Envelopando metadados via Ghostscript (ISO 19005)...")
            ps_meta_path = os.path.join(self.out_dir, "metadata_manifest.ps")
            
            # Construção do Dicionário OutputIntent para validação veraPDF
            ps_content = f"""%!
[ /Title ({self._escape_ps_string(title)})
  /Author ({self._escape_ps_string(creator)})
  /Subject ({self._escape_ps_string(description)})
  /Keywords ({self._escape_ps_string(publisher)})
  /Creator (Vidya Capture Framework)
  /DOCINFO pdfmark
[ /_objdef {{OutputIntent_PDFA}} /type /dict /OBJ pdfmark
[ {{OutputIntent_PDFA}} <<
  /Type /OutputIntent
  /S /GTS_PDFA1
  /OutputConditionIdentifier (sRGB)
  /RegistryName (http://www.color.org)
>> /PUT pdfmark
[ {{Catalog}} <</OutputIntents [ {{OutputIntent_PDFA}} ]>> /PUT pdfmark
"""
            with open(ps_meta_path, 'w', encoding='utf-8') as f: f.write(ps_content)
            
            gs_cmd = [
                "gs", "-dPDFA=2", "-dBATCH", "-dNOPAUSE", "-dNOOUTERSAVE",
                "-sProcessColorModel=DeviceRGB", 
                "-dColorConversionStrategy=/UseDeviceIndependentColor", # <--- CRÍTICO: Delega o ColorSpace interno
                "-sDEVICE=pdfwrite",
                "-dPDFACompatibilityPolicy=1", 
                f"-sOutputFile={final_pdfa_path}",
                ps_meta_path, raw_pdf_path
            ]
            
            try:
                process = subprocess.run(gs_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL, check=False)
                
                if os.path.exists(raw_pdf_path): os.remove(raw_pdf_path)
                if os.path.exists(ps_meta_path): os.remove(ps_meta_path)
                
                if process.returncode == 0:
                    return final_pdfa_path, "Ghostscript (ISO 19005)"
                else:
                    if os.path.exists(final_pdfa_path): os.rename(final_pdfa_path, fallback_pdf_path)
                    return fallback_pdf_path, "Ghostscript (ISO 19005 - Falha)"
            except Exception as e:
                logger.error(f"Falha de sistema ao invocar GS: {e}")
                if os.path.exists(raw_pdf_path): os.rename(raw_pdf_path, fallback_pdf_path)
                if os.path.exists(ps_meta_path): os.remove(ps_meta_path)
                return fallback_pdf_path, "Ghostscript (Falha Crítica)"
