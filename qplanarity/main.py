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

import numpy as np

# This is only used for delaunay graph generation
from scipy.spatial import Delaunay

__version__ = '1.4.1'

logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(filename)s %(funcName)s:%(lineno)s %(levelname)s %(message)s")
log = logging.getLogger('main')

PERF_DEBUG = False

from .qtutils import FSettings, FLayout, ColorButton, FCheckBox, FComboBox
from .linalg import random_circle_points, planar_graph, planar_graph_diff

class PlanarityApp(QApplication):
  def __init__(self, *args, **kwargs):
    super().__init__(*args, **kwargs)
    self.setOrganizationName('qplanarity')

app = PlanarityApp(sys.argv)

defaults = {
  'node': {
    'color': {
      'normal': QColor('#2244bb'), # QColor('crimson'),
      'hover': QColor('darkorange'), # QColor('darkorange'),
      'solved': QColor('crimson'), # QColor('darksalmon'),
    },
    'size': 24,
  },
  'ui': {
    'zoom': True,
    'graphtype': (0, ['Delaunay', 'Melange']),
    'background': {
      'normal': QColor('blanchedalmond'),
      'solved': QColor('wheat'),
    },
  },
}

S = FSettings(appname='qplanarity')
S.installOptions(defaults)

config_path = Path(QStandardPaths.writableLocation(QStandardPaths.AppConfigLocation))

if not config_path.exists():
  config_path.mkdir(parents=True)

state_file = config_path / 'qplanarity14.state'


# blue_brush = QBrush(Qt.blue, Qt.SolidPattern)
# red_brush = QBrush(Qt.red, Qt.SolidPattern)
# magenta_brush = QBrush(Qt.magenta, Qt.SolidPattern)
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
    self.setAcceptHoverEvents(True)
    self.setZValue(1.0)
    self.setFlags(QGraphicsItem.ItemIgnoresTransformations
                  | QGraphicsItem.ItemIsSelectable)
    self._hover = False

  def hoverEnterEvent(self, evt):
    log.debug("(%d) Enter hover", self.idx)
    self._hover = True
    self.scene().hover(self, True)
  
  def hoverLeaveEvent(self, evt):
    log.debug("(%d) Leave hover", self.idx)
    self._hover = False
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
    self.lines = []
    self.z_count = 1.0
    
    self.S = settings
    self.S['node/color'].onChange.connect(self.update_brushes)
    self.S['node/size'].onValue.connect(self.update_rects)
    self.S['ui/background'].onChange.connect(self.update_bg)
    self.update_brushes()
    self._grp = None

  def update_brushes(self):
    self._brush_normal = QBrush(self.S['node/color/normal'].get(), Qt.SolidPattern)
    self._brush_hover = QBrush(self.S['node/color/hover'].get(), Qt.SolidPattern)
    self._brush_solved = QBrush(self.S['node/color/solved'].get(), Qt.SolidPattern)
    for i in range(len(self.nodes)):
      self.update_node_brush(i)

  def update_rects(self, radius):
    node_rect = QRectF(-radius, -radius, radius*2, radius*2)
    for n in self.nodes:
      n.setRect(node_rect)

  def update_bg(self):
    color = self.S['ui/background/solved'].get() if self._pg.is_planar() else self.S['ui/background/normal'].get()
    if self.backgroundBrush().color() == color:
      # Do nothing.
      return

    self.setBackgroundBrush(QBrush(color, Qt.SolidPattern))
    self.invalidate(QRectF(-1000,-1000,5000,5000), QGraphicsScene.BackgroundLayer)

  def init(self, pg):
    self.clear()

    self._pg = pg

    self.z_count = 1.0
    self._grp = None
    self._finished = False

    self.nodes = []
    for i, pt in enumerate(pg.vertices):
      obj = Node(i)
      obj.setPos(*pt)
      self.nodes.append(obj)
      self.addItem(obj)

    self.lines = []
    for i,ln in enumerate(pg.lines):
      self.lines.append(self.addLine(*ln[0], *ln[1], self.line_pen(i)))

    self.update_bg()
    self.update_brushes()
    self.update_rects(self.S['node/size'].get())

  def line_pen(self, i):
    "QPen to use for line `i`."
    return black_pen if self._pg.is_line_untangled(i) else gray_pen

  def gravity(self, node):
    sz = self.S['node/size'].get()
    diff = planar_graph_diff(self._pg)
    
    for other in self._pg.neighbors(node.idx ):
      z = self._pg.vertices[other] - self._pg.vertices[node.idx]
      z *= 0.75
      if np.linalg.norm(z) < 3 * sz:
        # Don't pull nodes that are already close
        continue

      self.update_node_and_vertex(other, self._pg.vertices[node.idx] + z)

    self.apply_changes(diff)
    self.notify_updated()

  def update_node_brush(self, i):
    if self.nodes[i]._hover:
      brush = self._brush_hover
    elif self._pg.is_vertex_free(i):
      brush = self._brush_solved
    else:
      brush = self._brush_normal
    self.nodes[i].setBrush(brush)

  def update_node_and_vertex(self, i, pos):
    if isinstance(pos, QPointF):
      pos = [pos.x(), pos.y()]

    self._pg.update_vertex_pos(i, pos)  
    self.nodes[i].setPos(*pos)
    for l in self._pg.vertex_edges(i):
      self.lines[l].setLine(*self._pg.lines[l][0], *self._pg.lines[l][1])
  
  def apply_changes(self, changes):
    for n in changes.changed_vertices:
      self.update_node_brush(n)
    for l in changes.changed_edges:
      self.lines[l].setPen(self.line_pen(l))

    self.update_bg()

  def drag_start(self, node):
    sel = self.selectedItems()
    if node not in sel:
      self.clearSelection()
    else:
      self._grp = sel
      self._grppos = node.pos()

  def drag_move(self, node, pos):
    if self._grp:
      delta = pos - node.pos()
      for n in self._grp:
        n.setPos(n.pos() + delta)
      return

    diff = planar_graph_diff(self._pg)
    self.update_node_and_vertex(node.idx, pos)
    self.apply_changes(diff)

  def drag_stop(self, node):
    if self._grp:
      self.clearSelection()
      _grp = self._grp
      self._grp = None
    
      diff = planar_graph_diff(self._pg)
      delta = node.pos() - self._grppos
      for n in _grp:
        self.update_node_and_vertex(n.idx, n.pos() + delta)
      self.apply_changes(diff)

    self.notify_updated()

  def notify_updated(self):
    self.refit.emit()
    prog = np.count_nonzero(self._pg.tangle_array == 0)
    self.progress.emit(prog, len(self.lines))
    if prog == len(self.lines) and not self._finished:
      self._finished = True
      self.victory.emit()
  
  def hover(self, node, onoff):
    # Hover highlight and raise associated nodes.
    for other in self._pg.neighbors(node.idx):
      self.nodes[other]._hover = onoff
      self.nodes[other].setZValue(self.z_count)
      self.update_node_brush(other)

    self.update_node_brush(node.idx)
    
    if not onoff:
      for l in self._pg.vertex_edges(node.idx):
        self.lines[l].setPen(self.line_pen(l))
    else:
      self.z_count += 0.01
      for l in self._pg.vertex_edges(node.idx):
        self.lines[l].setPen(thick_pen)



class View(QGraphicsView):
  def __init__(self, scene, act_resize, *args):
    super().__init__(*args)
    self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    self.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)

    self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
    
    self.setScene(scene)
    scene.refit.connect(lambda: self.resizeEvent(None), Qt.QueuedConnection)
    self.act_resize = act_resize

    self.setDragMode(QGraphicsView.RubberBandDrag)

  def resizeEvent(self, evt):
    if not self.act_resize.isChecked():
      return
    margins = QMarginsF(30.0, 30.0, 30.0, 30.0)
    ib = self.scene().itemsBoundingRect()
    self.scene().setSceneRect(ib.marginsAdded(margins * 200))
    self.fitInView(ib.marginsAdded(margins), Qt.KeepAspectRatio)

  def mousePressEvent(self, evt):
    if evt.button() == Qt.LeftButton:
      self.setDragMode(QGraphicsView.ScrollHandDrag)
      super().mousePressEvent(evt)
    else:
      super().mousePressEvent(evt)
    
  def wheelEvent(self, evt):
    if not S['ui/zoom'].get():
      return
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
    super().mouseReleaseEvent(evt)
    if evt.button() == Qt.LeftButton:
      self.setDragMode(QGraphicsView.RubberBandDrag)


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
        20,
        [FCheckBox(S['ui/zoom'], text='Enable zoom (mouse wheel)')],
        20,
        ["Graph generation algorithm", FComboBox(S['ui/graphtype'])],
        ["""Delaunay generates "nicer" and more regular graphs. Melange generates more "lopsided" graphs that can become pathological and harder to make planar.\n"""],
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
    
    


newgame_text = """Enter number of vertices in graph.

A reasonable number is probably in the range 8 to 100.

A higher number doesn't necessarily mean it will be harder, just more
time-consuming, like a larger jigsaw puzzle. For example, anything
larger than 500 is likely to take several hours even if you're
experienced with playing planarity. The algorithm currently selected
in options will determine how the graph is generated.
"""


about_text = """


"""

class MainWindow(QMainWindow):
  def __init__(self, S, *args):
    super().__init__(*args, windowTitle="QPlanarity")

    self.setContextMenuPolicy(Qt.NoContextMenu)
    
    self.S = S
    sett_window = PlanaritySettings(S)
    self._options = sett_window
    
    self.a_quit = QAction("Quit", shortcut="Ctrl+Q", triggered=self.close)
    self.a_newgame = QAction("New Game", shortcut="Ctrl+N", triggered=self.newGame)
    self.a_autoresize = QAction(
      "Autocenter",
      shortcut="Ctrl+R",
      checkable=True,
      checked=True)
    self.a_about = QAction("About", triggered=self.about)
    tb = QToolBar(toolButtonStyle=Qt.ToolButtonTextOnly)
    tb.addAction(self.a_newgame)
    tb.addAction(self.a_autoresize)
    tb.addAction(self._options.visAction)
    tb.addAction(self.a_about)
    tb.addAction(self.a_quit)
    self.addToolBar(tb)

    self.statusBar().showMessage(" ")
    self.view = None
    self.setCentralWidget(QLabel("""
Welcome to QPlanarity!

Left mouse button: drag ball or scene

Right mouse button: multiselect
Right mouse button on ball: pull adjacent ball closer

Mouse wheel: zoom in and out

Ctrl+N = New game
Ctrl+Q = Quit
Ctrl+O = Options
Ctrl+R = Toggle autocenter

"""))

    if state_file.is_file():
      try:
        with state_file.open('rb') as f:
          self._graph = pickle.load(f)
      except Exception as e:
        log.warning(f"exception hit while trying to load previous state: {e}")
      else:
        self.init(self._graph)

  def about(self):
    QMessageBox.about(self, "About QPlanarity", f"""
<h1>QPlanarity <small>(v.{__version__})</small></h1>
<p><b>By Frank S. Hestvik (tristesse@gmail.com)</b></p>

<p>Inspired by an old Flash web game called Planarity. Made with
PyQt5.</p>

<p>Special credits to <i>poiko</i> and <i>Jean3tte</i> for being the
only people who might read this text.</p>""")

  def closeEvent(self, evt):
    self._options.close()
    
    if self.view is None:
      return

    log.info(f"Saving state to {state_file}")
    with state_file.open('wb') as f:
      pickle.dump(self._graph, f)

  def newGame(self):
    inp, ok = QInputDialog.getText(self, "New Game", newgame_text, text="10")
    if not ok:
      return

    try:
      n = int(inp)
    except ValueError:
      QMessageBox.warning(self, "Integer Error", f"Invalid number: {inp}")
      return

    if n < 4 or n > 10000:
      QMessageBox.warning(self, "Integer Error", f"The number should be in the range 4-10000")
      return
    if n >= 1000:
      if QMessageBox.question(self, "Warning!", "Handling such a big graph could be laggy!<br />Continue?") != QMessageBox.Yes:
        return

    graphtype = S['ui/graphtype'].choice()
    assert graphtype in ['Delaunay', 'Melange']
    try:
      g = RandomGraph3(n) if graphtype == 'Delaunay' else RandomGraph2(n)
    except Exception as e:
      QMessageBox.warning(self, "Graph Error", f"Exception while trying to generate graph!\n{str(e)}")
      log.warning(f"Error generating graph: {str(e)}")
      return

    edges, n2e = g.getEdges()
    pts = random_circle_points(len(n2e), 200.0)
    self._graph = planar_graph(pts, [[a,b] for a,b in edges])
    self.init(self._graph)

  def init(self, pg):
    scene = Scene(self.S)
    scene.init(pg)

    view = View(scene, self.a_autoresize)
    self.view = view
    scene.progress.connect(self.progress)
    scene.victory.connect(self.victory)
    self.setCentralWidget(view)

  def progress(self, a, b):
    self.statusBar().showMessage(f"{a} out of {b} lines untangled ({a/b:.1%})")
  def victory(self):
    # TODO: do something here? Display time taken?
    pass


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




