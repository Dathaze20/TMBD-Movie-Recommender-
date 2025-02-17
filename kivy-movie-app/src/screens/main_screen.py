from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.gridlayout import GridLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.spinner import Spinner
from kivy.uix.popup import Popup
from kivy.clock import Clock
from kivy.properties import ObjectProperty, StringProperty
from kivy.uix.button import Button
from kivy.uix.image import AsyncImage
from kivy.graphics import Color, Rectangle
from kivy.core.window import Window
from kivy.uix.textinput import TextInput
from .widgets.search_bar import SearchBar
from .widgets.movie_poster import MoviePoster
from kivy.lang import Builder

Builder.load_string("""
<MainScreen>:
    orientation: 'vertical'
    padding: 10
    canvas.before:
        Color: 
            rgba: 0.1, 0.1, 0.1, 1
        Rectangle:
            pos: self.pos
            size: self.size

    Label:
        text: "Popular Movies"
        font_size: '24sp'
        size_hint_y: None
        height: 50
        color: 1, 1, 1, 1

    SearchBar:
        id: search_bar
        size_hint_y: None
        height: 50

    ScrollView:
        size_hint: (1, 1)
        do_scroll_x: False

        GridLayout:
            id: poster_grid
            cols: 3
            spacing: 10
            size_hint_y: None
            height: self.minimum_height
""")

class MainScreen(BoxLayout):
    poster_grid = ObjectProperty(None)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.search_bar = SearchBar()
        self.search_bar.bind(on_search=self.perform_search)

    def perform_search(self, instance):
        search_query = self.search_bar.search_text.strip()
        if search_query:
            self.clear_movie_grid()
            self.load_movies(search_query)
        else:
            self.load_initial_movies()

    def clear_movie_grid(self):
        self.poster_grid.clear_widgets()

    def load_movies(self, query):
        # Logic to fetch and display movies based on the search query
        pass

    def load_initial_movies(self):
        # Logic to fetch and display initial popular movies
        pass

    def add_movie_poster(self, movie_details):
        poster = MoviePoster(movie_details)
        self.poster_grid.add_widget(poster)
"""