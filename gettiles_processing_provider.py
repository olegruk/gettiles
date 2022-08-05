# -*- coding: utf-8 -*-

from qgis.PyQt.QtGui import QIcon
from qgis.core import QgsProcessingProvider
from .get_tiles_processing_algorithm import GetTilesProcessingAlgorithm


import os.path

class gettilesProcessingProvider(QgsProcessingProvider):

    def __init__(self):
        QgsProcessingProvider.__init__(self)

    def unload(self):
        pass

    def loadAlgorithms(self):
        self.addAlgorithm(GetTilesProcessingAlgorithm())


    def id(self):
        return 'gettiles'

    def name(self):
        return 'GetTiles'

    def icon(self):
        return QIcon(os.path.dirname(__file__) + '/gettiles.png')

    def longName(self):
        return self.name()
