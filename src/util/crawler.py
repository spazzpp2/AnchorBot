#!/usr/bin/env python
# -*- encoding: utf-8 -*-

import urllib, re, Image as PIL
import chardet
from urlparse import urljoin
from lxml.cssselect import CSSSelector
from lxml.html import soupparser
from lxml.etree import tostring as xmltostring
from logger import log
from time import mktime, time
from datamodel import Article, Image, Keyword


"""
Generic crawler.
Follows redirections and delivers some useful functions for remote images.
"""
re_cln = re.compile( '(<img[^>]+>|[\n\r]|<script[^>]*>\s*</script>|<iframe.*</iframe>|</*html>|</*head>|</*div[^>]*>| [ ]+)', re.I )
re_cont = re.compile( "((<([abip]|li|ul|img|span|strong)[^>]*>.*)+(</([abip]|li|ul|span|strong)>.*)+)+", re.U + re.I )

class Crawler( object ):
    hyph_EN = "/usr/share/liblouis/tables/hyph_en_US.dic"
    hyph_DE = "/usr/share/liblouis/tables/hyph_de_DE.dic"
    hyph_FR = "/usr/share/liblouis/tables/hyph_fr_FR.dic"

    def __init__( self, cacher, analyzer, proxies=None, verbose=False ):
        self.opener = urllib.FancyURLopener( proxies )
        self.cache = cacher # for not retrieving things twice!
        self.verbose = verbose
        self.analyzer = analyzer

        self.hyphenator = None
        try:
            from hyphenator import Hyphenator
            try:
                self.hyphenator = Hyphenator( self.hyph_DE )
            except IOError:
                self.verbose and log( "Not using hyphenator since %s can not be loaded." % self.hyph_DE )
        except ImportError:
            self.verbose and log( "Not using hyphenator since it's not installed." )

    def __content( self, html, simcontent=None ):
        codec = chardet.detect(html)["encoding"]
        res = sorted([x[0].decode(codec) for x in re_cont.findall( html )], key=lambda x: len(x.split(" ")), reverse=True)
        return u"" # Naah, this is too random
        if res:
            print res
            return res[0]

    def crawlHTML( self, tree, similarcontent=None, depth=0, baseurl=None ):
        content = self.__content( xmltostring( tree ), similarcontent ) or xmltostring( tree )
        imagesel = CSSSelector( "img" )
        images = [urljoin( baseurl, img.get( "src" ) or img.attrib.values()[0] ) for img in imagesel( tree )]
        linksel = CSSSelector( "a" )
        for elem in linksel( tree ):
            link = urljoin( baseurl, elem.get( "href" ) )
            if link and link[-4:] in ( ".png", ".jpg", ".gif", "jpeg" ):
                images.append( link )
        return ( set( images ), self.clean( content ), )

    def unescape( self, text ):
        text = text.replace( "\/", "/" )
        text = text.replace( "&quot;", "\"" )
        text = text.replace( "&lt;", "<" )
        text = text.replace( "&gt;", ">" )
        return text

    def compare_image( self, im1, im2 ):
        im = PIL.open( self.cache[im1] )
        x1, y1 = im.size
        im = PIL.open( self.cache[im2] )
        x2, y2 = im.size
        if x1 * y1 < x2 * y2:
            return -1
        elif x1 * y1 == x2 * y2:
            return 0
        return 1

    def biggest_image( self, imagelist ):
        biggest = u""
        imagelist = list( set( imagelist ) )
        x, y = 0, 0
        errors = []
        for imgurl in imagelist:
            try:
                im = PIL.open( self.cache[imgurl] )
                if x * y < im.size[0] * im.size[1]:
                    x, y = im.size
                    biggest = imgurl
            except IOError:
                errors.append( imgurl )
        if errors and self.verbose:
            self.verbose and log( "PIL: " + str( errors ) )
        return biggest

    def closest_image( self, imagelist, x, y ):
        closest = None
        dx, dy = 10 ** 10, 10 ** 10
        errors = []
        for imgurl in imagelist:
            try:
                im = PIL.open( self.cache[imgurl] )
                if dx / dy > abs( im.size[0] - x ) / abs( im.size[1] - y ):
                    dx, dy = abs( im.size[0] - x ), abs( im.size[1] - y )
                    closest = imgurl
            except IOError:
                errors.append( self.cache[imgurl] )
        if errors and self.verbose:
            self.verbose and log( "PIL: " + str( errors ) )
        return closest

    def filter_images( self, images, minimum=None, maximum=None ):
        if not minimum and not maximum:
            return images
        else:
            minimum = minimum or ( 0, 0, )
            maximum = maximum or ( 9999, 9999, )

        result = []
        for imgurl in images:
            try:
                im = PIL.open( self.cache[imgurl] )
                if im.size[0] >= minimum[0] and im.size[1] >= minimum[1] and\
                     im.size[0] <= maximum[0] and im.size[1] <= maximum[1]:
                        result.append( imgurl )
            except IOError:
                self.verbose and log( "Can't open that file: %s" % self.cache[imgurl] )
        return result

    def clean( self, htmltext ):
        """Removes tags and adds optional hyphens (&shy;) to each word or sentence."""
        if self.hyphenator:
            tree = soupparser.fromstring( htmltext )
            self.recursive_hyph( tree, u"\u00AD" )
            htmltext = xmltostring( tree, encoding="utf8" )
        tmp = u""
        while hash( tmp ) != hash( htmltext ):
            tmp = htmltext
            htmltext = re_cln.sub( "", htmltext )
        return htmltext

    def recursive_hyph( self, tree, hyphen ):
        if tree.text:
            tree.text = " ".join( [self.hyphenator.inserted( word, hyphen ) for word in tree.text.split( " " )] ).decode( "utf-8" )
        if tree.tail:
            tree.tail = " ".join( [self.hyphenator.inserted( word, hyphen ) for word in tree.tail.split( " " )] ).decode( "utf-8" )

        for elem in tree:
            self.recursive_hyph( elem, hyphen )

    def get_link( self, entry ):
        link = ""
        try:
            link = entry.link
        except AttributeError:
            try:
                link = entry["links"][0]["href"]
            except KeyError:
                print "Warning! %s has no link!" % entry["title"]
        return link

    def enrich( self, entry, source, recursion=1 ):
        """Filters out images, adds images from html, cleans up content."""
        image = None
        images = set()
        # get more text and images
        try:
            html = entry["content"][0].value.decode( "utf-8" )
            images, content = self.crawlHTML( soupparser.fromstring( html ) )
        except KeyError:
            try:
                html = entry["summary_detail"].value.decode( "utf-8" )
                images, content = self.crawlHTML( soupparser.fromstring( html ) )
            except KeyError:
                try:
                    html = entry["summary"].value.decode( "utf-8" )
                    images, content = self.crawlHTML( soupparser.fromstring( html ) )
                except KeyError:
                    content = entry["title"]

        # get images from entry itself
        for key in ( "links", "enclosures" ):
            try:
                i = filter( lambda x: x.type.startswith( "image" ), entry[key] )
            except KeyError:
                pass
            images |= set( [item.href.decode( "utf-8" ) for item in i] )

        # get even more images from links in entry
        try:
            for link in entry["links"]:
                if link["href"]:
                    # check for encoding
                    f = open( self.cache[link["href"]] )
                    encoding = chardet.detect( f.read() )["encoding"]
                    f.seek( 0 )
                    if encoding and encoding is not "utf-8":
                        # reset the encoding to utf-8
                        html = f.read().decode( encoding ).encode( "utf-8" )
                    else:
                        html = f.read()
                    if html:
                        try:
                            imgs, cont = self.crawlHTML( 
                                soupparser.fromstring( html ),
                                baseurl=link["href"],
                                )
                            images |= imgs
                            content += cont
                        except ValueError, e:
                            self.verbose and log( "Wrong %s char? %s" % ( encoding, e, ) )
                            print "Wrong %s char? %s" % ( encoding, e, )

        except KeyError:
            self.verbose and log( "There were no links: %s" % entry )

        # filter out some images
        # give the images to the entry finally
        images = self.filter_images( images, minimum=( 40, 40, ) )
        if not image or image.endswith( "gif" ):
            image = self.biggest_image( images )
        #TODO resize image to a prefered size here!

        link = self.get_link( entry )

        try:
            date = mktime( entry.updated_parsed )
        except AttributeError:
            date = time()

        title = entry["title"]
        a = self.analyzer
        a.add( {a.eid: link, a.key: title} )
        keywords = [Keyword( kw ) for kw in a.get_keywords_of_article( {a.eid: link, a.key: title} )]
        art = Article( date, title, content, link, source, Image( image ) )
        return art, keywords
