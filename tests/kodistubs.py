"""Minimal stand-ins for the Kodi Python modules, recording what the scraper hands back."""
import sys
import types

LOGDEBUG, LOGINFO, LOGWARNING, LOGERROR = 0, 1, 2, 3

logged = []
added = {}
ended = {}
resolved = {}


def reset():
    logged.clear()
    added.clear()
    ended.clear()
    resolved.clear()


class ListItem:
    def __init__(self, label="", label2="", path="", offscreen=False):
        self.label = label
        self.properties = {}

    def setProperty(self, key, value):
        self.properties[key] = value

    def getProperty(self, key):
        return self.properties.get(key, "")

    def getLabel(self):
        return self.label


class Addon:
    settings = {}

    def __init__(self, id=""):
        self.id = id

    def getSetting(self, key):
        return self.settings.get(key, "")

    def getAddonInfo(self, key):
        return {"id": self.id, "path": "", "profile": ""}.get(key, "")


def log(msg, level=LOGDEBUG):
    logged.append((level, msg))


def addDirectoryItem(handle, url, listitem, isFolder=False, totalItems=0):
    added.setdefault(handle, []).append((url, listitem, isFolder))
    return True


def endOfDirectory(handle, succeeded=True, updateListing=False, cacheToDisc=True):
    ended[handle] = succeeded


def setResolvedUrl(handle, succeeded, listitem):
    resolved[handle] = (succeeded, listitem)


def translatePath(path):
    return path


def install():
    xbmc = types.ModuleType("xbmc")
    xbmc.log = log
    xbmc.LOGDEBUG, xbmc.LOGINFO, xbmc.LOGWARNING, xbmc.LOGERROR = LOGDEBUG, LOGINFO, LOGWARNING, LOGERROR
    xbmcgui = types.ModuleType("xbmcgui")
    xbmcgui.ListItem = ListItem
    xbmcplugin = types.ModuleType("xbmcplugin")
    xbmcplugin.addDirectoryItem = addDirectoryItem
    xbmcplugin.endOfDirectory = endOfDirectory
    xbmcplugin.setResolvedUrl = setResolvedUrl
    xbmcaddon = types.ModuleType("xbmcaddon")
    xbmcaddon.Addon = Addon
    xbmcvfs = types.ModuleType("xbmcvfs")
    xbmcvfs.translatePath = translatePath
    for module in (xbmc, xbmcgui, xbmcplugin, xbmcaddon, xbmcvfs):
        sys.modules[module.__name__] = module
