# Arquivo: gui/vidya_thumbnail_panel.py

import os
import glob # <--- ADICIONAR ESTA LINHA
from PyQt5 import QtWidgets, QtCore, QtGui
from core.config import COLOR_MAP
from core.logger import get_logger

logger = get_logger("ThumbnailPanel")

class VidyaThumbnailPanel(QtWidgets.QListWidget):
    
    pair_selected = QtCore.pyqtSignal(str, str)
    delete_item_requested = QtCore.pyqtSignal(str) # <--- ADICIONAR
    rebuild_finished = QtCore.pyqtSignal()         # <--- ADICIONAR
    auto_crop_requested = QtCore.pyqtSignal(list) # <--- ADICIONE ESTA LINHA

    def __init__(self, settings_ref: dict):
        super().__init__()
        self.settings = settings_ref
        self.setViewMode(QtWidgets.QListView.IconMode)
        self.setIconSize(QtCore.QSize(240, 240)) 
        self.setResizeMode(QtWidgets.QListView.Adjust)
        self.setWrapping(True)
        self.setSpacing(10)
        self.setUniformItemSizes(False) 
        self.setWordWrap(True)
        self.setMinimumWidth(140)

        self.setSortingEnabled(True)
        self.sortItems(QtCore.Qt.DescendingOrder)
        
        self.itemClicked.connect(self._on_item_clicked)
     
        # ---> ADICIONAR: Rastreamento do "último item editado"   
        self._last_edited_paths = []
        self._original_canvases = {}

    def clear(self):
        """Sobrescrita: Limpa o cache de RAM sempre que a lista for recarregada."""
        self._original_canvases.clear()
        super().clear()
        
    def takeItem(self, row):
        """Sobrescrita: Remove o canvas da RAM quando o usuário deletar uma foto."""
        item = self.item(row)
        if item:
            path = item.data(QtCore.Qt.UserRole)
            self._original_canvases.pop(path, None)
        return super().takeItem(row)

    @property
    def is_single_mode(self):
        """Avalia dinamicamente se o painel deve se comportar como Câmera Única."""
        return self.settings.get("project_mode") == "Mesa Plana (Câmera Única)"

    def _on_item_clicked(self, item):
        # ---> Limpa o amarelo assim que iniciar uma nova edição
        self.clear_last_edited_highlight()

        # Resgata o caminho REAL e imutável da imagem exata que recebeu o clique
        clicked_path = item.data(QtCore.Qt.UserRole)
        if not clicked_path:
            return

        # BIFURCAÇÃO: MODO SIMPLES (Câmera Única)
        if self.is_single_mode:
            self.pair_selected.emit(clicked_path, "")
            return

        # LÓGICA MODO DUPLO: Isola exatamente o item clicado e busca a irmã mais próxima
        display_text = item.text()
        try:
            norm_ts = display_text.split('_')[0]
        except Exception:
            return
            
        is_left_click = "Left" in os.path.basename(clicked_path)
        
        # A imagem clicada já assume imediatamente o seu lado correto
        left_path = clicked_path if is_left_click else ""
        right_path = clicked_path if not is_left_click else ""
        
        # Pega a posição (índice) do item clicado para medir a distância
        clicked_index = self.row(item)
        best_distance = 999999
        
        for i in range(self.count()):
            if i == clicked_index:
                continue # Pula a si mesmo
                
            curr_item = self.item(i)
            # Analisa apenas itens que compartilham o mesmo grupo de tempo
            if curr_item.text().startswith(norm_ts + "_"):
                p = curr_item.data(QtCore.Qt.UserRole)
                if not p:
                    continue
                    
                # Se clicamos na Esquerda, procuramos a Direita correspondente mais próxima
                if is_left_click and "Right" in os.path.basename(p):
                    dist = abs(i - clicked_index)
                    if dist < best_distance:
                        best_distance = dist
                        right_path = p
                        
                # Se clicamos na Direita, procuramos a Esquerda correspondente mais próxima
                elif not is_left_click and "Left" in os.path.basename(p):
                    dist = abs(i - clicked_index)
                    if dist < best_distance:
                        best_distance = dist
                        left_path = p
                        
        if left_path or right_path:
            self.pair_selected.emit(left_path, right_path)

    def _on_item_clicked_old(self, item):
        # ---> ADICIONAR: Limpa o amarelo assim que iniciar uma nova edição
        self.clear_last_edited_highlight()

        # BIFURCAÇÃO: MODO SIMPLES
        if self.is_single_mode:
            p = item.data(QtCore.Qt.UserRole)
            if p:
                # Envia o caminho na posição Left e None para a posição Right
                self.pair_selected.emit(p, "")
            return

        # LÓGICA ORIGINAL: MODO DUPLO
        display_text = item.text()
        try:
            norm_ts = display_text.split('_')[0]
        except Exception:
            return
            
        left_path = ""
        right_path = ""
        
        for i in range(self.count()):
            curr_item = self.item(i)
            if curr_item.text().startswith(norm_ts + "_"):
                p = curr_item.data(QtCore.Qt.UserRole)
                if p:
                    if "Left" in os.path.basename(p):
                        left_path = p
                    elif "Right" in os.path.basename(p):
                        right_path = p
                        
        if left_path or right_path:
            self.pair_selected.emit(left_path, right_path)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        
        # Define a folga exata que você pediu: a largura total menos 20 pixels.
        available_width = self.viewport().width() - 30
        if available_width < 50: available_width = 50
        
        # A MÁGICA ESTÁ AQUI:
        # Mantém a caixa delimitadora na proporção exata da miniatura (160x240).
        # Sem isso, o Qt cria uma caixa quadrada e esmaga a imagem pela altura.
        available_height = int(available_width * 1.5)
        
        self.setIconSize(QtCore.QSize(available_width, available_height))

    def update_settings_ref(self, new_settings: dict):
        self.settings = new_settings

    # =========================================================================
    # RASTREAMENTO VISUAL DE EDIÇÃO (UX)
    # =========================================================================
    def set_last_edited_highlight(self, paths):
        """Define os alvos e manda todas as miniaturas se reavaliarem."""
        self._last_edited_paths = [p for p in paths if p]
        self._refresh_all_items()

    def clear_last_edited_highlight(self):
        """Limpa os alvos e remove o visual amarelo de quem estiver marcado."""
        if not self._last_edited_paths: return 
        self._last_edited_paths = []
        self._refresh_all_items()

    def _refresh_all_items(self):
        """Varredura que manda cada miniatura se desenhar novamente."""
        for i in range(self.count()):
            item = self.item(i)
            file_path = item.data(QtCore.Qt.UserRole)
            self._apply_highlight_to_item(item, file_path)

    def _apply_highlight_to_item(self, item, file_path):
        """Aplica dinamicamente a pintura baseada no estado atual."""
        orig_canvas = self._original_canvases.get(file_path)
        if not orig_canvas: return

        # A imagem (ícone) SEMPRE será a original limpa, sem manipulação de pixels
        item.setIcon(QtGui.QIcon(orig_canvas))

        if file_path in self._last_edited_paths:
            # Pinta apenas o fundo da etiqueta de texto abaixo da imagem
            item.setBackground(QtGui.QBrush(QtGui.QColor("#f1c40f"))) # Fundo Amarelo
            item.setForeground(QtGui.QBrush(QtGui.QColor("#000000"))) # Texto preto para dar contraste
            
            font = item.font()
            font.setBold(True)
            item.setFont(font)
        else:
            # Reseta a etiqueta para o estado transparente e com a cor do tema
            item.setBackground(QtGui.QBrush(QtCore.Qt.transparent))
            item.setForeground(QtGui.QBrush()) 
            
            font = item.font()
            font.setBold(False)
            item.setFont(font)

    # =========================================================================
    # EVENTOS DE TECLADO
    # =========================================================================
    def keyPressEvent(self, event):
        # 1. Guarda qual era o item ANTES do teclado agir
        previous_item = self.currentItem()
        
        # 2. Deixa o QListWidget processar o evento (mover a seleção nativamente)
        super().keyPressEvent(event)
        
        # 3. Pega o item atual DEPOIS da tentativa de mover
        current_item = self.currentItem()
        
        teclas_navegacao = (
            QtCore.Qt.Key_Up, 
            QtCore.Qt.Key_Down, 
            QtCore.Qt.Key_Left, 
            QtCore.Qt.Key_Right
        )
        
        # 4. Só executa a rotina pesada se a seleção DE FATO mudou de lugar
        if event.key() in teclas_navegacao:
            if current_item and current_item != previous_item:
                self._on_item_clicked(current_item)
                
    # =========================================================================
    # FUNÇÕES DE CARREGAMENTO (DUPLO E SIMPLES)
    # =========================================================================
    def load_project_pairs(self, valid_pairs: list):
        """Carrega a estrutura antiga de pares (Left/Right)"""
        self.clear()
        for pair in valid_pairs:
            if "image" in pair and os.path.exists(pair["image"]):
                self.add_thumbnail(pair["image"])

    def load_project_single(self, valid_items: list):
        """Carrega a estrutura linear de câmera única"""
        self.clear()
        for item in valid_items:
            if "image" in item and os.path.exists(item["image"]):
                self.add_thumbnail(item["image"])

    # =========================================================================
    # RENDERIZAÇÃO INTELIGENTE DE THUMBNAILS
    # =========================================================================
    def add_thumbnail(self, file_path: str):
        if not os.path.exists(file_path): return
        
        filename = os.path.basename(file_path)
        working_dir = os.path.dirname(file_path)
        
        # Extrai o nome sem a extensão original (ex: "Temp_Left_12345678")
        name_no_ext = filename.rsplit('.', 1)[0]
        
        thumb_dir = os.path.join(working_dir, ".thumbnails")
        os.makedirs(thumb_dir, exist_ok=True)
        
        # --- CORREÇÃO: Força o caminho do cache a terminar sempre em .jpg ---
        thumb_path = os.path.join(thumb_dir, f"{name_no_ext}.jpg")
        
        try:
            parts = filename.split('_')
            side = parts[1] 
            ts = parts[2].split('.')[0]
        except Exception:
            side = "Left" if "Left" in filename else "Right"
            ts = "0000000000"

        if self.is_single_mode:
            color_name = self.settings.get("marker_color_left", "Vermelho")
        else:
            color_key = f"marker_color_{side.lower()}"
            color_name = self.settings.get(color_key, "Vermelho" if side == "Left" else "Verde")
            
        hex_color = COLOR_MAP.get(color_name, "#FF0000")
        
        base_w, base_h = 160, 240
        margin_w, margin_h = int(base_w * 0.03), int(base_h * 0.03)
        img_w, img_h = base_w - (margin_w * 2), base_h - (margin_h * 2)

        # 2. Mecanismo de Cache/Proxy Resiliente
        # Se a miniatura leve não existir no disco, nós a geramos agora para poupar RAM futura
        if not os.path.exists(thumb_path):
            try:
                from PIL import Image
                with Image.open(file_path) as img:
                    img.thumbnail((img_w, img_h))
                    # Salva com compressão agressiva e otimização para carregamento rápido
                    img.save(thumb_path, "JPEG", quality=70, optimize=True)
            except Exception as e:
                logger.error(f"Falha ao gerar proxy físico para {filename}: {e}")

        # 3. Carregamento seguro da miniatura (Consome pouquíssimos KBs de RAM)
        target_pixmap_path = thumb_path if os.path.exists(thumb_path) else file_path
        scaled_pixmap = QtGui.QPixmap(target_pixmap_path)
        
        if scaled_pixmap.isNull(): return
        
        # Se o proxy acabou de ser gerado por fallback do original, garante o redimensionamento visual correto
        if not target_pixmap_path.endswith(filename):
            scaled_pixmap = scaled_pixmap.scaled(img_w, img_h, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)

        canvas = QtGui.QPixmap(base_w, base_h)
        canvas.fill(QtGui.QColor(hex_color))

        painter = QtGui.QPainter(canvas)
        x_offset = (base_w - scaled_pixmap.width()) // 2
        y_offset = (base_h - scaled_pixmap.height()) // 2

        painter.drawPixmap(x_offset, y_offset, scaled_pixmap)
        painter.end()

        # NOVO: Guarda a matriz limpa (pura) na memória do painel
        self._original_canvases[file_path] = canvas.copy()

        # Se o item já existir (atualização), injeta a arte nele e aborta
        for i in range(self.count()):
            existing_item = self.item(i)
            if existing_item.data(QtCore.Qt.UserRole) == file_path:
                self._apply_highlight_to_item(existing_item, file_path)
                return 

        normalized_ts = ts
        if not self.is_single_mode:
            try:
                current_ts_int = int(ts)
                for i in range(self.count()):
                    existing_text = self.item(i).text()
                    existing_ts_str = existing_text.split('_')[0]
                    existing_ts_int = int(existing_ts_str)
                    if abs(current_ts_int - existing_ts_int) <= 5:
                        normalized_ts = existing_ts_str
                        break
            except Exception:
                pass

        if self.is_single_mode:
            display_name = f"{normalized_ts}"
        else:
            display_side = "Esq" if side == "Left" else "Dir"
            display_name = f"{normalized_ts}_{display_side}"

        # Cria um item "seco" e passa para a função mestre decidir se pinta ou não
        item = QtWidgets.QListWidgetItem(display_name)
        item.setData(QtCore.Qt.UserRole, file_path)
        self.addItem(item)
        
        self._apply_highlight_to_item(item, file_path)

    # =========================================================================
    # DELEÇÕES FÍSICAS (HD E INTERFACE)
    # =========================================================================
    def remove_last_two(self) -> dict:
        """Função Original: Remove o par do topo do lote"""
        deleted_paths = {}
        if self.count() == 0: return deleted_paths

        top_item = self.item(0)
        top_path = top_item.data(QtCore.Qt.UserRole)
        top_filename = os.path.basename(top_path)
        
        try:
            target_ts = int(top_filename.split('_')[2].split('.')[0])
        except Exception:
            target_ts = 0

        items_to_remove = []
        for i in range(self.count()):
            if len(items_to_remove) >= 2: break
            item = self.item(i)
            path = item.data(QtCore.Qt.UserRole)
            filename = os.path.basename(path)
            try:
                ts = int(filename.split('_')[2].split('.')[0])
            except Exception:
                ts = 0
                
            if target_ts == 0 or abs(target_ts - ts) <= 5:
                items_to_remove.append(item)
            else:
                break
                
        for item in items_to_remove:
            row = self.row(item)
            self.takeItem(row)
            file_path = item.data(QtCore.Qt.UserRole)
            if file_path and os.path.exists(file_path):
                side = "Left" if "Left" in os.path.basename(file_path) else "Right"
                deleted_paths[side] = file_path
                try:
                    os.remove(file_path)
                    json_path = file_path.rsplit('.', 1)[0] + ".json"
                    if os.path.exists(json_path): os.remove(json_path)
                    
                    # ---> NOVA INSERÇÃO: Limpa o proxy físico da memória de miniaturas
                    thumb_path = os.path.join(os.path.dirname(file_path), ".thumbnails", f"{os.path.basename(file_path).rsplit('.', 1)[0]}.jpg")
                    if os.path.exists(thumb_path):
                        os.remove(thumb_path)
                    # ---> FIM DA INSERÇÃO
                except Exception as e:
                    logger.error(f"Falha ao apagar HD: {e}")

        return deleted_paths

    def remove_specific_pair(self, left_path: str, right_path: str):
        """Função Original: Remove cirurgicamente dois caminhos (Revisão)"""
        paths_to_delete = [p for p in (left_path, right_path) if p]
        if not paths_to_delete: return
        
        items_to_remove = []
        for i in range(self.count()):
            item = self.item(i)
            if item.data(QtCore.Qt.UserRole) in paths_to_delete:
                items_to_remove.append(item)
                
        for item in items_to_remove:
            row = self.row(item)
            self.takeItem(row)
            file_path = item.data(QtCore.Qt.UserRole)
            if file_path and os.path.exists(file_path):
                try:
                    os.remove(file_path)
                    json_path = file_path.rsplit('.', 1)[0] + ".json"
                    if os.path.exists(json_path): os.remove(json_path)
                    
                    # ---> NOVA INSERÇÃO: Limpa o proxy físico da memória de miniaturas
                    thumb_path = os.path.join(os.path.dirname(file_path), ".thumbnails", f"{os.path.basename(file_path).rsplit('.', 1)[0]}.jpg")
                    if os.path.exists(thumb_path):
                        os.remove(thumb_path)
                    # ---> FIM DA INSERÇÃO
                    
                    logger.info(f"Par específico removido do HD: {file_path}")
                except Exception as e:
                    logger.error(f"Falha ao apagar HD: {e}")

    def remove_last_single(self) -> dict:
        """NOVA Função: Remove estritamente o item do topo da lista (Modo Câmera Única)"""
        deleted_paths = {}
        if self.count() == 0: return deleted_paths

        top_item = self.item(0)
        file_path = top_item.data(QtCore.Qt.UserRole)
        
        row = self.row(top_item)
        self.takeItem(row)
        
        if file_path and os.path.exists(file_path):
            # Envia "Left" para o Orquestrador, pois a Câmera Única usa a thread Left nativamente
            deleted_paths["Left"] = file_path
            try:
                os.remove(file_path)
                json_path = file_path.rsplit('.', 1)[0] + ".json"
                if os.path.exists(json_path): os.remove(json_path)
                
                # ---> NOVA INSERÇÃO: Limpa o proxy físico da memória de miniaturas
                thumb_path = os.path.join(os.path.dirname(file_path), ".thumbnails", f"{os.path.basename(file_path).rsplit('.', 1)[0]}.jpg")
                if os.path.exists(thumb_path):
                    os.remove(thumb_path)
                # ---> FIM DA INSERÇÃO
            except Exception as e:
                logger.error(f"Falha ao apagar HD: {e}")

        return deleted_paths

    def remove_specific_single(self, path: str):
        """NOVA Função: Remove cirurgicamente um único caminho (Modo Câmera Única)"""
        if not path: return
        
        items_to_remove = []
        for i in range(self.count()):
            item = self.item(i)
            if item.data(QtCore.Qt.UserRole) == path:
                items_to_remove.append(item)
                
        for item in items_to_remove:
            row = self.row(item)
            self.takeItem(row)
            file_path = item.data(QtCore.Qt.UserRole)
            if file_path and os.path.exists(file_path):
                try:
                    os.remove(file_path)
                    json_path = file_path.rsplit('.', 1)[0] + ".json"
                    if os.path.exists(json_path): os.remove(json_path)
                    # ---> NOVA INSERÇÃO: Limpa o proxy físico da memória de miniaturas
                    thumb_path = os.path.join(os.path.dirname(file_path), ".thumbnails", f"{os.path.basename(file_path).rsplit('.', 1)[0]}.jpg")
                    if os.path.exists(thumb_path):
                        os.remove(thumb_path)
                    # ---> FIM DA INSERÇÃO
                    logger.info(f"Imagem específica removida do HD: {file_path}")
                except Exception as e:
                    logger.error(f"Falha ao apagar HD: {e}")
                    
    # =========================================================================
    # MENU DE CONTEXTO E RECONSTRUÇÃO
    # =========================================================================
    def contextMenuEvent(self, event):
        item = self.itemAt(event.pos())
        if not item: return
        
        file_path = item.data(QtCore.Qt.UserRole)
        menu = QtWidgets.QMenu(self)
        
        # Dinamicamente ajusta o texto do menu para ser transparente ao usuário
        if self.is_single_mode:
            del_text = "Remover esta imagem do projeto"
        else:
            del_text = "Remover este par de imagens do projeto"
            
        action_autocrop = menu.addAction(QtGui.QIcon.fromTheme("object-crop"), "Criar recortes automaticamente (Auto Crop)") # <--- AÇÃO NOVA
        menu.addSeparator()
        action_del = menu.addAction(QtGui.QIcon.fromTheme("edit-delete"), del_text)
        menu.addSeparator()
        action_rebuild = menu.addAction(QtGui.QIcon.fromTheme("view-refresh"), "Reconstruir miniaturas (.thumbnails)")
        
        action = menu.exec_(self.mapToGlobal(event.pos()))
        
        if action == action_del:
            self.delete_item_requested.emit(file_path)
        elif action == action_rebuild:
            self._start_rebuild_worker()
        elif action == action_autocrop:
            paths_to_process = []
            
            if self.is_single_mode:
                paths_to_process.append(file_path)
            else:
                # Localiza a "irmã" do par para o modo Berço em V
                filename = os.path.basename(file_path)
                left_path = file_path if "Left" in filename else ""
                right_path = file_path if "Right" in filename else ""
                
                if not left_path:
                    expected_left = filename.replace("Right", "Left")
                    lp = os.path.join(os.path.dirname(file_path), expected_left)
                    if os.path.exists(lp): left_path = lp
                if not right_path:
                    expected_right = filename.replace("Left", "Right")
                    rp = os.path.join(os.path.dirname(file_path), expected_right)
                    if os.path.exists(rp): right_path = rp

                # A Pergunta Elegante ao Usuário!
                msg_box = QtWidgets.QMessageBox(self)
                msg_box.setWindowTitle("Auto Crop (Berço em V)")
                msg_box.setText("O sistema detectou um par de imagens atrelado a esta seleção.\nEm qual(is) câmera(s) deseja gerar os recortes automáticos?")
                
                btn_left = msg_box.addButton("Somente Esquerda", QtWidgets.QMessageBox.ActionRole) if left_path else None
                btn_right = msg_box.addButton("Somente Direita", QtWidgets.QMessageBox.ActionRole) if right_path else None
                btn_both = msg_box.addButton("Em Ambas", QtWidgets.QMessageBox.AcceptRole) if (left_path and right_path) else None
                btn_cancel = msg_box.addButton("Cancelar", QtWidgets.QMessageBox.RejectRole)
                
                msg_box.exec_()
                clicked_btn = msg_box.clickedButton()
                
                if clicked_btn == btn_left: paths_to_process.append(left_path)
                elif clicked_btn == btn_right: paths_to_process.append(right_path)
                elif clicked_btn == btn_both: paths_to_process.extend([left_path, right_path])
                else: return # O usuário cancelou

            if paths_to_process:
                self.auto_crop_requested.emit(paths_to_process)

    def _start_rebuild_worker(self):
        paths = []
        for i in range(self.count()):
            p = self.item(i).data(QtCore.Qt.UserRole)
            if p and os.path.exists(p):
                paths.append(p)
                
        if not paths: return
        
        self.progress_dialog = QtWidgets.QProgressDialog("Iniciando reconstrução...", "Cancelar", 0, 100, self)
        self.progress_dialog.setWindowTitle("Reconstruindo Cache Visual")
        self.progress_dialog.setWindowModality(QtCore.Qt.ApplicationModal)
        self.progress_dialog.setMinimumDuration(0)
        self.progress_dialog.setValue(0)
        
        self.worker = ThumbnailRebuilderWorker(paths)
        self.worker.progress.connect(lambda val, txt: (self.progress_dialog.setValue(val), self.progress_dialog.setLabelText(txt)))
        self.worker.finished.connect(self._on_rebuild_finished)
        self.worker.error.connect(self._on_rebuild_error)
        
        # Cancelamento seguro da Thread
        self.progress_dialog.canceled.connect(self.worker.cancel)
        self.worker.start()
        
    def _on_rebuild_finished(self):
        self.progress_dialog.close()
        QtWidgets.QMessageBox.information(self, "Sucesso", "O cache de miniaturas foi reconstruído com sucesso!")
        self.rebuild_finished.emit() # Informa a GUI principal para dar um 'reload' na lista
        
    def _on_rebuild_error(self, msg):
        self.progress_dialog.close()
        logger.error(f"Erro na reconstrução de miniaturas: {msg}")
        QtWidgets.QMessageBox.critical(self, "Erro", f"Falha ao reconstruir o cache:\n{msg}")
        
class ThumbnailRebuilderWorker(QtCore.QThread):
    progress = QtCore.pyqtSignal(int, str)
    finished = QtCore.pyqtSignal()
    error = QtCore.pyqtSignal(str)

    def __init__(self, image_paths):
        super().__init__()
        self.image_paths = image_paths
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True

    def run(self):
        try:
            from PIL import Image
            total = len(self.image_paths)
            if total == 0:
                self.finished.emit()
                return

            # 1. PURGE: Limpa todo o cache residual e órfão primeiro
            thumb_dirs = set(os.path.join(os.path.dirname(p), ".thumbnails") for p in self.image_paths)
            self.progress.emit(0, "Limpando lixo residual de miniaturas...")
            
            for t_dir in thumb_dirs:
                if self._is_cancelled: return
                if os.path.exists(t_dir):
                    for old_thumb in glob.glob(os.path.join(t_dir, "*.jpg")):
                        try: os.remove(old_thumb)
                        except: pass

            # 2. REBUILD: Gera as novas miniaturas
            base_w, base_h = 160, 240
            margin_w, margin_h = int(base_w * 0.03), int(base_h * 0.03)
            img_w, img_h = base_w - (margin_w * 2), base_h - (margin_h * 2)

            for idx, path in enumerate(self.image_paths):
                if self._is_cancelled: return
                
                filename = os.path.basename(path)
                self.progress.emit(int((idx / total) * 100), f"Comprimindo: {filename}")
                
                if os.path.exists(path):
                    thumb_dir = os.path.join(os.path.dirname(path), ".thumbnails")
                    os.makedirs(thumb_dir, exist_ok=True)
                    name_no_ext = filename.rsplit('.', 1)[0]
                    thumb_path = os.path.join(thumb_dir, f"{name_no_ext}.jpg")
                    
                    try:
                        with Image.open(path) as img:
                            img.thumbnail((img_w, img_h))
                            img.save(thumb_path, "JPEG", quality=70, optimize=True)
                    except Exception as e:
                        logger.error(f"Falha isolada na miniatura de {filename}: {e}")

            self.progress.emit(100, "Concluído")
            self.finished.emit()
        except Exception as e:
            self.error.emit(str(e))
