import os
import sys
import logging
import threading
from typing import List, Optional, Dict
from dotenv import load_dotenv

from kivy.config import Config
Config.set('kivy', 'keyboard_mode', 'system')

from kivy.app import App
from kivy.clock import Clock, mainthread
from kivy.core.window import Window
from kivy.graphics import Color, Rectangle, RoundedRectangle
from kivy.metrics import dp
from kivy.properties import StringProperty, NumericProperty
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

GENRES = {
    28: "Action", 12: "Adventure", 16: "Animation", 35: "Comedy",
    80: "Crime", 99: "Documentary", 18: "Drama", 10751: "Family",
    14: "Fantasy", 36: "History", 27: "Horror", 10402: "Music",
    9648: "Mystery", 10749: "Romance", 878: "Sci-Fi", 10770: "TV Movie",
    53: "Thriller", 10752: "War", 37: "Western",
}


def star_text(rating):
    filled = round((rating or 0) / 2)
    return '★' * filled + '☆' * (5 - filled)


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
        names = [GENRES.get(g, '') for g in self.genre_ids[:3]]
        return ' • '.join(n for n in names if n)


def fetch_movies(func, query=None, page_number=1):
    try:
        result = func(query=query, page=page_number) if query else func(page=page_number)
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

        poster_url = f"https://image.tmdb.org/t/p/w342/{movie.poster_path}"
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

        score = f"{movie.vote_average:.1f}" if movie.vote_average else ''
        stars_lbl = Label(
            text=f"{star_text(movie.vote_average)} {score}",
            font_size='9sp', color=GOLD,
            halign='left', valign='middle', size_hint_x=0.72,
        )
        stars_lbl.bind(size=lambda i, s: setattr(i, 'text_size', s))

        year_lbl = Label(
            text=movie.year, font_size='9sp', color=TEXT_MUTED,
            halign='right', valign='middle', size_hint_x=0.28,
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
            text='✕', size_hint_x=0.18,
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

    def _clear(self, *a):
        self.input.text = ''
        self.search_text = ''
        self.dispatch('on_search')

    def _submit(self, *a):
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
                background_color=ACCENT if name == 'Popular' else TAB_INACTIVE,
                color=TEXT_PRIMARY, font_size='13sp', bold=(name == 'Popular'),
            )
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
        self.loading_popup = None
        self.error_label = None
        self.grid = None
        self.search_bar = None
        self.title_label = None
        self.cat_bar = None
        self.current_cat = 'Popular'

    def build(self):
        Window.clearcolor = BG_COLOR

        sm = ScreenManager(transition=SlideTransition())
        self.sm = sm
        self.main_scr = Screen(name='Main')
        self.detail_scr = Screen(name='Detail')

        root = BoxLayout(orientation='vertical', padding=dp(6), spacing=dp(5))

        title_bar = BoxLayout(size_hint_y=None, height=dp(50), padding=[dp(14), 0])
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
        )
        self.title_label.bind(size=lambda i, s: setattr(i, 'text_size', s))
        title_bar.add_widget(self.title_label)
        root.add_widget(title_bar)

        self.search_bar = SearchBar()
        self.search_bar.bind(on_search=self._on_search)
        root.add_widget(self.search_bar)

        self.cat_bar = CategoryBar()
        self.cat_bar.bind(on_category=self._on_category)
        root.add_widget(self.cat_bar)

        self.error_label = Label(
            text='', color=ERROR_COLOR, size_hint_y=None,
            height=dp(0), font_size='13sp',
        )
        root.add_widget(self.error_label)

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
            self._show_error("TMDB_API_KEY missing. Add it to .env in the project folder.")
            return sm

        self._show_loading()
        threading.Thread(target=self._load_cat, args=('Popular',), daemon=True).start()
        return sm

    def _on_category(self, inst, cat):
        self.current_cat = cat
        self.title_label.text = f'{cat} Movies'
        self._clear_error()
        self._clear_grid()
        self._show_loading()
        threading.Thread(target=self._load_cat, args=(cat,), daemon=True).start()

    def _on_search(self, *a):
        q = self.search_bar.search_text.strip()
        self._clear_error()
        self._clear_grid()

        if not q:
            cat = self.cat_bar.active
            self.title_label.text = f'{cat} Movies'
            self._show_loading()
            threading.Thread(target=self._load_cat, args=(cat,), daemon=True).start()
            return

        self.title_label.text = f'Search: {q}'
        self._show_loading()
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
                self._show_error("Could not load movies. Check your connection.")
                self._hide_loading()
                return
            for mv in first:
                self.movie_cache[mv.id] = mv
                self._add_card(mv)
            self._hide_loading()

            for p in range(2, 4):
                if self.current_cat != cat:
                    return
                more = fetch_movies(func, page_number=p)
                if more:
                    for mv in more:
                        self.movie_cache[mv.id] = mv
                        self._add_card(mv)
        except Exception as e:
            logging.error(f"Load error: {e}")
            self._show_error(str(e))
            self._hide_loading()

    def _do_search(self, query):
        try:
            first = fetch_movies(Movie().search, query, 1)
            if not first:
                self._show_error("No movies found.")
                self._hide_loading()
                return
            for mv in first:
                self.movie_cache[mv.id] = mv
                self._add_card(mv)
            self._hide_loading()

            for p in range(2, 4):
                more = fetch_movies(Movie().search, query, p)
                if more:
                    for mv in more:
                        self.movie_cache[mv.id] = mv
                        self._add_card(mv)
        except Exception as e:
            logging.error(f"Search error: {e}")
            self._show_error(str(e))
            self._hide_loading()

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
            self.error_label.height = dp(26)

    @mainthread
    def _clear_error(self):
        if self.error_label:
            self.error_label.text = ''
            self.error_label.height = dp(0)

    @mainthread
    def _clear_grid(self):
        if self.grid:
            self.grid.clear_widgets()

    @mainthread
    def _show_loading(self):
        self.loading_popup = Popup(
            title='', separator_height=0,
            content=Label(text='Loading...', color=TEXT_PRIMARY, font_size='15sp'),
            size_hint=(None, None), size=(dp(150), dp(90)),
            auto_dismiss=False,
            background_color=(*CARD_COLOR[:3], 0.95),
        )
        self.loading_popup.open()

    @mainthread
    def _hide_loading(self):
        if self.loading_popup:
            self.loading_popup.dismiss()

    def _open_detail(self, inst):
        mid = getattr(inst, 'movie_id', None)
        if mid is None:
            return
        movie = self.movie_cache.get(mid)
        if not movie:
            return

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
            text='← Back', size_hint_x=0.22,
            background_normal='', background_color=ACCENT,
            color=TEXT_PRIMARY, font_size='13sp', bold=True,
        )
        back.bind(on_release=self._go_back)

        ttl = Label(
            text=movie.title, font_size='15sp', bold=True,
            color=TEXT_PRIMARY, shorten=True, shorten_from='right',
            halign='center', size_hint_x=0.78,
        )
        ttl.bind(size=lambda i, s: setattr(i, 'text_size', s))

        top.add_widget(back)
        top.add_widget(ttl)
        page.add_widget(top)

        scroll = ScrollView(size_hint=(1, 1), do_scroll_x=False)
        body = BoxLayout(
            orientation='vertical', size_hint_y=None,
            padding=dp(14), spacing=dp(10),
        )
        body.bind(minimum_height=body.setter('height'))

        if movie.poster_path:
            body.add_widget(AsyncImage(
                source=f"https://image.tmdb.org/t/p/w500/{movie.poster_path}",
                size_hint=(1, None), height=dp(380),
                allow_stretch=True, keep_ratio=True,
            ))

        body.add_widget(self._label(
            movie.title, '22sp', TEXT_PRIMARY, bold=True, height=dp(36),
        ))

        stars = star_text(movie.vote_average)
        score = f"{movie.vote_average:.1f}/10" if movie.vote_average else 'N/A'
        body.add_widget(self._label(f"{stars}  {score}", '16sp', GOLD, height=dp(28)))

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

        body.add_widget(Widget(size_hint_y=None, height=dp(30)))

        scroll.add_widget(body)
        page.add_widget(scroll)

        self.detail_scr.add_widget(page)
        self.sm.transition.direction = 'left'
        self.sm.current = 'Detail'

    def _label(self, text, size, color, bold=False, height=dp(30)):
        lbl = Label(
            text=text, font_size=size, color=color, bold=bold,
            size_hint_y=None, height=height,
            halign='left', text_size=(Window.width - dp(34), None),
        )
        return lbl

    def _go_back(self, *a):
        self.sm.transition.direction = 'right'
        self.sm.current = 'Main'


if __name__ == '__main__':
    MoviePosterApp().run()
