# ASCII filename wrapper so the bat never depends on Chinese names.
from importlib.machinery import SourceFileLoader
import os
import sys

here = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, here)
path = os.path.join(here, "发码工具.py")
if not os.path.isfile(path):
    path = os.path.join(here, "keygen_core.py")
mod = SourceFileLoader("hotspot_keygen", path).load_module()
mod.main()
