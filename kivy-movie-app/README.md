# Kivy Movie App

## Overview
The Kivy Movie App is a visually appealing application designed to provide users with an interactive experience for discovering and exploring movies. It utilizes the TMDB API to fetch movie data and presents it in an organized and user-friendly manner.

## Project Structure
```
kivy-movie-app
├── assets
│   ├── fonts
│   └── themes
├── src
│   ├── main.py
│   ├── screens
│   │   ├── main_screen.py
│   │   ├── detail_screen.py
│   └── widgets
│       ├── search_bar.py
│       ├── movie_poster.py
│       └── clear_button.py
├── .env
├── .gitignore
├── requirements.txt
└── README.md
```

## Features
- **Custom Fonts**: The app includes a selection of custom fonts for a modern typography experience.
- **Theming**: A cohesive color palette and design elements enhance the visual appeal of the app.
- **Movie Poster Grid**: An advanced layout for displaying movie posters, allowing for easy navigation and interaction.
- **Detailed Movie Information**: Users can view comprehensive details about each movie, including cast information, trailers, and user reviews.
- **Search Functionality**: A user-friendly search bar enables users to quickly find movies by title.
- **Responsive Design**: The app is optimized for various devices, ensuring a consistent experience across different screen sizes.
- **Accessibility Features**: The app includes features to improve accessibility for all users.

## Installation
1. Clone the repository:
   ```
   git clone https://github.com/yourusername/kivy-movie-app.git
   ```
2. Navigate to the project directory:
   ```
   cd kivy-movie-app
   ```
3. Install the required dependencies:
   ```
   pip install -r requirements.txt
   ```
4. Set up your environment variables in the `.env` file, including your TMDB API key.

## Usage
To run the application, execute the following command:
```
python src/main.py
```

## Contributing
Contributions are welcome! Please submit a pull request or open an issue for any enhancements or bug fixes.

## License
This project is licensed under the MIT License. See the LICENSE file for details.