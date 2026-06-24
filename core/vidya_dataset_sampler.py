# Arquivo: core/vidya_dataset_sampler.py

import random
import math
from core.logger import get_logger
from core.project_manager import VidyaSingleAuditor, VidyaProjectAuditor

logger = get_logger("DatasetSampler")

class VidyaDatasetSampler:
    """
    Motor de Amostragem Aleatória Estratificada.
    Garante que as imagens de Ground Truth sejam distribuídas uniformemente 
    ao longo da cronologia de captura do lote (Sessões).
    """
    
    @staticmethod
    def generate_ground_truth_pool(working_dir: str, is_single_mode: bool, num_sessions: int, samples_per_session: int) -> list:
        logger.info(f"Iniciando amostragem estratificada. Sessões: {num_sessions}, Amostras/Sessão: {samples_per_session}")

        # 1. Carregar a linha do tempo limpa usando os Auditores já existentes
        timeline = []
        if is_single_mode:
            report = VidyaSingleAuditor.audit_directory(working_dir)
            # Removemos recortes múltiplos (clips). O Ground Truth precisa ser feito na matriz original.
            timeline = [item for item in report.get("valid_items", []) if not item.get("is_clip", False)]
        else:
            report = VidyaProjectAuditor.audit_directory(working_dir)
            # Em modo Berço em V, o auditor já retorna uma lista linear ordenada por timestamp e lado
            timeline = report.get("valid_pairs", [])

        if not timeline:
            logger.warning("Nenhuma imagem válida encontrada no projeto para realizar a amostragem.")
            return []

        total_items = len(timeline)
        requested_total = num_sessions * samples_per_session

        # 2. Proteção de Borda (Fallback)
        # Se o utilizador pediu 10 amostras, mas o lote só tem 8 fotos no total,
        # devolvemos todo o lote sem sorteio.
        if total_items <= requested_total:
            logger.info(f"O tamanho do lote ({total_items}) é menor ou igual à amostra solicitada ({requested_total}). Retornando todo o lote.")
            return [item["image"] for item in timeline]

        # 3. Fatiamento Temporal (Sessões)
        # O math.ceil garante que não deixamos ficheiros de fora caso a divisão não seja inteira
        chunk_size = math.ceil(total_items / num_sessions)
        sessions = [timeline[i:i + chunk_size] for i in range(0, total_items, chunk_size)]

        sampled_images = []

        # 4. Extração Randômica sem Repetição
        for i, session_chunk in enumerate(sessions):
            # Se o último bloco for menor que a amostra desejada (sobra da divisão), limitamos a pescagem
            k = min(samples_per_session, len(session_chunk))
            
            # random.sample escolhe os itens sem repeti-los
            chosen_items = random.sample(session_chunk, k)
            
            for item in chosen_items:
                sampled_images.append(item["image"])
                
            logger.debug(f"Sessão {i+1}: Sorteou {k} imagens de um bloco de {len(session_chunk)}.")

        # Ordenar a saída novamente pelo tempo (ou nome) para a GUI de marcação abrir na ordem natural
        sampled_images.sort()

        logger.info(f"Amostragem concluída com sucesso: {len(sampled_images)} imagens isoladas para o Ground Truth.")
        return sampled_images
