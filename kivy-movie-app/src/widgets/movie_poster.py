from kivy.uix.image import AsyncImage
from kivy.uix.boxlayout import BoxLayout
from kivy.properties import ObjectProperty, StringProperty
from kivy.graphics import Color, Rectangle
from kivy.uix.label import Label
from kivy.core.text import Label as CoreLabel
from kivy.uix.button import ButtonBehavior

class MoviePoster(ButtonBehavior, BoxLayout):
    movie_id = ObjectProperty()
    poster_url = StringProperty()
    title = StringProperty()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.orientation = 'vertical'
        self.size_hint = (None, None)
        self.size = (150, 225)  # Default size for the poster

        with self.canvas.before:
            Color(1, 1, 1, 1)  # Background color
            self.rect = Rectangle(size=self.size, pos=self.pos)

        self.bind(size=self.update_rect, pos=self.update_rect)

        self.poster_image = AsyncImage(size_hint=(1, 0.9), allow_stretch=True)
        self.poster_image.bind(on_release=self.on_press)
        self.add_widget(self.poster_image)

        self.title_label = Label(size_hint=(1, 0.1), halign='center', valign='middle', text_size=(150, None))
        self.add_widget(self.title_label)

    def update_rect(self, *args):
        self.rect.pos = self.pos
        self.rect.size = self.size

    def on_press(self):
        self.dispatch('on_movie_selected')

    def on_movie_selected(self):
        pass  # This will be overridden in the main app to handle movie selection

    def load_movie(self, movie_details):
        self.movie_id = movie_details.id
        self.title = movie_details.title
        self.poster_url = f"https://image.tmdb.org/t/p/w500/{movie_details.poster_path}" if movie_details.poster_path else ''
        self.poster_image.source = self.poster_url
        self.title_label.text = self.title
        self.poster_image.reload()  # Reload the image to ensure it displays correctly