

from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtWidgets import *


class FVar(QObject):
  onChange = pyqtSignal(QObject)

  def __init__(self, parent, name):
    super().__init__(parent, objectName=name)
    self._name = name

  def __call__(self, val=None):
    if val is not None:
      return self.set(val)
    return self.get()

class FValueVar(FVar):
  def __init__(self, parent, name, val):
    super().__init__(parent, name)
    self._value = self.convert(val)

  def get(self):
    return self._value

  def set(self, val):
    val = self.convert(val)
    self._value = val
    self.onValue.emit(val)
    self.onChange.emit(self)


class FIntVar(FValueVar):
  onValue = pyqtSignal(int)

  def convert(self, val):
    return int(val)

class FColorVar(FValueVar):
  onValue = pyqtSignal(QColor)

  def convert(self, val):
    return QColor(val)


class FSettings(QSettings):
  def __init__(self, *args, appname=None, filename=None, **kwargs):
    assert appname or filename
    if filename:
      super().__init__(filename, QSettings.IniFormat)
    else:
      super().__init__(QSettings.IniFormat, QSettings.UserScope, appname, appname)

  def __getitem__(self, name):
    ch = self.findChild(FVar, name)
    assert ch is not None
    return ch

  def create(self, parent, name, val):
    if isinstance(val, dict):
      return self.createGroup(parent, name, val)

    actual = self.value(name) if self.contains(name) else val

    if isinstance(val, int):
      obj = FIntVar(parent, name, actual)
    elif isinstance(val, QColor):
      obj = FColorVar(parent, name, actual)
    else:
      raise RuntimeError(f'unknown type {type(val)} for {name}')

    return obj
  
  def createGroup(self, parent, name, val):
    grp = FVar(parent, name)
    for k, v in val.items():
      obj = self.create(grp, name + '/' + k, v)
      obj.onChange.connect(grp.onChange)
    return grp

  def varChanged(self, obj):
    self.setValue(obj.objectName(), obj.get())

  def installOptions(self, opts):
    for k, v in opts.items():
      obj = self.create(self, k, v)
      obj.onChange.connect(self.varChanged)





class FLayout(QBoxLayout):
  def __init__(self, tree, *args, direction=QBoxLayout.TopToBottom):
    super().__init__(direction, *args)

    for x in tree:
      if isinstance(x, tuple):
        self.addStuff(*x)
      else:
        self.addStuff(x)

  def addStuff(self, x, stretch=0):
    if isinstance(x, str):
      self.addWidget(QLabel(x), stretch)
    elif isinstance(x, list):
      self.addLayout(FLayout(x, direction=self.dualLayout()), stretch)
    elif isinstance(x, int):
      self.addSpacing(x)
    elif x is None:
      self.addStretch(1 if stretch == 0 else stretch)
    elif isinstance(x, QLayout):
      self.addLayout(x, stretch)
    else:

      self.addWidget(x, stretch)

  def dualLayout(self):
    if self.direction() == QBoxLayout.TopToBottom or self.direction() == QBoxLayout.BottomToTop:
      return QBoxLayout.LeftToRight
    return QBoxLayout.TopToBottom


class ColorButton(QPushButton):
  def __init__(self, fvar, *args, **kwargs):
    self.fvar = fvar
    super().__init__(*args, clicked=self.pickColor, **kwargs)
    self.fvar.onChange.connect(self.updateIcon)
    self.updateIcon()

  def pickColor(self):
    color = QColorDialog.getColor(self.fvar.get(), self)
    if not color.isValid():
      return
    self.fvar.set(color)

  def updateIcon(self):
    pix = QPixmap(32, 32)
    pix.fill(self.fvar.get())
    self.setText(self.fvar.get().name())
    self.setIcon(QIcon(pix))


