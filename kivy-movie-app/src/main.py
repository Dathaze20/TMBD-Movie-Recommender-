import os
import requests
import logging
from kivy.app import App
from kivy.uix.screenmanager import ScreenManager, Screen
from kivy.uix.boxlayout import BoxLayout
from kivy.clock import Clock
from kivy.core.window import Window
from dotenv import load_dotenv
from kivy.uix.popup import Popup
from kivy.uix.spinner import Spinner
from kivy.uix.label import Label
from kivy.uix.gridlayout import GridLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.button import Button
from kivy.uix.image import AsyncImage
from kivy.properties import ObjectProperty, StringProperty
from typing import List, Optional, Dict
from tmdbv3api import TMDb, Movie
from tmdbv3api.exceptions import TMDbException

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(filename='movie_app.log', level=logging.INFO, format='%(asctime)s:%(levelname)s:%(message)s')

# Set up Kivy window size
Window.size = (800, 600)

# Initialize TMDb API
api_key = os.getenv('TMDB_API_KEY')
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
        movie = Movie()
        result_page = func(query=query, page=page_number) if query else func(page=page_number)
        return [MovieDetails(m.title, m.overview, m.release_date, m.poster_path, m.id) for m in result_page] if result_page else None
    except (requests.exceptions.RequestException, Exception) as e:
        logging.error(f"Error: {e}")
        return None

class MoviePosterApp(App):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.movie_cache: Dict[int, MovieDetails] = {}
        self.loading_popup: Optional[Popup] = None
        self.screen_manager = ScreenManager()

    def build(self):
        self.main_screen = self.load_main_screen()
        self.detail_screen = self.load_detail_screen()
        self.screen_manager.add_widget(self.main_screen)
        self.screen_manager.add_widget(self.detail_screen)
        return self.screen_manager

    def load_main_screen(self):
        from screens.main_screen import MainScreen
        return MainScreen(app=self)

    def load_detail_screen(self):
        from screens.detail_screen import DetailScreen
        return DetailScreen(app=self)

    def show_loading_popup(self):
        self.loading_popup = Popup(title='Loading', content=Spinner(), size_hint=(None, None), size=(200, 200))
        self.loading_popup.open()

    def dismiss_loading_popup(self):
        if self.loading_popup:
            self.loading_popup.dismiss()

    def show_error(self, message: str):
        error_popup = Popup(title='Error', content=Label(text=message), size_hint=(None, None), size=(400, 200))
        error_popup.open()

if __name__ == '__main__':
    MoviePosterApp().run()