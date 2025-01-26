import os, requests, logging
from tmdbv3api import TMDb, Movie
from tmdbv3api.exceptions import TMDbException
from typing import List, Optional, Dict
from kivy.app import App
from kivy.uix.image import AsyncImage
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.gridlayout import GridLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.spinner import Spinner
from kivy.uix.popup import Popup
from kivy.uix.textinput import TextInput
from kivy.clock import Clock, mainthread
from dotenv import load_dotenv
from kivy.config import Config
from kivy.core.window import Window
from kivy.uix.screenmanager import ScreenManager, Screen
from kivy.uix.button import Button
from kivy.uix.behaviors import ButtonBehavior
from kivy.graphics import Color, Rectangle
from kivy.properties import StringProperty, ObjectProperty
from kivy.core.text import Label as CoreLabel

logging.basicConfig(filename='movie_app.log', level=logging.INFO, format='%(asctime)s:%(levelname)s:%(message)s')
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
        movie = Movie()
        result_page = func(query=query, page=page_number) if query else func(page=page_number)
        return [MovieDetails(m.title, m.overview, m.release_date, m.poster_path, m.id) for m in result_page] if result_page else None
    except (requests.exceptions.RequestException, Exception) as e:
        logging.error(f"Error: {e}")
        return None

class NoKeyboardTextInput(TextInput):
    def on_touch_down(self, touch):
        if self.collide_point(*touch.pos):
            Window.release_all_keyboards()
        return super().on_touch_down(touch)

class ClearButton(ButtonBehavior, Label):
    text = StringProperty('X')
    icon_size = StringProperty('12sp')
    bg_color = (0.7, 0.7, 0.7, 1)
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.bind(size=self.update_rect, pos=self.update_rect)
        self.update_rect()
        self.canvas.before.add(Color(*self.bg_color))
        self.rect = Rectangle()
        self.canvas.before.add(self.rect)
        
    def update_rect(self, *args):
        if self.parent:
            self.rect.pos = self.pos
            self.rect.size = self.size

    def on_text(self, instance, value):
       self._label = CoreLabel(text=value, font_size=self.icon_size)
       self._label.refresh()
       self.texture = self._label.texture
       self.texture_size = list(self._label.texture.size)

class SearchBar(BoxLayout):
    search_input = ObjectProperty(None)
    clear_button = ObjectProperty(None)
    search_text = StringProperty('')

    def __init__(self, **kwargs):
        super().__init__(orientation='horizontal', size_hint_y=None, height=Window.height * 0.07, **kwargs)
        self.search_input = NoKeyboardTextInput(hint_text='Search for a movie...', multiline=False, size_hint_x=0.9)
        self.clear_button = ClearButton(size_hint_x=0.1, icon_size='16sp')
        self.add_widget(self.search_input)
        self.add_widget(self.clear_button)
        self.clear_button.bind(on_release=self.clear_search_text)
        self.search_input.bind(text=self.on_text_change)

    def on_text_change(self, instance, value):
      self.search_text = value

    def clear_search_text(self, instance):
        self.search_input.text = ''
        self.search_text = ''
        
    def on_text_validate(self):
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
        root_layout = BoxLayout(orientation='vertical', padding=10)
        root_layout.add_widget(Label(text="Popular Movies", font_size='24sp', size_hint_y=None, height=50))
        self.search_bar = SearchBar()
        self.search_bar.bind(on_search=self.perform_search)
        self.search_bar.search_input.bind(on_text_validate=self.perform_search)
        root_layout.add_widget(self.search_bar)
        self.error_label = Label(text="", color=(1, 0, 0, 1), size_hint_y=None, height=30)
        root_layout.add_widget(self.error_label)
        scroll_view = ScrollView(size_hint=(1, 1), do_scroll_x=False)
        root_layout.add_widget(scroll_view)
        self.poster_grid_layout = GridLayout(cols=3, spacing=10, size_hint_y=None)
        self.poster_grid_layout.bind(minimum_height=self.poster_grid_layout.setter('height'))
        scroll_view.add_widget(self.poster_grid_layout)
        self.loading_popup = Popup(title='Loading', content=Spinner(), size_hint=(None, None), size=(200, 200))
        self.loading_popup.open()

        if not tmdb.api_key:
            self.show_error("Error: TMDB API key not found. Please check your environment variables or the default API key in the code.")
            self.loading_popup.dismiss()
            return root_layout

        Clock.schedule_once(self.load_movies, 1)
        self.main_screen.add_widget(root_layout)
        self.screen_manager.add_widget(self.main_screen)
        self.detail_screen = Screen(name="Detail Screen")
        self.screen_manager.add_widget(self.detail_screen)
        return self.screen_manager

    @mainthread
    def show_error(self, message: str):
       if self.error_label:
           self.error_label.text = message

    @mainthread
    def add_movie_poster(self, movie_details: MovieDetails):
        if not self.poster_grid_layout:
             return
        
        poster_path = movie_details.poster_path
        if poster_path:
            poster_url = f"https://image.tmdb.org/t/p/w500/{poster_path}"
            try:
                movie_poster = AsyncImage(source=poster_url, size_hint_y=None, height=300)
                movie_poster.movie_id = movie_details.id # Store the id
                movie_poster.bind(on_release=self.show_movie_details)
                self.poster_grid_layout.add_widget(movie_poster)
            except Exception as image_error:
                logging.error(f"Error loading poster: {image_error}")
                self.show_error("Error loading poster image. Please check your internet connection and try again.")
        else:
            logging.warning(f"No poster available for the movie: {movie_details.title}")

    def perform_search(self, instance):
        search_query = self.search_bar.search_text.strip()
        if not search_query:
          self.clear_movie_grid()
          self.load_initial_movies()
          return
        
        self.clear_movie_grid()
        self.show_loading_popup()
        Clock.schedule_once(lambda dt: self.search_movies_scheduled(search_query), 1)

    def search_movies_scheduled(self, query):
         try:
             all_search_movies = []
             for page_number in range(1, 6):
                  search_result_page = fetch_movies(Movie().search, query, page_number)
                  if search_result_page:
                      all_search_movies.extend(search_result_page)
                  else:
                      logging.error(f"Failed to get search results for page {page_number}")
                      continue
             
             if not all_search_movies:
                 self.show_error("No movies found with that name.")
                 self.clear_movie_grid()
                 return
             
             for movie_details in all_search_movies:
               self.movie_cache[movie_details.id] = movie_details
               self.add_movie_poster(movie_details)
         except TMDbException as tmdb_error:
             error_message = f"TMDb API error: {tmdb_error}. Please check your API key and try again."
             logging.error(error_message)
             self.show_error(error_message)
         except Exception as general_error:
             error_message = f"General error: {general_error}. Please check your setup and try again."
             logging.error(error_message)
             self.show_error(error_message)
         finally:
             if self.loading_popup:
                  self.loading_popup.dismiss()
    
    def show_loading_popup(self):
        self.loading_popup = Popup(title='Loading', content=Spinner(), size_hint=(None, None), size=(200, 200))
        self.loading_popup.open()
    
    def clear_movie_grid(self):
       if self.poster_grid_layout:
          self.poster_grid_layout.clear_widgets()
    
    def load_initial_movies(self):
         self.clear_movie_grid()
         self.show_loading_popup()
         Clock.schedule_once(self.load_movies, 1)
         
    def load_movies(self, dt):
        try:
            all_popular_movies = []
            for page_number in range(1, 6):
                popular_movies_page = fetch_movies(Movie().popular, page_number=page_number)
                if popular_movies_page:
                    all_popular_movies.extend(popular_movies_page)
                else:
                    logging.error(f"Failed to get popular movies for page {page_number}")
                    continue

            for movie_details in all_popular_movies:
                self.movie_cache[movie_details.id] = movie_details
                self.add_movie_poster(movie_details)
        except TMDbException as tmdb_error:
            error_message = f"TMDb API error: {tmdb_error}. Please check your API key and try again."
            logging.error(error_message)
            self.show_error(error_message)
        except Exception as general_error:
            error_message = f"General error: {general_error}. Please check your setup and try again."
            logging.error(error_message)
            self.show_error(error_message)
        finally:
            if self.loading_popup:
                self.loading_popup.dismiss()

    def show_movie_details(self, instance):
       movie_id = getattr(instance, 'movie_id', None)
       if movie_id is None:
           self.show_error("Movie ID not found.")
           return

       movie_details = self.movie_cache.get(movie_id)
       if movie_details is None:
            self.show_error("Movie not in cache, could not display details.")
            return

       self.detail_screen.clear_widgets()
       detail_layout = BoxLayout(orientation='vertical', padding=10)
       detail_layout.add_widget(Label(text=movie_details.title, font_size='24sp', size_hint_y=None, height=50))
       movie_overview = Label(text=movie_details.overview, font_size='16sp', text_size=(Window.width - 40, None), size_hint_y=None, halign='left', valign='top')
       movie_overview.bind(texture_size=movie_overview.setter('size'))
       detail_layout.add_widget(movie_overview)
       detail_layout.add_widget(Label(text=f"Release Date: {movie_details.release_date}", font_size='16sp', size_hint_y=None, height=30))
       back_button = Button(text="Back", size_hint_y=None, height=50)
       back_button.bind(on_release=self.go_back)
       detail_layout.add_widget(back_button)
       self.detail_screen.add_widget(detail_layout)
       self.screen_manager.current = "Detail Screen"

    def go_back(self, instance):
       self.screen_manager.current = "Main Screen"

if __name__ == '__main__':
    MoviePosterApp().run()
