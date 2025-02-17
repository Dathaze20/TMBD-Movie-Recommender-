from kivy.uix.boxlayout import BoxLayout
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.properties import StringProperty, ObjectProperty
from kivy.lang import Builder

Builder.load_string('''
<SearchBar>:
    orientation: 'horizontal'
    size_hint_y: None
    height: '50dp'
    padding: [10, 10, 10, 10]
    spacing: 10

    TextInput:
        id: search_input
        hint_text: 'Search for a movie...'
        multiline: False
        size_hint_x: 0.8
        on_text_validate: root.on_search()

    Button:
        text: 'Clear'
        size_hint_x: 0.2
        on_release: root.clear_search_text()
''')

class SearchBar(BoxLayout):
    search_input = ObjectProperty(None)
    search_text = StringProperty('')

    def on_search(self):
        search_query = self.search_input.text.strip()
        if search_query:
            self.dispatch('on_search_query', search_query)

    def clear_search_text(self):
        self.search_input.text = ''
        self.search_text = ''
        self.dispatch('on_search_query', '')  # Dispatch empty query to reset search

    def on_search_query(self, query):
        pass  # This will be overridden in the main screen to handle search logic