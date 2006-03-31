#!/usr/bin/python
# -*- coding: UTF-8 -*-

# Eigene Ausnahmen
from exceptions import *

import os, sys, time, ConfigParser, subprocess, socket

class Uploader:
    def __init__(self, request, path):
        self.request = request

        # Shorthands
        self.cfg        = self.request.cfg
        self.path       = self.request.path
        self.context    = self.request.context
        self.db         = self.request.db

        self.request.echo("Buffsize:",self.cfg["upload_bufsize"])

        self.db.clean_up_uploads() # Alte Uploads in DB löschen

        try:
            filename, bytes = self.handle_upload()
        except NoUpload:
            pass
        else:
            clientInfo = self.get_clientInfo()
            fileInfo = self.get_file_info(filename)
            self.write_info_file(clientInfo, fileInfo, filename, bytes)
            #~ self.email_notify()

        self.context["filelist"] = self.filelist()
        self.index()


    def handle_upload(self):
        """ Speichert eine gerade hochgeldadene Datei ab """
        try:
            fileObject = self.request.FILES['upload']
        except KeyError:
            # Es gibt kein Upload
            raise NoUpload

        filename = fileObject.filename

        totalBytes = self.request.environ["CONTENT_LENGTH"]

        id = self.db.insert_upload(filename, totalBytes, current_bytes = 0)

        self.request.write("<p>Upload File '%s'</p>" % filename)
        self.db.log(type="upload_start", item=filename)

        filename = os.path.join(self.cfg["upload_dir"], filename)

        bufsize = self.cfg["upload_bufsize"]
        bytesreaded = 0
        try:
            f = file(filename, 'wb')
            time_threshold = start_time = int(time.time())
            while 1:
                data = fileObject.read(bufsize)
                if not data:
                    break
                bytesreaded += len(data)
                f.write(data)

                current_time = int(time.time())
                if current_time > time_threshold:
                    self.db.update_upload(id, bytesreaded)
                    self.request.write("<p>read: %sBytes (%s)</p>" % (
                            bytesreaded, time.strftime("%H:%M:%S", time.localtime())
                        )
                    )
                    time_threshold = current_time

            self.db.update_upload(id, bytesreaded)
            end_time = time.time()
            f.close()

            performance = bytesreaded / (end_time-start_time) / 1024
            self.request.write("<h3>saved with %.2fKByes/sec.</h3>" % performance)
        except Exception, e:
            self.request.write("<h3>Can't save file: %s</h3>" % e)
            return "", 0

        self.db.log(type="upload_end", item="file: %s, size: %s" % (filename, bytesreaded))
        return filename, bytesreaded

    def email_notify(self):
        """
        Sendet eine eMail, das eine neue Datei hochgeladen wurde
        Nutzt die seperate email-Klasse
        """
        if not self.request.cfg.send_email_notify:
            return

        email().send(
            from_adress = notifer_email_from_adress,
            to_adress   = notifer_email_to_adress,
            subject     = "uploaded: '%s' from '%s'" % (
                filename, client_info
            ),
            text        = email_notify_text % {
                "client_info"   : client_info,
                "fileinfo"      : fileinfo,
                "info"          : "%s (Python v%s)" % (
                    __info__, sys.version
                ),
            }
        )

    def index(self):
        """
        Informations-Seite anzeigen
        """
        self.request.render("Upload_base")


    def filelist(self):
        try:
            dirlist = os.listdir(self.cfg["upload_dir"])
        except Exception, e:
            self.request.write("Error: Can't read filelist: %s" % e)
            return

        filelist = []
        for filename in dirlist:
            if filename.endswith(".nfo"):
                continue

            #~ if self.request.cfg.allow_download:
                #~ url = posixpath.join(
                    #~ self.request.environ.get('SCRIPT_NAME', ''),
                    #~ "download/%s" % urllib.quote_plus(filename)
                #~ )
                #~ html_part = '<a href="%s">%s</a>' % (
                    #~ url, cgi.escape(filename)
                #~ )
            #~ else:
                #~ html_part = cgi.escape(filename)

            #~ try:
            info = self.read_info_file(filename)
            filelist.append(info)
            #~ except Exception, e:
                #~ self.request.write('Error, get fileInfo: %s\n' % e)

        return filelist



    #_________________________________________________________________________


    def write_info_file(self, clientInfo, fileInfo, filename, bytesreaded):
        """ Info-Datei zur hochgeladenen Datei schreiben """
        f = file(filename+".nfo", "wU")
        config = ConfigParser.ConfigParser()
        config.add_section("info")

        config.set("info", "clientInfo", clientInfo)
        config.set("info", "filename", filename)
        config.set("info", "bytes", bytesreaded)
        config.set("info", "fileInfo", fileInfo)
        config.set("info", "uploadTime", time.strftime("%d %b %Y %H:%M:%S", time.localtime()))

        config.write(f)
        f.close()


    def read_info_file(self, filename):
        """ vorhandene Info-Datei lesen (f�r die Upload-Datei-Tabelle) """
        info = {
            "filename"      : filename,
            "size"          : -1,
        }
        infoFile = "%s.nfo" % os.path.join(self.cfg["upload_dir"], filename)
        try:
            f = file(infoFile, "rU")
        except Exception, e:
            info.update({"fileInfo": "Can't read infofile: %s" % e})
            return info

        config = ConfigParser.ConfigParser()
        config.readfp(f)
        f.close()

        info.update({
            "filename"      : filename,
            "clientInfo"    : config.get("info", "clientInfo"),
            "size"          : int(config.get("info", "bytes")),
            "fileInfo"      : config.get("info", "fileInfo"),
            "uploadTime"    : config.get("info", "uploadTime"),
        })

        return info


    #_________________________________________________________________________


    def get_clientInfo(self):
        """
        Liefert einen String mit Domain-Namen und evtl. vorhandenen Usernamen zur�ck
        """
        try:
            clientInfo = socket.getfqdn(self.request.environ["REMOTE_ADDR"])
        except Exception, e:
            clientInfo = "Error: %s" % e

        # Usernamen hinzuf�gen
        clientInfo = "%s - %s" % (self.request.environ["REMOTE_USER"], clientInfo)

        return clientInfo


    def get_file_info(self, filename):
        """ Datei Information mit Linux 'file' Befehl zusammentragen """
        if sys.platform == "win32":
            # Unter Windows gibt es keinen File-Befehl
            return "<small>(file info only available under Linux!)</small>"

        try:
            proc = subprocess.Popen(
                args        = ["file", filename],
                stdout      = subprocess.PIPE,
                stderr      = subprocess.PIPE
            )
        except Exception, e:
            return "Can't make file subprocess: %s" % e

        try:
            file_cmd_out = proc.stdout.read()
        except Exception, e:
            return "Can't read stdout from subprocess: %s" % e

        proc.stdout.close()

        try:
            file_cmd_out = file_cmd_out.split(":",1)[1]
        except Exception, e:
            return "Can't prepare String: '%s' Error: %s" % (file_cmd_out, e)

        if file_cmd_out.find("ERROR") != -1:
            # Ersatz f�r >"ERROR" in fileInfo< ;)
            return ""
        else:
            return file_cmd_out.strip()


class email:
    """
    Kleine Hilfsklasse um Text-EMails zu versenden
    """
    def send(self, from_adress, to_adress, subject, text):
        import time, smtplib
        from email.MIMEText import MIMEText

        msg = MIMEText(
            _text = text,
            _subtype = "plain",
            _charset = "UTF-8"
        )
        msg['From'] = from_adress
        msg['To'] = to_adress
        msg['Subject'] = subject
        # Datum nach RFC 2822 Internet email standard.
        msg['Date'] = time.strftime("%a, %d %b %Y %H:%M:%S +0000", time.gmtime())
        msg['User-Agent'] = "%s (Python v%s)" % (__info__, sys.version)

        s = smtplib.SMTP()
        s.connect()
        s.sendmail(msg['From'], [msg['To']], msg.as_string())
        s.close()




def index(request, path):
    Uploader(request, path)