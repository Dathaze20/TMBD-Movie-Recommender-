import os
import json
import time
import socket
import hashlib
import traceback
import logging
import threading
import urllib.request
import webbrowser
from concurrent.futures import ThreadPoolExecutor
from typing import Dict
from dotenv import load_dotenv

from kivy.config import Config
Config.set('kivy', 'keyboard_mode', 'system')

from kivy.animation import Animation
from kivy.app import App
from kivy.clock import Clock, mainthread
from kivy.core.window import Window
from kivy.graphics import Color, Rectangle, RoundedRectangle
from kivy.metrics import dp
from kivy.properties import StringProperty
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.gridlayout import GridLayout
from kivy.uix.image import AsyncImage
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.screenmanager import ScreenManager, Screen, SlideTransition
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput
from kivy.uix.widget import Widget
from kivy.utils import platform
from kivy import kivy_data_dir
from tmdbv3api import TMDb, Movie

from movie_utils import star_text, MovieDetails

# Kivy's default font (Roboto) has no glyphs for ★ ☆ ✕ ← ▶, so those render
# as blank boxes - DejaVuSans (also bundled with Kivy, on every platform
# including Android) does have them.
#
# font_name pointing at a file that is not there does not fail here; it fails
# later, when Kivy first renders a label using it. On Android that surfaces as
# the app closing the instant it opens, with nothing on screen to explain it.
# So check once, and fall back to the always-registered default rather than
# taking the whole app down over some missing glyphs.
_DEJAVU = os.path.join(kivy_data_dir, 'fonts', 'DejaVuSans.ttf')
if os.path.exists(_DEJAVU):
    SYMBOL_FONT = _DEJAVU
else:
    SYMBOL_FONT = 'Roboto'
    logging.warning(
        "DejaVuSans.ttf not found at %s - falling back to Roboto. "
        "Symbol glyphs (star, back arrow) may render as boxes.", _DEJAVU
    )

# Prevent a flaky/hung mobile connection from blocking a background thread
# (and the loading popup) forever.
socket.setdefaulttimeout(15)

# Android ships no system CA bundle that Python's ssl module can find, so
# every HTTPS call - the TMDB API and the poster CDN alike - fails on a
# packaged APK unless ssl is pointed at the certifi bundle bundled with it.
# setdefault means a real system bundle (desktop, Pydroid) still wins.
try:
    import certifi
    os.environ.setdefault('SSL_CERT_FILE', certifi.where())
    os.environ.setdefault('REQUESTS_CA_BUNDLE', certifi.where())
except Exception as e:
    logging.debug(f"certifi unavailable, relying on system CA store: {e}")

def _find_env_file():
    """Look for .env next to the script, in the current working directory,
    and one level up - covers the common ways an Android runner (Pydroid,
    Termux) can end up launching main.py from an unexpected working
    directory or a nested folder from a zip download."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    candidates = []
    for d in (script_dir, os.getcwd(), os.path.dirname(script_dir)):
        path = os.path.join(d, '.env')
        if path not in candidates:
            candidates.append(path)
    for path in candidates:
        if os.path.exists(path):
            return path, candidates
    return None, candidates


_script_dir = os.path.dirname(os.path.abspath(__file__))
_env_path, _env_candidates = _find_env_file()
load_dotenv(_env_path) if _env_path else load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(asctime)s:%(levelname)s:%(message)s')

# Original fallback key this project shipped with from its very first commit -
# used only if no TMDB_API_KEY is found via .env/environment, so the app
# works out of the box regardless of where .env ends up on a given device.
# A .env with your own key always takes priority over this.
_DEFAULT_API_KEY = '412cb4afbe96d39f9db34601104ff7e4'

api_key = os.getenv('TMDB_API_KEY') or _DEFAULT_API_KEY
if not os.getenv('TMDB_API_KEY'):
    _checked = ', '.join(_env_candidates)
    logging.warning(f"TMDB_API_KEY not found (checked for .env at: {_checked}); using built-in default key.")

# Module-level failures happen before build() runs, so the crash screen
# cannot catch them - the app would just close. Record the traceback instead
# and let build() display it.
STARTUP_ERROR = None
try:
    tmdb = TMDb()
    tmdb.api_key = api_key or ''
    tmdb.wait_on_rate_limit = True
    # tmdbv3api caches identical GET requests indefinitely (unbounded
    # lru_cache) on its own, independent of our _category_cache TTL/refresh
    # logic below - disable it so our cache is the single source of truth and
    # the refresh button actually reaches TMDB's servers instead of replaying
    # old data.
    tmdb.cache = False
except Exception:
    STARTUP_ERROR = traceback.format_exc()
    logging.error("TMDB client setup failed:\n%s", STARTUP_ERROR)
    tmdb = None

TMDB_ATTRIBUTION = "This product uses the TMDB API but is not endorsed or certified by TMDB."

BG_COLOR = (0.05, 0.05, 0.1, 1)
CARD_COLOR = (0.12, 0.12, 0.18, 1)
SURFACE_COLOR = (0.16, 0.16, 0.23, 1)
ACCENT = (0.42, 0.36, 0.91, 1)
ACCENT_GLOW = (0.55, 0.48, 1.0, 1)
TEXT_PRIMARY = (0.95, 0.95, 0.97, 1)
TEXT_MUTED = (0.52, 0.52, 0.62, 1)
GOLD = (1.0, 0.84, 0.0, 1)
SEARCH_BG = (0.1, 0.1, 0.17, 1)
ERROR_COLOR = (0.92, 0.26, 0.21, 1)
TAB_INACTIVE = (0.12, 0.12, 0.18, 0.7)

CATEGORIES = ['Popular', 'Top Rated', 'Now Playing', 'Watchlist']

# Caps how many movies a single browsing/search session can load into the
# grid (TMDB returns 20/page) - keeps widget/texture memory bounded on phones
# during long scroll sessions instead of growing without limit.
MAX_PAGES = 10

# How long a browsed category's results stay cached in memory before a tab
# switch triggers a fresh network fetch instead of showing the cached list.
CACHE_TTL = 300

# Seconds of typing pause before search-as-you-type fires, so we don't issue
# a network request on every single keystroke.
SEARCH_DEBOUNCE = 0.5


def fetch_movies(func, query=None, page_number=1):
    try:
        result = func(query, page=page_number) if query else func(page=page_number)
        if not result:
            return None
        out = []
        for m in result:
            out.append(MovieDetails(
                title=m.title,
                overview=getattr(m, 'overview', ''),
                release_date=getattr(m, 'release_date', ''),
                poster_path=getattr(m, 'poster_path', ''),
                movie_id=m.id,
                vote_average=getattr(m, 'vote_average', 0),
                genre_ids=getattr(m, 'genre_ids', []),
            ))
        return out
    except Exception as e:
        logging.error(f"Fetch error: {e}")
        return None


def fetch_movie_extra(movie_id):
    """Single call (append_to_response) for cast, similar movies, and trailer."""
    cast, similar, trailer_key = [], [], None
    try:
        d = Movie().details(movie_id, append_to_response='credits,similar,videos')

        credits = getattr(d, 'credits', None)
        if credits:
            for c in list(getattr(credits, 'cast', []) or [])[:8]:
                name = getattr(c, 'name', '')
                if name:
                    cast.append(name)

        sim = getattr(d, 'similar', None)
        if sim:
            for m2 in list(getattr(sim, 'results', []) or [])[:10]:
                if not getattr(m2, 'poster_path', ''):
                    continue
                similar.append(MovieDetails(
                    title=getattr(m2, 'title', ''),
                    overview=getattr(m2, 'overview', ''),
                    release_date=getattr(m2, 'release_date', ''),
                    poster_path=getattr(m2, 'poster_path', ''),
                    movie_id=m2.id,
                    vote_average=getattr(m2, 'vote_average', 0),
                    genre_ids=getattr(m2, 'genre_ids', []),
                ))

        vids = getattr(d, 'videos', None)
        if vids:
            results = list(getattr(vids, 'results', []) or [])
            for v in results:
                if getattr(v, 'site', '') == 'YouTube' and getattr(v, 'type', '') == 'Trailer':
                    trailer_key = getattr(v, 'key', None)
                    break
            if not trailer_key:
                for v in results:
                    if getattr(v, 'site', '') == 'YouTube':
                        trailer_key = getattr(v, 'key', None)
                        break
    except Exception as e:
        logging.error(f"Extra details fetch error: {e}")
    return cast, similar, trailer_key


class PosterCache:
    """Caches downloaded poster bytes on disk so relaunching the app doesn't
    re-download every poster from scratch."""
    _dir = None
    _pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix='poster-cache')

    @classmethod
    def _cache_dir(cls):
        if cls._dir is None:
            app = App.get_running_app()
            base = app.user_data_dir if app else _script_dir
            cls._dir = os.path.join(base, 'poster_cache')
            os.makedirs(cls._dir, exist_ok=True)
        return cls._dir

    @classmethod
    def _local_path(cls, poster_path, size):
        name = hashlib.sha1(f"{size}/{poster_path}".encode()).hexdigest() + '.jpg'
        return os.path.join(cls._cache_dir(), name)

    @classmethod
    def source(cls, poster_path, size='w185'):
        if not poster_path:
            return ''
        local = cls._local_path(poster_path, size)
        if os.path.exists(local):
            return local
        cls._pool.submit(cls._download, poster_path, size)
        return f"https://image.tmdb.org/t/p/{size}/{poster_path}"

    @classmethod
    def _download(cls, poster_path, size):
        local = cls._local_path(poster_path, size)
        if os.path.exists(local):
            return
        try:
            url = f"https://image.tmdb.org/t/p/{size}/{poster_path}"
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = resp.read()
            tmp = local + '.tmp'
            with open(tmp, 'wb') as f:
                f.write(data)
            os.replace(tmp, local)
        except Exception as e:
            logging.debug(f"Poster cache skip: {e}")


def open_external_url(url):
    try:
        if platform == 'android':
            from jnius import autoclass, cast
            Intent = autoclass('android.content.Intent')
            Uri = autoclass('android.net.Uri')
            PythonActivity = autoclass('org.kivy.android.PythonActivity')
            intent = Intent(Intent.ACTION_VIEW, Uri.parse(url))
            activity = cast('android.app.Activity', PythonActivity.mActivity)
            activity.startActivity(intent)
        else:
            webbrowser.open(url)
    except Exception as e:
        logging.error(f"Could not open URL: {e}")


class MovieCard(ButtonBehavior, BoxLayout):
    def __init__(self, movie, **kwargs):
        super().__init__(orientation='vertical', spacing=0, padding=0, **kwargs)
        self.movie_id = movie.id
        self.size_hint_y = None

        with self.canvas.before:
            Color(*CARD_COLOR)
            self._card_bg = RoundedRectangle(
                pos=self.pos, size=self.size, radius=[dp(10)]
            )
        self.bind(
            pos=lambda i, v: setattr(i._card_bg, 'pos', v),
            size=lambda i, v: setattr(i._card_bg, 'size', v),
        )

        poster_url = PosterCache.source(movie.poster_path, 'w185')
        self.poster = AsyncImage(
            source=poster_url, size_hint=(1, None),
            allow_stretch=True, keep_ratio=True,
        )
        self.add_widget(self.poster)

        info = BoxLayout(
            orientation='vertical', size_hint_y=None, height=dp(50),
            padding=[dp(5), dp(3)],
        )

        title_lbl = Label(
            text=movie.title, font_size='11sp', color=TEXT_PRIMARY,
            halign='left', valign='middle',
            shorten=True, shorten_from='right', size_hint_y=0.5,
        )
        title_lbl.bind(size=lambda i, s: setattr(i, 'text_size', s))

        bottom_row = BoxLayout(size_hint_y=0.5)

        score = f"{movie.vote_average:.1f}" if movie.vote_average else 'N/A'
        stars_lbl = Label(
            text=f"★ {score}",
            font_size='10sp', color=GOLD, font_name=SYMBOL_FONT, bold=True,
            halign='left', valign='middle', size_hint_x=0.55,
            shorten=True, shorten_from='right',
        )
        stars_lbl.bind(size=lambda i, s: setattr(i, 'text_size', s))

        year_lbl = Label(
            text=movie.year, font_size='9sp', color=TEXT_MUTED,
            halign='right', valign='middle', size_hint_x=0.45,
            shorten=True, shorten_from='right',
        )
        year_lbl.bind(size=lambda i, s: setattr(i, 'text_size', s))

        bottom_row.add_widget(stars_lbl)
        bottom_row.add_widget(year_lbl)
        info.add_widget(title_lbl)
        info.add_widget(bottom_row)
        self.add_widget(info)

        self.bind(size=self._resize)

    def _resize(self, *args):
        h = self.width * 1.5
        self.poster.height = h
        self.height = h + dp(50)


class SkeletonCard(BoxLayout):
    """Placeholder shown in the grid while a category/search's first page
    is loading, instead of blocking the whole screen with a popup."""

    def __init__(self, **kwargs):
        super().__init__(orientation='vertical', spacing=dp(6), padding=0, **kwargs)
        self.size_hint_y = None

        with self.canvas.before:
            Color(*CARD_COLOR)
            self._bg = RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(10)])
        self.bind(
            pos=lambda i, v: setattr(i._bg, 'pos', v),
            size=lambda i, v: setattr(i._bg, 'size', v),
        )

        self._poster_ph = Widget(size_hint=(1, None))
        with self._poster_ph.canvas:
            Color(*SURFACE_COLOR)
            self._poster_rect = RoundedRectangle(radius=[dp(8)])
        self._poster_ph.bind(
            pos=lambda i, v: setattr(self._poster_rect, 'pos', v),
            size=lambda i, v: setattr(self._poster_rect, 'size', v),
        )
        self.add_widget(self._poster_ph)

        info = BoxLayout(
            orientation='vertical', size_hint_y=None, height=dp(50),
            padding=[dp(5), dp(8)], spacing=dp(6),
        )
        for line_height, width_frac in ((dp(10), 0.7), (dp(8), 0.4)):
            line = Widget(size_hint=(width_frac, None), height=line_height)
            with line.canvas:
                Color(*SURFACE_COLOR)
                rect = RoundedRectangle(radius=[dp(4)])
            line.bind(
                pos=lambda i, v, r=rect: setattr(r, 'pos', v),
                size=lambda i, v, r=rect: setattr(r, 'size', v),
            )
            info.add_widget(line)
        self.add_widget(info)

        self.bind(size=self._resize)
        anim = Animation(opacity=0.45, duration=0.6) + Animation(opacity=1.0, duration=0.6)
        anim.repeat = True
        anim.start(self)

    def _resize(self, *args):
        h = self.width * 1.5
        self._poster_ph.height = h
        self.height = h + dp(50)


class SearchBar(BoxLayout):
    search_text = StringProperty('')

    def __init__(self, **kwargs):
        super().__init__(
            orientation='horizontal', size_hint_y=None, height=dp(46),
            spacing=dp(6), padding=[dp(4), 0], **kwargs,
        )
        self.register_event_type('on_search')
        self._debounce_ev = None

        with self.canvas.before:
            Color(*SEARCH_BG)
            self._bg = RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(14)])
        self.bind(
            pos=lambda i, v: setattr(i._bg, 'pos', v),
            size=lambda i, v: setattr(i._bg, 'size', v),
        )

        self.input = TextInput(
            hint_text='Search movies...',
            hint_text_color=(0.4, 0.4, 0.52, 1),
            multiline=False, size_hint_x=0.82,
            background_color=(0, 0, 0, 0),
            foreground_color=TEXT_PRIMARY,
            cursor_color=ACCENT_GLOW,
            padding=[dp(14), dp(12)],
            font_size='15sp',
        )
        clear = Button(
            text='✕', size_hint_x=0.18, font_name=SYMBOL_FONT,
            background_normal='',
            background_color=(*ACCENT[:3], 0.85),
            color=TEXT_PRIMARY, font_size='18sp',
        )

        self.add_widget(self.input)
        self.add_widget(clear)

        clear.bind(on_release=self._clear)
        self.input.bind(text=self._text_changed)
        self.input.bind(on_text_validate=self._submit)

    def _text_changed(self, inst, val):
        self.search_text = val
        if self._debounce_ev:
            self._debounce_ev.cancel()
        self._debounce_ev = Clock.schedule_once(lambda dt: self.dispatch('on_search'), SEARCH_DEBOUNCE)

    def _clear(self, *a):
        if self._debounce_ev:
            self._debounce_ev.cancel()
        self.input.text = ''
        self.search_text = ''
        self.dispatch('on_search')

    def _submit(self, *a):
        if self._debounce_ev:
            self._debounce_ev.cancel()
        self.dispatch('on_search')

    def on_search(self):
        pass


class CategoryBar(BoxLayout):
    active = StringProperty('Popular')

    def __init__(self, **kwargs):
        super().__init__(
            orientation='horizontal', size_hint_y=None, height=dp(38),
            spacing=dp(4), padding=[dp(2), dp(2)], **kwargs,
        )
        self.register_event_type('on_category')
        self._btns = {}

        for name in CATEGORIES:
            btn = Button(
                text=name, background_normal='',
                background_color=ACCENT if name == 'Popular' else TAB_INACTIVE,
                color=TEXT_PRIMARY, font_size='10.5sp', bold=(name == 'Popular'),
                size_hint_x=len(name), shorten=True, shorten_from='right',
                halign='center', valign='middle',
            )
            btn.bind(size=lambda i, s: setattr(i, 'text_size', (s[0] - dp(6), s[1])))
            btn.bind(on_release=lambda inst, n=name: self._pick(n))
            self._btns[name] = btn
            self.add_widget(btn)

    def _pick(self, name):
        if name == self.active:
            return
        self.active = name
        for n, b in self._btns.items():
            b.background_color = ACCENT if n == name else TAB_INACTIVE
            b.bold = (n == name)
        self.dispatch('on_category', name)

    def on_category(self, *a):
        pass


class MoviePosterApp(App):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.movie_cache: Dict[int, MovieDetails] = {}
        self.favorites: Dict[int, MovieDetails] = {}
        self.fav_file = None
        self.error_label = None
        self.grid = None
        self.search_bar = None
        self.title_label = None
        self.cat_bar = None
        self.current_cat = 'Popular'
        self._search_query = None
        self.load_generation = 0
        self._current_page = 1
        self._has_more = True
        self._loading_more = False
        self._current_movies = []
        self._category_cache = {}
        self._detail_token = 0
        self._detail_body = None

    def build(self):
        """Build the UI, but never die silently.

        An exception here kills the app before anything is drawn. On desktop
        you get a traceback in the terminal; on Android the app just closes
        the instant you open it, with no way to see why short of a USB cable
        and adb. So catch it and put the traceback on screen instead.
        """
        try:
            if STARTUP_ERROR:
                raise RuntimeError(
                    "Failed during module import:\n" + STARTUP_ERROR
                )
            return self._build_ui()
        except Exception:
            report = traceback.format_exc()
            logging.error("Startup failed:\n%s", report)
            try:
                path = os.path.join(self.user_data_dir, 'crash.txt')
                with open(path, 'w') as fh:
                    fh.write(report)
            except Exception:
                path = '(could not be written)'
            return self._crash_screen(report, path)

    def _crash_screen(self, report, path):
        root = BoxLayout(orientation='vertical', padding=dp(12), spacing=dp(8))
        with root.canvas.before:
            Color(*BG_COLOR)
            root._bg = Rectangle(pos=root.pos, size=root.size)
        root.bind(
            pos=lambda i, v: setattr(i._bg, 'pos', v),
            size=lambda i, v: setattr(i._bg, 'size', v),
        )
        head = Label(
            text='Startup failed', font_size='20sp', bold=True,
            color=ERROR_COLOR, size_hint_y=None, height=dp(34),
        )
        sub = Label(
            text=f'Saved to {path}', font_size='11sp', color=TEXT_MUTED,
            size_hint_y=None, height=dp(20),
        )
        scroll = ScrollView(size_hint=(1, 1), do_scroll_x=True)
        body = Label(
            text=report, font_size='11sp', color=TEXT_PRIMARY,
            size_hint=(None, None), halign='left', valign='top',
        )
        body.bind(texture_size=body.setter('size'))
        scroll.add_widget(body)
        for w in (head, sub, scroll):
            root.add_widget(w)
        return root

    def _build_ui(self):
        Window.clearcolor = BG_COLOR
        Window.bind(on_keyboard=self._on_key)
        # Without this the Android soft keyboard covers the search field
        # instead of pushing it up into view.
        Window.softinput_mode = 'below_target'
        self._load_favorites()

        sm = ScreenManager(transition=SlideTransition())
        self.sm = sm
        self.main_scr = Screen(name='Main')
        self.detail_scr = Screen(name='Detail')

        root = BoxLayout(orientation='vertical', padding=dp(6), spacing=dp(5))

        title_bar = BoxLayout(size_hint_y=None, height=dp(50), padding=[dp(14), 0], spacing=dp(8))
        with title_bar.canvas.before:
            Color(*CARD_COLOR)
            title_bar._bg = RoundedRectangle(
                pos=title_bar.pos, size=title_bar.size, radius=[dp(14)]
            )
        title_bar.bind(
            pos=lambda i, v: setattr(i._bg, 'pos', v),
            size=lambda i, v: setattr(i._bg, 'size', v),
        )
        self.title_label = Label(
            text='Popular Movies', font_size='20sp', bold=True,
            color=TEXT_PRIMARY, halign='left',
            shorten=True, shorten_from='right',
        )
        self.title_label.bind(size=lambda i, s: setattr(i, 'text_size', s))
        refresh_btn = Button(
            text='↻', size_hint=(None, None), size=(dp(34), dp(34)),
            background_normal='', background_color=TAB_INACTIVE,
            color=TEXT_PRIMARY, font_size='18sp', font_name=SYMBOL_FONT,
        )
        refresh_btn.bind(on_release=self._on_refresh)
        about_btn = Button(
            text='i', size_hint=(None, None), size=(dp(34), dp(34)),
            background_normal='', background_color=TAB_INACTIVE,
            color=TEXT_PRIMARY, font_size='16sp', bold=True, italic=True,
        )
        about_btn.bind(on_release=self._show_about)
        title_bar.add_widget(self.title_label)
        title_bar.add_widget(refresh_btn)
        title_bar.add_widget(about_btn)
        root.add_widget(title_bar)

        self.search_bar = SearchBar()
        self.search_bar.bind(on_search=self._on_search)
        root.add_widget(self.search_bar)

        self.cat_bar = CategoryBar()
        self.cat_bar.bind(on_category=self._on_category)
        root.add_widget(self.cat_bar)

        self.error_label = Label(
            text='', color=ERROR_COLOR, size_hint_y=None,
            height=dp(0), font_size='13sp', font_name=SYMBOL_FONT,
            halign='center', valign='middle',
        )
        self.error_label.bind(
            width=lambda i, w: setattr(i, 'text_size', (w - dp(12), None)),
            texture_size=lambda i, s: setattr(i, 'height', s[1] + dp(10) if i.text else 0),
        )
        root.add_widget(self.error_label)

        self.scroll = ScrollView(
            size_hint=(1, 1), do_scroll_x=False,
            bar_width=dp(3), bar_color=(*ACCENT[:3], 0.4),
        )
        self.scroll.bind(scroll_y=self._on_scroll)
        self.grid = GridLayout(
            cols=3, spacing=dp(5), padding=dp(3), size_hint_y=None,
        )
        self.grid.bind(minimum_height=self.grid.setter('height'))
        self.scroll.add_widget(self.grid)
        root.add_widget(self.scroll)

        self.loading_more_label = Label(
            text='', color=TEXT_MUTED, size_hint_y=None,
            height=0, font_size='12sp',
        )
        root.add_widget(self.loading_more_label)

        self.main_scr.add_widget(root)
        sm.add_widget(self.main_scr)
        sm.add_widget(self.detail_scr)

        if not api_key:
            checked = ' OR '.join(_env_candidates)
            self._show_error(f"TMDB_API_KEY missing. Checked for a .env file at: {checked}")
            return sm

        self._show_skeletons()
        gen = self.load_generation
        threading.Thread(target=self._load_cat, args=('Popular', gen), daemon=True).start()
        return sm

    # -- favorites / watchlist -------------------------------------------------

    def _load_favorites(self):
        self.fav_file = os.path.join(self.user_data_dir, 'favorites.json')
        try:
            if os.path.exists(self.fav_file):
                with open(self.fav_file, 'r') as f:
                    raw = json.load(f)
                for item in raw:
                    mv = MovieDetails.from_json(item)
                    self.favorites[mv.id] = mv
        except Exception as e:
            logging.error(f"Favorites load error: {e}")

    def _save_favorites(self):
        try:
            raw = [mv.to_json() for mv in self.favorites.values()]
            with open(self.fav_file, 'w') as f:
                json.dump(raw, f)
        except Exception as e:
            logging.error(f"Favorites save error: {e}")

    def is_favorite(self, movie_id):
        return movie_id in self.favorites

    def toggle_favorite(self, movie):
        if movie.id in self.favorites:
            del self.favorites[movie.id]
        else:
            self.favorites[movie.id] = movie
        self._save_favorites()

    # -- navigation / category / search -----------------------------------------

    def _reset_pagination(self):
        self._current_page = 1
        self._has_more = True
        self._loading_more = False
        self._current_movies = []
        self._hide_loading_more()

    def _show_watchlist(self):
        self._has_more = False
        if not self.favorites:
            self._show_error("Your watchlist is empty. Open a movie and tap ☆ to add it.")
            return
        for mv in self.favorites.values():
            self.movie_cache[mv.id] = mv
            self._add_card(mv)

    def _snapshot_scroll_position(self):
        prev = self.current_cat
        if prev and prev != 'Watchlist' and prev in self._category_cache and self.scroll:
            self._category_cache[prev]['scroll_y'] = self.scroll.scroll_y

    def _save_category_cache(self, cat):
        self._category_cache[cat] = {
            'movies': list(self._current_movies),
            'page': self._current_page,
            'has_more': self._has_more,
            'ts': time.time(),
            'scroll_y': self._category_cache.get(cat, {}).get('scroll_y', 1),
        }

    def _load_from_cache(self, cat):
        cached = self._category_cache.get(cat)
        if not cached or (time.time() - cached['ts']) >= CACHE_TTL:
            return False
        self._current_movies = list(cached['movies'])
        self._current_page = cached['page']
        self._has_more = cached['has_more']
        self._loading_more = False
        for mv in self._current_movies:
            self.movie_cache[mv.id] = mv
            self._add_card(mv)
        scroll_y = cached.get('scroll_y', 1)
        Clock.schedule_once(lambda dt: setattr(self.scroll, 'scroll_y', scroll_y), 0.05)
        return True

    def _on_category(self, inst, cat):
        self._snapshot_scroll_position()
        self.load_generation += 1
        gen = self.load_generation
        self.current_cat = cat
        self.search_bar.input.text = ''
        self.search_bar.search_text = ''
        self._search_query = None
        self.title_label.text = 'My Watchlist' if cat == 'Watchlist' else f'{cat} Movies'
        self._clear_error()
        self._clear_grid()

        if cat == 'Watchlist':
            self._reset_pagination()
            self._show_watchlist()
            return

        if self._load_from_cache(cat):
            return

        self._reset_pagination()
        self._show_skeletons()
        threading.Thread(target=self._load_cat, args=(cat, gen), daemon=True).start()

    def _on_refresh(self, *a):
        if self._search_query:
            self._on_search()
            return
        self._category_cache.pop(self.current_cat, None)
        self._on_category(None, self.current_cat)

    def _on_search(self, *a):
        q = self.search_bar.search_text.strip()
        self._snapshot_scroll_position()
        self.load_generation += 1
        gen = self.load_generation
        self._clear_error()
        self._clear_grid()
        self._reset_pagination()

        if not q:
            self._search_query = None
            cat = self.cat_bar.active
            self.current_cat = cat
            self.title_label.text = 'My Watchlist' if cat == 'Watchlist' else f'{cat} Movies'
            if cat == 'Watchlist':
                self._show_watchlist()
                return
            if self._load_from_cache(cat):
                return
            self._show_skeletons()
            threading.Thread(target=self._load_cat, args=(cat, gen), daemon=True).start()
            return

        self._search_query = q
        self.title_label.text = f'Search: {q}'
        self._show_skeletons()
        threading.Thread(target=self._do_search, args=(q, gen), daemon=True).start()

    def _cat_func(self, cat):
        m = Movie()
        if cat == 'Top Rated':
            return m.top_rated
        if cat == 'Now Playing':
            return m.now_playing
        return m.popular

    def _load_cat(self, cat, gen):
        try:
            func = self._cat_func(cat)
            first = fetch_movies(func, page_number=1)
            if gen != self.load_generation:
                return
            self._clear_grid()
            if not first:
                self._show_error("Could not load movies. Check your connection.")
                self._has_more = False
                return
            self._current_movies = []
            for mv in first:
                self.movie_cache[mv.id] = mv
                self._current_movies.append(mv)
                self._add_card(mv)
            self._current_page = 1
            self._has_more = True
            self._save_category_cache(cat)
        except Exception as e:
            logging.error(f"Load error: {e}")
            self._clear_grid()
            self._show_error("Could not load movies. Check your connection.")
            self._has_more = False

    def _do_search(self, query, gen):
        try:
            first = fetch_movies(Movie().search, query, 1)
            if gen != self.load_generation:
                return
            self._clear_grid()
            if not first:
                self._show_error("No movies found.")
                self._has_more = False
                return
            for mv in first:
                self.movie_cache[mv.id] = mv
                self._add_card(mv)
            self._current_page = 1
            self._has_more = True
        except Exception as e:
            logging.error(f"Search error: {e}")
            self._clear_grid()
            self._show_error("Search failed. Check your connection.")
            self._has_more = False

    # -- infinite scroll ----------------------------------------------------

    def _on_scroll(self, instance, value):
        if value <= 0.15:
            self._load_more()

    def _load_more(self):
        if self._loading_more or not self._has_more or self.current_cat == 'Watchlist':
            return
        self._loading_more = True
        self._show_loading_more()
        gen = self.load_generation
        threading.Thread(target=self._fetch_more, args=(gen,), daemon=True).start()

    def _fetch_more(self, gen):
        try:
            next_page = self._current_page + 1
            if next_page > MAX_PAGES:
                self._has_more = False
                return
            if self._search_query:
                more = fetch_movies(Movie().search, self._search_query, next_page)
            else:
                func = self._cat_func(self.current_cat)
                more = fetch_movies(func, page_number=next_page)
            if gen != self.load_generation:
                return
            if not more:
                self._has_more = False
                return
            self._current_page = next_page
            for mv in more:
                self.movie_cache[mv.id] = mv
                self._current_movies.append(mv)
                self._add_card(mv)
            if not self._search_query:
                self._save_category_cache(self.current_cat)
        except Exception as e:
            logging.error(f"Load more error: {e}")
        finally:
            self._loading_more = False
            self._hide_loading_more()

    # -- widget helpers -------------------------------------------------------

    @mainthread
    def _add_card(self, movie):
        if not self.grid or not movie.poster_path:
            return
        card = MovieCard(movie)
        card.bind(on_release=self._open_detail)
        self.grid.add_widget(card)

    @mainthread
    def _show_error(self, msg):
        if self.error_label:
            self.error_label.text = msg

    @mainthread
    def _clear_error(self):
        if self.error_label:
            self.error_label.text = ''
            self.error_label.height = 0

    @mainthread
    def _clear_grid(self):
        if self.grid:
            self.grid.clear_widgets()

    @mainthread
    def _show_loading_more(self):
        if self.loading_more_label:
            self.loading_more_label.text = 'Loading more...'
            self.loading_more_label.height = dp(24)

    @mainthread
    def _hide_loading_more(self):
        if self.loading_more_label:
            self.loading_more_label.text = ''
            self.loading_more_label.height = 0

    @mainthread
    def _show_skeletons(self, count=9):
        if self.grid:
            for _ in range(count):
                self.grid.add_widget(SkeletonCard())

    def _show_about(self, *a):
        content = BoxLayout(orientation='vertical', padding=dp(16), spacing=dp(12))
        lbl = Label(
            text=TMDB_ATTRIBUTION, color=TEXT_PRIMARY, font_size='13sp',
            halign='center', valign='middle', size_hint_y=1,
            text_size=(dp(280), None),
        )
        content.add_widget(lbl)
        close = Button(
            text='Close', size_hint_y=None, height=dp(40),
            background_normal='', background_color=ACCENT, color=TEXT_PRIMARY,
        )
        content.add_widget(close)
        popup = Popup(
            title='About', size_hint=(None, None), size=(dp(300), dp(200)),
            content=content, background_color=(*CARD_COLOR[:3], 0.98),
        )
        close.bind(on_release=popup.dismiss)
        popup.open()

    def _on_key(self, window, key, *args):
        if key == 27:
            if self.sm.current == 'Detail':
                self._go_back()
                return True
            return False
        return False

    # -- detail screen --------------------------------------------------------

    def _open_detail(self, inst):
        mid = getattr(inst, 'movie_id', None)
        if mid is None:
            return
        movie = self.movie_cache.get(mid)
        self._render_detail(movie)

    def _render_detail(self, movie):
        if not movie:
            return
        self._detail_token += 1
        token = self._detail_token

        self.detail_scr.clear_widgets()

        page = BoxLayout(orientation='vertical')
        with page.canvas.before:
            Color(*BG_COLOR)
            page._bg = Rectangle(pos=page.pos, size=page.size)
        page.bind(
            pos=lambda i, v: setattr(i._bg, 'pos', v),
            size=lambda i, v: setattr(i._bg, 'size', v),
        )

        top = BoxLayout(size_hint_y=None, height=dp(48), padding=[dp(6), dp(4)], spacing=dp(6))
        with top.canvas.before:
            Color(*CARD_COLOR)
            top._bg = Rectangle(pos=top.pos, size=top.size)
        top.bind(
            pos=lambda i, v: setattr(i._bg, 'pos', v),
            size=lambda i, v: setattr(i._bg, 'size', v),
        )

        back = Button(
            text='← Back', size_hint_x=0.22, font_name=SYMBOL_FONT,
            background_normal='', background_color=ACCENT,
            color=TEXT_PRIMARY, font_size='13sp', bold=True,
        )
        back.bind(on_release=self._go_back)

        ttl = Label(
            text=movie.title, font_size='15sp', bold=True,
            color=TEXT_PRIMARY, shorten=True, shorten_from='right',
            halign='center', size_hint_x=0.62,
        )
        ttl.bind(size=lambda i, s: setattr(i, 'text_size', s))

        fav_btn = Button(
            text=('★' if self.is_favorite(movie.id) else '☆'), size_hint_x=0.16,
            font_name=SYMBOL_FONT,
            background_normal='', background_color=ACCENT,
            color=GOLD, font_size='18sp', bold=True,
        )

        def _toggle_fav(btn_inst):
            self.toggle_favorite(movie)
            btn_inst.text = '★' if self.is_favorite(movie.id) else '☆'

        fav_btn.bind(on_release=_toggle_fav)

        top.add_widget(back)
        top.add_widget(ttl)
        top.add_widget(fav_btn)
        page.add_widget(top)

        scroll = ScrollView(size_hint=(1, 1), do_scroll_x=False)
        body = BoxLayout(
            orientation='vertical', size_hint_y=None,
            padding=dp(14), spacing=dp(10),
        )
        body.bind(minimum_height=body.setter('height'))

        if movie.poster_path:
            poster_wrap = BoxLayout(size_hint=(1, None), height=dp(380))
            with poster_wrap.canvas.before:
                Color(*SURFACE_COLOR)
                poster_bg = RoundedRectangle(radius=[dp(10)])
            poster_wrap.bind(
                pos=lambda i, v, r=poster_bg: setattr(r, 'pos', v),
                size=lambda i, v, r=poster_bg: setattr(r, 'size', v),
            )
            poster_wrap.add_widget(AsyncImage(
                source=PosterCache.source(movie.poster_path, 'w500'),
                allow_stretch=True, keep_ratio=True,
            ))
            body.add_widget(poster_wrap)

        body.add_widget(self._label(
            movie.title, '22sp', TEXT_PRIMARY, bold=True, height=dp(36),
        ))

        stars = star_text(movie.vote_average)
        score = f"{movie.vote_average:.1f}/10" if movie.vote_average else 'N/A'
        body.add_widget(self._label(f"{stars}  {score}", '16sp', GOLD, height=dp(28), font_name=SYMBOL_FONT))

        meta = []
        if movie.year:
            meta.append(movie.year)
        if movie.genre_text:
            meta.append(movie.genre_text)
        if meta:
            body.add_widget(self._label(' | '.join(meta), '13sp', TEXT_MUTED, height=dp(22)))

        sep = Widget(size_hint_y=None, height=dp(1))
        with sep.canvas:
            Color(*SURFACE_COLOR)
            sep._r = Rectangle(pos=sep.pos, size=sep.size)
        sep.bind(
            pos=lambda i, v: setattr(i._r, 'pos', v),
            size=lambda i, v: setattr(i._r, 'size', v),
        )
        body.add_widget(sep)

        body.add_widget(self._label('Overview', '16sp', TEXT_PRIMARY, bold=True, height=dp(28)))

        if movie.overview:
            ov = Label(
                text=movie.overview, font_size='14sp',
                color=(0.78, 0.78, 0.84, 1), size_hint_y=None,
                halign='left', valign='top',
                text_size=(Window.width - dp(34), None),
            )
            ov.bind(texture_size=ov.setter('size'))
            body.add_widget(ov)

        scroll.add_widget(body)
        page.add_widget(scroll)

        self.detail_scr.add_widget(page)
        self.sm.transition.direction = 'left'
        self.sm.current = 'Detail'

        self._detail_body = body
        threading.Thread(target=self._load_extra_details, args=(movie.id, token), daemon=True).start()

    def _load_extra_details(self, movie_id, token):
        cast, similar, trailer_key = fetch_movie_extra(movie_id)
        if token != self._detail_token:
            return
        self._apply_extra_details(cast, similar, trailer_key)

    @mainthread
    def _apply_extra_details(self, cast, similar, trailer_key):
        body = self._detail_body
        if not body:
            return

        if trailer_key:
            trailer_btn = Button(
                text='▶  Watch Trailer', size_hint_y=None, height=dp(42),
                font_name=SYMBOL_FONT,
                background_normal='', background_color=ERROR_COLOR,
                color=TEXT_PRIMARY, font_size='14sp', bold=True,
            )
            trailer_btn.bind(
                on_release=lambda i: open_external_url(f"https://www.youtube.com/watch?v={trailer_key}")
            )
            body.add_widget(trailer_btn)

        if cast:
            body.add_widget(self._label('Cast', '16sp', TEXT_PRIMARY, bold=True, height=dp(28)))
            cast_scroll = ScrollView(
                size_hint=(1, None), height=dp(30),
                do_scroll_x=True, do_scroll_y=False, bar_width=0,
            )
            cast_box = BoxLayout(size_hint=(None, 1), spacing=dp(14))
            cast_box.bind(minimum_width=cast_box.setter('width'))
            for name in cast:
                cast_box.add_widget(Label(
                    text=name, font_size='12sp', color=TEXT_MUTED,
                    size_hint_x=None, width=dp(130),
                    text_size=(dp(130), None), shorten=True, shorten_from='right',
                ))
            cast_scroll.add_widget(cast_box)
            body.add_widget(cast_scroll)

        if similar:
            body.add_widget(self._label('Similar Movies', '16sp', TEXT_PRIMARY, bold=True, height=dp(28)))
            sim_scroll = ScrollView(
                size_hint=(1, None), height=dp(215),
                do_scroll_x=True, do_scroll_y=False, bar_width=0,
            )
            sim_box = BoxLayout(size_hint=(None, 1), spacing=dp(8))
            sim_box.bind(minimum_width=sim_box.setter('width'))
            for mv in similar:
                self.movie_cache[mv.id] = mv
                thumb = MovieCard(mv)
                thumb.size_hint_x = None
                thumb.width = dp(110)
                thumb.bind(on_release=lambda inst: self._render_detail(self.movie_cache.get(inst.movie_id)))
                sim_box.add_widget(thumb)
            sim_scroll.add_widget(sim_box)
            body.add_widget(sim_scroll)

        body.add_widget(Widget(size_hint_y=None, height=dp(20)))

    def _label(self, text, size, color, bold=False, height=None, font_name=None):
        # This helper is only ever used for single-line rows (title, rating,
        # meta, section headers) - shorten instead of wrap so a long value
        # never overflows its fixed height.
        lbl = Label(
            text=text, font_size=size, color=color, bold=bold,
            size_hint_y=None, height=height if height is not None else dp(30),
            halign='left', text_size=(Window.width - dp(34), None),
            font_name=font_name or 'Roboto',
            shorten=True, shorten_from='right',
        )
        return lbl

    def _go_back(self, *a):
        self.sm.transition.direction = 'right'
        self.sm.current = 'Main'

    def on_pause(self):
        # Returning True lets Android background the app and resume it with
        # state intact. The default (False) tears the app down instead.
        return True

    def on_resume(self):
        pass


if __name__ == '__main__':
    MoviePosterApp().run()
