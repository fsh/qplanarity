
from setuptools import setup


setup(
  name='qplanarity',
  description='Puzzle game about untangling graphs',
  version='1.4.2',

  long_description_content_type='text/markdown', # when is text/org going to be supported pls thx
  long_description=open('README.md', 'r').read(),
  keywords='planarity game qt5 untangle planar graph untangling'.split(),
  
  url='https://gitlab.com/franksh/qplanarity',
  author='Frank S. Hestvik',
  author_email='tristesse@gmail.com',
  license='BSD3',
  packages=['qplanarity'],
  install_requires=['PyQt5', 'numpy', 'scipy'],
  python_requires='>=3.7', # dataclasses?
  entry_points={
    'gui_scripts': ['qplanarity = qplanarity.main:main'],
  },
  classifiers=[
    "Development Status :: 5 - Production/Stable",
    "License :: OSI Approved :: GNU General Public License v3 (GPLv3)",
    "Intended Audience :: End Users/Desktop",
    "Programming Language :: Python :: 3",
  ],
)

