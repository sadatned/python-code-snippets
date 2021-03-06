#!/usr/bin/python
# coding: ISO-8859-1

"""
    makes thumbs with the PIL

    Created by Jens Diemer
    
    Useable by a small "client" script, e.g.:

-------------------------------------------------------------------------------   
#!/usr/bin/python
# coding: ISO-8859-1

import sys, datetime, os

#sys.path.insert(0,"/path/to/thumb_maker/") # Please change path, if needed.

from thumb_maker import ThumbMaker, ThumbMakerCfg

ThumbMakerCfg.path_to_convert = os.getcwd()
ThumbMakerCfg.do_path_walk = False
ThumbMakerCfg.path_output = os.path.join(os.getcwd(), "Web")
ThumbMakerCfg.make_smaller    = True
ThumbMakerCfg.smaller_size    = (800, 600)
ThumbMakerCfg.image_text      = "(resized by thumb maker (c) Jens Diemer)" # LOL

ThumbMaker( ThumbMakerCfg ).go()

-------------------------------------------------------------------------------

license:
    GNU General Public License v3 or above
    http://www.opensource.org/licenses/gpl-license.php
"""


import sys, os, time, fnmatch, urllib, string
import optparse


try:
    import Image, ImageFont, ImageDraw

    # PIL's Fehler "Suspension not allowed here" work around:
    # s. http://mail.python.org/pipermail/image-sig/1999-August/000816.html
    import ImageFile
    ImageFile.MAXBLOCK = 1000000 # default is 64k
except ImportError, err:
    print "Import Error: %s" % err
    print "You must install PIL, The Python Image Library"
    print "http://www.pythonware.com/products/pil/index.htm"
    sys.exit()



class ThumbMakerCfg(object):
    # Standardwerte
    path_to_convert = os.getcwd()
    extentions = (".jpg", ".jpeg", ".png")
    do_path_walk = True # look into sub-directories ?
    path_output = path_to_convert
    make_thumbs = True
    thumb_size = (160, 120)
    thumb_suffix = "_thumb"

    make_smaller = False
    smaller_size = (640, 480)
    suffix = "_WEB"
    image_text = ""
    text_color = "#000000"

    jpegQuality = 85

    clean_filenames = True

    rename_rules = [
        (" ", "_"),
        ("�", "ae"),
        ("�", "oe"),
        ("�", "ue"),
        ("�", "Ae"),
        ("�", "Oe"),
        ("�", "Ue"),
        ("�", "ss"),
    ]

    def setup_from_cli(self):
        parser = optparse.OptionParser("usage: %prog [options] picture1 picture2")

        parser.add_option("--make-smaller", dest="make_smaller", default=False, action="store_true",
            help="Make a smaller image with 'suffix' ?")
        parser.add_option(
            "--size", type="string",
            dest="smaller_size", default="%ix%i" % self.smaller_size,
            help="smaller size (if --make-smaller used) default: %ix%i" % self.smaller_size)
        parser.add_option("--suffix", dest="suffix", default=self.suffix,
            help="Make a smaller image with 'suffix' ?")

        parser.add_option("--image_text", dest="image_text", default=self.image_text, type="string",
            help="Add text to the image")
        parser.add_option("--text_color", dest="text_color", default=self.text_color, type="string",
            help="Color of the given --image_text")

        parser.add_option("--jpegQuality", dest="jpegQuality", default=self.jpegQuality, type="int",
            help="JPEG quality")

        (options, args) = parser.parse_args()
        if len(args) == 1:
            parser.error("incorrect number of arguments")
        self.pictures = args

        self.make_smaller = options.make_smaller
        self.smaller_size = tuple([int(px) for px in options.smaller_size.split("x")])
        self.image_text = options.image_text
        self.text_color = options.text_color
        self.jpegQuality = options.jpegQuality

    def iter_pictures(self):
        for pic_path in self.pictures:
            name, ext = os.path.splitext(pic_path)
            if ext not in self.extentions:
                print "Skip (no valid file extension): %s" % pic_path
            else:
                yield pic_path




class ThumbMaker(object):
    def __init__(self, cfg):
        self.cfg = cfg
        self.skip_file_pattern = [
            "*%s.*" % self.cfg.thumb_suffix,
            "*%s.*" % self.cfg.suffix
        ]

    def cli(self):
        """
        CLI Interface...
        """
        print "Pictures to process: %r" % self.cfg.pictures
        for pic_path in self.cfg.iter_pictures():
            path, filename = os.path.split(pic_path)
            print "Convert %s..." % filename

            self.cfg.path_output = path
            print "path:", path
            self.process_file(pic_path)
        print " -- END -- "

    def go(self):
        """ Aktion starten """
        time_begin = time.time()

        if not os.path.isdir(self.cfg.path_output):
            print "Make output dir '%s'..." % self.cfg.path_output,
            try:
                os.makedirs(self.cfg.path_output)
            except Exception, e:
                print "Error!"
                print "Can't make ouput dir:", e
                sys.exit()
            else:
                print "OK"

        print "work path:", self.cfg.path_to_convert

        for root, dirs, files in os.walk(self.cfg.path_to_convert):
            print root
            print "_" * 80
            for file_name in files:
                filename, extension = os.path.splitext(file_name)
                if extension not in self.cfg.extentions:
                    print "Skip %r (wrong file extension), ok." % filename
                    continue
                abs_file = os.path.join(self.cfg.path_to_convert, root, file_name)

                self.process_file(abs_file)

            if not self.cfg.do_path_walk:
                break

        print "-" * 80
        print "all files converted in %0.2fsec." % (time.time() - time_begin)

    def process_file(self, abs_file):
        path, im_name = os.path.split(abs_file)
        print abs_file
        try:
            im_obj = Image.open(abs_file)
        except IOError:
            # Ist wohl kein Bild, oder unbekanntes Format
            #~ print "Not a image, skip.\n"
            return
        except OverflowError, e:
            print ">>> OverflowError: %s" % e
            print "Not a picture ? (...%s)" % abs_file[10:]
            print
            return

        print "%-40s - %4s %12s %s" % (
            im_name, im_obj.format, im_obj.size, im_obj.mode
        )

        if self.cfg.clean_filenames == True:
            # Dateinamen s�ubern
            im_name = self.clean_filename(im_name)

        # Kleinere Bilder f�r's Web erstellen
        if self.cfg.make_smaller == True:
            self.convert(
                im_obj=im_obj,
                im_path=self.cfg.path_output,
                im_name=im_name,
                suffix=self.cfg.suffix,
                size=self.cfg.smaller_size,
                text=self.cfg.image_text,
                color=self.cfg.text_color,
            )

        # Thumbnails erstellen
        if self.cfg.make_thumbs == True:
            self.convert(
                im_obj=im_obj,
                im_path=self.cfg.path_output,
                im_name=im_name,
                suffix=self.cfg.thumb_suffix,
                size=self.cfg.thumb_size,
            )
        print "-" * 3

    def convert(self,
        im_obj, # Das PIL-Image-Objekt
        im_path, # Der Pfad in dem das neue Bild gespeichert werden soll
        im_name, # Der vollst�ndige Name der Source-Datei
        suffix, # Der Anhang f�r den Namen
        size, # Die max. gr��e des Bildes als Tuple
        text="", # Text der unten rechts ins Bild eingeblendet wird
        color="#00000", # Textfarbe
       ):
        """ Rechnet das Bild kleiner und f�gt dazu den Text """

        name, ext = os.path.splitext(im_name)
        out_name = name + suffix + ".jpg"
        out_abs_name = os.path.join(im_path, out_name)

        for skip_pattern in self.skip_file_pattern:
            if fnmatch.fnmatch(im_name, skip_pattern):
                #~ print "Skip file."
                return

        if os.path.isfile(out_abs_name):
            print "File '%s' exists! Skip." % out_name
            return

        print "resize (max %ix%i)..." % size,
        try:
            im_obj.thumbnail(size, Image.ANTIALIAS)
        except Exception, e:
            print ">>>Error: %s" % e
            return
        else:
            print "OK, real size %ix%i" % im_obj.size

        if im_obj.mode != "RGB":
            print "convert to RGB...",
            im_obj = im_obj.convert("RGB")
            print "OK"

        if text != "":
            # unter Linux ganzen Pfad angeben:
            font_obj = ImageFont.truetype('arial.ttf', 12)
            ImageDraw.Draw(im_obj).text(
                (10, 10), text, font=font_obj, fill=color
            )

        print "save '%s'..." % out_name,
        try:
            im_obj.save(
                out_abs_name, "JPEG", quality=self.cfg.jpegQuality,
                optimize=True, progressive=False
            )
        except Exception, e:
            print "ERROR:", e
        else:
            print "OK"

    def clean_filename(self, file_name):
        """ Dateinamen f�r's Web s�ubern """

        if urllib.quote(file_name) == file_name:
            # Gibt nix zu ersetzten!
            return file_name

        fn, ext = os.path.splitext(file_name)

        for rule in self.cfg.rename_rules:
            fn = fn.replace(rule[0], rule[1])

        allowed_chars = string.ascii_letters + string.digits
        allowed_chars += ".-_#"

        # Nur ASCII Zeichen erlauben und gleichzeitig trennen
        parts = [""]
        for char in fn:
            if not char in allowed_chars:
                parts.append("")
            else:
                parts[-1] += char

        # Erster Buchstabe immer gro� geschrieben
        parts = [i[0].upper() + i[1:] for i in parts if i != ""]
        fn = "".join(parts)

        return fn + ext



if __name__ == "__main__":
    cfg = ThumbMakerCfg()
    cfg.setup_from_cli()

    ThumbMaker(cfg).cli()









