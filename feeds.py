import feedparser
import time
import calendar
import uuid
import urlparse
import util
import cPickle as pickle
from settings import settings

def cmp_timestamp(a, b):
    return cmp(a.timestamp, b.timestamp)
    
def cmp_received(a, b):
    n = cmp(a.received, b.received)
    if n != 0:
        return n
    return cmp_timestamp(a, b)
    
def create_id(entry):
    keys = ['id', 'link', 'title']
    for key in keys:
        if key in entry:
            return str(entry[key])
    return uuid.uuid4().hex
    
class Item(object):
    def __init__(self, feed, id):
        self.feed = feed
        self.id = id
        self.timestamp = int(time.time())
        self.received = int(time.time())
        self.title = ''
        self.description = ''
        self.link = ''
        self.author = ''
        self.read = False
    @property
    def time_since(self):
        return util.time_since(self.timestamp)
        
class Feed(object):
    def __init__(self, url):
        self.uuid = uuid.uuid4().hex
        self.url = url
        self.enabled = True
        self.last_poll = 0
        self.interval = settings.DEFAULT_POLLING_INTERVAL
        self.etag = None
        self.modified = None
        self.title = ''
        self.link = ''
        self.id_list = []
        self.id_set = set()
    def make_copy(self):
        feed = Feed(self.url)
        for key in ['uuid', 'enabled', 'interval', 'title', 'link']:
            value = getattr(self, key)
            setattr(feed, key, value)
        return feed
    def copy_from(self, feed):
        for key in ['enabled', 'interval', 'title', 'link']:
            value = getattr(feed, key)
            setattr(self, key, value)
    @property
    def favicon_url(self):
        components = urlparse.urlsplit(self.url)
        scheme, domain = components[:2]
        return '%s://%s/favicon.ico' % (scheme, domain)
    def clear_cache(self):
        self.id_list = []
        self.id_set = set()
    def clean_cache(self, size):
        for id in self.id_list[:-size]:
            self.id_set.remove(id)
        self.id_list = self.id_list[-size:]
    def should_poll(self):
        if not self.enabled:
            return False
        now = int(time.time())
        duration = now - self.last_poll
        return duration >= self.interval
    def poll(self):
        result = []
        self.last_poll = int(time.time())
        d = feedparser.parse(self.url, etag=self.etag, modified=self.modified)
        self.etag = d.get('etag', None)
        self.modified = d.get('modified', None)
        feed = d.get('feed', None)
        if feed:
            self.title = self.title or feed.get('title', '')
            self.link = self.link or feed.get('link', self.url)
        entries = d.get('entries', [])
        for entry in entries:
            id = create_id(entry)
            if id in self.id_set:
                continue
            self.id_list.append(id)
            self.id_set.add(id)
            item = Item(self, id)
            item.timestamp = calendar.timegm(entry.get('date_parsed', time.gmtime()))
            item.title = util.format(entry.get('title', ''), settings.POPUP_TITLE_LENGTH)
            item.description = util.format(entry.get('description', ''), settings.POPUP_BODY_LENGTH)
            item.link = entry.get('link', '')
            item.author = util.format(entry.get('author', '')) # TODO: max length
            result.append(item)
        self.clean_cache(settings.FEED_CACHE_SIZE)
        return result
        
class FeedManager(object):
    def __init__(self):
        self.feeds = []
        self.items = []
    def add_url(self, url):
        feed = Feed(url)
        self.feeds.append(feed)
        return feed
    def should_poll(self):
        return any(feed.should_poll() for feed in self.feeds)
    def poll(self):
        all_items = []
        for feed in self.feeds:
            if feed.should_poll():
                items = feed.poll()
                all_items.extend(items)
        all_items.sort(cmp=cmp_timestamp)
        return all_items
    def purge_items(self, max_age):
        now = int(time.time())
        for item in list(self.items):
            age = now - item.received
            if age > max_age:
                self.items.remove(item)
    def load(self, path='feeds.dat'):
        try:
            with open(path, 'rb') as input:
                self.feeds, self.items = pickle.load(input)
        except Exception:
            self.feeds, self.items = [], []
    def save(self, path='feeds.dat'):
        with open(path, 'wb') as output:
            data = (self.feeds, self.items)
            pickle.dump(data, output, -1)
    def clear_item_history(self):
        del self.items[:]
    def clear_feed_cache(self):
        for feed in self.feeds:
            feed.clear_cache()
            