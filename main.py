import os
import logging
import requests
from typing import List, Optional, Dict

from kivy.app import App
from kivy.clock import Clock, mainthread
from kivy.config import Config
from kivy.core.window import Window
from kivy.graphics import Color, Rectangle
from kivy.properties import StringProperty, ObjectProperty
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.gridlayout import GridLayout
from kivy.uix.image import AsyncImage
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.screenmanager import ScreenManager, Screen
from kivy.uix.scrollview import ScrollView
from kivy.uix.spinner import Spinner
from kivy.uix.textinput import TextInput
from dotenv import load_dotenv
from tmdbv3api import TMDb, Movie
from tmdbv3api.exceptions import TMDbException

logging.basicConfig(
    filename='movie_app.log',
    level=logging.INFO,
    format='%(asctime)s:%(levelname)s:%(message)s'
)
load_dotenv()
Config.set('graphics', 'width', '800')
Config.set('graphics', 'height', '600')
Config.set('kivy', 'keyboard_mode', 'system')
Config.set('graphics', 'fullscreen', 'auto')

api_key = os.getenv('TMDB_API_KEY', '412cb4afbe96d39f9db34601104ff7e4')
tmdb = TMDb()
tmdb.api_key = api_key


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


class ClickableImage(ButtonBehavior, AsyncImage):
    pass


class ClearButton(ButtonBehavior, Label):
    bg_color = (0.7, 0.7, 0.7, 1)

    def __init__(self, **kwargs):
        kwargs.setdefault('text', 'X')
        super().__init__(**kwargs)
        with self.canvas.before:
            Color(*self.bg_color)
            self.rect = Rectangle(pos=self.pos, size=self.size)
        self.bind(size=self._update_rect, pos=self._update_rect)

    def _update_rect(self, *args):
        self.rect.pos = self.pos
        self.rect.size = self.size


class SearchBar(BoxLayout):
    search_text = StringProperty('')

    def __init__(self, **kwargs):
        super().__init__(
            orientation='horizontal',
            size_hint_y=None,
            height=Window.height * 0.07,
            **kwargs
        )
        self.register_event_type('on_search')

        self.search_input = TextInput(
            hint_text='Search for a movie...',
            multiline=False,
            size_hint_x=0.9
        )
        self.clear_button = ClearButton(size_hint_x=0.1)

        self.add_widget(self.search_input)
        self.add_widget(self.clear_button)

        self.clear_button.bind(on_release=self._clear_text)
        self.search_input.bind(text=self._on_text_change)
        self.search_input.bind(on_text_validate=self._on_validate)

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
        self.screen_manager = ScreenManager()
        self.main_screen = Screen(name="Main Screen")
        self.detail_screen = Screen(name="Detail Screen")

        root_layout = BoxLayout(orientation='vertical', padding=10)

        root_layout.add_widget(
            Label(text="Popular Movies", font_size='24sp', size_hint_y=None, height=50)
        )

        self.search_bar = SearchBar()
        self.search_bar.bind(on_search=self.perform_search)
        root_layout.add_widget(self.search_bar)

        self.error_label = Label(text="", color=(1, 0, 0, 1), size_hint_y=None, height=30)
        root_layout.add_widget(self.error_label)

        scroll_view = ScrollView(size_hint=(1, 1), do_scroll_x=False)
        self.poster_grid_layout = GridLayout(cols=3, spacing=10, size_hint_y=None)
        self.poster_grid_layout.bind(minimum_height=self.poster_grid_layout.setter('height'))
        scroll_view.add_widget(self.poster_grid_layout)
        root_layout.add_widget(scroll_view)

        self.main_screen.add_widget(root_layout)
        self.screen_manager.add_widget(self.main_screen)
        self.screen_manager.add_widget(self.detail_screen)

        if not tmdb.api_key:
            self.show_error("Error: TMDB API key not found. Check your environment variables.")
            return self.screen_manager

        self.show_loading_popup()
        Clock.schedule_once(self.load_movies, 1)

        return self.screen_manager

    @mainthread
    def show_error(self, message: str):
        if self.error_label:
            self.error_label.text = message

    @mainthread
    def clear_error(self):
        if self.error_label:
            self.error_label.text = ""

    @mainthread
    def add_movie_poster(self, movie_details: MovieDetails):
        if not self.poster_grid_layout:
            return

        if not movie_details.poster_path:
            logging.warning(f"No poster available for: {movie_details.title}")
            return

        poster_url = f"https://image.tmdb.org/t/p/w500/{movie_details.poster_path}"
        movie_poster = ClickableImage(source=poster_url, size_hint_y=None, height=300)
        movie_poster.movie_id = movie_details.id
        movie_poster.bind(on_release=self.show_movie_details)
        self.poster_grid_layout.add_widget(movie_poster)

    def perform_search(self, *args):
        search_query = self.search_bar.search_text.strip()
        self.clear_error()
        self.clear_movie_grid()

        if not search_query:
            self.load_initial_movies()
            return

        self.show_loading_popup()
        Clock.schedule_once(lambda dt: self._search_movies(search_query), 0.5)

    def _search_movies(self, query):
        try:
            all_movies = []
            for page_number in range(1, 6):
                page = fetch_movies(Movie().search, query, page_number)
                if page:
                    all_movies.extend(page)

            if not all_movies:
                self.show_error("No movies found with that name.")
                return

            for movie in all_movies:
                self.movie_cache[movie.id] = movie
                self.add_movie_poster(movie)
        except TMDbException as e:
            logging.error(f"TMDb API error: {e}")
            self.show_error(f"TMDb API error: {e}")
        except Exception as e:
            logging.error(f"Search error: {e}")
            self.show_error(f"Error searching movies: {e}")
        finally:
            self.dismiss_loading_popup()

    def show_loading_popup(self):
        self.loading_popup = Popup(
            title='Loading',
            content=Spinner(),
            size_hint=(None, None),
            size=(200, 200)
        )
        self.loading_popup.open()

    def dismiss_loading_popup(self):
        if self.loading_popup:
            self.loading_popup.dismiss()

    def clear_movie_grid(self):
        if self.poster_grid_layout:
            self.poster_grid_layout.clear_widgets()

    def load_initial_movies(self):
        self.show_loading_popup()
        Clock.schedule_once(self.load_movies, 1)

    def load_movies(self, dt):
        try:
            all_movies = []
            for page_number in range(1, 6):
                page = fetch_movies(Movie().popular, page_number=page_number)
                if page:
                    all_movies.extend(page)

            for movie in all_movies:
                self.movie_cache[movie.id] = movie
                self.add_movie_poster(movie)
        except TMDbException as e:
            logging.error(f"TMDb API error: {e}")
            self.show_error(f"TMDb API error: {e}")
        except Exception as e:
            logging.error(f"Load error: {e}")
            self.show_error(f"Error loading movies: {e}")
        finally:
            self.dismiss_loading_popup()

    def show_movie_details(self, instance):
        movie_id = getattr(instance, 'movie_id', None)
        if movie_id is None:
            self.show_error("Movie ID not found.")
            return

        movie = self.movie_cache.get(movie_id)
        if movie is None:
            self.show_error("Movie not in cache.")
            return

        self.detail_screen.clear_widgets()
        detail_layout = BoxLayout(orientation='vertical', padding=10)

        detail_layout.add_widget(
            Label(text=movie.title, font_size='24sp', size_hint_y=None, height=50)
        )

        if movie.poster_path:
            detail_layout.add_widget(
                AsyncImage(
                    source=f"https://image.tmdb.org/t/p/w500/{movie.poster_path}",
                    size_hint_y=None,
                    height=400
                )
            )

        overview = Label(
            text=movie.overview,
            font_size='16sp',
            text_size=(Window.width - 40, None),
            size_hint_y=None,
            halign='left',
            valign='top'
        )
        overview.bind(texture_size=overview.setter('size'))
        detail_layout.add_widget(overview)

        detail_layout.add_widget(
            Label(
                text=f"Release Date: {movie.release_date}",
                font_size='16sp',
                size_hint_y=None,
                height=30
            )
        )

        back_button = Button(text="Back", size_hint_y=None, height=50)
        back_button.bind(on_release=self.go_back)
        detail_layout.add_widget(back_button)

        self.detail_screen.add_widget(detail_layout)
        self.screen_manager.current = "Detail Screen"

    def go_back(self, instance):
        self.screen_manager.current = "Main Screen"


if __name__ == '__main__':
    MoviePosterApp().run()
