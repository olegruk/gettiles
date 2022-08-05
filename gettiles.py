# -*- coding: utf-8 -*-


import os.path
import processing
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction
from qgis.core import QgsApplication

from .rectangleAreaTool import RectangleAreaTool
from .gettiles_processing_provider import gettilesProcessingProvider

class GetTilesPlugin:

    def __init__(self, iface):
        self.iface = iface
        self.menu = "&GetTiles"
        self.canvas = iface.mapCanvas()
        self.provider = None
        self.toolbar = self.iface.addToolBar('GetTiles Toolbar')
        self.toolbar.setObjectName('GetTilesToolbar')


    def initGui(self):
        iconGetTiles = QIcon(os.path.dirname(__file__) + '/gettiles.png')
        self.GetTilesAction = QAction(iconGetTiles, "Get tiles", self.iface.mainWindow())
        self.GetTilesAction.setObjectName("GetTiles")
        self.GetTilesAction.triggered.connect(self.GetTiles)
        self.GetTilesAction.setEnabled(True)
        self.GetTilesAction.setCheckable(True)
        self.toolbar.addAction(self.GetTilesAction)
        self.iface.addPluginToMenu(self.menu, self.GetTilesAction)

        self.GetTilesTool = RectangleAreaTool(self.iface.mapCanvas(), self.GetTilesAction)
        self.GetTilesTool.rectangleCreated.connect(self.GetTilesII)

        self.initProcessing()

    def initProcessing(self):
        self.provider = gettilesProcessingProvider()
        QgsApplication.processingRegistry().addProvider(self.provider)

    def unload(self):
        self.iface.removePluginMenu(self.menu, self.GetTilesAction)
        self.iface.removeToolBarIcon(self.GetTilesAction)
        QgsApplication.processingRegistry().removeProvider(self.provider)
        del self.toolbar


    def GetTiles(self,b):
        if b:
            self.prevMapTool = self.iface.mapCanvas().mapTool()
            self.iface.mapCanvas().setMapTool(self.GetTilesTool)
        else:
            self.iface.mapCanvas().setMapTool(self.prevMapTool)
            self.NamedGridAction.setChecked(False)

    def GetTilesII(self, startX, startY, endX, endY):
        if startX == endX and startY == endY:
            return
        extent = '%f,%f,%f,%f'%(startX, endX, startY, endY)
        self.iface.mapCanvas().setMapTool(self.prevMapTool)
        processing.execAlgorithmDialog('gettiles:Get tiles', {'EXTENT': extent})
        self.iface.mapCanvas().refresh()
        self.iface.mapCanvas().redrawAllLayers()