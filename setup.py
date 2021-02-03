
from setuptools import setup


setup(
  name='qplanarity',
  description='a puzzle game about untangling graphs',
  version='1.0',
  url='https://gitlab.com/franksh/qplanarity',
  author='Frank S. Hestvik',
  author_email='tristesse@gmail.com',
  license='BSD3',
  packages=['qplanarity'],
  install_requires=['PyQt5', 'numpy', 'scipy'],
  entry_points={
    'gui_scripts': ['qplanarity = qplanarity.main:main'],
  }
)

