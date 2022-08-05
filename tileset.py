# -*- coding: utf-8 -*-

#******************************************************************************
#
# QMetaTiles
# ---------------------------------------------------------
# Generates tiles (using metatiles) from a QGIS project
#
# Copyright (C) 2015-2019 we-do-IT (info@we-do-it.com)
# Copyright (C) 2012-2014 NextGIS (info@nextgis.org)
#
# This source is free software; you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free
# Software Foundation, either version 2 of the License, or (at your option)
# any later version.
#
# This code is distributed in the hope that it will be useful, but WITHOUT ANY
# WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE. See the GNU General Public License for more
# details.
#
# A copy of the GNU General Public License is available on the World Wide Web
# at <http://www.gnu.org/licenses/>. You can also obtain it by writing
# to the Free Software Foundation, 51 Franklin Street, Suite 500 Boston,
# MA 02110-1335 USA.
#
#******************************************************************************

import os
import time
import json
import codecs
import tempfile
from string import Template
from qgis.core import QgsCoordinateTransform, QgsCoordinateReferenceSystem, QgsMapSettings, QgsProject, QgsVectorFileWriter, QgsMapRendererCustomPainterJob, QgsFeatureRequest
from qgis.utils import Qgis
from qgis.PyQt.QtGui import QColor, QImage, QPainter
from qgis.PyQt.QtCore import QFile, QDir, QIODevice, QSize

from .tile import Tile
from .metatile import Metatile
from .writers import DirectoryWriter, ZipWriter, MBTilesWriter
import configparser
from datetime import datetime

class TileSet:
    '''
    A tileset is a collection of tiles in multiple zoom levels that span a given extent, through a specified
    range of zooms. It provides all the functionality to export the via single tiles or metatiled tiles.
    '''
    def __init__(self, layers, extents, minZoom, maxZoom, tile_width, tile_height, transp, quality, format, outputPath, rootDir, antialiasing, tmsConvention, mapUrl, viewer, metatile, metatile_size, metatile_buffer, llg_features):

        #  use the info from the user interface.
        self.layers = layers
        self.extents = extents
        self.minZoom = minZoom
        self.maxZoom = maxZoom
        self.zoom_ranges = range(minZoom, maxZoom + 1)
        self.output = outputPath
        self.tile_width = tile_width
        self.tile_height = tile_height
        if rootDir:
            self.rootDir = rootDir
        else:
            self.rootDir = 'tileset_%s' % str(time.time()).split('.')[0]
        self.antialias = antialiasing
        self.tmsConvention = tmsConvention
        self.format = format
        self.quality = quality
        self.mapurl = mapUrl
        self.viewer = viewer
        if self.output.isDir():
            self.mode = 'DIR'
        elif self.output.suffix().lower() == "zip":
            self.mode = 'ZIP'
        elif self.output.suffix().lower() == 'mbtiles':
            self.mode = 'MBTILES'
            self.tmsConvention = True
        self.metatile = metatile
        self.metatile_size = metatile_size
        self.metatile_buffer = metatile_buffer
        self.llg_features = llg_features
        self.temp_folder = None

        #  set the background colour of the image.
        if transp == 0:
            self.transparency = 255
        elif transp == 100:
            self.transparency = 0
        else:
            self.transparency = 255 - (int( float(transp) / 100.0 * 256.0 ) - 1)
        # import pydevd; pydevd.settrace(port=5678)
        myRed = QgsProject.instance().readNumEntry('Gui', '/CanvasColorRedPart', 255)[0]
        myGreen = QgsProject.instance().readNumEntry('Gui', '/CanvasColorGreenPart', 255)[0]
        myBlue = QgsProject.instance().readNumEntry('Gui', '/CanvasColorBluePart', 255)[0]
        self.color = QColor(myRed, myGreen, myBlue, self.transparency)
        image = QImage(tile_width, tile_height, QImage.Format_ARGB32)

        #  set the render settings.
        self.settings = QgsMapSettings()
        self.settings.setLayers(self.layers)
        self.settings.setBackgroundColor(self.color)
        self.settings.setOutputDpi(image.logicalDpiX())
        self.settings.setDestinationCrs(QgsCoordinateReferenceSystem('EPSG:3857'))
        self.settings.setLayers(self.layers)
        self.settings.setFlag(QgsMapSettings.UseAdvancedEffects, True)
        self.settings.setFlag(QgsMapSettings.ForceVectorOutput, True)
        self.settings.setFlag(QgsMapSettings.DrawLabeling, True)
        if self.antialias:
            self.settings.setFlag(QgsMapSettings.Antialiasing, True)

        #  set up a projection transformation for conveting extents etc.
        self.projector = QgsCoordinateTransform(QgsCoordinateReferenceSystem('EPSG:4326'), QgsCoordinateReferenceSystem('EPSG:3857'), QgsProject.instance())
        self.tiles = []

    def run(self):
        """
        A function to run the main functions of the class. This is a duplication to a certain extent of that
        found in tilingthread. This would be of use running the process from a script, without the GUI.
        Doesn't give any progress, useful for debugging as it doesn't use a seperate thread.
        """

        #  sets the writer and writes a .mapurl or leaflet file if necessary.
        self.set_writer()
        #  if selected, export the vector features and metadata associated with the tileset
        if self.llg_features and self.mode == 'DIR':
            self.write_llg_conf_metadata()
            self.export_features()
        #  first stage of the tile writing process.
        #  generate a list of tiles.
        self.count_tiles(self.get_first_tile())
        #  test if this is a metatiled job or not.
        if self.metatile:
            #  work out the metatiles needed to cover the area.
            self.tileset_ranges()
            self.tileset_size()
            metatiles = self.count_metatiles()
            #  render and slice all the metatiles
            for metatile in metatiles:
                self.render_metatile(metatile)
                metatile.slice()
        #  process a standard (non-metatiled) job
        else:
            for tile in self.tiles:
                self.render_tile(tile)
        self.writer.finalize(self.temp_folder)

    def get_first_tile(self):
        return Tile(0, 0, 0)

    def render(self):
        """
        A function that renders a tile or a metatile, based on the extents and configuration in settings.
        """
        #  set an empty empty image object and attach to color.
        img = QImage(self.settings.outputSize(), QImage.Format_ARGB32)
        img.fill(0) #resolves with tiles overwriting each other multiple times
        p = QPainter()
        p.begin(img)
        # rendering
        job = QgsMapRendererCustomPainterJob(self.settings, p)
        job.renderSynchronously()   # !important use this method so that TileLayerPlugin layer is rendered correctly.
        p.end()
        return img

    def render_tile(self, tile):
        """
        Renders a tile.
        """
        self.settings.setExtent(self.projector.transform(tile.toRectangle()))
        self.settings.setOutputSize(QSize(self.tile_width, self.tile_height))
        img = self.render()
        self.writer.writeTile(tile, img, self.format, self.quality)

    def render_metatile(self, metatile):
        """
        Renders a metatile.
        """
        self.settings.setExtent( self.projector.transform(metatile.rectangle()))
        self.settings.setOutputSize(QSize(metatile.width, metatile.height))
        img = self.render()
        metatile.write_metatile(img, self.format, self.quality)

    def set_writer(self):
        """
        Set the output writer type and write a mapurl and/or leaflet viewer.
        """
        if self.mode == 'DIR':
            self.writer = DirectoryWriter(self.output, self.rootDir, self.tmsConvention)
            if self.mapurl:
                self.writeMapurlFile()
            if self.viewer:
                self.writeLeafletViewer()
            QDir().mkpath(os.path.join(self.output.absoluteFilePath(), self.rootDir))
        elif self.mode == 'ZIP':
            self.writer = ZipWriter(self.output, self.rootDir, self.tmsConvention)
            self.temp_folder = os.path.join(tempfile.mkdtemp(), self.rootDir)
            QDir().mkpath(self.temp_folder)
        elif self.mode == 'MBTILES':
            self.temp_folder = os.path.join(tempfile.mkdtemp(), self.rootDir)
            QDir().mkpath(self.temp_folder)
            self.writer = MBTilesWriter(self.output, self.rootDir, self.tmsConvention)

    def export_features(self):
        """
        A function to export the features for all vector layers into a folder named JSON. This can be used for
        use in the LatLonGO mobile product.
        """
        self.json_path = os.path.join(self.output.absoluteFilePath(), self.rootDir, 'json')
        QDir().mkpath(self.json_path)
        for layer in self.layers:
            ## test if the layer has features and that it is a vector layer.
            if  layer.type() == 0:
                if layer.featureCount() > 0:
                    ## convert the extent into the same coordinate system as the layer.
                    tmp_extent = QgsCoordinateTransform(QgsCoordinateReferenceSystem('EPSG:4326'), layer.crs(), QgsProject.instance()).transform(self.extents)
                    ## filter by the extent used
                    request = QgsFeatureRequest(tmp_extent)
                    features = layer.getFeatures(request)
                    ## set the filepath
                    filePath = os.path.join(self.json_path, layer.name())
                    ## create an instance of an empty QgsVectorFileWriter
                    writer = QgsVectorFileWriter(filePath, 'utf-8', layer.fields(), layer.wkbType(), QgsCoordinateReferenceSystem('EPSG:4326'), 'GeoJSON')
                    ## write features into the writer
                    trans = QgsCoordinateTransform(layer.crs(), QgsCoordinateReferenceSystem('EPSG:4326'), QgsProject.instance())
                    for feat in features:
                        feat.geometry().transform(trans)
                        writer.addFeature(feat)
                    ## push the writer to file
                    del writer

    def count_tiles(self, tile):
        """
        Recursive function to find all tiles within the extents and zoom range of this tileset.
        """

        if not self.extents.intersects(tile.toRectangle()):
            return
        if self.minZoom <= tile.z and tile.z <= self.maxZoom:
            self.tiles.append(tile)
        if tile.z < self.maxZoom:
            for x in range(2 * tile.x, 2 * tile.x + 2, 1):
                for y in range(2 * tile.y, 2 * tile.y + 2, 1):
                    sub_tile = Tile(x, y, tile.z + 1)
                    self.count_tiles(sub_tile)

    def tileset_ranges(self):
        """
        Function to calculate the tile extents (by tile number) number in each zoom level.
        """
        all_zooms = {}
        #  loop through each zoom level.
        tiles = self.tiles
        for z in self.zoom_ranges:
            #  create a list of tiles for this zoom level
            sub_tiles = [tile for tile in tiles if tile.z == z]
            # sort the list by row number then grab the first and last (min and  max)
            sub_tiles.sort(key=lambda tile: tile.y, reverse=False)
            row_min = sub_tiles[0].y
            row_max = sub_tiles[-1].y
            # sort the list by column number then grab the first and last (min and  max)
            sub_tiles.sort(key=lambda tile: tile.x, reverse=False)
            col_min = sub_tiles[0].x
            col_max = sub_tiles[-1].x
            #  create a tuple with the 4 values
            result = ( row_min, row_max, col_min, col_max )
            #  add to this zoom level result to a dictionary.
            all_zooms[z] = result

        self.ranges = all_zooms

    def write_llg_conf_metadata(self):
        '''
        Adds some metadata used in the packing.
        '''

        # This code writes all the layers, fields and search fields (up to 9 fields) to config file as a helper.
        layer_list = []
        for layer in self.layers:
            layer_dict = {"NAME": layer.name(),
                          "FIELDS" : [ fld.name() for fld in layer.fields().toList() ],
                          "SEARCH_FIELDS" : [ fld.name() for fld in layer.fields().toList() ][:9]
                         }
            layer_list.append(layer_dict)
        layers = {"LAYERS": layer_list}

        cfg = configparser.ConfigParser()
        cfg.read(os.path.join(os.path.dirname(__file__), 'metadata.txt'))
        plugin_version = cfg.get('general', 'version')
        
        #  this code generates the metadata needed.
        metadata = {
            'map.minZoom':                          self.minZoom,
            'map.maxZoom':                          self.maxZoom,
            'map.tileSideLength':                   self.tile_width,
            'map.tileFormat':                       self.format.lower(),
            'map.type':                             'overlay',
            'map.coverage.topLeft.latitude':        self.extents.yMaximum(),
            'map.coverage.topLeft.longitude':       self.extents.xMinimum(),
            'map.coverage.bottomRight.latitude':    self.extents.yMinimum(),
            'map.coverage.bottomRight.longitude':   self.extents.xMaximum(),
            'map.coverage.center.latitude':         self.extents.center().y(),
            'map.coverage.center.longitude':        self.extents.center().x(),
            'map.shortSourceSystem':                "qgis",
            'map.longSourceSystem':                 "QGIS "+Qgis.QGIS_VERSION+", "+self.rootDir,
            'map.extractorVersion':                 plugin_version,
            'map.created':                          datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
        }
        #  combine metadata and config into one dict
        json_output = {"CONFIG": layers, "METADATA": metadata}

        #  write the json to a config file.
        self.metadata_path = os.path.join(self.output.absoluteFilePath(), self.rootDir, '{}.conf'.format(self.rootDir))
        with open(self.metadata_path, 'w') as f:
            f.seek(0)
            json.dump(json_output, f, indent=4)

    def tileset_size(self):
        '''
        Find the size of each zoom level in terms of tiles. Simple Max-Min for cols and rows.
        '''
        all_zooms = {}
        for z in self.zoom_ranges:
            tiles = self.ranges[z]
            result = {'rows': (tiles[1] - tiles[0]) + 1, 'cols': (tiles[3] - tiles[2]) + 1}
            all_zooms[z] = result
        self.sizes = all_zooms

    def buffer_extent(self, ranges):
        '''
        Function to increase the extent of the tile by a set amount, to have a tile buffer.
        '''
        row_min = ranges[0] - 1
        row_max = ranges[1] + 1
        col_min = ranges[2] - 1
        col_max = ranges[3] + 1
        return row_min, row_max, col_min, col_max

    def count_metatiles(self):

        """Function to generate all the metatiles for each zoom level, returns a list of metatiles."""

        metatiles =[]
        metatile_rows = self.metatile_size['rows']
        metatile_cols = self.metatile_size['cols']

        for z in self.zoom_ranges:
            size = self.sizes[z]
            set_range = self.ranges[z]
            buffered = False

            #  test if the metatile is bigger than the job_extent at this zoom level.
            if metatile_cols >= size['cols'] and metatile_rows >= size['rows']:
                metatiles.append(Metatile(set_range, z, buffered, self))
            else:
                row_offset = ((set_range[1] + 1) - set_range[0]) % metatile_rows
                col_offset = ((set_range[3] + 1) - set_range[2]) % metatile_cols

                # test if there are any tile rows ommitted through discrepancies between the metatile size and number of
                # rows, change region size if true to accommodate metatile
                if row_offset > 0:
                    sr = list(set_range)
                    sr[1] += row_offset
                    set_range = tuple(sr)

                # test if there are any tile columns ommitted through discrepancies between the metatile size and number
                # of columns, change region size if true to accommodate metatile
                if col_offset > 0:
                    sr = list(set_range)
                    sr[3] += col_offset
                    set_range = tuple(sr)

                #  set the initial tile before walking through the tile set.
                col_range = (set_range[2], set_range[2] + metatile_cols - 1)
                row_range = (set_range[0], set_range[0] + metatile_rows - 1)

                #  test the column range to check if it is within the tile range for this zoom level, execute if it is.
                while col_range[0] < set_range[3]:

                    #  test the row range to check if it is within the tile range for this zoom level, execute if it is.
                    while row_range[0] < set_range[1]:

                        #  get the extent for the current tile.
                        extents = (row_range[0], row_range[1], col_range[0], col_range[1])

                        # apply the buffer at this stage if specified by user.
                        if self.metatile_buffer:
                            buffered = True
                            extents = self.buffer_extent(extents)

                        #  create a Metatile instance and add it to the list.
                        metatiles.append(Metatile(extents, z, buffered, self))

                        #  move the row_range forward to the next metatile
                        row_range = (row_range[1] + 1, row_range[1] + metatile_rows)

                    #  move the col_range forward to the next metatile
                    col_range = (col_range[1] + 1, col_range[1] + metatile_cols)

                    #  reset the row back to the start again, for next run
                    row_range = (set_range[0], set_range[0] + metatile_rows - 1)
            metatile_rows = self.metatile_size['rows']
            metatile_cols = self.metatile_size['cols']
        if len(metatiles) > 0:
            if self.mode == 'DIR':
                self.metatiles_path = os.path.join(self.output.absoluteFilePath(), self.rootDir, 'metatiles')
            else:
                self.metatiles_path = os.path.join(self.temp_folder, 'metatiles')
            QDir().mkpath(self.metatiles_path)
        return metatiles

    def writeMapurlFile(self):
        filePath = '%s/%s.mapurl' % (self.output.absoluteFilePath(), self.rootDir)
        tileServer = 'tms' if self.tmsConvention else 'google'
        with open(filePath, 'w') as mapurl:
            mapurl.write('%s=%s\n' % ('url', self.rootDir + '/ZZZ/XXX/YYY.png'))
            mapurl.write('%s=%s\n' % ('minzoom', self.minZoom))
            mapurl.write('%s=%s\n' % ('maxzoom', self.maxZoom))
            mapurl.write('%s=%f %f\n' % ('center', self.extents.center().x(), self.extents.center().y()))
            mapurl.write('%s=%s\n' % ('type', tileServer))

    def writeLeafletViewer(self):
        templateFile = QFile(':/resources/viewer.html')
        if templateFile.open(QIODevice.ReadOnly | QIODevice.Text):
            viewer = MyTemplate(str(templateFile.readAll(), 'utf-8'))
            tilesDir = '%s/%s' % (self.output.absoluteFilePath(), self.rootDir)
            useTMS = 'true' if self.tmsConvention else 'false'
            substitutions = {'tilesdir': tilesDir, 'tilesext': self.format.lower(), 'tilesetname': self.rootDir, 'tms': useTMS, 'centerx': self.extents.center().x(),'centery': self.extents.center().y(),'avgzoom': (self.maxZoom + self.minZoom) / 2,'maxzoom': self.maxZoom}
            filePath = '%s/%s.html' % (self.output.absoluteFilePath(), self.rootDir)
            with codecs.open(filePath, 'w', 'utf-8') as fOut:
                fOut.write(viewer.substitute(substitutions))
            templateFile.close()

class MyTemplate(Template):
    delimiter = '@'
    def __init__(self, templateString):
        Template.__init__(self, templateString)
