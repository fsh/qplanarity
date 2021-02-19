
import numpy as np

# Abominations of the tech world:
#
# 1. PHP
# 2. security through obscurity mentality
# 3.000000000007 floating point math

# So let's burn the world down with approximate math and unicode:

ε = 0.0000001
εn1 = 1 - ε
τ = np.pi * 2

# Important:
#
# np.finfo(np.float64).eps
# np.nextafter(1.0, 0.0)

def inner_intersect_cross(a, b):
  """Finds line segments that intersect at a single _inner_ point.

  This means:
  - The segment endpoints are not counted as part of the lines.
  - They do not intersect if collinear and overlapping.

  Side note: floating point math is a bitch.

  """
  # Not x.reshape because this allows the parameters to be Python values.
  a = np.reshape(a, (-1, 2, 2))
  b = np.reshape(b, (-1, 2, 2))
  
  Δa = a[:,1] - a[:,0]
  Δb = b[:,1] - b[:,0]
  ΔL = b[:,0] - a[:,0]

  mag = np.cross(Δa, Δb)

  # mag == 0 means collinear or parallel, so keep it False.
  res = mag != 0

  t = np.cross(ΔL, Δb)
  u = np.cross(ΔL, Δa)

  m_ = mag[res]
  t_ = t[res] / m_
  u_ = u[res] / m_

  res[res] = (t_ > ε) \
    & (t_ < εn1) \
    & (u_ > ε) \
    & (u_ < εn1)

  return res

def orientation(a, b, c):
  """Gives orientation of three points.

  -1 for counterclockwise.
  0 for collinear.
  +1 for clockwise.

  """
  return np.sign(np.cross(a - b, c - b))

def inner_intersect_orient(A1, A2, B1, B2):
  """Same functionality as `inner_intersect_orient` but slower and
  hopefully more robust w.r.t. floating point math.

  """
  o1 = orientation(A1, A2, B1)
  o2 = orientation(A2, A1, B2)
  o3 = orientation(B1, B2, A1)
  o4 = orientation(B2, B1, A2)
  return (o1 != 0) & (o1 == o2) & (o3 != 0) & (o3 == o4)


def random_circle_points(n, radius=1.0):
  """`n` random points on a circle with radius `radius` as a (n, 2) array.

  """
  ix = np.arange(n, dtype=np.float64)
  pts = radius * np.vstack(
    [np.cos(ix * τ / n),
     np.sin(ix * τ / n)]).T
  np.random.shuffle(pts)
  return pts


class planar_graph():
  """State of a graph embedded in the Euclidean plane.

  The initial line collision count loop is O(E^2) because it's faster
  to do the naive thing with numpy than to try to do anything clever
  with plain Python loops. This is a sad reality. To beat numpy one
  would need a good sweep-line algorithm (O(E*log(E))) which I'm not
  prepared to do currently.

  """
  def __init__(self, positions, edges):
    self._pos = np.array(positions, dtype=np.float64)
    assert self._pos.shape == (self.n_nodes, 2)
    
    self._e2n = np.array(edges, dtype=np.int32)
    assert self._e2n.shape == (self.n_edges, 2)
    assert np.min(self._e2n) == 0
    assert np.max(self._e2n) < self.n_edges

    self._n2e = [list() for _ in range(self.n_nodes)]
    self._lines = np.zeros((len(edges), 2, 2), dtype=np.float64)
    for i,(a,b) in enumerate(self._e2n):
      self._n2e[a].append(i)
      self._n2e[b].append(i)
      self._lines[i] = (self._pos[a], self._pos[b])

    self._coll_cache = dict()

    # NB! NB! O(E^2)
    self._n_lcolls = np.array([np.sum(self.line_collisions(i)) for i in range(self.n_edges)], dtype=np.int32)
    self._n_ncolls = np.array([self._n_lcolls[es].sum() for es in self._n2e])

  @property
  def n_edges(self):
    "Number of edges."
    return len(self._e2n)

  @property
  def n_nodes(self):
    "Number of nodes."
    return len(self._pos)

  @property
  def vertices(self):
    "An array of shape (#,2) giving vertex coordinates."
    return self._pos

  @property
  def lines(self):
    "An array of shape (#,2,2) giving line coordinates."
    return self._lines

  def is_vertex_free(self, i):
    "Returns `True` if all the edges of the given vertex are untangled."
    return self._n_ncolls[i] == 0

  def is_line_untangled(self, i):
    "Returns `True` if the edge does not intersect with any other line."
    return self._n_lcolls[i] == 0

  def is_planar(self):
    "Returns `True` if the graph is planar (no lines intersect)."
    return np.all(self._n_lcolls == 0)

  def neighbors(self, i):
    "Returns the vertices connected to the given node `i` as an array."
    return self._e2n[self._n2e[i]].sum(1) - i

  def vertex_edges(self, i):
    return self._n2e[i]

  @property
  def tangle_array(self):
    return self._n_lcolls
  
  def update_vertex_pos(self, n, pos):
    """Updates the position of a given vertex.

    This is where the main logic behind planarity resides.
    """
    edges = self._n2e[n]

    precoll = [self.line_collisions(e) for e in edges]

    # Actually update positions.
    self._pos[n] = pos
    self._lines[edges] = [self._pos[self._e2n[e]] for e in edges]

    postcoll = [self.line_collisions(e, force_eval=True) for e in edges]

    self._n_lcolls[edges] = np.sum(postcoll, 1)
    dirty = np.zeros(self.n_edges, np.bool)

    for pre,post in zip(precoll, postcoll):
      diff = post ^ pre
      dirty |= diff

      self._n_lcolls[diff & post] += 1
      self._n_lcolls[diff & pre] -= 1

    # Sanity check: coll count should be >= 0
    assert np.all(self._n_lcolls >= 0)

    # TODO: there's a bug (floating point math) that can trigger this (hard to reproduce).
    # Sanity check: the current edges should not have been touched.
    # assert not np.any(dirty[edges])

    # Remove edges whose collision count changed from cache.
    for e in dirty.nonzero()[0]:
      self._coll_cache.pop(e, None)

    # Finally update node collision counts.
    dirty[edges] = True
    for n_ in np.unique(self._e2n[dirty].flatten()):
      self._n_ncolls[n_] = self._n_lcolls[self._n2e[n_]].sum()


  def line_collisions(self, e, force_eval=False):
    if force_eval or e not in self._coll_cache:
      self._coll_cache[e] = inner_intersect_cross(self._lines[e], self._lines)
    return self._coll_cache[e]


class planar_graph_diff():
  """Tracks changes of `planar_graph`.

  Intended to be used in conjuction with
  `planar_graph.update_node_pos()` to access changes:

  ```
  delta = planar_graph_diff(g)
  g.update_vertex_pos(...)
  for e in delta.tangled_edges:
    # edges that became tangled after the previous node update.
    ...
  ```
  """
  def __init__(self, graph):
    self._pre_l = graph._n_lcolls.copy()
    self._pre_n = graph._n_ncolls.copy()
    self._graph = graph

  @property
  def changed_edges(self):
    return ((self._graph._n_lcolls == 0) ^ (self._pre_l == 0)).nonzero()[0]
  
  @property
  def tangled_edges(self):
    return ((self._graph._n_lcolls > 0) & (self._pre_l == 0)).nonzero()[0]
    
  @property
  def free_edges(self):
    return ((self._graph._n_lcolls == 0) & (self._pre_l > 0)).nonzero()[0]

  @property
  def changed_vertices(self):
    return ((self._graph._n_ncolls == 0) ^ (self._pre_n == 0)).nonzero()[0]

  @property
  def tangled_vertices(self):
    return ((self._graph._n_ncolls > 0) & (self._pre_n == 0)).nonzero()[0]

  @property
  def free_vertices(self):
    return ((self._graph._n_ncolls == 0) & (self._pre_n > 0)).nonzero()[0]

### Test stuff.

random_magnitudes = lambda sz: 1-np.random.random(size=sz)
random_angles = lambda sz: np.random.uniform(0.0, 2*np.pi, sz)

def random_lineflip(x1, x2):
  which = np.random.randint(0, 2, (len(x1), 1), dtype=bool)
  return np.where(which, x1, x2), np.where(which, x2, x1)

def testset_nonintersecting(n=10):
  """Generates a set of line segments that don't intersect (but might
  share common endpoints).

  """
  O = np.array([0.0,0.0]) # np.random.normal(0.0, 1.0, 2)
  while True:
    r = np.random.random(size=n+1)
    r /= np.sum(r)
    if np.max(r) < 0.25:
      break
  a = 2*np.pi*np.cumsum(r[:-1])
  pts = O + random_magnitudes((n,1)) * np.vstack([np.cos(a), np.sin(a)]).T
  return random_lineflip(pts, np.roll(pts, -1, axis=0))

def testset_random(n=10):
  x1 = np.random.normal(0.0, 1.0, (n, 2))
  x2 = np.random.normal(0.0, 1.0, (n, 2))
  return x1, x2

def testset_intersecting(n=10):
  """Generates a random set of line segments all intersecting at single
  inner point.

  """
  O = np.random.normal(0.0, 1.0, 2)
  a = random_angles(n)
  m1 = random_magnitudes((n,1))
  m2 = -random_magnitudes((n,1))
  pts = np.vstack([np.cos(a), np.sin(a) ]).T
  return O + pts * m1, O + pts * m2

def test_intersects(n=10):
  for f in [inner_intersect_orient, inner_intersect_cross]:
    x1,x2 = testset_nonintersecting(n)
    assert not np.any(f(x1[0],x2[0], x1[1:],x2[1:]))
    x1,x2 = testset_intersecting(n)
    assert np.all(f(x1[0],x2[0], x1[1:],x2[1:]))

  a1,a2 = testset_random(n)
  b1,b2 = testset_random(n)
  assert np.all(inner_intersect_orient(a1,a2,b1,b2) == inner_intersect_cross(a1,a2,b1,b2))

