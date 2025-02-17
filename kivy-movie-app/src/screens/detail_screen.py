from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.image import AsyncImage
from kivy.uix.scrollview import ScrollView
from kivy.properties import ObjectProperty
from kivy.core.window import Window

class DetailScreen(BoxLayout):
    movie_title = ObjectProperty(None)
    movie_overview = ObjectProperty(None)
    movie_release_date = ObjectProperty(None)
    movie_poster = ObjectProperty(None)
    back_button = ObjectProperty(None)

    def __init__(self, **kwargs):
        super().__init__(orientation='vertical', padding=10, **kwargs)
        self.add_widget(Label(text="Movie Details", font_size='24sp', size_hint_y=None, height=50))
        
        self.movie_poster = AsyncImage(size_hint_y=None, height=400)
        self.add_widget(self.movie_poster)

        self.movie_title = Label(font_size='20sp', size_hint_y=None, height=40)
        self.add_widget(self.movie_title)

        self.movie_overview = Label(font_size='16sp', text_size=(Window.width - 40, None), size_hint_y=None)
        self.movie_overview.bind(texture_size=self.movie_overview.setter('size'))
        self.add_widget(self.movie_overview)

        self.movie_release_date = Label(font_size='16sp', size_hint_y=None, height=30)
        self.add_widget(self.movie_release_date)

        self.back_button = Button(text="Back", size_hint_y=None, height=50)
        self.back_button.bind(on_release=self.go_back)
        self.add_widget(self.back_button)

    def display_movie_details(self, movie_details):
        self.movie_title.text = movie_details.title
        self.movie_overview.text = movie_details.overview
        self.movie_release_date.text = f"Release Date: {movie_details.release_date}"
        self.movie_poster.source = f"https://image.tmdb.org/t/p/w500/{movie_details.poster_path}"

    def go_back(self, instance):
        self.parent.parent.current = "Main Screen"