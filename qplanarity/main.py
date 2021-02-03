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


app = QApplication(sys.argv)
app.setApplicationName('QPlanarity')

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
    delaunay = Delaunay(random_disc_points(n))
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
    super().__init__(-10.0, -10.0, 20.0, 20.0, *args)
    self.idx = idx
    self.setBrush(blue_brush)
    self.setAcceptHoverEvents(True)
    self.setZValue(1.0)

  def hoverEnterEvent(self, evt):
    log.debug("(%d) Enter hover", self.idx)
    self.setBrush(red_brush)
    self.scene().hover(self, True)
  def hoverLeaveEvent(self, evt):
    log.debug("(%d) Leave hover", self.idx)
    self.setBrush(blue_brush)
    self.scene().hover(self, False)
  def mousePressEvent(self, evt):
    if evt.button() == Qt.RightButton:
      self.scene().gravity(self)
    else:
      self.scene().updateNode(self)
  def mouseMoveEvent(self, evt):
    self.setPos(evt.scenePos())
    self.scene().updateNode(self)
  def mouseReleaseEvent(self, evt):
    self.scene().checkVictory()


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

  # Do is the simple way instead.
  pts = [200.0 * QPointF(math.cos(i*math.tau/n),
                         math.sin(i*math.tau/n)) for i in range(n)]
  rnd.shuffle(pts)
  return pts


class Scene(QGraphicsScene):
  victory = pyqtSignal()
  progress = pyqtSignal(int,int)
  refit = pyqtSignal()

  def __init__(self, *args):
    super().__init__(*args)

  def init(self, edges, node2lines, pt_list):
    self.clear()
    n = len(node2lines)

    self.nodes = []
    for i, pt in enumerate(pt_list):
      self.nodes.append(Node(i))
      self.nodes[i].setPos(pt)

    lines = dict()
    collisions = dict()
    for ab in edges:
      a,b = ab
      lines[ab] = self.addLine(QLineF(self.nodes[a].pos(), self.nodes[b].pos()), gray_pen)
      lines[ab].ab = ab

      for l in lines[ab].collidingItems(Qt.IntersectsItemShape):
        # Skip lines that just collide on connection.
        if len(set(l.ab + ab)) < 4:
          continue
        collisions.setdefault(ab, set()).add(l.ab)
        collisions.setdefault(l.ab, set()).add(ab)

    self.untangled = set(edges - collisions.keys())
    for e in self.untangled:
      lines[e].setPen(black_pen)

    # Now add the nodes.
    for i in range(n):
      self.addItem(self.nodes[i])

    self.lines = lines
    self.node2lines = node2lines
    self.collisions = collisions
    self.z_count = 1.0

  def neighbors(self, node):
    for (a,b) in self.node2lines[node.idx]:
      yield self.nodes[a+b-node.idx]

  def hover(self, node, onoff):
    self.z_count += 0.01
    others = self.node2lines[node.idx]
    for ab in others:
      line = self.lines[ab]
      if onoff:
        line.setPen(thick_pen)
      else:
        line.setPen(black_pen if ab in self.untangled else gray_pen)
    for other in self.neighbors(node):
      other.setBrush(red_brush if onoff else blue_brush)
      other.setZValue(self.z_count)

  def gravity(self, node):
    for other in self.neighbors(node):
      z = other.pos() - node.pos()
      z *= 0.9
      if QPointF.dotProduct(z, z) < 30.0**2:
        # Only pull nodes that are further away than 3x diameter of nodes.
        continue
      other.setPos(z + node.pos())
      self.updateNode(other)

  def updateNode(self, node):
    # Check this node's edges to remove any potential collisions.
    for ab in self.node2lines[node.idx]:
      a,b = ab
      self.lines[ab].setLine(QLineF(self.nodes[a].pos(), self.nodes[b].pos()))
      coll = set()
      for l in self.lines[ab].collidingItems(Qt.IntersectsItemShape):
        # Skip nodes.
        if not isinstance(l, QGraphicsLineItem):
          continue
        # If lines are connected, skip.
        if len(set(l.ab + ab)) < 4:
          continue
        # We have a regular collision.
        coll.add(l.ab)

      log.debug("Collisions for line %s: %s", str(ab), str(list(sorted(coll))))
      log.debug("Previous collisions       : %s", str(list(sorted(self.collisions.get(ab,set())))))
      # Check previous collisions.
      for xy in self.collisions.get(ab, ()):
        if xy in coll:
          # Collision we've already seen.
          continue
        # Remove collision.
        #log.debug("Removing %s-%s", str(xy), str(ab))
        self.collisions[xy].remove(ab)
        if len(self.collisions[xy]) == 0:
          log.debug("Is now collision free: %s", str(xy))
          del self.collisions[xy]
          self.untangled.add(xy)
          self.lines[xy].setPen(black_pen)
      # We'll set pen on unhover.
      if len(coll) > 0:
        self.collisions[ab] = coll
        if ab in self.untangled:
          self.untangled.remove(ab)
        for xy in coll:
          if xy not in self.collisions:
            log.debug("Tangling up %s", str(xy))
            self.untangled.remove(xy)
            self.collisions[xy] = set()
            self.lines[xy].setPen(gray_pen)
          self.collisions[xy].add(ab)
      elif ab in self.collisions:
        del self.collisions[ab]
        self.untangled.add(ab)
    log.debug("%.2f%% untangled", 100.0 * len(self.untangled)/float(len(self.lines)))
    self.progress.emit(len(self.untangled), len(self.lines))

    # # Sanity checking.
    # for x in self.lines.keys():
    #   if x in self.collisions:
    #     assert x not in self.untangled, "x:%s" % str(x)
    #   elif x in self.untangled:
    #     assert x not in self.collisions, "x:%s" % str(x)
    #   else:
    #     assert False, "x:%s isn't in anything" % str(x)

  def checkVictory(self):
    self.refit.emit()
    if len(self.collisions) != 0:
      return

    # Victory!
    self.victory.emit()


class View(QGraphicsView):
  def __init__(self, scene, act_resize, *args):
    super().__init__(*args)
    self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    self.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
    self.setScene(scene)
    scene.refit.connect(lambda: self.resizeEvent(None), Qt.QueuedConnection)
    self.act_resize = act_resize

  def resizeEvent(self, evt):
    if not self.act_resize.isChecked():
      return
    ib = self.scene().itemsBoundingRect().marginsAdded(QMarginsF(20,20,20,20))
    #print(self.scene().sceneRect())
    #print("ib", ib, "YES" if evt is None else "NO")
    self.scene().setSceneRect(ib)
    #print("scenerect", self.scene().sceneRect())
    self.fitInView(ib, Qt.KeepAspectRatio)

# class BoxLayout(QBoxLayout):
#   def __init__(self, tree, direction=QBoxLayout.TopToBottom):
#     super().__init__(direction)

#     for x in tree:
#       if isinstance(x, tuple):
#         self.addItem(*x)
#       else:
#         self.addItem(x)

#   def addItem(self, x, stretch=0):
#     if isinstance(x, str):
#       self.addWidget(QLabel(x), stretch)
#     elif isinstance(x, list):
#       self.addLayout(BoxLayout(x, self.nextDirection()), stretch)
#     elif isinstance(x, int):
#       self.addSpacing(x)
#     elif x is None:
#       self.addStretch(1 if stretch == 0 else stretch)
#     elif isinstance(x, QLayout):
#       self.addLayout(x, stretch)
#     else:
#       self.addWidget(x, stretch)

#   def nextDirection(self):
#     if self.direction() == QBoxLayout.TopToBottom:
#       return QBoxLayout.LeftToRight
#     return QBoxLayout.TopToBottom

# class GameDialog(QDialog):
#   def __init__(self, *args):
#     super().__init__(*args, windowTitle="New Game")

#     self.setLayout(BoxLayout([
#       []
#     ]))
#     layout = QHBoxLayout()
#     layout.addWidget()
#     layout.addLayout



newgame_text = """
Enter game parameters.

Two graph generation modes currently exist:
delaunay N
melange N

Delaunay graphs are more regular and can be easier. Melange graphs can
be much more lopsided and might require more fiddling to make planar.
Both options only take a single parameter, namely the number of of
desired nodes in the graph."""


class MainWindow(QMainWindow):
  def __init__(self, *args):
    super().__init__(*args, windowTitle="QPLanarity")

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
    tb.addAction(self.a_autoresize)
    self.addToolBar(tb)

    self.statusBar().showMessage(" ")
    self.view = None
    self.setCentralWidget(QLabel("Welcome to QPlanarity!\nCtrl+N = New Game\nCtrl+Q = Quit"))

    if state_file.is_file():
      with state_file.open('rb') as f:
        (pts,self._graph) = pickle.load(f)
        self.init(*self._graph, [QPointF(x,y) for x,y in pts])


  def closeEvent(self, evt):
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
      if QMessageBox.question(self, "Warning!", "Graph generation might take a long time, continue?") != QMessageBox.Yes:
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
    scene = Scene()
    if pts is None:
      pts = random_circle_points(len(node2lines))
    scene.init(edges, node2lines, pts)

    view = View(scene, self.a_autoresize)
    self.view = view
    self.view.setBackgroundBrush(QBrush(Qt.white, Qt.SolidPattern))
    scene.progress.connect(self.progress)
    scene.victory.connect(self.victory)
    view.setScene(scene)
    self.setCentralWidget(view)

  def progress(self, a, b):
    self.statusBar().showMessage(f"{a} out of {b} lines untangled ({a/b:.1%})")
  def victory(self):
    self.view.setBackgroundBrush(QBrush(QColor("blanchedalmond"), Qt.SolidPattern))

def main():
  window = MainWindow()
  window.show()
  return app.exec_()

if __name__ == '__main__':
  sys.exit(main())

