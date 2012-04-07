# -*- encoding:: utf-8 -*-

import sys
import webbrowser

from sqlalchemy.sql.expression import desc
from time import time, localtime, strftime
from flask import Flask, render_template, url_for, request, redirect, jsonify
from threading import Thread

from util.anchorbot import Anchorbot, DBPATH
from util.datamodel import get_session_from_new_engine, Source, Article, Image, Keyword, Kw2art

host = "0.0.0.0"
port = 8000
app = Flask(__name__)
bot = None # yet

def update_event(x, y):
    print "update!", x, y

def show(mode, content):
    return render_template(
            "layout.html",
            style=url_for("static", filename="default.css"),
            mode=mode,
            content=content
        )

@app.route("/")
def start():
    global bot
    return show("start", [])

@app.route("/gallery/key/top/<top>")
@app.route("/gallery/key/top/<top>/<number>")
@app.route("/gallery/key/top/<top>/<number>/<since>")
def top_keywords(top, number=5, since=3*24*60*60):
    global bot
    top, number, since = map(int, [top, number, since])
    s = get_session_from_new_engine(DBPATH)
    keywords = list(s.query(Keyword).\
            join(Keyword.articles).\
            filter(Article.timesread == 0).\
            filter(Article.date > time()-since).\
            order_by(desc(Keyword.clickcount)).\
            group_by(Keyword.ID).\
            offset(top*number).limit(number))
    content = jsonify(keywords=[kw.dictionary() for kw in keywords])
    s.close()
    return content

@app.route("/gallery/art/top/<key>/<top>")
@app.route("/gallery/art/top/<key>/<top>/<number>")
@app.route("/gallery/art/top/<key>/<top>/<number>/<since>")
def top_articles(key, top, number=5, since=3*24*60*60):
    global bot
    key, top, number, since = map(int, [key, top, number, since])
    s = get_session_from_new_engine(DBPATH)
    articles = list(s.query(Article).\
            join(Article.keywords).\
            filter(Keyword.ID == key).\
            filter(Article.timesread == 0).\
            #filter(Article.date > time()-since).\
            order_by(desc(Article.date)).\
            group_by(Article.ID).\
            offset(top*number).limit(number))
    content = jsonify(articles=[art.dictionary() for art in articles])
    s.close()
    return content


@app.route("/offset/<offset>")
@app.route("/offset/<offset>/<number>")
def gallery(offset=0, number=30):
    global bot
    offset, number = int(offset), int(number)
    now = time()
    s = get_session_from_new_engine(DBPATH)
    articles = []
    if offset == 0:
        articles = list(s.query(Article).filter(Article.timesread == 0).\
                group_by(Article.title).\
                join(Article.keywords).\
                filter(Keyword.clickcount > 0).\
                order_by(desc(Keyword.clickcount)).\
                #group_by(Keyword.ID).\
                limit(number).offset(offset*number))
    articles += list(s.query(Article).filter(Article.timesread == 0).\
            filter(Article.date > now-7*24*60*60).\
            group_by(Article.title).\
            join(Article.keywords).\
            filter(Keyword.clickcount == 0).\
            order_by(desc(Article.date)).\
            limit(number - len(articles)).offset(offset*number))
    content = render_template("galery.html", articles=articles)
    s.close()
    return content

@app.route("/_hate/id/<keyword_id>")
@app.route("/_hate/<keyword>")
def hate_key(keyword_id, keyword):
    change_key(-1, keyword_id, keyword)

@app.route("/_like/id/<keyword_id>")
@app.route("/_like/<keyword>")
def like_key(keyword_id, keyword):
    change_key(1, keyword_id, keyword)

def change_key(change, keyword_id=None, keyword=None):
    global bot
    s = get_session_from_new_engine(DBPATH)
    if keyword and not keyword_id:
        kw = s.query(Keyword).filter(Keyword.word == keyword).first()
    else:
        kw = s.query(Keyword).filter(Keyword.ID == keyword_id).first()
    if not kw:
        return "None found."
    kw.clickcount += change
    s.merge(kw)
    s.commit()
    s.close()
    return "ignored %s" % keyword

@app.route("/key/id/<keyword_id>")
@app.route("/key/<keyword>")
@app.route("/key/<keyword>/<offset>")
@app.route("/key/<keyword>/<offset>/<limit>")
def read_about_key(keyword_id=None, keyword=None, offset=0, limit=10):
    global bot
    offset, limit = map(int, [offset, limit])
    s = get_session_from_new_engine(DBPATH)
    if keyword and not keyword_id:
        kw = s.query(Keyword).filter(Keyword.word == keyword).first()
    else:
        kw = s.query(Keyword).filter(Keyword.ID == keyword_id).first()
    kw.clickcount += 1
    s.merge(kw)
    s.commit()
    arts = s.query(Article).join(Article.keywords).filter(Keyword.ID == kw.ID)
    arts = arts.order_by(desc(Article.date)).limit(limit).offset(offset*limit)
    content = show("more", arts)
    for art in arts:
        art.timesread+=1
        s.merge(art)
    s.commit()
    s.close()
    return content

@app.route("/quit")
def shutdown():
    global bot
    try:
        request.environ.get("werkzeug.server.shutdown")()
    except:
        print "Not using werkzeug engine."
    bot.shutdown()
    return "bye"

@app.route("/_feeds")
def get_feeds():
    s = get_session_from_new_engine(DBPATH)
    sources = s.query(Source).order_by(Source.title).all()
    content = render_template("feeds.html", sources=sources)
    s.close()
    return content

@app.route("/_keywords")
def get_keywords():
    s = get_session_from_new_engine(DBPATH)
    keywords = s.query(Keyword).order_by(desc(Keyword.clickcount)).limit(30)
    content = render_template("keywords.html", keywords=keywords)
    s.close()
    return content

@app.route("/feed/id/<fid>")
@app.route("/feed/<url>")
def read_feed(fid=None, url=None):
    s = get_session_from_new_engine(DBPATH)
    if url:
        arts = s.query(Article).join(Article.source)
        arts = arts.filter(Source.link.contains(url)).order_by(Article.date)
        arts = arts.all()
    else:
        arts = s.query(Article).join(Article.source)
        arts = arts.filter(Source.ID == fid).order_by(desc(Article.date)).all()
    srclist = s.query(Source).order_by(Source.title).all()
    content = show("more", arts)
    s.close()
    return content

@app.route("/redirect/<aid>")
def redirect_source(aid=None, url=None):
    global bot
    s = get_session_from_new_engine(DBPATH)
    art = s.query(Article).filter(Article.ID == aid).one()
    url = art.link
    s.close()
    return redirect(url)

@app.route("/add/<path:url>")
def add_feed(url=None):
    global bot
    try:
        if not url:
            return "nok"
        bot.add_feed(url)
        return "ok"
    except Exception, e:
        print str(e)

@app.route("/read/<aid>")
def read_article(aid=None):
    global bot
    s = get_session_from_new_engine(DBPATH)
    arts = s.query(Article).filter(Article.ID == aid).all()
    for art in arts:
        art.timesread += 1
        s.merge(art)
    s.commit()
    srclist = s.query(Source).order_by(Source.title).all()
    content = show("more", arts)
    s.close()

def setup_anchorbot(urls, cache_only, verbose, update_event):
    global bot
    bot = bot or Anchorbot(cache_only, verbose, update_event)
    if urls:
        map(bot.add_url, urls)
    return bot

def main(urls=[], cache_only=False, verbose=False, open_browser=False):
    """The main func which creates an AnchorBot
    """
    global host
    global port
    global app
    global bot
    if open_browser:
        print "Opening localhost:5000 in browser..."
        b = Thread(target=webbrowser.open, args=("localhost:5000",))
        b.start()
    bot = setup_anchorbot(urls, cache_only, verbose, update_event)
    print "Running bot..."
    bot.run()
    print "Running app..."
    app.run(host=host, port=port, debug=True, use_reloader=False)

def get_cmd_options():
    usage = __file__
    return usage

if __name__ == "__main__":
    if len(sys.argv) > 1:
        main(
                sys.argv[1:] if "-a" in sys.argv else [],
                "-v" in sys.argv,  # verbose option
                "-c" in sys.argv,  # print cache only
                "-o" in sys.argv)  # open browser
    else:
        main()
