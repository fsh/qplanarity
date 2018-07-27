
from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtWidgets import *
import sys
import random as rnd
import logging
import itertools
import math

logging.basicConfig(level=logging.DEBUG, format="%(asctime)s %(filename)s %(funcName)s:%(lineno)s %(levelname)s %(message)s")
log = logging.getLogger('main')

app = QApplication(sys.argv)

blue_brush = QBrush(Qt.blue, Qt.SolidPattern)
red_brush = QBrush(Qt.red, Qt.SolidPattern)
magenta_brush = QBrush(Qt.magenta, Qt.SolidPattern)
black_pen = QPen(Qt.black)
thick_pen = QPen(Qt.black)
thick_pen.setWidth(2.0)
gray_pen = QPen(Qt.gray)



class RandomGraph2(object):
  """
  Random Planar Graph Mk2.

  Algorithm works as follows. At each step we attach a number of triangles to the outside of the graph along randomly chosen
  edges. Then we form a new face of N+1 edges by picking N edges that run along the outside and adding an edge between their
  non-shared endpoints. These two steps are repeated until certain criteria are met.

  Parameters:
  """
  def __init__(self, node_limit=30, outside_limit=None, ):
    self.outside_edges = set([(0,1),(1,2),(0,2)])
    self.node_idx = 3
    self.limit = node_limit
    if outside_limit is None:
      # Try to limit edges on the outside to some percentage of the amount of nodes in the graph? Not sure what this parameter should be.
      outside_limit = int(node_limit*0.75 + 0.5)

    self.denseness_parameter = 0.3 # [0-1) higher number will have greater chance of generating clusters of highly connected nodes
    self.sparseness_parameter = 0.6 # [0-1) ]higher number will generate larger 'holes' or 'lakes' in the graph (too close to 1.0 might stall the algo)

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
          return self.removeLines()
        if xy[0] in endpoints or xy[1] in endpoints:
          # We found a line connected to one of the endpoints.
          other = xy
          break
      assert(other is not None) # Sanity check.
      self.outside_edges.remove(xy)
      self.edges.add(xy)
      if xy[0] in endpoints:
        xy = (sum(endpoints) - xy[0], xy[1])
      else:
        xy = (sum(endpoints) - xy[1], xy[0])
      endpoints = (min(xy), max(xy))
      log.debug("remvoing %s, new endpoints=%s", str(xy), str(endpoints))
      if rnd.random() > self.sparseness_parameter:
        break
    self.outside_edges.add(endpoints)

  def getEdges(self):
    n2e = [list() for i in range(self.node_idx)]
    for (a,b) in self.edges:
      n2e[a].append((a,b))
      n2e[b].append((a,b))
    return (self.edges, n2e)

class Node(QGraphicsEllipseItem):
  def __init__(self, idx, *args):
    super().__init__(-5.0, -5.0, 10.0, 10.0, *args)
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
    self.scene().updateNode(self)
  def mouseMoveEvent(self, evt):
    self.setPos(evt.scenePos())
    self.scene().updateNode(self)
  def mouseReleaseEvent(self, evt):
    self.scene().checkVictory()


class Scene(QGraphicsScene):
  victory = pyqtSignal()
  progress = pyqtSignal(int,int)
  refit = pyqtSignal()

  def __init__(self, n, *args):
    super().__init__(*args)
    self.init(n)

  def init(self, n=300):
    self.clear()
    g = RandomGraph1(n)

    # Find a number close to the square root of n that is coprime with n.
    a = int(math.sqrt(n))
    while math.gcd(a,n) > 1:
      a += 1

    # First create & place the nodes but don't add them to the scene just yet so we can do more efficient collision detection.
    self.nodes = []
    for i in range(n):
      self.nodes.append(Node(i))
      ri = (a*i + 0xbabe) % n
      self.nodes[i].setPos(200.0*math.cos(2*math.pi*ri/n),
                           200.0*math.sin(2*math.pi*ri/n))

    edges, node2lines = g.getEdges()
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

  def hover(self, node, onoff):
    self.z_count += 0.01
    others = self.node2lines[node.idx]
    for ab in others:
      line = self.lines[ab]
      if onoff:
        line.setPen(thick_pen)
      else:
        line.setPen(black_pen if ab in self.untangled else gray_pen)
    for (a,b) in others:
      o = a+b-node.idx
      self.nodes[o].setBrush(red_brush if onoff else blue_brush)
      self.nodes[o].setZValue(self.z_count)

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

      #log.debug("Collisions for line %s: %s", str(ab), str(list(sorted(coll))))
      #log.debug("Previous collisions       : %s", str(list(sorted(self.collisions.get(ab,set())))))
      # Check previous collisions.
      for xy in self.collisions.get(ab, ()):
        if xy in coll:
          # Collision we've already seen.
          continue
        # Remove collision.
        #log.debug("Removing %s-%s", str(xy), str(ab))
        self.collisions[xy].remove(ab)
        if len(self.collisions[xy]) == 0:
          log.debug("Is now collision free")
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
          self.collisions[xy].add(ab)
      elif ab in self.collisions:
        del self.collisions[ab]
        self.untangled.add(ab)
    log.info("%.2f%% untangled", 100.0 * len(self.untangled)/float(len(self.lines)))
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
  def __init__(self, scene, *args):
    super().__init__(*args)
    self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    self.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
    self.setScene(scene)
    scene.refit.connect(lambda: self.resizeEvent(None), Qt.QueuedConnection)

  def resizeEvent(self, evt):
    ib = self.scene().itemsBoundingRect().marginsAdded(QMarginsF(20,20,20,20))
    #print(self.scene().sceneRect())
    #print("ib", ib, "YES" if evt is None else "NO")
    self.scene().setSceneRect(ib)
    #print("scenerect", self.scene().sceneRect())
    self.fitInView(ib, Qt.KeepAspectRatio)

N = int(sys.argv[1])
scene = Scene(N)
view = View(scene)
window = QMainWindow()
anim = None
blur = QGraphicsBlurEffect()


# scene.victory.connect(foo)

view.setScene(scene)

class Contents(QWidget):
  def __init__(self, *args):
    super().__init__(*args)

    self.label = QLabel("QPlanarity!")
    lay = QVBoxLayout()
    lay.addWidget(view)
    lay.addWidget(self.label)
    self.setLayout(lay)
    scene.progress.connect(self.progress)
    scene.victory.connect(self.victory)

  def progress(self, a, b):
    self.label.setText("%d out of %d lines untangled (%.1f%%)" % (a, b, 100.0*a/b))
  def victory(self):
    lbl = QLabel(self)
    lbl.setText("YOU WIN")
    lbl.setGeometry(50, 50, 100, 100)


contents = Contents()

def foo():
  #blur.setBlurHints(QGraphicsBlurEffect.AnimationHint)
  global anim
  anim = QPropertyAnimation(blur, "blurRadius".encode())
  anim.setDuration(10000)
  anim.setStartValue(0.0)
  anim.setEndValue(25.0)
  contents.setGraphicsEffect(blur)
  anim.start()
  print("animation start")


window.setCentralWidget(contents)
window.show()

# foo()
# print(anim)
# timer = QTimer()
# timer.setInterval(100)
# def gogo():
#   print("hello %f" % blur.blurRadius())
#   #scene.update(scene.sceneRect())
#   #scene.advance()
#   contents.repaint()
#   contents.resize(500,500)
# timer.timeout.connect(gogo)
# timer.start()

sys.exit(app.exec_())
