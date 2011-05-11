import urllib, os, time
try:
    import cpickle as pickle
except ImportError:
    import pickle
from logger import log

class Cacher(object):
    """
    Object-Wrapper around a dict. Have seen smaller and quickier, though.
    """
    def __init__(self):
        self.dic = {}

    def get(self, url):
        return self.dic[url]
    
    def __getitem__(self, url):
        try:
            obj = self.dic[url]
            log("Ha! Gottcha!")
            return obj
        except KeyError:
            return None

    def __setitem__(self, url, obj):
        if self[url]:
            log("Overwriting %s" % url)
        self.dic[url] = obj

    def clear(self):
        self.dic = {}

class PersistentCacher(object):
    def __init__(self, localdir="/tmp/lyrebird/", max_age_in_days=-1):
        self.localdir = os.path.realpath(os.path.dirname(localdir))
        if not os.path.isdir(localdir):
            os.mkdir(localdir)
        self.dloader = urllib.FancyURLopener()
        self.exp = -1
        self.dont_dl = (".swf",)
        self.storpath = storpath = os.path.join( localdir, "agedic.pkl" )
        self.stor = {}
        if os.path.exists( storpath ):
            try:
                self.stor = pickle.load( open(storpath, 'r') )
            except EOFError:
                print "Cache corrupted.."
                for f in os.listdir( localdir ):
                    os.remove(os.path.join(localdir, f))
            self.check_for_old_files(max_age_in_days)

    def check_for_old_files(self, max_age_in_days):
        then = time.time() - max_age_in_days*24*60*60
        for url, (newurl,creation) in filter(lambda x: x[1][1]<then, self.stor.items()):
            del self[url]

    def __newurl(self, url):
        return os.path.join(self.localdir, str(hash(url)).replace("-","0"))

    def __getitem__(self, url, verbose=False):
        if url[-4:] in self.dont_dl:
            if verbose:
                log("Ignoring "+ url)
            return url
        try:
            result, tt = self.stor[url]
            if verbose:
                log("Getting %s from cache." % url)
            return result
        except KeyError:
            newurl = self.__newurl(url)
            if verbose:
                log("Downloading %s." % url)
            try:
                if not os.path.exists(newurl):
                    self.dloader.retrieve(url, newurl)
                if verbose:
                    log("Cached %s to %s." % (url, newurl, ))
                self.stor[url] = self.stor[newurl] = (newurl, time.time())
            except IOError:
                if verbose:
                    log("IOError: Filename too long?")
            return newurl

    def __delitem__(self, url):
        try:
            os.remove(self.stor[url])
            del self.stor[self.__newurl(url)]
            del self.stor[url]
        except:
            pass # oll korrect
        pickle.dump(self.stor, open(self.storpath, 'w'))

    def __del__(self):
        pickle.dump(self.stor, open(self.storpath, 'w'))

    def clear():
        for url in self.stor.values():
            os.remove(url) # uh oh
        self.stor = {}

if __name__ == "__main__":
    c = Cacher()
    print c["abc"]
    c["abc"] = 1
    print c["abc"]
