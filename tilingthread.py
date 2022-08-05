# -*- coding: utf-8 -*-

from qgis.PyQt.QtCore import QThread, QMutex, pyqtSignal
from .tileset import TileSet

class TilingThread(QThread):

    rangeChanged = pyqtSignal(str, int)
    updateProgress = pyqtSignal()
    processFinished = pyqtSignal() 
    processInterrupted = pyqtSignal()

    def __init__(self, layers, extents, minZoom, maxZoom, tile_width, tile_height, transp, quality, format, outputPath, rootDir, antialiasing, tmsConvention, mapUrl, viewer, metatile, metatile_size, metatile_buffer, llg_features):

        QThread.__init__(self, QThread.currentThread())
        self.mutex = QMutex()
        self.stopMe = 0
        self.interrupted = False

        #  grab a couple of basic options needed.
        self.metatile = metatile
        self.features = llg_features

        self.tileset = TileSet(layers,
                                extents,
                                minZoom,
                                maxZoom,
                                tile_width,
                                tile_height,
                                transp,
                                quality,
                                format,
                                outputPath,
                                rootDir,
                                antialiasing,
                                tmsConvention,
                                mapUrl,
                                viewer,
                                metatile,
                                metatile_size,
                                metatile_buffer,
                                llg_features)

    def run(self):

        self.mutex.lock()
        self.stopMe = 0
        self.mutex.unlock()

        #  bring tileset into scope to save a few selfs.
        tileset = self.tileset

        #  sets the writer and writes a .mapurl or leaflet file if necessary.
        tileset.set_writer()

        #  if selected, export the vector features associated with the tileset
        if self.features and tileset.mode == 'DIR':
            self.rangeChanged.emit(self.tr('Exporting LatLonGO Features...'), 1)
            self.updateProgress.emit()
            tileset.export_features()
            tileset.write_llg_conf_metadata()

        #  generate a list of tiles.
        self.rangeChanged.emit(self.tr('Searching tiles...'), 1)
        self.updateProgress.emit()
        tileset.count_tiles(tileset.get_first_tile())

        #  test if this is a metatiled job or not.
        if self.metatile:
            #  work out the metatiles needed to cover the area.
            self.rangeChanged.emit(self.tr('Generating metatiles...'), 1)
            self.updateProgress.emit()
            tileset.tileset_ranges()
            tileset.tileset_size()
            metatiles = tileset.count_metatiles()
            #  render and slice all the metatiles
            self.rangeChanged.emit(self.tr('Rendering Metatiles: %v from %m (%p%)'), len(metatiles))
            for metatile in metatiles:
                tileset.render_metatile(metatile)
                metatile.slice()
                self.updateProgress.emit()
                self.mutex.lock()
                s = self.stopMe
                self.mutex.unlock()
                if s == 1:
                    self.interrupted = True
                    break
        #  process a standard (non-metatiled) job
        else:
            self.rangeChanged.emit(self.tr('Rendering Tiles: %v from %m (%p%)'), len(tileset.tiles))
            for tile in tileset.tiles:
                tileset.render_tile(tile)
                self.updateProgress.emit()
                self.mutex.lock()
                s = self.stopMe
                self.mutex.unlock()
                if s == 1:
                    self.interrupted = True
                    break
        tileset.writer.finalize()
        if not self.interrupted:
            self.processFinished.emit()
        else:
            self.processInterrupted.emit()

    def stop(self):
        self.mutex.lock()
        self.stopMe = 1
        self.mutex.unlock()
        QThread.wait(self)
