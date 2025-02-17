from kivy.utils import get_color_from_hex

class Theme:
    primary_color = get_color_from_hex("#6200EE")
    primary_variant_color = get_color_from_hex("#3700B3")
    secondary_color = get_color_from_hex("#03DAC6")
    background_color = get_color_from_hex("#FFFFFF")
    surface_color = get_color_from_hex("#FFFFFF")
    error_color = get_color_from_hex("#B00020")
    on_primary_color = get_color_from_hex("#FFFFFF")
    on_secondary_color = get_color_from_hex("#000000")
    on_background_color = get_color_from_hex("#000000")
    on_surface_color = get_color_from_hex("#000000")
    on_error_color = get_color_from_hex("#FFFFFF")

    font_family = "Roboto"
    font_size_small = "14sp"
    font_size_medium = "18sp"
    font_size_large = "24sp"