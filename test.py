import os, sys

qmetatiles_path = os.path.dirname(os.path.abspath(__file__)).removesuffix('gettiles') + 'QMetaTiles'
print(qmetatiles_path)

sys.path.append(qmetatiles_path)

print (sys.path)

from tilingthread import TilingThread