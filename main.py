import os
import requests
from tmdbv3api import TMDb, Movie
from tmdbv3api.exceptions import TMDbException
from typing import List, Optional
from kivy.app import App
from kivy.uix.image import AsyncImage
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.gridlayout import GridLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.spinner import Spinner
from kivy.uix.popup import Popup
from kivy.uix.textinput import TextInput
from kivy.clock import Clock
from dotenv import load_dotenv
from kivy.config import Config
from kivy.core.window import Window
from kivy.uix.screenmanager import ScreenManager, Screen
from kivy.clock import mainthread
import logging

# Configure logging
logging.basicConfig(filename='movie_app.log', level=logging.INFO, format='%(asctime)s:%(levelname)s:%(message)s')

# Load environment variables
load_dotenv()

# Set Kivy configurations
Config.set('graphics', 'width', '800')
Config.set('graphics', 'height', '600')
Config.set('kivy', 'keyboard_mode', 'system')  # Disable the virtual keyboard
Config.set('graphics', 'fullscreen', 'auto')

# Replace with your actual API key or use environment variables
api_key = os.getenv('TMDB_API_KEY', '412cb4afbe96d39f9db34601104ff7e4')
tmdb = TMDb()
tmdb.api_key = api_key

# MovieDetails class to store movie details
class MovieDetails:
    def __init__(self, title, overview, release_date, poster_path):
        self.title = title
        self.overview = overview
        self.release_date = release_date
        self.poster_path = poster_path

# Function to fetch popular movies
def fetch_popular_movies(page_number: int) -> Optional[List[MovieDetails]]:
    try:
        movie = Movie()
        popular_movies_page = movie.popular(page=page_number)
        if popular_movies_page:
            movie_details_list = []
            for movie_data in popular_movies_page:
                movie_details = MovieDetails(
                    title=movie_data.title,
                    overview=movie_data.overview,
                    release_date=movie_data.release_date,
                    poster_path=movie_data.poster_path
                )
                movie_details_list.append(movie_details)
            return movie_details_list
    except requests.exceptions.RequestException as request_error:
        logging.error(f"Request error occurred: {request_error}")
        return None
    except Exception as general_error:
        logging.error(f"Unexpected error: {general_error}")
        return None

# TextInput class to disable virtual keyboard
class NoKeyboardTextInput(TextInput):
    def on_touch_down(self, touch):
        if self.collide_point(*touch.pos):
            Window.release_all_keyboards()
        return super().on_touch_down(touch)

# Main app class
class MoviePosterApp(App):
    def build(self):
        self.screen_manager = ScreenManager()

        # Main screen
        self.main_screen = Screen(name="Main Screen")
        root_layout = BoxLayout(orientation='vertical')
        title_label = Label(text="Popular Movies", font_size='24sp', size_hint_y=None, height=50)
        root_layout.add_widget(title_label)
        search_bar = NoKeyboardTextInput(hint_text='Search for a movie...', multiline=False, size_hint_y=None, height=Window.height * 0.07)
        root_layout.add_widget(search_bar)
        error_label = Label(text="", color=(1, 0, 0, 1), size_hint_y=None, height=30)
        root_layout.add_widget(error_label)
        scroll_view = ScrollView(size_hint=(1, 1), do_scroll_x=False)
        root_layout.add_widget(scroll_view)
        poster_grid_layout = GridLayout(cols=3, spacing=10, size_hint_y=None)
        poster_grid_layout.bind(minimum_height=poster_grid_layout.setter('height'))
        scroll_view.add_widget(poster_grid_layout)
        loading_popup = Popup(title='Loading', content=Spinner(), size_hint=(None, None), size=(200, 200))
        loading_popup.open()

        if not tmdb.api_key:
            error_label.text = "Error: TMDB API key not found. Please check your environment variables or the default API key in the code."
            loading_popup.dismiss()
            return root_layout

        # Function to load movies
        def load_movies(dt):
            try:
                all_popular_movies = []
                for page_number in range(1, 6):
                    popular_movies_page = fetch_popular_movies(page_number)
                    if popular_movies_page:
                        all_popular_movies.extend(popular_movies_page)
                    else:
                        logging.error(f"Failed to get popular movies for page {page_number}")
                        continue

                for movie_details in all_popular_movies:
                    poster_path = movie_details.poster_path
                    if poster_path:
                        poster_url = f"https://image.tmdb.org/t/p/w500/{poster_path}"
                        try:
                            movie_poster = AsyncImage(source=poster_url, size_hint_y=None, height=300)
                            movie_poster.bind(on_release=self.show_movie_details)
                            poster_grid_layout.add_widget(movie_poster)
                        except Exception as image_error:
                            logging.error(f"Error loading poster: {image_error}")
                            error_label.text = "Error loading poster image. Please check your internet connection and try again."
                    else:
                        logging.warning(f"No poster available for the movie: {movie_details.title}")

            except TMDbException as tmdb_error:
                error_message = f"TMDb API error: {tmdb_error}. Please check your API key and try again."
                logging.error(error_message)
                error_label.text = error_message
            except Exception as general_error:
                error_message = f"General error: {general_error}. Please check your setup and try again."
                logging.error(error_message)
                error_label.text = error_message
            finally:
                loading_popup.dismiss()

        Clock.schedule_once(load_movies, 1)

        self.main_screen.add_widget(root_layout)
        self.screen_manager.add_widget(self.main_screen)

        # Detail screen
        self.detail_screen = Screen(name="Detail Screen")
        self.screen_manager.add_widget(self.detail_screen)

        return self.screen_manager

    # Function to show movie details
    def show_movie_details(self, instance):
        self.detail_screen.clear_widgets()
        detail_layout = BoxLayout(orientation='vertical')
        movie_title = Label(text="Movie Title", font_size='24sp', size_hint_y=None, height=50)
        detail_layout.add_widget(movie_title)
        movie_overview = Label(text="Movie Overview", font_size='16sp')
        detail_layout.add_widget(movie_overview)
        movie_release_date = Label(text="Release Date", font_size='16sp')
        detail_layout.add_widget(movie_release_date)
        back_button = Button(text="Back", size_hint_y=None, height=50)
        back_button.bind(on_release=self.go_back)
        detail_layout.add_widget(back_button)
        self.detail_screen.add_widget(detail_layout)
        self.screen_manager.current = "Detail Screen"

    # Function to go back to main screen
    def go_back(self, instance):
        self.screen_manager.current = "Main Screen"

if __name__ == '__main__':
    MoviePosterApp().run()
