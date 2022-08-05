# -*- coding: utf-8 -*-

from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtCore import QDir, QFileInfo
from qgis.core import (QgsProcessingParameterExtent,
                       QgsProcessingParameterEnum,
                       QgsProcessingParameterString,
                       QgsProcessingParameterBoolean,
                       QgsProcessingParameterRasterLayer,
                       QgsProcessingAlgorithm,
                       QgsProcessingParameterFolderDestination,
                       QgsProject,
                       QgsCoordinateTransform,
                       QgsCoordinateReferenceSystem,
                       QgsRectangle,
                       QgsLayerTreeLayer,
                       QgsRasterLayer)
import os.path
import math, re
from .tilingthread import TilingThread
from .tileset import TileSet

class GetTilesProcessingAlgorithm(QgsProcessingAlgorithm):

    MINZOOM = 'MINZOOM'
    MAXZOOM = 'MAXZOOM'
    EXTENT = 'EXTENT'
    SINGLELAYER = 'SINGLELAYER'
    INPUT = 'INPUT'
    SUBSET = 'SUBSET'
    OUTPUT = 'OUTPUT'

    def initAlgorithm(self, config=None):
        self.zoomlist = ['z0', 'z1', 'z2', 'z3', 'z4', 'z5', 'z6', 'z7', 'z8', 'z9', 'z10', 'z11', 'z12', 'z13', 'z14', 'z15', 'z16', 'z17', 'z18', 'z19', 'z20', 'z21', 'z22', 'z23', 'z24']
        self.addParameter(QgsProcessingParameterEnum(self.MINZOOM, 'Min zoom of cached map', self.zoomlist, defaultValue=13))
        self.addParameter(QgsProcessingParameterEnum(self.MAXZOOM, 'Max zoom of cached map', self.zoomlist, defaultValue=15))
        self.addParameter(QgsProcessingParameterExtent(self.EXTENT, 'Cache extent'))
        self.addParameter(QgsProcessingParameterBoolean(self.SINGLELAYER, 'Cache single raster layer.', defaultValue=True, optional=False))
        self.addParameter(QgsProcessingParameterRasterLayer(self.INPUT, 'Cached layer:', optional=True))
        self.addParameter(QgsProcessingParameterString(self.SUBSET, 'Cache folder name', optional=False, defaultValue='Cache'))
        self.addParameter(QgsProcessingParameterFolderDestination(self.OUTPUT, 'Folder to store map tiles (by default - home folder of you project):'))
        self.workThread = None

    def processAlgorithm(self, parameters, context, feedback):

        crs = context.project().crs()
        minzoom = self.parameterAsEnum(parameters, self.MINZOOM, context)
        maxzoom = self.parameterAsEnum(parameters, self.MAXZOOM, context)
        if minzoom > maxzoom:
            feedback.pushConsoleInfo('Maximum zoom value is lower than minimum. Please correct this and try again.')
            return
 
        bbox = self.parameterAsExtent(parameters, self.EXTENT, context, crs)
        outfolder = self.parameterAsFile(parameters, self.OUTPUT, context)
        root_dir = self.parameterAsString(parameters, self.SUBSET, context)
        cached_layer = self.parameterAsRasterLayer(parameters, self.INPUT, context)
        single_layer = self.parameterAsBoolean(parameters, self.SINGLELAYER, context)

        fileInfo = QFileInfo(outfolder)
        if fileInfo.isDir() and not len(QDir(outfolder).entryList(QDir.Dirs | QDir.Files | QDir.NoDotAndDotDot)) == 0:
            feedback.pushConsoleInfo('Selected directory is not empty.')
            #return
        feedback.pushConsoleInfo(f"fileInfo:{fileInfo}.")

        extent = QgsCoordinateTransform(crs, QgsCoordinateReferenceSystem('EPSG:4326'), QgsProject.instance()).transform(bbox)
        arctanSinhPi = math.degrees(math.atan(math.sinh(math.pi)))
        extent = extent.intersect(QgsRectangle(-180, -arctanSinhPi, 180, arctanSinhPi))

        prj_file = QgsProject.instance().fileName()
        root = QgsProject.instance().layerTreeRoot()
        layers = root.checkedLayers()
        tile_width = 256
        tile_height = 256
        transp = 100
        quality = 70
        tile_format = 'PNG'
        enable_antialiasing = False
        tmsconvention = False
        writeMapurl = False
        writeViewer = False
        metatile = False
        metatile_size = {'rows': 2, 'cols': 2}
        metatile_buffer = False
        llg_features = False
        if single_layer:
            layers = [cached_layer]

        self.workThread = TilingThread( layers,
                                        extent,
                                        minzoom,
                                        maxzoom,
                                        tile_width,
                                        tile_height,
                                        transp,
                                        quality,
                                        tile_format,
                                        fileInfo,
                                        root_dir,
                                        enable_antialiasing,
                                        tmsconvention,
                                        writeMapurl,
                                        writeViewer,
                                        metatile,
                                        metatile_size,
                                        metatile_buffer,
                                        llg_features
                                        )
        
        self.workThread.rangeChanged.connect(self.setProgressRange)
        self.workThread.updateProgress.connect(self.updateProgress)
        self.workThread.processFinished.connect(self.processFinished)
        self.workThread.processInterrupted.connect(self.processInterrupted)
        self.workThread.start()

        #  this does the same thing but without using a seperate thread. Good for debugging.
        #no_thread = TileSet(layers,extent,minzoom,maxzoom,tile_width,tile_height,
        #                                            transp,quality,tile_format,fileInfo,root_dir,
        #                                            enable_antialiasing,tmsconvention,writeMapurl,writeViewer,metatile,metatile_size,
        #                                            metatile_buffer,llg_features)
        #no_thread.run()
        
        #create a xyz layer
        full_path = re.sub('\\\\','/',outfolder) + '/' + root_dir
        urlWithParams = 'type=xyz&url=file:///%(f)s/{z}/{x}/{y}.%(t)s&zmax=15&zmin=13&crs=EPSG3857'%{'f':full_path,'t':tile_format}
        rlayer = QgsRasterLayer(urlWithParams, f'{root_dir}', 'wms')
        #rlayer.isValid()

        #create a groop for xyz layers
        root = QgsProject.instance().layerTreeRoot()
        group = root.findGroup('Local tiles')
        QgsProject.instance().addMapLayer(rlayer)
        group.insertChildNode(0, QgsLayerTreeLayer(rlayer))

        return {self.OUTPUT: [outfolder, full_path, prj_file]}

    def uncheckLayers(self, layers):
        for lay in layers:
            node = QgsProject.instance().layerTreeRoot().findLayer(lay)
            if node:
                node.setItemVisibilityChecked(False)

    def checkLayers(self, layers):
        for lay in layers:
            node = QgsProject.instance().layerTreeRoot().findLayer(lay)
            if node:
                node.setItemVisibilityChecked(True)
     
    def setProgressRange(self, message, value):
        self.progressBar.setFormat(message)
        self.progressBar.setRange(0, value)

    def updateProgress(self):
        self.progressBar.setValue(self.progressBar.value() + 1)

    def processInterrupted(self):
        self.stopProcessing()

    def processFinished(self):
        self.stopProcessing()

    def stopProcessing(self):
        if self.workThread is not None:
            self.workThread.stop()
            self.workThread = None

    def name(self):
        return 'Get tiles'

    def icon(self):
        return QIcon(os.path.dirname(__file__) + '/gettiles.png')

    def displayName(self):
        return self.name()

    def group(self):
        return self.groupId()

    def groupId(self):
        return ''

    def createInstance(self):
        return GetTilesProcessingAlgorithm()