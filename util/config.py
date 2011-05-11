import os, threading, time
try:
    import cpickle as pickle
except:
    import pickle

class SelfRenewingLock(threading.Thread):

    def __init__(self, lockfile, dtime=13):
        super(SelfRenewingLock, self).__init__()
        self.lockfile = lockfile
        self.__locked = False
        self.DTIME = dtime
        self.daemon = True

    def run(self):
        while(True):
            self.__renew()
            time.sleep(self.DTIME)

    def __renew(self):
        f = open(self.lockfile, 'w')
        pickle.dump(list(time.localtime())[:5], f, -1)

    def locked(self):
        if self.__locked:
            return self.__locked
        elif os.path.exists(self.lockfile):
            old = pickle.load(open(self.lockfile, 'r'))
            old[-1] += self.DTIME
            self.__locked = old >= list(time.localtime())[:5]
        else:
            self.__locked = False
        return self.__locked

    def __del__(self):
        os.remove(self.lockfile)

class Config(object):

    locked = False

    def __init__(self, path, defaults=dict(), defaultabos=set()):
        self.path = os.path.realpath(path)
        self.lockfile = os.path.join(self.path, "lock")
        self.lock = SelfRenewingLock(self.lockfile)
        self.locked = self.lock.locked()
        if self.locked:
            raise Exception
        if not os.path.isdir(self.path):
            os.mkdir(self.path)
        self.lock.start()
        self.configfile = os.path.join(self.path, "config")
        self.abofile = os.path.join(self.path, "abos")
        if os.path.exists(self.abofile):
            f = open(self.abofile, 'r')
            self.abos = set(filter(lambda x: len(x)>0, f.read().split("\n")))
            print self.abos
            f.close()
        else:
            self.abos = defaultabos
        if os.path.exists(self.configfile):
            self.read_config()
        else:
            self.config = defaults
            self.write_config()

    def read_config(self):
        f = open(self.configfile, 'r')
        self.config = pickle.load(f)
        f.close()

    def write_config(self):
        f = open(self.configfile, 'w')
        pickle.dump(self.config, f, -1)
        f.close()

    def set(self, name, value):
        self.config[name] = value

    def __setitem__(self, name, value):
        self.set(name, value)

    def get(self, name):
        try:
            return self.config[name]
        except KeyError:
            return None

    def add_abo(self, url):
        self.abos.add(url)
        self.write_abos()

    def get_abos(self):
        return self.abos

    def del_abo(self, url):
        self.abos.remove(url)
        self.write_abos()

    def write_abos(self):
        f = open(self.abofile, "w")
        for abo in self.abos:
            f.write("%s\n" % abo)
        f.close()

    def quit(self):
        if not self.locked:
            self.write_abos()
            self.write_config()
            del self.lock

if __name__ == "__main__":
    s = SelfRenewingLock("/tmp/testlock", 1)
    print s.locked()
    s.start()
    print s.locked()
