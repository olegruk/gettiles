# -*- coding: utf-8 -*-

#******************************************************************************
#
# QMetaTiles
# ---------------------------------------------------------
# Generates tiles (using metatiles) from a QGIS project
#
# Copyright (C) 2015 we-do-IT (info@we-do-it.com)
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
import sqlite3
import zipfile
import shutil

from qgis.PyQt.QtCore import QDir, QTemporaryFile, QByteArray, QBuffer, QIODevice
#from qgis.PyQt.QtGui import *

from .mbutils import mbtiles_setup, mbtiles_connect, optimize_connection, optimize_database

class DirectoryWriter:
    def __init__(self, outputPath, rootDir, tmsConvention):
        self.output = outputPath
        self.rootDir = rootDir
        self.tmsConvention = tmsConvention

    def writeTile(self, tile, image, format, quality):
        path = '%s/%s/%s' % (self.rootDir, tile.z, tile.x)
        dirPath = '%s/%s' % (self.output.absoluteFilePath(), path)
        QDir().mkpath(dirPath)
        y = tile.y
        if self.tmsConvention:
            y = tile.y_tms
        image.save('%s/%s.%s' % (dirPath, y, format.lower()), format, quality)

    def finalize(self, temp_folder = None):
        pass

class ZipWriter:
    def __init__(self, outputPath, rootDir, tmsConvention):
        self.output = outputPath
        self.rootDir = rootDir
        self.tmsConvention = tmsConvention
        self.zipFile = zipfile.ZipFile(str(self.output.absoluteFilePath()), 'w')
        self.tempFile = QTemporaryFile()
        self.tempFile.setAutoRemove(False)
        self.tempFile.open(QIODevice.WriteOnly)
        self.tempFileName = self.tempFile.fileName()
        self.tempFile.close()

    def writeTile(self, tile, image, format, quality):
        path = '%s/%s/%s' % (self.rootDir, tile.z, tile.x)
        image.save(self.tempFileName, format, quality)
        y = tile.y
        if self.tmsConvention:
            y = tile.y_tms
        tilePath = '%s/%s.%s' % (path, y, format.lower())
        self.zipFile.write(self.tempFileName, tilePath)

    def finalize(self, temp_folder = None):
        self.tempFile.close()
        self.tempFile.remove()
        self.zipFile.close()
        if temp_folder:
            shutil.rmtree(temp_folder)

class MBTilesWriter:
    def __init__(self, outputPath, rootDir, tmsConvention):
        self.output = outputPath
        self.rootDir = rootDir
        self.tmsConvention = tmsConvention

        self.connection = mbtiles_connect(unicode(self.output.absoluteFilePath()),False)
        self.cursor = self.connection.cursor()
        optimize_connection(self.cursor)
        mbtiles_setup(self.cursor)

    def writeTile(self, tile, image, format, quality):
        data = QByteArray()
        buff = QBuffer(data)
        image.save(buff, format, quality)
        y = tile.y
        if self.tmsConvention:
            y = tile.y_tms
        self.cursor.execute('''INSERT INTO tiles(zoom_level, tile_column, tile_row, tile_data) VALUES (?, ?, ?, ?);''', (tile.z, tile.x, y, sqlite3.Binary(buff.data())))
        buff.close()

    def finalize(self, temp_folder = None):
        optimize_database(self.connection,False)
        self.connection.commit()
        self.connection.close()
        self.cursor = None
        if temp_folder:
            shutil.rmtree(temp_folder)

class ShrinkImage:
    def __init__(self, outputPath, rootDir, json=False):
        self.output = outputPath
        self.rootDir = rootDir

    def shrink(self, tile, quality):
        path = '%s/%s/%s' % (self.rootDir, tile.z, tile.x)
        dirPath = '%s/%s' % (self.output.absoluteFilePath(), path)
        im = Image.open('%s/%s.png' % (dirPath, tile.y))
        im.load()
        alpha = im.split()[-1]
        im = im.convert('RGB').convert('P', palette=Image.ADAPTIVE, colors=255)
        mask = Image.eval(alpha, lambda a: 255 if a <=128 else 0)
        im.paste(255, mask)
        im.save('%s/%s.png' % (dirPath, tile.y), transparency=255, quality= quality)

    def finalize(self):
        pass