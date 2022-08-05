# -*- coding: utf-8 -*-

def classFactory(iface):
    from .gettiles import GetTilesPlugin
    return GetTilesPlugin(iface)
