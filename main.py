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

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s:%(levelname)s:%(message)s'
)

api_key = os.getenv('TMDB_API_KEY')
if not api_key:
    logging.error("TMDB_API_KEY not found in .env file")

tmdb = TMDb()
tmdb.api_key = api_key or ''

BG_COLOR = (0.08, 0.08, 0.12, 1)
CARD_COLOR = (0.14, 0.14, 0.2, 1)
ACCENT_COLOR = (0.9, 0.3, 0.1, 1)
TEXT_COLOR = (0.95, 0.95, 0.95, 1)
SEARCH_BG = (0.18, 0.18, 0.25, 1)


class MovieDetails:
    def __init__(self, title: str, overview: str, release_date: str, poster_path: str, id: int):
        self.title = title
        self.overview = overview
        self.release_date = release_date
        self.poster_path = poster_path
        self.id = id


def fetch_movies(func, query=None, page_number=1) -> Optional[List[MovieDetails]]:
    try:
        result_page = func(query=query, page=page_number) if query else func(page=page_number)
        if not result_page:
            return None
        return [
            MovieDetails(m.title, m.overview, m.release_date, m.poster_path, m.id)
            for m in result_page
        ]
    except Exception as e:
        logging.error(f"Error fetching movies: {e}")
        return None


class MovieCard(ButtonBehavior, BoxLayout):
    def __init__(self, movie_details, **kwargs):
        super().__init__(orientation='vertical', spacing=dp(2), **kwargs)
        self.movie_id = movie_details.id
        self.size_hint_y = None

        poster_url = f"https://image.tmdb.org/t/p/w342/{movie_details.poster_path}"
        self.poster = AsyncImage(
            source=poster_url,
            size_hint=(1, None),
            allow_stretch=True,
            keep_ratio=True,
        )
        self.add_widget(self.poster)

        title_label = Label(
            text=movie_details.title,
            size_hint=(1, None),
            height=dp(32),
            font_size='12sp',
            color=TEXT_COLOR,
            halign='center',
            valign='middle',
            shorten=True,
            shorten_from='right',
        )
        title_label.bind(size=lambda inst, sz: setattr(inst, 'text_size', sz))
        self.add_widget(title_label)

        self.bind(size=self._update_height)

    def _update_height(self, *args):
        poster_h = self.width * 1.5
        self.poster.height = poster_h
        self.height = poster_h + dp(32)


class SearchBar(BoxLayout):
    search_text = StringProperty('')

    def __init__(self, **kwargs):
        super().__init__(
            orientation='horizontal',
            size_hint_y=None,
            height=dp(48),
            spacing=dp(8),
            **kwargs
        )
        self.register_event_type('on_search')

        with self.canvas.before:
            Color(*SEARCH_BG)
            self.bg_rect = RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(12)])
        self.bind(pos=self._update_bg, size=self._update_bg)

        self.search_input = TextInput(
            hint_text='Search for a movie...',
            hint_text_color=(0.5, 0.5, 0.6, 1),
            multiline=False,
            size_hint_x=0.85,
            background_color=(0, 0, 0, 0),
            foreground_color=TEXT_COLOR,
            cursor_color=ACCENT_COLOR,
            padding=[dp(12), dp(12), dp(12), dp(12)],
        )
        clear_btn = Button(
            text='X',
            size_hint_x=0.15,
            background_color=(*ACCENT_COLOR[:3], 0.8),
            background_normal='',
            color=TEXT_COLOR,
            font_size='16sp',
            bold=True,
        )

        self.add_widget(self.search_input)
        self.add_widget(clear_btn)

        clear_btn.bind(on_release=self._clear_text)
        self.search_input.bind(text=self._on_text_change)
        self.search_input.bind(on_text_validate=self._on_validate)

    def _update_bg(self, *args):
        self.bg_rect.pos = self.pos
        self.bg_rect.size = self.size

    def _on_text_change(self, instance, value):
        self.search_text = value

    def _clear_text(self, instance):
        self.search_input.text = ''
        self.search_text = ''
        self.dispatch('on_search')

    def _on_validate(self, instance):
        self.dispatch('on_search')

    def on_search(self):
        pass


class MoviePosterApp(App):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.movie_cache: Dict[int, MovieDetails] = {}
        self.loading_popup: Optional[Popup] = None
        self.error_label: Optional[Label] = None
        self.poster_grid_layout: Optional[GridLayout] = None
        self.search_bar: Optional[SearchBar] = None

    def build(self):
        Window.clearcolor = BG_COLOR

        self.screen_manager = ScreenManager(transition=SlideTransition())
        self.main_screen = Screen(name="Main Screen")
        self.detail_screen = Screen(name="Detail Screen")

        root_layout = BoxLayout(orientation='vertical', padding=dp(8), spacing=dp(6))

        title_bar = BoxLayout(size_hint_y=None, height=dp(52))
        with title_bar.canvas.before:
            Color(*CARD_COLOR)
            title_bar._bg = RoundedRectangle(pos=title_bar.pos, size=title_bar.size, radius=[dp(10)])
        title_bar.bind(
            pos=lambda i, v: setattr(i._bg, 'pos', v),
            size=lambda i, v: setattr(i._bg, 'size', v),
        )
        title_label = Label(
            text='Popular Movies',
            font_size='22sp',
            bold=True,
            color=TEXT_COLOR,
        )
        title_bar.add_widget(title_label)
        self.title_label = title_label
        root_layout.add_widget(title_bar)

        self.search_bar = SearchBar()
        self.search_bar.bind(on_search=self.perform_search)
        root_layout.add_widget(self.search_bar)

        self.error_label = Label(
            text="",
            color=ACCENT_COLOR,
            size_hint_y=None,
            height=dp(0),
            font_size='14sp',
        )
        root_layout.add_widget(self.error_label)

        scroll_view = ScrollView(size_hint=(1, 1), do_scroll_x=False, bar_width=dp(4))
        self.poster_grid_layout = GridLayout(
            cols=3,
            spacing=dp(6),
            padding=dp(4),
            size_hint_y=None,
        )
        self.poster_grid_layout.bind(minimum_height=self.poster_grid_layout.setter('height'))
        scroll_view.add_widget(self.poster_grid_layout)
        root_layout.add_widget(scroll_view)

        self.main_screen.add_widget(root_layout)
        self.screen_manager.add_widget(self.main_screen)
        self.screen_manager.add_widget(self.detail_screen)

        if not api_key:
            self.show_error("TMDB_API_KEY missing. Add it to .env in the project folder.")
            return self.screen_manager

        self.show_loading_popup()
        threading.Thread(target=self.load_movies, daemon=True).start()

        return self.screen_manager

    @mainthread
    def show_error(self, message: str):
        if self.error_label:
            self.error_label.text = message
            self.error_label.height = dp(30)

    @mainthread
    def clear_error(self):
        if self.error_label:
            self.error_label.text = ""
            self.error_label.height = dp(0)

    @mainthread
    def add_movie_poster(self, movie_details: MovieDetails):
        if not self.poster_grid_layout:
            return
        if not movie_details.poster_path:
            return

        card = MovieCard(movie_details)
        card.bind(on_release=self.show_movie_details)
        self.poster_grid_layout.add_widget(card)

    def perform_search(self, *args):
        search_query = self.search_bar.search_text.strip()
        self.clear_error()
        self.clear_movie_grid()

        if not search_query:
            self.title_label.text = 'Popular Movies'
            self.load_initial_movies()
            return

        self.title_label.text = f'Results: {search_query}'
        self.show_loading_popup()
        threading.Thread(target=self._search_movies, args=(search_query,), daemon=True).start()

    def _search_movies(self, query):
        try:
            page = fetch_movies(Movie().search, query, 1)
            if not page:
                self.show_error("No movies found with that name.")
                self.dismiss_loading_popup()
                return

            for movie in page:
                self.movie_cache[movie.id] = movie
                self.add_movie_poster(movie)
            self.dismiss_loading_popup()

            for page_number in range(2, 6):
                more = fetch_movies(Movie().search, query, page_number)
                if more:
                    for movie in more:
                        self.movie_cache[movie.id] = movie
                        self.add_movie_poster(movie)
        except TMDbException as e:
            logging.error(f"TMDb API error: {e}")
            self.show_error(f"TMDb API error: {e}")
            self.dismiss_loading_popup()
        except Exception as e:
            logging.error(f"Search error: {e}")
            self.show_error(f"Error searching movies: {e}")
            self.dismiss_loading_popup()

    @mainthread
    def show_loading_popup(self):
        self.loading_popup = Popup(
            title='',
            separator_height=0,
            content=Label(text='Loading movies...', color=TEXT_COLOR, font_size='16sp'),
            size_hint=(None, None),
            size=(dp(200), dp(120)),
            auto_dismiss=False,
            background_color=(*CARD_COLOR[:3], 0.95),
        )
        self.loading_popup.open()

    @mainthread
    def dismiss_loading_popup(self):
        if self.loading_popup:
            self.loading_popup.dismiss()

    @mainthread
    def clear_movie_grid(self):
        if self.poster_grid_layout:
            self.poster_grid_layout.clear_widgets()

    def load_initial_movies(self):
        self.show_loading_popup()
        threading.Thread(target=self.load_movies, daemon=True).start()

    def load_movies(self):
        try:
            page = fetch_movies(Movie().popular, page_number=1)
            if not page:
                self.show_error("Could not load movies. Check your internet connection.")
                self.dismiss_loading_popup()
                return

            for movie in page:
                self.movie_cache[movie.id] = movie
                self.add_movie_poster(movie)
            self.dismiss_loading_popup()

            for page_number in range(2, 6):
                more = fetch_movies(Movie().popular, page_number=page_number)
                if more:
                    for movie in more:
                        self.movie_cache[movie.id] = movie
                        self.add_movie_poster(movie)
        except TMDbException as e:
            logging.error(f"TMDb API error: {e}")
            self.show_error(f"TMDb API error: {e}")
            self.dismiss_loading_popup()
        except Exception as e:
            logging.error(f"Load error: {e}")
            self.show_error(f"Error loading movies: {e}")
            self.dismiss_loading_popup()

    def show_movie_details(self, instance):
        movie_id = getattr(instance, 'movie_id', None)
        if movie_id is None:
            return

        movie = self.movie_cache.get(movie_id)
        if movie is None:
            return

        self.detail_screen.clear_widgets()

        detail_root = BoxLayout(orientation='vertical', padding=dp(0), spacing=dp(0))
        with detail_root.canvas.before:
            Color(*BG_COLOR)
            detail_root._bg = Rectangle(pos=detail_root.pos, size=detail_root.size)
        detail_root.bind(
            pos=lambda i, v: setattr(i._bg, 'pos', v),
            size=lambda i, v: setattr(i._bg, 'size', v),
        )

        top_bar = BoxLayout(size_hint_y=None, height=dp(50), padding=[dp(8), 0])
        with top_bar.canvas.before:
            Color(*CARD_COLOR)
            top_bar._bg = Rectangle(pos=top_bar.pos, size=top_bar.size)
        top_bar.bind(
            pos=lambda i, v: setattr(i._bg, 'pos', v),
            size=lambda i, v: setattr(i._bg, 'size', v),
        )

        back_button = Button(
            text='< Back',
            size_hint_x=0.25,
            background_color=(*ACCENT_COLOR[:3], 0.9),
            background_normal='',
            color=TEXT_COLOR,
            font_size='14sp',
            bold=True,
        )
        back_button.bind(on_release=self.go_back)
        top_bar.add_widget(back_button)

        top_bar.add_widget(Label(
            text=movie.title,
            font_size='16sp',
            bold=True,
            color=TEXT_COLOR,
            shorten=True,
            shorten_from='right',
            text_size=(Window.width * 0.65, None),
            halign='center',
        ))
        detail_root.add_widget(top_bar)

        scroll = ScrollView(size_hint=(1, 1), do_scroll_x=False)
        content = BoxLayout(orientation='vertical', size_hint_y=None, padding=dp(12), spacing=dp(12))
        content.bind(minimum_height=content.setter('height'))

        if movie.poster_path:
            poster = AsyncImage(
                source=f"https://image.tmdb.org/t/p/w500/{movie.poster_path}",
                size_hint=(1, None),
                height=dp(350),
                allow_stretch=True,
                keep_ratio=True,
            )
            content.add_widget(poster)

        title = Label(
            text=movie.title,
            font_size='22sp',
            bold=True,
            color=TEXT_COLOR,
            size_hint_y=None,
            height=dp(40),
            halign='left',
            text_size=(Window.width - dp(40), None),
        )
        content.add_widget(title)

        if movie.release_date:
            date_label = Label(
                text=f"Release: {movie.release_date}",
                font_size='14sp',
                color=(0.6, 0.6, 0.7, 1),
                size_hint_y=None,
                height=dp(24),
                halign='left',
                text_size=(Window.width - dp(40), None),
            )
            content.add_widget(date_label)

        if movie.overview:
            overview = Label(
                text=movie.overview,
                font_size='14sp',
                color=(0.8, 0.8, 0.85, 1),
                size_hint_y=None,
                halign='left',
                valign='top',
                text_size=(Window.width - dp(40), None),
            )
            overview.bind(texture_size=overview.setter('size'))
            content.add_widget(overview)

        content.add_widget(Widget(size_hint_y=None, height=dp(20)))

        scroll.add_widget(content)
        detail_root.add_widget(scroll)

        self.detail_screen.add_widget(detail_root)
        self.screen_manager.transition.direction = 'left'
        self.screen_manager.current = "Detail Screen"

    def go_back(self, instance):
        self.screen_manager.transition.direction = 'right'
        self.screen_manager.current = "Main Screen"


if __name__ == '__main__':
    MoviePosterApp().run()
