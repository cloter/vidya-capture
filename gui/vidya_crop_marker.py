# Arquivo: gui/vidya_crop_marker.py

import math
from PyQt5 import QtWidgets, QtGui, QtCore
from core.config import COLOR_MAP

class VidyaCropMarker(QtWidgets.QGraphicsPolygonItem):
    """
    Componente poligonal vetorial sobreposto para demarcação da área útil de corte.
    Suporta redimensionamento por arraste de arestas, trava de proporção, Menu de Contexto,
    Sincronização em Tempo Real e Injeção de Topos Ortogonais.
    """
    def __init__(self, initial_color_name: str, initial_opacity: int = 8, initial_weight: int = 100):
        super().__init__() 
        
        self.setFlags(
            QtWidgets.QGraphicsItem.ItemIsMovable |
            QtWidgets.QGraphicsItem.ItemIsSelectable |
            QtWidgets.QGraphicsItem.ItemSendsGeometryChanges
        )
        self.setAcceptHoverEvents(True) 
        
        poly = QtGui.QPolygonF([
            QtCore.QPointF(0, 0),
            QtCore.QPointF(300, 0),
            QtCore.QPointF(300, 450),
            QtCore.QPointF(0, 450)
        ])
        self.setPolygon(poly)
        
        self.image_width = 0
        self.image_height = 0
        self.current_color_name = initial_color_name
        self.current_opacity = initial_opacity
        self.thickness_weight = initial_weight
        
        self.update_color(initial_color_name, initial_opacity, initial_weight)
        
        self.resizing = False
        self.resizing_edge = None
        self.edge_type = None 
        self.handle_size = 10.0  
        self._initial_pos = None
        self._initial_polygon = None

        self.keep_ratio = False
        self.image_ratio = 1.0
        
        self.copy_exact_callback = None
        self.copy_mirror_callback = None
        self.maximize_local_callback = None  
        self.maximize_both_callback = None   
        self.resize_percent_callback = None
        
        self.toggle_ratio_callback = None
        self.toggle_replicate_callback = None
        self.is_replicate_on = False
        self.is_single_mode = False  
        
        self.is_child_clip = False
        self.add_clip_callback = None
        self.remove_clip_callback = None
        
        self.duplicate_callback = None  # <--- ADICIONE ESTA LINHA AQUI
        self.save_undo_state_callback = None # <--- ADICIONE ESTA LINHA
        self.reset_all_clips_callback = None # <--- NOVO GATILHO
        self.sync_callback = None
        self.start_manual_deskew_callback = None # <--- GATILHO DO DESKEW MANUAL
        # NOVAS INSERÇÕES:
        self.cancel_manual_deskew_callback = None 
        self.is_deskew_active = False
        # ---> NOVAS INSERÇÕES PARA REMOÇÃO DE DESKEW:
        self.remove_manual_deskew_callback = None
        self.has_deskew_points = False

    def set_image_bounds(self, w, h):
        self.image_width = w
        self.image_height = h
        self.update_color(self.current_color_name, self.current_opacity, self.thickness_weight)

    def update_color(self, color_name: str, opacity_percent: int = 8, thickness_weight: int = 100):
        self.current_color_name = color_name
        self.current_opacity = opacity_percent
        self.thickness_weight = thickness_weight

        hex_color = COLOR_MAP.get(color_name, "#FF0000")
        if color_name.lower() == "vinho": hex_color = "#800020"
        qcolor = QtGui.QColor(hex_color)
        
        max_dim = max(getattr(self, 'image_width', 0), getattr(self, 'image_height', 0))
        base_thickness = max_dim / 200.0
        
        if max_dim > 0:
            weight_factor = thickness_weight / 100.0
            calculated_thickness = 1 + base_thickness * weight_factor
        else:
            calculated_thickness = base_thickness

        pen = QtGui.QPen(qcolor)
        pen.setWidthF(calculated_thickness)
        pen.setStyle(QtCore.Qt.DashLine)
        self.setPen(pen)
        
        fill_color = QtGui.QColor(hex_color)
        alpha_val = int((opacity_percent / 100.0) * 255)
        fill_color.setAlpha(alpha_val) 
        self.setBrush(QtGui.QBrush(fill_color))

    def _normalize_polygon(self):
        """Garante que o bounding box do polígono fique com a origem em (0,0) local,
        corrigindo distorções de matriz durante redimensionamentos globais (Ajustar Tamanho)."""
        poly = self.polygon()
        bbox = poly.boundingRect()
        
        if abs(bbox.left()) < 0.1 and abs(bbox.top()) < 0.1:
            return

        current_pos = self.pos()
        self.setPos(current_pos.x() + bbox.left(), current_pos.y() + bbox.top())
        
        new_poly = QtGui.QPolygonF()
        for i in range(poly.count()):
            pt = poly.at(i)
            new_poly.append(QtCore.QPointF(pt.x() - bbox.left(), pt.y() - bbox.top()))
            
        self.setPolygon(new_poly)

    # =========================================================================
    # EXPORTAÇÃO E IMPORTAÇÃO GEOMÉTRICA
    # =========================================================================
    def get_geometry(self) -> dict:
        rect = self.sceneBoundingRect()
        poly = self.polygon()
        pts = [{"x": poly.at(i).x(), "y": poly.at(i).y()} for i in range(poly.count())]
        
        return {
            "x": rect.x(),
            "y": rect.y(),
            "width": rect.width(),
            "height": rect.height(),
            "polygon": pts
        }

    def set_geometry(self, geom: dict):
        if geom and isinstance(geom, dict):
            self.setPos(geom.get("x", 0), geom.get("y", 0))
            target_w = geom.get("width", 300)
            target_h = geom.get("height", 450)

            if "polygon" in geom and geom["polygon"]:
                pts = geom["polygon"]
                poly = QtGui.QPolygonF([QtCore.QPointF(p["x"], p["y"]) for p in pts])
                
                bbox = poly.boundingRect()
                if bbox.width() > 0 and bbox.height() > 0:
                    scale_x = target_w / bbox.width()
                    scale_y = target_h / bbox.height()
                    if abs(scale_x - 1.0) > 0.01 or abs(scale_y - 1.0) > 0.01:
                        trans = QtGui.QTransform()
                        trans.scale(scale_x, scale_y)
                        poly = trans.map(poly)
                
                self.setPolygon(poly)
                self._normalize_polygon() # Recalcula a matriz
            else:
                poly = QtGui.QPolygonF([
                    QtCore.QPointF(0, 0),
                    QtCore.QPointF(target_w, 0),
                    QtCore.QPointF(target_w, target_h),
                    QtCore.QPointF(0, target_h)
                ])
                self.setPolygon(poly)
        else:
            self.setPos(0, 0)

    def get_next_clip_geometry(self) -> dict:
        rect = self.sceneBoundingRect()
        w = rect.width()
        h = rect.height()
        return {
            "x": rect.x() + (w * 0.10),
            "y": rect.y() + (h * 0.10),
            "width": w,
            "height": h,
            "polygon": []  
        }

    def set_replicate_state(self, state: bool):
        self.is_replicate_on = state

    # =========================================================================
    # LÓGICA DE DETECÇÃO DE ARESTAS
    # =========================================================================
    def _get_edge_at(self, pos: QtCore.QPointF):
        poly = self.polygon()
        count = poly.count()
        s = self.handle_size
        
        for i in range(count):
            p1 = poly.at(i)
            p2 = poly.at((i + 1) % count)
            
            is_horizontal = abs(p1.y() - p2.y()) < 0.1
            is_vertical = abs(p1.x() - p2.x()) < 0.1
            
            if is_horizontal:
                min_x, max_x = min(p1.x(), p2.x()), max(p1.x(), p2.x())
                if min_x - s <= pos.x() <= max_x + s:
                    if abs(pos.y() - p1.y()) <= s:
                        return i, 'H'
            elif is_vertical:
                min_y, max_y = min(p1.y(), p2.y()), max(p1.y(), p2.y())
                if min_y - s <= pos.y() <= max_y + s:
                    if abs(pos.x() - p1.x()) <= s:
                        return i, 'V'
        return None, None

    # =========================================================================
    # MENU DE CONTEXTO E CRIAÇÃO DO TOPO
    # =========================================================================
    def contextMenuEvent(self, event: QtWidgets.QGraphicsSceneContextMenuEvent):
        edge_idx, edge_type = self._get_edge_at(event.pos())
        menu = QtWidgets.QMenu()
        
        # Inicializa variáveis para fugir do UnboundLocalError
        action_add_topo = None
        action_join_edges = None # <--- Inicializa a nova ação
        action_copy = None
        action_mirror = None
        action_remove_deskew = None # <--- Inicializa a nova ação de remoção
        action_deskew = None        # <--- Garante que a variável exista em todos os fluxos
        action_replicate = None
        action_add_clip = None
        action_duplicate = None
        action_remove_clip = None
        action_bring_front = None
        action_send_back = None
        
        # ---> INÍCIO DA INSERÇÃO 1: INICIALIZAÇÃO
        action_flip_h = None
        action_flip_v = None
        action_rot_cw = None
        action_rot_ccw = None
        # ---> FIM DA INSERÇÃO 1

        if edge_idx is not None:
            poly = self.polygon()
            p1 = poly.at(edge_idx)
            p2 = poly.at((edge_idx + 1) % poly.count())
            
            # Calcula o tamanho da aresta clicada
            edge_length = math.hypot(p2.x() - p1.x(), p2.y() - p1.y())
            
            action_add_topo = menu.addAction("Criar Topo nesta Aresta")
            action_add_topo.setIcon(QtGui.QIcon.fromTheme("path-union"))
            
            # Se a aresta tiver 20px ou menos, oferece a opção de simplificação
            if edge_length <= 100:
                action_join_edges = menu.addAction("Unir arestas adjacentes (Simplificar)")
                action_join_edges.setIcon(QtGui.QIcon.fromTheme("format-justify-center"))
                
            menu.addSeparator()

        if not getattr(self, 'is_single_mode', False):
            action_copy = menu.addAction("Copiar Recorte do Lado Oposto")
            action_mirror = menu.addAction("Copiar Recorte do Lado Oposto (Espelhado)")
            menu.addSeparator() 
            
        # ---> INÍCIO DA SUBSTITUIÇÃO: OPÇÃO DE DESKEW MANUAL DINÂMICA
        if getattr(self, 'is_deskew_active', False):
            action_deskew = menu.addAction("Cancelar alinhamento manual")
            action_deskew.setIcon(QtGui.QIcon.fromTheme("process-stop"))
        elif getattr(self, 'has_deskew_points', False):
            action_remove_deskew = menu.addAction("Remover pontos de alinhamento manual")
            action_remove_deskew.setIcon(QtGui.QIcon.fromTheme("edit-delete"))
        else:
            action_deskew = menu.addAction("Iniciar alinhamento manual (Deskew de 4 pontos)")
            action_deskew.setIcon(QtGui.QIcon.fromTheme("transform-move"))
        menu.addSeparator()
        # ---> FIM DA SUBSTITUIÇÃO
        
        # ---> INÍCIO DA INSERÇÃO 2: OPÇÕES DE TRANSFORMAÇÃO NO MENU
        menu.addSeparator()
        action_flip_h = menu.addAction("Espelhar Horizontalmente")
        action_flip_h.setIcon(QtGui.QIcon.fromTheme("object-flip-horizontal"))
        
        action_flip_v = menu.addAction("Espelhar Verticalmente")
        action_flip_v.setIcon(QtGui.QIcon.fromTheme("object-flip-vertical"))
        
        action_rot_cw = menu.addAction("Girar 90° Horário")
        action_rot_cw.setIcon(QtGui.QIcon.fromTheme("object-rotate-right"))
        
        action_rot_ccw = menu.addAction("Girar 90° Anti-horário")
        action_rot_ccw.setIcon(QtGui.QIcon.fromTheme("object-rotate-left"))
        menu.addSeparator()
        # ---> FIM DA INSERÇÃO 2

        # Restaura todas as opções de redimensionamento
        menu_resize = menu.addMenu("Ajustar Tamanho do Recorte...")
        menu_resize.setIcon(QtGui.QIcon.fromTheme("transform-scale"))
        action_100_local = menu_resize.addAction("100% da Imagem")
        action_90_local = menu_resize.addAction("90% da Imagem")
        action_80_local = menu_resize.addAction("80% da Imagem")
        action_75_local = menu_resize.addAction("75% da Imagem")
        action_66_local = menu_resize.addAction("66% da Imagem")
        action_50_local = menu_resize.addAction("50% da Imagem")
        action_33_local = menu_resize.addAction("33% da Imagem")
        action_25_local = menu_resize.addAction("25% da Imagem")
        menu.addSeparator() 
        
        text_ratio = "Desabilitar Trava de Proporção" if self.keep_ratio else "Habilitar Trava de Proporção"
        action_ratio = menu.addAction(text_ratio)
        
        if not getattr(self, 'is_single_mode', False):
            text_replicate = "Desabilitar Replicação" if getattr(self, 'is_replicate_on', False) else "Habilitar Replicação"
            action_replicate = menu.addAction(text_replicate)
            
        action_duplicate = None # Declara para não dar UnboundLocalError
        action_reset_all = None # <--- DECLARAÇÃO DA AÇÃO
        
        if getattr(self, 'is_single_mode', False):
            menu.addSeparator()
            
            # Verifica a quantidade de vértices do vetor para alterar os rótulos dinamicamente
            num_vertices = self.polygon().count()
            is_quadro = (num_vertices <= 4)
            
            texto_duplicar = "Duplicar o quadro atual" if is_quadro else "Duplicar o polígono atual"
            texto_remover = "Remover este Quadro" if is_quadro else "Remover este Polígono"
            
            action_add_clip = menu.addAction("Criar um quadro novo (tamanho da imagem)")
            action_add_clip.setIcon(QtGui.QIcon.fromTheme("list-add"))
            
            action_duplicate = menu.addAction(texto_duplicar)
            action_duplicate.setIcon(QtGui.QIcon.fromTheme("edit-copy"))
            
            if getattr(self, 'is_child_clip', False):
                action_remove_clip = menu.addAction(texto_remover)
                action_remove_clip.setIcon(QtGui.QIcon.fromTheme("list-remove"))
                
            menu.addSeparator()
            action_reset_all = menu.addAction("Remover extras e resetar o quadro principal")
            action_reset_all.setIcon(QtGui.QIcon.fromTheme("edit-clear"))
                
        if self.scene() and len([item for item in self.scene().items() if isinstance(item, VidyaCropMarker)]) > 1:
            menu.addSeparator()
            action_bring_front = menu.addAction("Trazer para Frente")
            action_send_back = menu.addAction("Enviar para Trás")
           
        selected_action = menu.exec_(event.screenPos())
        
        if selected_action:
            if selected_action == action_add_topo:
                self._create_topo(edge_idx)
            elif selected_action == action_join_edges:     # <--- NOVA INTERCEPTAÇÃO
                self._join_adjacent_edges(edge_idx)        # <---
            elif selected_action == action_copy and self.copy_exact_callback: 
                self.copy_exact_callback()
            elif selected_action == action_mirror and self.copy_mirror_callback: 
                self.copy_mirror_callback()
            elif selected_action == action_ratio and self.toggle_ratio_callback: 
                self.toggle_ratio_callback()
            elif selected_action == action_replicate and self.toggle_replicate_callback: 
                self.toggle_replicate_callback()
            elif selected_action == action_100_local and self.resize_percent_callback:
                self.resize_percent_callback(self, 1.00)
            elif selected_action == action_90_local and self.resize_percent_callback:
                self.resize_percent_callback(self, 0.90)
            elif selected_action == action_80_local and self.resize_percent_callback:
                self.resize_percent_callback(self, 0.80)
            elif selected_action == action_75_local and self.resize_percent_callback:
                self.resize_percent_callback(self, 0.75)
            elif selected_action == action_66_local and self.resize_percent_callback:
                self.resize_percent_callback(self, 0.66)
            elif selected_action == action_50_local and self.resize_percent_callback:
                self.resize_percent_callback(self, 0.50)
            elif selected_action == action_33_local and self.resize_percent_callback:
                self.resize_percent_callback(self, 0.33)
            elif selected_action == action_25_local and self.resize_percent_callback:
                self.resize_percent_callback(self, 0.25)
            elif selected_action == action_add_clip and self.add_clip_callback:
                self.add_clip_callback()
            elif selected_action == action_duplicate and self.duplicate_callback:
                self.duplicate_callback(self)
            elif selected_action == action_remove_clip and self.remove_clip_callback:
                self.remove_clip_callback(self)
            elif action_reset_all and selected_action == action_reset_all and self.reset_all_clips_callback:
                self.reset_all_clips_callback(self)
            elif action_bring_front and selected_action == action_bring_front:
                self._bring_to_front()
            elif action_send_back and selected_action == action_send_back:
                self._send_to_back()
            elif action_remove_deskew and selected_action == action_remove_deskew:
                if self.remove_manual_deskew_callback:
                    self.remove_manual_deskew_callback(self)
            elif action_deskew and selected_action == action_deskew:
                if getattr(self, 'is_deskew_active', False):
                    if self.cancel_manual_deskew_callback:
                        self.cancel_manual_deskew_callback(self)
                else:
                    if self.start_manual_deskew_callback:
                        self.start_manual_deskew_callback(self)
            elif selected_action == action_flip_h:
                self._apply_transformation(flip_h=True)
            elif selected_action == action_flip_v:
                self._apply_transformation(flip_v=True)
            elif selected_action == action_rot_cw:
                self._apply_transformation(angle=90)
            elif selected_action == action_rot_ccw:
                self._apply_transformation(angle=-90)
                
        event.accept()

    def _create_topo(self, edge_idx):
        poly = self.polygon()
        pts = [poly.at(i) for i in range(poly.count())]
        
        p1 = pts[edge_idx]
        next_idx = (edge_idx + 1) % len(pts)
        p2 = pts[next_idx]
        
        dx = p2.x() - p1.x()
        dy = p2.y() - p1.y()
        L = math.hypot(dx, dy)
        
        if L < 15: return
        
        if self.save_undo_state_callback:             # <--- ADICIONE
            self.save_undo_state_callback(self)       # <--- ADICIONE
            
        ux = dx / L
        uy = dy / L
        
        nx = uy
        ny = -ux
        h = L * 0.33
        
        A = QtCore.QPointF(p1.x() + ux * (L / 3), p1.y() + uy * (L / 3))
        B = QtCore.QPointF(A.x() + nx * h, A.y() + ny * h)
        C = QtCore.QPointF(p1.x() + ux * (2 * L / 3) + nx * h, p1.y() + uy * (2 * L / 3) + ny * h)
        D = QtCore.QPointF(p1.x() + ux * (2 * L / 3), p1.y() + uy * (2 * L / 3))
        
        if next_idx == 0:
            pts.extend([A, B, C, D])
        else:
            pts = pts[:next_idx] + [A, B, C, D] + pts[next_idx:]
            
        self.setPolygon(QtGui.QPolygonF(pts))
        self._normalize_polygon() # Recalcula a matriz após adicionar os vértices
        
        if self.sync_callback:
            self.sync_callback()
    
    def _clean_polygon(self, pts):
        """Varre o polígono iterativamente removendo pontos sobrepostos, colineares ou 'spikes'."""
        changed = True
        # Executa até que o polígono esteja limpo, mas nunca o reduz a menos de 4 pontas (quadro base)
        while changed and len(pts) > 4:
            changed = False
            n = len(pts)
            for i in range(n):
                p_prev = pts[(i - 1) % n]
                p_curr = pts[i]
                p_next = pts[(i + 1) % n]
                
                # É colinear (ou spike) se os 3 pontos compartilharem o mesmo eixo X ou o mesmo eixo Y
                is_collinear = (abs(p_prev.x() - p_curr.x()) < 0.1 and abs(p_curr.x() - p_next.x()) < 0.1) or \
                               (abs(p_prev.y() - p_curr.y()) < 0.1 and abs(p_curr.y() - p_next.y()) < 0.1)
                
                # É duplicata se o ponto atual for exatamente igual ao próximo
                is_duplicate = abs(p_curr.x() - p_next.x()) < 0.1 and abs(p_curr.y() - p_next.y()) < 0.1
                
                if is_collinear or is_duplicate:
                    pts.pop(i) # Remove o vértice inútil
                    changed = True
                    break # Quebra o for e reinicia a verificação matemática com o novo tamanho
        return pts

    def _join_adjacent_edges(self, edge_idx):
        """Achata uma aresta curta projetando o segmento adjacente menor sobre o maior."""
        poly = self.polygon()
        pts = [poly.at(i) for i in range(poly.count())]
        n = len(pts)
        
        p1 = pts[edge_idx]
        p2 = pts[(edge_idx + 1) % n]
        
        is_horizontal = abs(p1.y() - p2.y()) < 0.1
        
        # Aresta anterior: de p_prev a p1
        prev_idx = (edge_idx - 1) % n
        p_prev = pts[prev_idx]
        len_prev = math.hypot(p1.x() - p_prev.x(), p1.y() - p_prev.y())
        
        # Aresta posterior: de p2 a p_next
        next_idx = (edge_idx + 2) % n
        p_next = pts[next_idx]
        len_next = math.hypot(p_next.x() - p2.x(), p_next.y() - p2.y())
        
        # Estratégia inteligente: mover a aresta mais curta em direção à mais longa
        move_next = len_prev >= len_next
        
        if self.save_undo_state_callback:             # <--- ADICIONE
            self.save_undo_state_callback(self)       # <--- ADICIONE
        
        if is_horizontal:
            # Aresta clicada é Horizontal. As vizinhas são Verticais. Equaliza-se o eixo X.
            if move_next:
                pts[(edge_idx + 1) % n].setX(p1.x())
                pts[(edge_idx + 2) % n].setX(p1.x())
            else:
                pts[edge_idx].setX(p2.x())
                pts[(edge_idx - 1) % n].setX(p2.x())
        else:
            # Aresta clicada é Vertical. As vizinhas são Horizontais. Equaliza-se o eixo Y.
            if move_next:
                pts[(edge_idx + 1) % n].setY(p1.y())
                pts[(edge_idx + 2) % n].setY(p1.y())
            else:
                pts[edge_idx].setY(p2.y())
                pts[(edge_idx - 1) % n].setY(p2.y())
                
        # Limpa as sobras matemáticas
        clean_pts = self._clean_polygon(pts)
        
        # Aplica o novo polígono simplificado
        if len(clean_pts) >= 4:
            self.setPolygon(QtGui.QPolygonF(clean_pts))
            self._normalize_polygon()
            if self.sync_callback:
                self.sync_callback()

    def _apply_transformation(self, flip_h=False, flip_v=False, angle=0):
        """Aplica rotações ou espelhamentos relativos ao centro do bounding box."""
        # 1. Tira a "foto" instantânea do estado anterior para permitir Ctrl+Z
        if self.save_undo_state_callback:
            self.save_undo_state_callback(self)

        poly = self.polygon()
        rect = poly.boundingRect()
        
        # Encontra o centro geométrico exato do quadro
        cx = rect.center().x()
        cy = rect.center().y()

        # Prepara a matriz de transformação do PyQt
        trans = QtGui.QTransform()
        
        # Move o eixo para o centro do quadro
        trans.translate(cx, cy)

        # Aplica as manipulações
        if flip_h:
            trans.scale(-1, 1)
        if flip_v:
            trans.scale(1, -1)
        if angle != 0:
            trans.rotate(angle)

        # Retorna o eixo para a posição original
        trans.translate(-cx, -cy)

        # Aplica a matemática sobre todos os vértices e normaliza a âncora
        new_poly = trans.map(poly)
        self.setPolygon(new_poly)
        self._normalize_polygon() 

        # Sincroniza com o lado direito se a flag de replicação estiver ativa
        if self.sync_callback:
            self.sync_callback()
                            
    # =========================================================================
    # LÓGICA DE PROPORÇÃO E EMPILHAMENTO
    # =========================================================================
    def set_keep_ratio(self, keep: bool):
        self.keep_ratio = keep
        if keep and self.image_ratio > 0:
            self._snap_to_ratio()

    def set_image_ratio(self, ratio: float):
        self.image_ratio = ratio
        if self.keep_ratio:
            self._snap_to_ratio()

    def _snap_to_ratio(self):
        if self.image_ratio <= 0: return
        poly = self.polygon()
        rect = poly.boundingRect()
        if rect.height() <= 0: return
        
        w = rect.width()
        h = w / self.image_ratio
        
        scale_y = h / rect.height()
        trans = QtGui.QTransform()
        trans.scale(1.0, scale_y)
        self.setPolygon(trans.map(poly))

    def _bring_to_front(self):
        if not self.scene(): return
        max_z = max([item.zValue() for item in self.scene().items() if isinstance(item, VidyaCropMarker)] + [0.0])
        self.setZValue(max_z + 1.0)

    def _send_to_back(self):
        if not self.scene(): return
        markers = [item for item in self.scene().items() if isinstance(item, VidyaCropMarker) and item != self]
        if not markers: return
        self.setZValue(0.0)
        markers.sort(key=lambda m: m.zValue())
        for i, m in enumerate(markers):
            m.setZValue(float(i + 1))

    # =========================================================================
    # DETECÇÃO E ARRASTE FÍSICO DO MOUSE
    # =========================================================================
    def hoverMoveEvent(self, event):
        if self.resizing: return
        edge_idx, edge_type = self._get_edge_at(event.pos())
        if edge_type == 'H': self.setCursor(QtCore.Qt.SizeVerCursor)
        elif edge_type == 'V': self.setCursor(QtCore.Qt.SizeHorCursor)
        else: self.setCursor(QtCore.Qt.SizeAllCursor)
        super().hoverMoveEvent(event)

    def hoverLeaveEvent(self, event):
        self.setCursor(QtCore.Qt.ArrowCursor)
        super().hoverLeaveEvent(event)

    def itemChange(self, change, value):
        if change == QtWidgets.QGraphicsItem.ItemPositionHasChanged:
            if self.sync_callback:
                self.sync_callback()
        return super().itemChange(change, value)

    def mousePressEvent(self, event):
        self._bring_to_front()
        
        # 1. Tira a FOTO RASCUNHO sempre que o rato for pressionado (Aresta ou Meio)
        if self.save_undo_state_callback:
            self.save_undo_state_callback(self, is_draft=True)
            
        edge_idx, edge_type = self._get_edge_at(event.pos())
        if edge_idx is not None:
            self.resizing = True
            self.resizing_edge = edge_idx
            self.edge_type = edge_type
            self._initial_pos = event.pos()
            self._initial_polygon = self.polygon()
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.resizing:
            poly = self.polygon()
            pts = [poly.at(i) for i in range(poly.count())]
            
            p1 = pts[self.resizing_edge]
            next_idx = (self.resizing_edge + 1) % len(pts)
            p2 = pts[next_idx]
            
            if getattr(self, 'keep_ratio', False) and getattr(self, 'image_ratio', 0) > 0:
                orig_poly = self._initial_polygon
                orig_rect = orig_poly.boundingRect()
                delta_x = event.pos().x() - self._initial_pos.x()
                delta_y = event.pos().y() - self._initial_pos.y()
                
                scale = 1.0
                anchor = QtCore.QPointF(0, 0)
                
                if self.edge_type == 'H':
                    if p1.y() <= orig_rect.center().y():
                        new_h = orig_rect.height() - delta_y
                        scale = new_h / orig_rect.height() if orig_rect.height() > 0 else 1.0
                        anchor = QtCore.QPointF(orig_rect.left(), orig_rect.bottom())
                    else:
                        new_h = orig_rect.height() + delta_y
                        scale = new_h / orig_rect.height() if orig_rect.height() > 0 else 1.0
                        anchor = QtCore.QPointF(orig_rect.left(), orig_rect.top())
                else:
                    if p1.x() <= orig_rect.center().x():
                        new_w = orig_rect.width() - delta_x
                        scale = new_w / orig_rect.width() if orig_rect.width() > 0 else 1.0
                        anchor = QtCore.QPointF(orig_rect.right(), orig_rect.top())
                    else:
                        new_w = orig_rect.width() + delta_x
                        scale = new_w / orig_rect.width() if orig_rect.width() > 0 else 1.0
                        anchor = QtCore.QPointF(orig_rect.left(), orig_rect.top())
                        
                if scale < 0.1: scale = 0.1
                
                new_pts = []
                for pt in [orig_poly.at(i) for i in range(orig_poly.count())]:
                    nx = anchor.x() + (pt.x() - anchor.x()) * scale
                    ny = anchor.y() + (pt.y() - anchor.y()) * scale
                    new_pts.append(QtCore.QPointF(nx, ny))
                self.setPolygon(QtGui.QPolygonF(new_pts))
                
            else:
                if self.edge_type == 'H':
                    new_y = event.pos().y()
                    pts[self.resizing_edge].setY(new_y)
                    pts[next_idx].setY(new_y)
                else:
                    new_x = event.pos().x()
                    pts[self.resizing_edge].setX(new_x)
                    pts[next_idx].setX(new_x)
                self.setPolygon(QtGui.QPolygonF(pts))

            if self.sync_callback:
                self.sync_callback()
                
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.resizing:
            self.resizing = False
            self.resizing_edge = None
            self.edge_type = None
            self._normalize_polygon() # Recalcula a matriz e ancora quando termina de puxar
            
            if self.sync_callback:
                self.sync_callback()
            event.accept()
        else:
            super().mouseReleaseEvent(event)
            
        # 2. Ao soltar o clique, AVALIA O RASCUNHO. Se houve mudança, oficializa.
        if self.save_undo_state_callback:
            self.save_undo_state_callback(self, commit_draft=True)
