import importlib.util
import sys
import numpy
import matplotlib
import PIL

assert importlib.util.find_spec('torch') is None
assert numpy.__version__ == '1.26.4'
print('ISOLATED_CPU_ENVIRONMENT', sys.version, numpy.__version__, matplotlib.__version__, PIL.__version__)
