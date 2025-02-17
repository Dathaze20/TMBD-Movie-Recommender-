from kivy.uix.button import Button
from kivy.properties import StringProperty
from kivy.graphics import Color, Rectangle

class ClearButton(Button):
    text = StringProperty('X')
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

    def on_release(self):
        self.dispatch('on_clear')

    def on_clear(self):
        pass