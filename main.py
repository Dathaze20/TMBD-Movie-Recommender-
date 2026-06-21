import os
import sys
import logging
import threading
import requests as http_req
from typing import List, Optional, Dict
from dotenv import load_dotenv

from kivy.config import Config
Config.set('kivy', 'keyboard_mode', 'system')

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
from kivy.uix.screenmanager import ScreenManager, Screen, SlideTransition
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput
from kivy.uix.widget import Widget
from tmdbv3api import TMDb, Movie
from tmdbv3api.exceptions import TMDbException

_script_dir = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(_script_dir, '.env'))

logging.basicConfig(level=logging.INFO, format='%(asctime)s:%(levelname)s:%(message)s')

api_key = os.getenv('TMDB_API_KEY')
if not api_key:
    logging.error("TMDB_API_KEY not found in .env file")

tmdb = TMDb()
tmdb.api_key = api_key or ''

BG = (0.05, 0.05, 0.1, 1)
CARD = (0.12, 0.12, 0.18, 1)
SURFACE = (0.16, 0.16, 0.23, 1)
ACCENT = (0.42, 0.36, 0.91, 1)
ACCENT_GL = (0.55, 0.48, 1.0, 1)
TXT = (0.95, 0.95, 0.97, 1)
TXT_M = (0.52, 0.52, 0.62, 1)
SEARCH_BG = (0.1, 0.1, 0.17, 1)
ERR = (0.92, 0.26, 0.21, 1)
TAB_OFF = (0.12, 0.12, 0.18, 0.7)

GREEN = "4CAF50"
AMBER = "FFC107"
RED_HEX = "F44336"

GENRES = {
    28: "Action", 12: "Adventure", 16: "Animation", 35: "Comedy",
    80: "Crime", 99: "Documentary", 18: "Drama", 10751: "Family",
    14: "Fantasy", 36: "History", 27: "Horror", 10402: "Music",
    9648: "Mystery", 10749: "Romance", 878: "Sci-Fi", 10770: "TV Movie",
    53: "Thriller", 10752: "War", 37: "Western",
}


def rating_hex(score):
    if score >= 7:
        return GREEN
    if score >= 5:
        return AMBER
    return RED_HEX


def fmt_runtime(mins):
    if not mins:
        return ''
    h, m = divmod(mins, 60)
    return f"{h}h {m}m" if h else f"{m}m"


class MovieDetails:
    def __init__(self, title, overview, release_date, poster_path, movie_id,
                 vote_average=0, genre_ids=None):
        self.title = title
        self.overview = overview
        self.release_date = release_date
        self.poster_path = poster_path
        self.id = movie_id
        self.vote_average = vote_average or 0
        self.genre_ids = genre_ids or []

    @property
    def year(self):
        return self.release_date[:4] if self.release_date else ''

    @property
    def genre_text(self):
        return ' / '.join(GENRES.get(g, '') for g in self.genre_ids[:3] if g in GENRES)


def fetch_movies(func, query=None, page_number=1):
    try:
        result = func(query=query, page=page_number) if query else func(page=page_number)
        if not result:
            return None
        return [MovieDetails(
            title=m.title,
            overview=getattr(m, 'overview', ''),
            release_date=getattr(m, 'release_date', ''),
            poster_path=getattr(m, 'poster_path', ''),
            movie_id=m.id,
            vote_average=getattr(m, 'vote_average', 0),
            genre_ids=getattr(m, 'genre_ids', []),
        ) for m in result]
    except Exception as e:
        logging.error(f"Fetch error: {e}")
        return None


def fetch_detail(movie_id):
    try:
        resp = http_req.get(
            f"https://api.themoviedb.org/3/movie/{movie_id}",
            params={"api_key": api_key, "append_to_response": "credits"},
            timeout=10,
        )
        if resp.status_code == 200:
            return resp.json()
    except Exception as e:
        logging.error(f"Detail error: {e}")
    return None


class MovieCard(ButtonBehavior, BoxLayout):
    def __init__(self, movie, **kwargs):
        super().__init__(orientation='vertical', spacing=0, padding=0, **kwargs)
        self.movie_id = movie.id
        self.size_hint_y = None

        with self.canvas.before:
            Color(*CARD)
            self._bg = RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(8)])
        self.bind(
            pos=lambda i, v: setattr(i._bg, 'pos', v),
            size=lambda i, v: setattr(i._bg, 'size', v),
        )

        self.poster = AsyncImage(
            source=f"https://image.tmdb.org/t/p/w185/{movie.poster_path}",
            size_hint=(1, None), allow_stretch=True, keep_ratio=True,
        )
        self.add_widget(self.poster)

        info = BoxLayout(
            orientation='vertical', size_hint_y=None, height=dp(44),
            padding=[dp(5), dp(3)],
        )

        title = Label(
            text=movie.title, font_size='11sp', color=TXT,
            halign='left', valign='middle',
            shorten=True, shorten_from='right', size_hint_y=0.55,
        )
        title.bind(size=lambda i, s: setattr(i, 'text_size', s))

        score = movie.vote_average
        hx = rating_hex(score)
        sc = f"{score:.1f}" if score else '--'
        yr = movie.year
        meta_txt = f"[color={hx}]{sc}[/color]"
        if yr:
            meta_txt += f"  |  {yr}"

        meta = Label(
            text=meta_txt, markup=True,
            font_size='10sp', color=TXT_M,
            halign='left', valign='middle', size_hint_y=0.45,
        )
        meta.bind(size=lambda i, s: setattr(i, 'text_size', s))

        info.add_widget(title)
        info.add_widget(meta)
        self.add_widget(info)
        self.bind(size=self._resize)

    def _resize(self, *a):
        h = self.width * 1.5
        self.poster.height = h
        self.height = h + dp(44)


class SearchBar(BoxLayout):
    search_text = StringProperty('')

    def __init__(self, **kwargs):
        super().__init__(
            orientation='horizontal', size_hint_y=None, height=dp(46),
            spacing=dp(6), padding=[dp(4), 0], **kwargs,
        )
        self.register_event_type('on_search')
        with self.canvas.before:
            Color(*SEARCH_BG)
            self._bg = RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(14)])
        self.bind(
            pos=lambda i, v: setattr(i._bg, 'pos', v),
            size=lambda i, v: setattr(i._bg, 'size', v),
        )

        self.input = TextInput(
            hint_text='Search movies...', hint_text_color=(0.4, 0.4, 0.52, 1),
            multiline=False, size_hint_x=0.82,
            background_color=(0, 0, 0, 0), foreground_color=TXT,
            cursor_color=ACCENT_GL, padding=[dp(14), dp(12)], font_size='15sp',
        )
        clear = Button(
            text='X', size_hint_x=0.18, background_normal='',
            background_color=(*ACCENT[:3], 0.85), color=TXT, font_size='16sp',
        )
        self.add_widget(self.input)
        self.add_widget(clear)
        clear.bind(on_release=self._clear)
        self.input.bind(text=self._chg)
        self.input.bind(on_text_validate=self._go)

    def _chg(self, i, v):
        self.search_text = v

    def _clear(self, *a):
        self.input.text = ''
        self.search_text = ''
        self.dispatch('on_search')

    def _go(self, *a):
        self.dispatch('on_search')

    def on_search(self):
        pass


class CategoryBar(BoxLayout):
    active = StringProperty('Popular')

    def __init__(self, **kwargs):
        super().__init__(
            orientation='horizontal', size_hint_y=None, height=dp(38),
            spacing=dp(5), padding=[dp(2), dp(2)], **kwargs,
        )
        self.register_event_type('on_category')
        self._btns = {}
        for name in ['Popular', 'Top Rated', 'Now Playing']:
            btn = Button(
                text=name, background_normal='',
                background_color=ACCENT if name == 'Popular' else TAB_OFF,
                color=TXT, font_size='13sp', bold=(name == 'Popular'),
            )
            btn.bind(on_release=lambda i, n=name: self._pick(n))
            self._btns[name] = btn
            self.add_widget(btn)

    def _pick(self, name):
        if name == self.active:
            return
        self.active = name
        for n, b in self._btns.items():
            b.background_color = ACCENT if n == name else TAB_OFF
            b.bold = (n == name)
        self.dispatch('on_category', name)

    def on_category(self, *a):
        pass


class MoviePosterApp(App):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.movie_cache: Dict[int, MovieDetails] = {}
        self.status_label = None
        self.error_label = None
        self.grid = None
        self.search_bar = None
        self.title_label = None
        self.cat_bar = None
        self.cur_cat = 'Popular'
        self._detail_body = None
        self._extras_lbl = None

    def build(self):
        Window.clearcolor = BG
        sm = ScreenManager(transition=SlideTransition())
        self.sm = sm
        self.main_scr = Screen(name='Main')
        self.detail_scr = Screen(name='Detail')

        root = BoxLayout(orientation='vertical', padding=dp(6), spacing=dp(5))

        title_bar = BoxLayout(size_hint_y=None, height=dp(50), padding=[dp(14), 0])
        with title_bar.canvas.before:
            Color(*CARD)
            title_bar._bg = RoundedRectangle(
                pos=title_bar.pos, size=title_bar.size, radius=[dp(14)],
            )
        title_bar.bind(
            pos=lambda i, v: setattr(i._bg, 'pos', v),
            size=lambda i, v: setattr(i._bg, 'size', v),
        )
        self.title_label = Label(
            text='Popular Movies', font_size='20sp', bold=True,
            color=TXT, halign='left',
        )
        self.title_label.bind(size=lambda i, s: setattr(i, 'text_size', s))
        title_bar.add_widget(self.title_label)
        root.add_widget(title_bar)

        self.search_bar = SearchBar()
        self.search_bar.bind(on_search=self._on_search)
        root.add_widget(self.search_bar)

        self.cat_bar = CategoryBar()
        self.cat_bar.bind(on_category=self._on_cat)
        root.add_widget(self.cat_bar)

        self.error_label = Label(
            text='', color=ERR, size_hint_y=None, height=dp(0), font_size='13sp',
        )
        root.add_widget(self.error_label)

        self.status_label = Label(
            text='Loading...', color=TXT_M, size_hint_y=None, height=dp(26),
            font_size='13sp',
        )
        root.add_widget(self.status_label)

        scroll = ScrollView(
            size_hint=(1, 1), do_scroll_x=False,
            bar_width=dp(3), bar_color=(*ACCENT[:3], 0.4),
        )
        self.grid = GridLayout(
            cols=3, spacing=dp(5), padding=dp(3), size_hint_y=None,
        )
        self.grid.bind(minimum_height=self.grid.setter('height'))
        scroll.add_widget(self.grid)
        root.add_widget(scroll)

        self.main_scr.add_widget(root)
        sm.add_widget(self.main_scr)
        sm.add_widget(self.detail_scr)

        if not api_key:
            self._err("TMDB_API_KEY missing. Add it to .env in the project folder.")
            self._status('')
            return sm

        threading.Thread(target=self._load_cat, args=('Popular',), daemon=True).start()
        return sm

    def _on_cat(self, inst, cat):
        self.cur_cat = cat
        self.title_label.text = f'{cat} Movies'
        self._clr_err()
        self._clr_grid()
        self._status('Loading...')
        threading.Thread(target=self._load_cat, args=(cat,), daemon=True).start()

    def _on_search(self, *a):
        q = self.search_bar.search_text.strip()
        self._clr_err()
        self._clr_grid()
        if not q:
            cat = self.cat_bar.active
            self.title_label.text = f'{cat} Movies'
            self._status('Loading...')
            threading.Thread(target=self._load_cat, args=(cat,), daemon=True).start()
            return
        self.title_label.text = f'Search: {q}'
        self._status('Searching...')
        threading.Thread(target=self._do_search, args=(q,), daemon=True).start()

    def _cat_func(self, cat):
        m = Movie()
        if cat == 'Top Rated':
            return m.top_rated
        if cat == 'Now Playing':
            return m.now_playing
        return m.popular

    def _load_cat(self, cat):
        try:
            func = self._cat_func(cat)
            first = fetch_movies(func, page_number=1)
            if not first:
                self._err("Could not load movies. Check your connection.")
                self._status('')
                return
            for mv in first:
                self.movie_cache[mv.id] = mv
                self._add_card(mv)
            self._status('')

            for p in range(2, 4):
                if self.cur_cat != cat:
                    return
                more = fetch_movies(func, page_number=p)
                if more:
                    for mv in more:
                        self.movie_cache[mv.id] = mv
                        self._add_card(mv)
        except Exception as e:
            logging.error(f"Load error: {e}")
            self._err(str(e))
            self._status('')

    def _do_search(self, query):
        try:
            first = fetch_movies(Movie().search, query, 1)
            if not first:
                self._err("No movies found.")
                self._status('')
                return
            for mv in first:
                self.movie_cache[mv.id] = mv
                self._add_card(mv)
            self._status('')

            for p in range(2, 4):
                more = fetch_movies(Movie().search, query, p)
                if more:
                    for mv in more:
                        self.movie_cache[mv.id] = mv
                        self._add_card(mv)
        except Exception as e:
            logging.error(f"Search error: {e}")
            self._err(str(e))
            self._status('')

    @mainthread
    def _add_card(self, movie):
        if not self.grid or not movie.poster_path:
            return
        card = MovieCard(movie)
        card.bind(on_release=self._open_detail)
        self.grid.add_widget(card)

    @mainthread
    def _err(self, msg):
        if self.error_label:
            self.error_label.text = msg
            self.error_label.height = dp(26)

    @mainthread
    def _clr_err(self):
        if self.error_label:
            self.error_label.text = ''
            self.error_label.height = dp(0)

    @mainthread
    def _clr_grid(self):
        if self.grid:
            self.grid.clear_widgets()

    @mainthread
    def _status(self, text):
        if self.status_label:
            self.status_label.text = text
            self.status_label.height = dp(26) if text else dp(0)

    def _open_detail(self, inst):
        mid = getattr(inst, 'movie_id', None)
        if mid is None:
            return
        movie = self.movie_cache.get(mid)
        if not movie:
            return

        self.detail_scr.clear_widgets()
        w = Window.width - dp(34)

        page = BoxLayout(orientation='vertical')
        with page.canvas.before:
            Color(*BG)
            page._bg = Rectangle(pos=page.pos, size=page.size)
        page.bind(
            pos=lambda i, v: setattr(i._bg, 'pos', v),
            size=lambda i, v: setattr(i._bg, 'size', v),
        )

        top = BoxLayout(
            size_hint_y=None, height=dp(48),
            padding=[dp(6), dp(4)], spacing=dp(6),
        )
        with top.canvas.before:
            Color(*CARD)
            top._bg = Rectangle(pos=top.pos, size=top.size)
        top.bind(
            pos=lambda i, v: setattr(i._bg, 'pos', v),
            size=lambda i, v: setattr(i._bg, 'size', v),
        )
        back = Button(
            text='< Back', size_hint_x=0.22, background_normal='',
            background_color=ACCENT, color=TXT, font_size='13sp', bold=True,
        )
        back.bind(on_release=self._go_back)
        ttl = Label(
            text=movie.title, font_size='15sp', bold=True, color=TXT,
            shorten=True, shorten_from='right', halign='center', size_hint_x=0.78,
        )
        ttl.bind(size=lambda i, s: setattr(i, 'text_size', s))
        top.add_widget(back)
        top.add_widget(ttl)
        page.add_widget(top)

        scroll = ScrollView(size_hint=(1, 1), do_scroll_x=False)
        body = BoxLayout(
            orientation='vertical', size_hint_y=None,
            padding=dp(14), spacing=dp(8),
        )
        body.bind(minimum_height=body.setter('height'))
        self._detail_body = body

        if movie.poster_path:
            body.add_widget(AsyncImage(
                source=f"https://image.tmdb.org/t/p/w500/{movie.poster_path}",
                size_hint=(1, None), height=dp(380),
                allow_stretch=True, keep_ratio=True,
            ))

        body.add_widget(self._lbl(movie.title, '22sp', TXT, bold=True, h=dp(36), w=w))

        score = movie.vote_average
        hx = rating_hex(score)
        sc = f"{score:.1f}/10" if score else 'N/A'
        body.add_widget(self._lbl(
            f"[color={hx}]{sc}[/color]", '17sp', TXT_M,
            h=dp(28), w=w, markup=True,
        ))

        meta = []
        if movie.year:
            meta.append(movie.year)
        if movie.genre_text:
            meta.append(movie.genre_text)
        if meta:
            body.add_widget(self._lbl(' | '.join(meta), '13sp', TXT_M, h=dp(22), w=w))

        body.add_widget(self._sep())
        body.add_widget(self._lbl('Overview', '16sp', TXT, bold=True, h=dp(28), w=w))

        if movie.overview:
            ov = Label(
                text=movie.overview, font_size='14sp',
                color=(0.78, 0.78, 0.84, 1), size_hint_y=None,
                halign='left', valign='top', text_size=(w, None),
            )
            ov.bind(texture_size=ov.setter('size'))
            body.add_widget(ov)

        body.add_widget(self._sep())
        self._extras_lbl = self._lbl(
            'Loading details...', '12sp', TXT_M, h=dp(20), w=w,
        )
        body.add_widget(self._extras_lbl)
        body.add_widget(Widget(size_hint_y=None, height=dp(30)))

        scroll.add_widget(body)
        page.add_widget(scroll)
        self.detail_scr.add_widget(page)
        self.sm.transition.direction = 'left'
        self.sm.current = 'Detail'

        threading.Thread(
            target=self._fetch_extras, args=(movie.id,), daemon=True,
        ).start()

    def _fetch_extras(self, movie_id):
        data = fetch_detail(movie_id)
        if data:
            self._show_extras(data)
        else:
            self._set_extras_text('')

    @mainthread
    def _show_extras(self, data):
        body = self._detail_body
        if not body:
            return
        w = Window.width - dp(34)

        if self._extras_lbl and self._extras_lbl.parent:
            body.remove_widget(self._extras_lbl)

        runtime = data.get('runtime', 0)
        tagline = data.get('tagline', '')
        vote_count = data.get('vote_count', 0)
        budget = data.get('budget', 0)
        revenue = data.get('revenue', 0)

        info = []
        if runtime:
            info.append(fmt_runtime(runtime))
        if vote_count:
            info.append(f"{vote_count:,} votes")
        if info:
            body.add_widget(self._lbl(' | '.join(info), '13sp', TXT_M, h=dp(22), w=w))

        if tagline:
            body.add_widget(self._lbl(
                f'"{tagline}"', '13sp', ACCENT_GL, h=dp(26), w=w,
            ))

        if budget:
            body.add_widget(self._lbl(
                f"Budget: ${budget:,.0f}", '12sp', TXT_M, h=dp(20), w=w,
            ))
        if revenue:
            body.add_widget(self._lbl(
                f"Revenue: ${revenue:,.0f}", '12sp', TXT_M, h=dp(20), w=w,
            ))

        credits = data.get('credits', {})
        crew = credits.get('crew', [])
        cast = credits.get('cast', [])[:8]

        directors = [c['name'] for c in crew if c.get('job') == 'Director']
        if directors:
            body.add_widget(self._sep())
            body.add_widget(self._lbl('Director', '15sp', TXT, bold=True, h=dp(26), w=w))
            body.add_widget(self._lbl(
                ', '.join(directors), '13sp', TXT_M, h=dp(22), w=w,
            ))

        if cast:
            body.add_widget(self._sep())
            body.add_widget(self._lbl('Cast', '15sp', TXT, bold=True, h=dp(26), w=w))
            for actor in cast:
                name = actor.get('name', '')
                char = actor.get('character', '')
                line = f"{name}  -  {char}" if char else name
                body.add_widget(self._lbl(
                    line, '12sp', (0.7, 0.7, 0.78, 1), h=dp(22), w=w,
                ))

        body.add_widget(Widget(size_hint_y=None, height=dp(40)))

    @mainthread
    def _set_extras_text(self, text):
        if self._extras_lbl:
            self._extras_lbl.text = text

    def _lbl(self, text, size, color, bold=False, h=dp(30), w=None, markup=False):
        return Label(
            text=text, font_size=size, color=color, bold=bold, markup=markup,
            size_hint_y=None, height=h, halign='left',
            text_size=(w or (Window.width - dp(34)), None),
        )

    def _sep(self):
        s = Widget(size_hint_y=None, height=dp(1))
        with s.canvas:
            Color(*SURFACE)
            s._r = Rectangle(pos=s.pos, size=s.size)
        s.bind(
            pos=lambda i, v: setattr(i._r, 'pos', v),
            size=lambda i, v: setattr(i._r, 'size', v),
        )
        return s

    def _go_back(self, *a):
        self.sm.transition.direction = 'right'
        self.sm.current = 'Main'


if __name__ == '__main__':
    MoviePosterApp().run()
