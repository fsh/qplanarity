#!/usr/bin/env python3

from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtWidgets import *
import sys
import random as rnd
import logging
import itertools
import math
from pathlib import Path
import pickle

# These two are only used for Graph3 generation.
import numpy as np
from scipy.spatial import Delaunay

logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(filename)s %(funcName)s:%(lineno)s %(levelname)s %(message)s")
log = logging.getLogger('main')

PERF_DEBUG = False

from .qtutils import FSettings, FLayout, ColorButton


class PlanarityApp(QApplication):
  def __init__(self, *args, **kwargs):
    super().__init__(*args, **kwargs)
    self.setOrganizationName('qplanarity')
    self.setApplicationName('qplanarity')

app = PlanarityApp(sys.argv)

defaults = {
  'node': {
    'color': {
      'normal': QColor('#2244bb'),
      'hover': QColor('#5b9fff'),
      'solved': QColor('#e7d08b'),
    },
    'size': 24,
  }
}

S = FSettings(appname='qplanarity')
S.installOptions(defaults)

config_path = Path(QStandardPaths.writableLocation(QStandardPaths.AppConfigLocation))

if not config_path.exists():
  config_path.mkdir(parents=True)

state_file = config_path / 'qplanarity.state'


blue_brush = QBrush(Qt.blue, Qt.SolidPattern)
red_brush = QBrush(Qt.red, Qt.SolidPattern)
magenta_brush = QBrush(Qt.magenta, Qt.SolidPattern)
black_pen = QPen(Qt.black)
thick_pen = QPen(Qt.black)
gray_pen = QPen(Qt.gray)
for pen in [black_pen, thick_pen, gray_pen]:
  pen.setCosmetic(True)
thick_pen.setWidthF(4.0)
gray_pen.setWidthF(2.0)
black_pen.setWidthF(2.0)


import dataclasses

@dataclasses.dataclass(frozen=True)
class edge():
  """An edge acts sort of like a two-element tuple that sorts its arguments, so
  `edge(x,y) == edge(y,x)`.

  Invariant: `edge.a <= edge.b`.

  `edge1 & edge2` returns the common vertex between two edges or None if the
  edges are not contiguous.

  """
  a: int
  b: int

  def __init__(self, a: int, b: int):
    if a > b:
      b,a = a,b
    object.__setattr__(self, 'a', a)
    object.__setattr__(self, 'b', b)

  def __contains__(self, x):
    return x == self.a or x == self.b

  def __iter__(self):
    return iter(dataclasses.astuple(self))

  def __and__(self, other):
    if self.a in other:
      return self.a
    if self.b in other:
      return self.b
    return None

@dataclasses.dataclass
class graph():
  edges: set = dataclasses.field(default_factory=set)
  n2e: list = dataclasses.field(default_factory=list)

  def num_edges(self):
    return len(self.e)
  def num_nodes(self):
    return len(self.n2e)

  def degree(self, n):
    return len(self.n2e[n])

  def add_edge(self, e):
    if e in self.edges:
      return

    # Extend n2e list.
    if e.b >= self.num_nodes():
      self.n2e.extend(set() for _ in range(self.num_nodes(), e.b + 1))

    self.edges.add(e)
    self.n2e[e.a].add(e)
    self.n2e[e.b].add(e)



class RandomGraph2(object):
  """Random Planar Graph Mk2.

  Algorithm works as follows. At each step we attach a number of triangles to
  the outside of the graph along randomly chosen edges. Then we form a new face
  of N+1 edges by picking N edges that run along the outside and adding an edge
  between their non-shared endpoints. These two steps are repeated until
  certain criteria are met.

  Parameters:

  """
  def __init__(self, node_limit=30, outside_limit=None):
    self.outside_edges = set([(0,1),(1,2),(0,2)])
    self.node_idx = 3
    self.limit = node_limit
    if outside_limit is None:
      # Try to limit edges on the outside to some percentage of the amount of nodes in the graph? Not sure what this parameter should be.
      outside_limit = 5 + int(node_limit*0.5 + 0.5)

    self.denseness_parameter = 0.2 # [0-1) lower number will have greater chance of generating clusters of highly connected nodes
    self.sparseness_parameter = 0.7 # [0-1) ]higher number will generate larger 'holes' or 'lakes' in the graph (too close to 1.0 might stall the algo)

    log.info("Generating random graph of %d nodes with ~%d outside edges", node_limit, outside_limit)
    self.edges = set()
    while self.node_idx < node_limit:
      self.addLines()
      while len(self.outside_edges) > outside_limit:
        # Randomly skip this step early in the process.
        if rnd.random() < 1 / (1 + self.node_idx):
          break
        self.removeLines()
    self.edges.update(self.outside_edges)
    log.info("Graph generated: %d nodes and %d internal + %d outside = %d edges",
             self.node_idx, len(self.edges), len(self.outside_edges), len(self.edges) + len(self.outside_edges))

  def addLines(self):
    """Adds random outside lines. Increases node count."""
    ab = rnd.choice(tuple(self.outside_edges))
    pivot = rnd.choice(ab)
    base = ab[0]+ab[1]-pivot

    # XXX: some hack to prevent too dense links.
    cnt = sum(1 for xy in self.edges if pivot in xy)
    if cnt * rnd.random() > 2.0:
      return self.addLines()

    log.debug("(nodecnt: %d) Adding edges from base %d and pivot %d", self.node_idx, base, pivot)
    while True:
      self.outside_edges.remove(ab)
      self.edges.add(ab)
      self.outside_edges.add((base,self.node_idx))
      self.outside_edges.add((pivot,self.node_idx))
      base = self.node_idx
      ab = (pivot,self.node_idx)
      self.node_idx += 1
      if rnd.random() > self.denseness_parameter or self.node_idx >= self.limit:
        break
  def removeLines(self):
    """Removes random outside lines. Does not increase node count."""
    if len(self.outside_edges) < 5:
      return
    ab = rnd.choice(tuple(self.outside_edges))
    self.outside_edges.remove(ab)
    self.edges.add(ab)
    log.debug("(nodecnt: %d) Removing edges, starting with endpoints %s", self.node_idx, str(ab))
    endpoints = ab
    while True:
      other = None
      for xy in self.outside_edges:
        log.debug("end=%s xy=%s", str(endpoints), str(xy))
        if xy == endpoints:
          # We've gone too far and curled all the way around the outside! Let's retry.
          assert False, "sanity failed, this should never occur"
        if xy[0] in endpoints or xy[1] in endpoints:
          # We found a line connected to one of the endpoints.
          other = xy
          break
      assert other is not None, "failed to find other outside line" # Sanity check.
      self.outside_edges.remove(xy)
      self.edges.add(xy)
      if xy[0] in endpoints:
        xy = (sum(endpoints) - xy[0], xy[1])
      else:
        xy = (sum(endpoints) - xy[1], xy[0])
      endpoints = (min(xy), max(xy))
      log.debug("removing %s, new endpoints=%s", str(xy), str(endpoints))
      if rnd.random() > self.sparseness_parameter or len(self.outside_edges) < 5:
        break
    self.outside_edges.add(endpoints)

  def getEdges(self):
    n2e = [list() for i in range(self.node_idx)]
    for (a,b) in self.edges:
      n2e[a].append((a,b))
      n2e[b].append((a,b))
    return (self.edges, n2e)


class RandomGraph3():
  """Generates a random planar graph by calculating a Delaunay triangulation on a
  random set of points in the unit disc and then removing random edges.

  """

  def __init__(self, n):
    self.n2e = []
    self.edges = set()
    self.discard_chance = 0.33
    self.banned = set() # Banned (discarded) edges.
    self.init(n)

  def edge_count(self, v):
    return len(self.n2e[v])

  def add_edge(self, a, b):
    if (a,b) in self.edges or (a,b) in self.banned:
      return

    # Extend n2e list.
    for _ in range(len(self.n2e), b+1):
      self.n2e.append([])

    if self.edge_count(a) >= 2 and self.edge_count(b) >= 2 and rnd.random() < self.discard_chance:
      log.info(f"Discarding edge: ({a},{b})")
      self.banned.add((a,b))
      return

    self.edges.add((a,b))
    self.n2e[a].append((a,b))
    self.n2e[b].append((a,b))


  def init(self, n):
    self._solution = random_disc_points(n)
    delaunay = Delaunay(self._solution)
    for pts in delaunay.simplices:
      # Sort points & add edges.
      a, c = min(pts), max(pts)
      b = sum(pts) - a - c
      self.add_edge(a,b)
      self.add_edge(a,c)
      self.add_edge(b,c)

    log.info(f"Generated Delaunay graph w/ {len(self.edges)} edges and {len(self.n2e)} nodes")

  def getEdges(self):
    return self.edges, self.n2e


def random_disc_points(n):
  r, t = np.random.random((2,n))
  r = np.sqrt(r)
  t *= math.tau
  return np.stack([r * np.cos(t), r * np.sin(t)], axis=-1)


class Node(QGraphicsEllipseItem):
  def __init__(self, idx, *args):
    super().__init__(-12.0, -12.0, 24.0, 24.0, *args)
    self.idx = idx
    self.setBrush(blue_brush)
    self.setAcceptHoverEvents(True)
    self.setZValue(1.0)
    self.setFlags(QGraphicsItem.ItemIgnoresTransformations
                  | QGraphicsItem.ItemIsSelectable)
    self._hover = False
    self._solved = False

  def hoverEnterEvent(self, evt):
    log.debug("(%d) Enter hover", self.idx)
    self.scene().hover(self, True)
  
  def hoverLeaveEvent(self, evt):
    log.debug("(%d) Leave hover", self.idx)
    self.scene().hover(self, False)

  def mousePressEvent(self, evt):
    if evt.button() == Qt.RightButton:
      self.scene().gravity(self)
    else:
      self.scene().drag_start(self)
  
  def mouseMoveEvent(self, evt):
    self.scene().drag_move(self, evt.scenePos())

  def mouseReleaseEvent(self, evt):
    self.scene().drag_stop(self)

  def updateBrushes(self):
    if not (scene := self.scene()):
      return
    if self._hover:
      self.setBrush(scene._brush_hover)
    elif self._solved:
      self.setBrush(scene._brush_solved)
    else:
      self.setBrush(scene._brush_normal)
    
    self.setRect(scene._node_rect)
    
  def setSolved(self, flag):
    self._solved = flag
    self.updateBrushes()


def random_circle_points(n):
  # # Find a number close to the square root of n that is coprime with n and use
  # # linear congruence.
  # a = int(math.sqrt(n))
  # while math.gcd(a,n) > 1:
  #   a += 1
  # for i in range(n):
  #   ri = (a*i + 0xbabe) % n
  #   yield 200.0 * QPointF(math.cos(2*math.pi*ri/n),
  #                         math.sin(2*math.pi*ri/n))

  # Do it the simple way instead.
  pts = [200.0 * QPointF(math.cos(i*math.tau/n),
                         math.sin(i*math.tau/n)) for i in range(n)]
  rnd.shuffle(pts)
  return pts



class LineColl():
  def __init__(self, lines):
    self.lines = dict(lines)

    self.free = set()
    check = set(self.lines.keys())
    left = set(self.lines.keys())
    while check:
      ab = check.pop()
      left.remove(ab)
      thisline = self.lines[ab]
      dirty = set()
      for xy in left:
        if xy[0] in ab or xy[1] in ab:
          continue
        typ, _ = thisline.intersects(self.lines[xy])
        if typ == QLineF.BoundedIntersection:
          dirty.add(xy)
      if not dirty:
        self.free.add(ab)
      else:
        check -= dirty

  def is_gray(self, ab):
    line1 = self.lines[ab]
    for xy, line2 in self.lines.items():
      if xy[0] in ab or xy[1] in ab:
        continue
      typ, _ = line1.intersects(line2)
      if typ == QLineF.BoundedIntersection:
        return True
    return False
    
  def move_begin(self, lines):
    self.tmp_lines = lines
    self.tmp_truegray = set()
    self.tmp_gray = self.calc_gray()

  def move_update(self, lines):
    self.tmp_lines = lines
    self.lines.update(lines)
    now_gray = self.calc_gray()

    # new gray: for sure
    new_gray = now_gray - self.tmp_gray

    # now free lines: need to check if they were gray before or not
    
    new_black = self.tmp_gray - now_gray
    self.tmp_truegray.update(xy for xy in new_black if xy not in self.tmp_truegray and self.is_gray(xy))
    new_black -= self.tmp_truegray

    self.tmp_gray = now_gray

    self.free -= new_gray
    self.free |= new_black
    return new_gray, new_black

  def move_stop(self):
    for ab in self.tmp_lines.keys():
      if self.is_gray(ab):
        self.free.discard(ab)
      else:
        self.free.add(ab)

  def calc_gray(self):
    "Finds the lines now intersecting tmp_lines"
    gray = set()
    for xy, ln2 in self.lines.items():
      x,y = xy
      for ab, ln1 in self.tmp_lines.items():
        if x in ab or y in ab:
          continue
        typ, _ = ln1.intersects(ln2)
        if typ == QLineF.BoundedIntersection:
          gray.add(xy)
          break
    return gray

    



class Scene(QGraphicsScene):
  victory = pyqtSignal()
  progress = pyqtSignal(int,int)
  refit = pyqtSignal()

  def __init__(self, settings, *args):
    super().__init__(*args)
    self.nodes = []
    self.lines = dict()
    self.node2lines = dict()
    self.z_count = 1.0
    
    self.S = settings
    self.S['node'].onChange.connect(self.updateBrushes)
    self.updateBrushes()
    self._grp = None

  def updateBrushes(self):
    self._brush_normal = QBrush(self.S['node/color/normal'].get(), Qt.SolidPattern)
    self._brush_hover = QBrush(self.S['node/color/hover'].get(), Qt.SolidPattern)
    self._brush_solved = QBrush(self.S['node/color/solved'].get(), Qt.SolidPattern)
    radius = float(self.S['node/size'].get())
    self._node_rect = QRectF(-radius, -radius, radius*2, radius*2)
    for n in self.nodes:
      n.updateBrushes()

  def init(self, edges, node2lines, pt_list):
    self.clear()
    n = len(node2lines)

    self.nodes = []
    for i, pt in enumerate(pt_list):
      obj = Node(i)
      obj.setPos(pt)
      self.nodes.append(obj)

    linedict = {(a,b): QLineF(pt_list[a], pt_list[b]) for a,b in edges}

    self.line_coll = LineColl(linedict)

    self.lines = lines = dict()
    for ab, ln in linedict.items():
      lines[ab] = self.addLine(ln, self.line_pen(ab))

    # Now add the nodes.
    for i in range(n):
      self.addItem(self.nodes[i])

    self.node2lines = node2lines
    self.z_count = 1.0
    self._grp = None

  def postInit(self):
    list(self.find_solved())

    self.updateBrushes()
    if len(self.line_coll.free) == len(self.lines):
      self.victory.emit()

  def neighbors(self, node):
    for (a,b) in self.node2lines[node.idx]:
      yield self.nodes[a+b-node.idx]

  def gravity(self, node):
    for other in self.neighbors(node):
      z = other.pos() - node.pos()
      z *= 0.75
      if QPointF.dotProduct(z, z) < 50.0**2:
        # Don't pull nodes that are already close
        continue

      self.drag_start(other)

      self.drag_move(other, z + node.pos())
      self.drag_stop(other)

  def node_lines(self, idx):
    return {
      ab: QLineF(self.nodes[ab[0]].pos(), self.nodes[ab[1]].pos())
      for ab in self.node2lines[idx] }

  def line_pen(self, ab):
    return black_pen if ab in self.line_coll.free else gray_pen

  def find_solved(self):
    for i,lines in enumerate(self.node2lines):
      solved = False
      for ab in lines:
        if ab not in self.line_coll.free:
          break
      else:
        solved = True
      if self.nodes[i]._solved != solved:
        self.nodes[i]._solved = solved
        yield i

  def drag_start(self, node):
    sel = self.selectedItems()
    if node not in sel:
      self.clearSelection()
      lc = self.node_lines(node.idx)
      self.line_coll.move_begin(lc)
    else:
      self._grp = sel
      self._grppos = node.pos()

  def drag_move(self, node, pos):
    if self._grp:
      delta = pos - node.pos()
      for n in self._grp:
        n.setPos(n.pos() + delta)
      return

    node.setPos(pos)

    lc = self.node_lines(node.idx)
    for ab, ln in lc.items():
      self.lines[ab].setLine(ln)

    new_gray, new_free = self.line_coll.move_update(lc)

    for ab in new_free:
      self.lines[ab].setPen(black_pen)
    for ab in new_gray:
      self.lines[ab].setPen(gray_pen)

    if new_free or new_gray:
      for i in self.find_solved():
        self.nodes[i].updateBrushes()

    self.progress.emit(len(self.line_coll.free), len(self.lines))

  def update_selection_drag(self, delta):
    self.clearSelection()
    _grp = self._grp
    self._grp = None

    for n in _grp:
      n.setPos(n.pos() + delta)

    for n in _grp:
      self.drag_start(n)
      self.drag_move(n, n.pos() - delta)
      self.drag_stop(n)

      for ab in self.node2lines[n.idx]:
        line = self.lines[ab]
        line.setPen(self.line_pen(ab))


  def drag_stop(self, node):
    if self._grp:
      self.update_selection_drag(self._grppos - node.pos())
      return

    self.line_coll.move_stop()
    for i in self.find_solved():
      self.nodes[i].updateBrushes()

    self.checkVictory()

  def hover(self, node, onoff):
    self.z_count += 0.01
    others = self.node2lines[node.idx]
    for ab in others:
      line = self.lines[ab]
      if onoff:
        line.setPen(thick_pen)
      else:
        line.setPen(self.line_pen(ab))

    node._hover = onoff
    node.updateBrushes()
    for other in self.neighbors(node):
      other._hover = onoff
      other.setZValue(self.z_count)
      other.updateBrushes()

  def checkVictory(self):
    self.refit.emit()
    if len(self.line_coll.free) == len(self.lines):
      self.victory.emit()




class View(QGraphicsView):
  def __init__(self, scene, act_resize, *args):
    super().__init__(*args)
    self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    self.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)

    self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
    #self.setResizeAnchor(QGraphicsView.AnchorUnderMouse)
    
    self.setScene(scene)
    scene.refit.connect(lambda: self.resizeEvent(None), Qt.QueuedConnection)
    self.act_resize = act_resize

    self.setDragMode(QGraphicsView.RubberBandDrag)

  def resizeEvent(self, evt):
    if not self.act_resize.isChecked():
      return
    margins = QMarginsF(30.0, 30.0, 30.0, 30.0)
    ib = self.scene().itemsBoundingRect()
    #print(self.scene().sceneRect())
    #print("ib", ib, "YES" if evt is None else "NO")
    self.scene().setSceneRect(ib.marginsAdded(margins * 100))
    #print("scenerect", self.scene().sceneRect())
    self.fitInView(ib.marginsAdded(margins), Qt.KeepAspectRatio)


  def mousePressEvent(self, evt):
    if evt.button() == Qt.RightButton:
      self.setDragMode(QGraphicsView.ScrollHandDrag)
      super().mousePressEvent(evt)
      if evt.isAccepted():
        return
      fake = QMouseEvent(QEvent.MouseButtonPress, QPointF(evt.pos()), Qt.LeftButton, evt.buttons(), Qt.KeyboardModifiers())
      super().mousePressEvent(fake)
    else:
      super().mousePressEvent(evt)
    
  def wheelEvent(self, evt):
    factor = 1.2
    if evt.angleDelta().y() < 0:
      factor = 1.0 / factor
    self.scale(factor, factor)

  def mouseMoveEvent(self, evt):
    super().mouseMoveEvent(evt)
    if evt.isAccepted():
      return
    evt.accept()

  def mouseReleaseEvent(self, evt):
    if evt.button() == Qt.RightButton:
      fake = QMouseEvent(QEvent.MouseButtonRelease, QPointF(evt.pos()),
                         Qt.LeftButton, evt.buttons(), Qt.KeyboardModifiers())
      super().mouseReleaseEvent(fake)
      self.setDragMode(QGraphicsView.RubberBandDrag)
    super().mouseReleaseEvent(evt)


class PlanaritySettings(QDialog):
  visibilityChanged = pyqtSignal(bool)

  def __init__(self, S, *args, **kwargs):
    super().__init__(*args, **kwargs)

    size_slider = QSlider(
      minimum=1, maximum=80,
      orientation=Qt.Horizontal, value=S['node/size'].get(),
      valueChanged=S['node/size'].set)

    self.setLayout(FLayout(
      [
        ["Size of balls", size_slider],
        ["Normal balls", ColorButton(S['node/color/normal'])],
        ["Touched balls", ColorButton(S['node/color/hover'])],
        ["Untangled balls", ColorButton(S['node/color/solved'])],
      ]))

    vis_action = QAction("Options", shortcut="Ctrl+O", checkable=True,
                         triggered=self.setVisible, checked=self.isVisible())
    vis_action.triggered.connect(self.setVisible)
    self.visAction = vis_action

    self.addAction(vis_action)
    self.addAction(QAction("Close", self, shortcut="Ctrl+Q", triggered=self.close))

  def showEvent(self, evt):
    self.visAction.setChecked(True)
  def hideEvent(self, evt):
    self.visAction.setChecked(False)
    
    


newgame_text = """
Enter game parameters.

Two graph generation modes currently exist:
delaunay N
melange N

Delaunay graphs are more regular and can be easier. Melange graphs can
be much more lopsided and might require more fiddling to make planar.
Both options only take a single parameter, namely the number of of
desired nodes in the graph."""


about_text = """


"""

class MainWindow(QMainWindow):
  def __init__(self, S, *args):
    super().__init__(*args, windowTitle="QPLanarity")

    self.S = S
    sett_window = PlanaritySettings(S)
    self._options = sett_window
    
    self.a_quit = QAction("Quit", shortcut="Ctrl+Q", triggered=self.close)
    self.a_newgame = QAction("New Game", shortcut="Ctrl+N", triggered=self.newGame)
    self.a_autoresize = QAction(
      "Autoresize",
      shortcut="Ctrl+R",
      checkable=True,
      checked=True)
    tb = QToolBar(toolButtonStyle=Qt.ToolButtonTextOnly)
    tb.addAction(self.a_newgame)
    tb.addAction(self.a_quit)
    tb.addAction(self._options.visAction)
    tb.addAction(self.a_autoresize)
    self.addToolBar(tb)

    self.statusBar().showMessage(" ")
    self.view = None
    self.setCentralWidget(QLabel("""
Welcome to QPlanarity!

Left mouse: drag (when hovering a ball), or select multiple balls
Right mouse: pull adjacent balls (when hovering), or pan the scene
Mouse wheel: zoom in and out

Ctrl+N = New Game
Ctrl+Q = Quit
Ctrl+O = Options

"""))

    if state_file.is_file():
      with state_file.open('rb') as f:
        (pts,self._graph) = pickle.load(f)
        self.init(*self._graph, [QPointF(x,y) for x,y in pts])


  def closeEvent(self, evt):
    self._options.close()
    
    if self.view is None:
      return

    scene = self.view.scene()
    pts = [(n.pos().x(), n.pos().y()) for n in scene.nodes]
    log.info("Saving state to qplanarity.state")
    with state_file.open('wb') as f:
      pickle.dump((pts,self._graph), f)

  def newGame(self):
    inp, ok = QInputDialog.getText(self, "New Game", newgame_text, text="delaunay 20")
    if not ok:
      return
    inp = inp.split()

    if len(inp) == 0 or inp[0] not in ('delaunay', 'melange'):
      QMessageBox.warning(self, "Invalid Graph", f"Invalid graph type: '{inp[0] if inp else ''}'\nMust be one of 'delaunay' or 'melange'.")
      return

    n = 20 if len(inp) < 2 else int(inp[1])
    if n >= 1000:
      if QMessageBox.question(self, "Warning!", "Handling such a big graph could be laggy!<br />Continue?") != QMessageBox.Yes:
        return
    if n < 3 or n >= 20000:
      QMessageBox.warning(self, "Invalid Graph", f"Invalid <N>: {n}")
      return

    try:
      assert inp[0] in ['delaunay', 'melange', '']
      g = RandomGraph3(n) if inp[0] == 'delaunay' else RandomGraph2(n)
    except Exception as e:
      log.warning(f"Error generating graph: {str(e)}")
      return
    self._graph = g.getEdges()
    self.init(*self._graph)

  def init(self, edges, node2lines, pts=None):
    scene = Scene(self.S)
    if pts is None:
      pts = random_circle_points(len(node2lines))
    scene.init(edges, node2lines, pts)

    view = View(scene, self.a_autoresize)
    self.view = view
    self.view.setBackgroundBrush(QBrush(Qt.white, Qt.SolidPattern))
    scene.progress.connect(self.progress)
    scene.victory.connect(self.victory)
    self.setCentralWidget(view)
    scene.postInit()

  def progress(self, a, b):
    self.statusBar().showMessage(f"{a} out of {b} lines untangled ({a/b:.1%})")
  def victory(self):
    self.view.setBackgroundBrush(QBrush(QColor("blanchedalmond"), Qt.SolidPattern))


def debug():
  import time
  v = [time.time()]
  def _st():
    v.append(time.time())
    return v[-1] - v[-2]
    
  with state_file.open('rb') as f:
    (pts,(edges,n2e)) = pickle.load(f)
  pts = [QPointF(x,y) for x,y in pts]
  LF = {(a,b): QLineF(pts[a], pts[b]) for a,b in edges}
  print("load random", _st())
  LineColl(LF)
  print("DONE", _st())

  G = RandomGraph3(1000)
  pts = [QPointF(*(100.0*x)) for x in G._solution]
  LF = {(a,b): QLineF(pts[a], pts[b]) for a,b in G.getEdges()[0]}
  
  print("load ordered", _st())
  B = LineColl(LF)
  print("DONE", _st())

  print(len(B.free))

    
def main():
  if PERF_DEBUG:
    debug()
    return 0
  window = MainWindow(S)
  window.show()
  return app.exec_()

if __name__ == '__main__':
  sys.exit(main())




