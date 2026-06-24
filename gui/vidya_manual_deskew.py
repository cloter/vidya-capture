# Arquivo: gui/vidya_manual_deskew.py

from PyQt5 import QtWidgets, QtCore, QtGui

class DeskewNode(QtWidgets.QGraphicsEllipseItem):
    """Um nó individual (canto) do Deskew Manual que pode ser arrastado."""
    def __init__(self, index, parent):
        # Cria um círculo centralizado no clique
        super().__init__(-10, -10, 20, 20, parent)
        self.index = index
        self.setFlag(QtWidgets.QGraphicsItem.ItemIsMovable)
        self.setFlag(QtWidgets.QGraphicsItem.ItemSendsGeometryChanges)
        
        # Visual: Amarelo chamativo com borda escura para alto contraste
        self.setBrush(QtGui.QBrush(QtGui.QColor(241, 196, 15))) 
        self.setPen(QtGui.QPen(QtCore.Qt.black, 2))
        self.setZValue(10) # Fica acima das linhas
        self.setCursor(QtCore.Qt.PointingHandCursor)

    def itemChange(self, change, value):
        if change == QtWidgets.QGraphicsItem.ItemPositionHasChanged:
            self.parentItem().update_node_position(self.index, value)
        return super().itemChange(change, value)
        
    # NOVA INSERÇÃO: Engatilha o salvamento no JSON apenas ao soltar o arraste
    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        self.parentItem().geometry_changed.emit()

class VidyaManualDeskewMarker(QtWidgets.QGraphicsObject):
    """Gerenciador do quadrilátero de Deskew Manual (4 pontos)."""
    
    # Sinal emitido quando a posição de qualquer nó muda
    geometry_changed = QtCore.pyqtSignal() 
    
    def __init__(self, opacity=10):
        super().__init__()
        self.setZValue(5) # Acima da imagem, abaixo do marcador de Crop principal
        self.nodes = []
        self.points = []
        
        # Visual da linha: Amarela tracejada
        alpha = int(255 * (opacity / 10.0))
        self._pen = QtGui.QPen(QtGui.QColor(241, 196, 15, alpha), 3, QtCore.Qt.DashLine)

    def boundingRect(self):
        if not self.points: return QtCore.QRectF()
        poly = QtGui.QPolygonF(self.points)
        # Borda extra para não cortar o desenho dos nós nas extremidades
        return poly.boundingRect().adjusted(-20, -20, 20, 20)

    def paint(self, painter, option, widget=None):
        if not self.points: return
        painter.setPen(self._pen)
        painter.setBrush(QtCore.Qt.NoBrush)
        
        poly = QtGui.QPolygonF(self.points)
        
        # Desenha linha aberta se estiver na fase de marcação (1, 2 ou 3 pontos)
        if len(self.points) < 4:
            painter.drawPolyline(poly)
        else:
            painter.drawPolygon(poly)

    def add_point(self, pos: QtCore.QPointF) -> bool:
        """Adiciona um novo ponto na cena. Retorna True se atingiu os 4 pontos."""
        if len(self.points) < 4:
            self.points.append(pos)
            node = DeskewNode(len(self.points)-1, self)
            node.setPos(pos)
            self.nodes.append(node)
            self.prepareGeometryChange()
            
            if len(self.points) == 4:
                return True
        return False

    def update_node_position(self, index, pos):
        """Disparado pelo DeskewNode quando ele é arrastado com o mouse."""
        if 0 <= index < len(self.points):
            self.points[index] = pos
            self.prepareGeometryChange()
            # REMOVIDO: self.geometry_changed.emit() -> O disco rígido agradece!

    def set_geometry(self, points_list: list):
        """Carrega do JSON: [{'x': 10, 'y': 10}, ...]"""
        self.clear()
        for i, pt in enumerate(points_list):
            if i >= 4: break
            pos = QtCore.QPointF(pt['x'], pt['y'])
            self.points.append(pos)
            node = DeskewNode(i, self)
            node.setPos(pos)
            self.nodes.append(node)
        self.prepareGeometryChange()

    def get_geometry(self) -> list:
        """Exporta para o JSON: [{'x': 10, 'y': 10}, ...]"""
        if len(self.points) < 4: return []
        return [{"x": int(pt.x()), "y": int(pt.y())} for pt in self.points]

    def clear(self):
        """Remove os nós e apaga a geometria visual."""
        for node in self.nodes:
            if self.scene():
                self.scene().removeItem(node)
        self.nodes = []
        self.points = []
        self.prepareGeometryChange()
