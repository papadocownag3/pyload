#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
    This program is free software; you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation; either version 3 of the License,
    or (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
    See the GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program; if not, see <http://www.gnu.org/licenses/>.
    
    @author: mkaay
    @version: v0.3.1
"""

import sys

from time import sleep

from PyQt4.QtCore import *
from PyQt4.QtGui import *

from uuid import uuid4 as uuid
import re
import gettext
from os.path import basename, dirname, join

from module.gui.ConnectionManager import *
from module.gui.connector import *
from module.gui.MainWindow import *
from module.gui.PWInputWindow import *
from module.gui.Queue import *
from module.gui.Collector import *
from module.gui.XMLParser import *

class main(QObject):
    def __init__(self):
        """
            main setup
        """
        QObject.__init__(self)
        self.app = QApplication(sys.argv)
        self.init(True)
    
    def init(self, first=False):
        """
            set main things up
        """
        self.parser = XMLParser("module/config/gui.xml", "module/config/gui_default.xml")
        lang = self.parser.xml.elementsByTagName("language").item(0).toElement().text()
        if not lang:
            parser = XMLParser("module/config/gui_default.xml")
            lang = parser.xml.elementsByTagName("language").item(0).toElement().text()

        translation = gettext.translation("pyLoadGui", join(dirname(__file__), "locale"), languages=[str(lang)])
        translation.install(unicode=(True if sys.stdout.encoding.lower().startswith("utf") else False))

        self.mainWindow = MainWindow()
        self.pwWindow = PWInputWindow()
        self.connWindow = ConnectionManager()
        self.connector = connector()
        self.mainloop = self.Loop(self)
        self.connectSignals()
        
        self.checkClipboard = False
        default = self.refreshConnections()
        self.connData = None
        self.captchaProcessing = False
        if not first:
            self.connWindow.show()
        else:
            self.connWindow.edit.setData(default)
            data = self.connWindow.edit.getData()
            self.slotConnect(data)
    
    def startMain(self):
        """
            start all refresh threads and show main window
        """
        if not self.connector.canConnect():
            self.init()
            return
        self.connector.start()
        sleep(1)
        self.restoreMainWindow()
        self.mainWindow.show()
        self.initQueue()
        self.initPackageCollector()
        self.initLinkCollector()
        self.mainloop.start()
        self.clipboard = self.app.clipboard()
        self.connect(self.clipboard, SIGNAL('dataChanged()'), self.slotClipboardChange)
        self.mainWindow.actions["clipboard"].setChecked(self.checkClipboard)
    
    def stopMain(self):
        """
            stop all refresh threads and hide main window
        """
        self.disconnect(self.clipboard, SIGNAL('dataChanged()'), self.slotClipboardChange)
        self.mainloop.stop()
        self.connector.stop()
        self.mainWindow.saveWindow()
        self.mainWindow.hide()
        self.queue.stop()
        self.mainloop.wait()
        self.connector.wait()
        self.queue.wait()
    
    def connectSignals(self):
        """
            signal and slot stuff, yay!
        """
        self.connect(self.connector, SIGNAL("error_box"), self.slotErrorBox)
        self.connect(self.connWindow, SIGNAL("saveConnection"), self.slotSaveConnection)
        self.connect(self.connWindow, SIGNAL("removeConnection"), self.slotRemoveConnection)
        self.connect(self.connWindow, SIGNAL("connect"), self.slotConnect)
        self.connect(self.pwWindow, SIGNAL("ok"), self.slotPasswordTyped)
        self.connect(self.pwWindow, SIGNAL("cancel"), self.quit)
        self.connect(self.mainWindow, SIGNAL("connector"), self.slotShowConnector)
        self.connect(self.mainWindow, SIGNAL("addLinks"), self.slotAddLinks)
        self.connect(self.mainWindow, SIGNAL("addPackage"), self.slotAddPackage)
        self.connect(self.mainWindow, SIGNAL("setDownloadStatus"), self.slotSetDownloadStatus)
        self.connect(self.mainWindow, SIGNAL("saveMainWindow"), self.slotSaveMainWindow)
        self.connect(self.mainWindow, SIGNAL("pushPackageToQueue"), self.slotPushPackageToQueue)
        self.connect(self.mainWindow, SIGNAL("restartDownload"), self.slotRestartDownload)
        self.connect(self.mainWindow, SIGNAL("removeDownload"), self.slotRemoveDownload)
        self.connect(self.mainWindow, SIGNAL("addContainer"), self.slotAddContainer)
        self.connect(self.mainWindow, SIGNAL("stopAllDownloads"), self.slotStopAllDownloads)
        self.connect(self.mainWindow, SIGNAL("setClipboardStatus"), self.slotSetClipboardStatus)
        self.connect(self.mainWindow, SIGNAL("changePackageName"), self.slotChangePackageName)
        self.connect(self.mainWindow, SIGNAL("pullOutPackage"), self.slotPullOutPackage)
        self.connect(self.mainWindow.captchaDock, SIGNAL("done"), self.slotCaptchaDone)
    
    def slotShowConnector(self):
        """
            emitted from main window (menu)
            hide the main window and show connection manager
            (to switch to other core)
        """
        self.stopMain()
        self.init()
    
    def quit(self):
        """
            quit gui
        """
        self.app.quit()
    
    def loop(self):
        """
            start application loop
        """
        sys.exit(self.app.exec_())
    
    def slotErrorBox(self, msg):
        """
            display a nice error box
        """
        msgb = QMessageBox(QMessageBox.Warning, "Error", msg)
        msgb.exec_()
    
    def initPackageCollector(self):
        """
            init the package collector view
            * columns
            * selection
            * refresh thread
            * drag'n'drop
        """
        view = self.mainWindow.tabs["collector"]["package_view"]
        view.setColumnCount(1)
        view.setHeaderLabels(["Name"])
        view.setSelectionBehavior(QAbstractItemView.SelectRows)
        view.setSelectionMode(QAbstractItemView.ExtendedSelection)
        def dropEvent(klass, event):
            event.setDropAction(Qt.CopyAction)
            event.accept()
            view = event.source()
            if view == klass:
                items = view.selectedItems()
                for item in items:
                    if not hasattr(item.parent(), "getPackData"):
                        continue
                    target = view.itemAt(event.pos())
                    if not hasattr(target, "getPackData"):
                        target = target.parent()
                    klass.emit(SIGNAL("droppedToPack"), target.getPackData()["id"], item.getFileData()["id"])
                event.accept()
                return
            items = view.selectedItems()
            for item in items:
                row = view.indexOfTopLevelItem(item)
                view.takeTopLevelItem(row)
        def dragEvent(klass, event):
            view = event.source()
            dragOkay = False
            items = view.selectedItems()
            for item in items:
                if hasattr(item, "_data"):
                    if item._data["id"] == "fixed" or item.parent()._data["id"] == "fixed":
                        dragOkay = True
                else:
                    dragOkay = True
            if dragOkay:
                event.accept()
            else:
                event.ignore()
        view.dropEvent = dropEvent
        view.dragEnterEvent = dragEvent
        view.setDragEnabled(True)
        view.setDragDropMode(QAbstractItemView.DragDrop)
        view.setDropIndicatorShown(True)
        view.setDragDropOverwriteMode(True)
        self.connect(view, SIGNAL("droppedToPack"), self.slotAddFileToPackage)
        self.packageCollector = PackageCollector(view, self.connector)
    
    def initLinkCollector(self):
        """
            init the link collector
            * refresh thread
        """
        self.linkCollector = LinkCollector(self.mainWindow.tabs["collector"]["package_view"], self.packageCollector.linkCollector, self.connector)
    
    def initQueue(self):
        """
            init the queue view
            * columns
            * refresh thread
            * progressbar
        """
        view = self.mainWindow.tabs["queue"]["view"]
        view.setColumnCount(4)
        view.setHeaderLabels([_("Name"), _("Plugin"), _("Status"), _("Progress")])
        view.setColumnWidth(0, 300)
        view.setColumnWidth(1, 100)
        view.setColumnWidth(2, 200)
        view.setColumnWidth(3, 100)
        self.queue = Queue(view, self.connector)
        delegate = QueueProgressBarDelegate(view, self.queue)
        view.setItemDelegateForColumn(3, delegate)
        self.queue.start()
    
    def refreshServerStatus(self):
        """
            refresh server status and overall speed in the status bar
        """
        status = self.connector.getServerStatus()
        if status["pause"]:
            status["status"] = _("Paused")
        else:
            status["status"] = _("Running")
        status["speed"] = int(status["speed"])
        text = _("Status: %(status)s | Speed: %(speed)s kb/s") % status
        self.mainWindow.actions["toggle_status"].setChecked(not status["pause"])
        self.mainWindow.serverStatus.setText(text)
    
    def refreshLog(self):
        """
            update log window
        """
        offset = self.mainWindow.tabs["log"]["text"].logOffset
        lines = self.connector.getLog(offset)
        if not lines:
            return
        self.mainWindow.tabs["log"]["text"].logOffset += len(lines)
        for line in lines:
            self.mainWindow.tabs["log"]["text"].emit(SIGNAL("append(QString)"), line)
        cursor = self.mainWindow.tabs["log"]["text"].textCursor()
        cursor.movePosition(QTextCursor.End, QTextCursor.MoveAnchor)
        self.mainWindow.tabs["log"]["text"].setTextCursor(cursor)
    
    def updateAvailable(self):
        """
            update notification
        """
        status = self.connector.updateAvailable()
        if status:
            self.mainWindow.statusbar.emit(SIGNAL("showMsg"), _("Update Available"))
        else:
            self.mainWindow.statusbar.emit(SIGNAL("showMsg"), "")
    
    def getConnections(self):
        """
            parse all connections in the config file
        """
        connectionsNode = self.parser.xml.elementsByTagName("connections").item(0)
        if connectionsNode.isNull():
            raise Exception("null")
        connections = self.parser.parseNode(connectionsNode)
        ret = []
        for conn in connections:
            data = {}
            data["type"] = conn.attribute("type", "remote")
            data["default"] = conn.attribute("default", "False")
            data["id"] = conn.attribute("id", uuid().hex)
            if data["default"] == "True":
                data["default"] = True
            else:
                data["default"] = False
            subs = self.parser.parseNode(conn, "dict")
            if not subs.has_key("name"):
                data["name"] = _("Unnamed")
            else:
                data["name"] = subs["name"].text()
            if data["type"] == "remote":
                if not subs.has_key("server"):
                    continue
                else:
                    data["host"] = subs["server"].text()
                    data["ssl"] = subs["server"].attribute("ssl", "False")
                    if data["ssl"] == "True":
                        data["ssl"] = True
                    else:
                        data["ssl"] = False
                    data["user"] = subs["server"].attribute("user", "admin")
                    data["port"] = int(subs["server"].attribute("port", "7227"))
            ret.append(data)
        return ret
    
    def slotSaveConnection(self, data):
        """
            save connection to config file
        """
        connectionsNode = self.parser.xml.elementsByTagName("connections").item(0)
        if connectionsNode.isNull():
            raise Exception("null")
        connections = self.parser.parseNode(connectionsNode)
        connNode = self.parser.xml.createElement("connection")
        connNode.setAttribute("default", str(data["default"]))
        connNode.setAttribute("type", data["type"])
        connNode.setAttribute("id", data["id"])
        nameNode = self.parser.xml.createElement("name")
        nameText = self.parser.xml.createTextNode(data["name"])
        nameNode.appendChild(nameText)
        connNode.appendChild(nameNode)
        if data["type"] == "remote":
            serverNode = self.parser.xml.createElement("server")
            serverNode.setAttribute("ssl", data["ssl"])
            serverNode.setAttribute("user", data["user"])
            serverNode.setAttribute("port", data["port"])
            hostText = self.parser.xml.createTextNode(data["host"])
            serverNode.appendChild(hostText)
            connNode.appendChild(serverNode)
        found = False
        for c in connections:
            cid = c.attribute("id", "None")
            if str(cid) == str(data["id"]):
                found = c
                break
        if found:
            connectionsNode.replaceChild(connNode, found)
        else:
            connectionsNode.appendChild(connNode)
        self.parser.saveData()
        self.refreshConnections()
    
    def slotRemoveConnection(self, data):
        """
            remove connection from config file
        """
        connectionsNode = self.parser.xml.elementsByTagName("connections").item(0)
        if connectionsNode.isNull():
            raise Exception("null")
        connections = self.parser.parseNode(connectionsNode)
        found = False
        for c in connections:
            cid = c.attribute("id", "None")
            if str(cid) == str(data["id"]):
                found = c
                break
        if found:
            connectionsNode.removeChild(found)
        self.parser.saveData()
        self.refreshConnections()
    
    def slotConnect(self, data):
        """
            slot: connect button in connectionmanager
            show password window if remote connection or start connecting
        """
        self.connWindow.hide()
        self.connData = data
        if data["type"] == "local":
            self.slotPasswordTyped("")
        else:
            self.pwWindow.show()
    
    def slotPasswordTyped(self, pw):
        """
            connect to a core
            if connection is local, parse the core config file for data
            set up connector, show main window
        """
        data = self.connData
        data["password"] = pw
        if not data["type"] == "remote":
            coreparser = XMLParser("module/config/core.xml", "module/config/core_default.xml")
            sections = coreparser.parseNode(coreparser.root, "dict")
            conf = coreparser.parseNode(sections["remote"], "dict")
            ssl = coreparser.parseNode(sections["ssl"], "dict")
            data["port"] = conf["port"].text()
            data["user"] = conf["username"].text()
            data["password"] = conf["password"].text()
            data["host"] = "127.0.0.1"
            if str(ssl["activated"].text()).lower() == "true":
                data["ssl"] = True
            else:
                data["ssl"] = False
        if data["ssl"]:
            data["ssl"] = "s"
        else:
            data["ssl"] = ""
        server_url = "http%(ssl)s://%(user)s:%(password)s@%(host)s:%(port)s/" % data
        self.connector.setAddr(str(server_url))
        self.startMain()
    
    def refreshConnections(self):
        """
            reload connetions and display them
        """
        self.parser.loadData()
        conns = self.getConnections()
        self.connWindow.emit(SIGNAL("setConnections(connections)"), conns)
        for conn in conns:
            if conn["default"]:
                return conn
        return None
    
    def slotAddLinks(self, links):
        """
            emitted from main window
            add urls to the collector
        """
        self.connector.addURLs(links)
    
    def slotSetDownloadStatus(self, status):
        """
            toolbar start/pause slot
        """
        self.connector.setPause(not status)
    
    def slotAddPackage(self, name, ids):
        """
            emitted from main window
            add package to the collector
        """
        packid = self.connector.newPackage(str(name))
        for fileid in ids:
            self.connector.addFileToPackage(fileid, packid)
        self.mainWindow.lastAddedID = packid
    
    def slotAddFileToPackage(self, pid, fid):
        """
            emitted from collector view after a drop action
        """
        self.connector.addFileToPackage(fid, pid)
    
    def slotAddContainer(self, path):
        """
            emitted from main window
            add container
        """
        filename = basename(path)
        type = "".join(filename.split(".")[-1])
        fh = open(path, "r")
        content = fh.read()
        fh.close()
        self.connector.uploadContainer(filename, type, content)
    
    def slotSaveMainWindow(self, state, geo):
        """
            save the window geometry and toolbar/dock position to config file
        """
        mainWindowNode = self.parser.xml.elementsByTagName("mainWindow").item(0)
        if mainWindowNode.isNull():
            mainWindowNode = self.parser.xml.createElement("mainWindow")
            self.parser.root.appendChild(mainWindowNode)
        stateNode = mainWindowNode.toElement().elementsByTagName("state").item(0)
        geoNode = mainWindowNode.toElement().elementsByTagName("geometry").item(0)
        newStateNode = self.parser.xml.createTextNode(state)
        newGeoNode = self.parser.xml.createTextNode(geo)
        
        stateNode.removeChild(stateNode.firstChild())
        geoNode.removeChild(geoNode.firstChild())
        stateNode.appendChild(newStateNode)
        geoNode.appendChild(newGeoNode)
        
        self.parser.saveData()
    
    def restoreMainWindow(self):
        """
            load and restore main window geometry and toolbar/dock position from config
        """
        mainWindowNode = self.parser.xml.elementsByTagName("mainWindow").item(0)
        if mainWindowNode.isNull():
            return
        nodes = self.parser.parseNode(mainWindowNode, "dict")
        
        state = str(nodes["state"].text())
        geo = str(nodes["geometry"].text())
        
        self.mainWindow.restoreWindow(state, geo)
        self.mainWindow.captchaDock.hide()
    
    def slotPushPackageToQueue(self, id):
        """
            emitted from main window
            push the collector package to queue
        """
        self.connector.pushPackageToQueue(id)
    
    def slotRestartDownload(self, id, isPack):
        """
            emitted from main window
            restart download
        """
        if isPack:
            self.connector.restartPackage(id)
        else:
            self.connector.restartFile(id)
    
    def slotRemoveDownload(self, id, isPack):
        """
            emitted from main window
            remove download
        """
        if isPack:
            self.connector.removePackage(id)
        else:
            self.connector.removeFile(id)
    
    def slotStopAllDownloads(self):
        """
            emitted from main window
            stop all running downloads
        """
        self.connector.stopAllDownloads()
    
    def slotClipboardChange(self):
        """
            called if clipboard changes
        """
        if self.checkClipboard:
            text = self.clipboard.text()
            pattern = re.compile(r"(http|https)://[a-z0-9]+([\-\.]{1}[a-z0-9]+)*\.[a-z]{2,5}(([0-9]{1,5})?/.*)?")
            matches = pattern.finditer(text)
            for match in matches:
                self.slotAddLinks([str(match.group(0))])
    
    def slotSetClipboardStatus(self, status):
        """
            set clipboard checking
        """
        self.checkClipboard = status
    
    def slotChangePackageName(self, pid, name):
        """
            package name edit finished
        """
        self.connector.setPackageName(pid, str(name))
    
    def slotPullOutPackage(self, pid, isPack):
        """
            pull package out of the queue
        """
        if isPack:
            self.connector.pullOutPackage(pid)
    
    def checkCaptcha(self):
        if self.connector.captchaWaiting() and self.mainWindow.captchaDock.isFree():
            cid, img, imgType = self.connector.getCaptcha()
            self.mainWindow.captchaDock.emit(SIGNAL("setTask"), cid, str(img), imgType)
    
    def slotCaptchaDone(self, cid, result):
        self.connector.setCaptchaResult(str(cid), str(result))
    
    def pullEvents(self):
        events = self.connector.getEvents()
        for event in events:
            if event[1] == "queue":
                self.queue.addEvent(event)
            elif event[1] == "packages":
                self.packageCollector.addEvent(event)
            elif event[1] == "collector":
                self.linkCollector.addEvent(event)
    
    class Loop(QThread):
        """
            main loop (not application loop)
        """
        
        def __init__(self, parent):
            QThread.__init__(self)
            self.parent = parent
            self.running = True
        
        def run(self):
            while self.running:
                sleep(1)
                self.update()
        
        def update(self):
            """
                methods to call
            """
            self.parent.refreshServerStatus()
            self.parent.refreshLog()
            self.parent.updateAvailable()
            self.parent.checkCaptcha()
            self.parent.pullEvents()
        
        def stop(self):
            self.running = False

if __name__ == "__main__":
    app = main()
    app.loop()

