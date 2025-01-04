# TMDB Movie Recommender App

This is a movie recommendation app built using Python and Kivy, leveraging the TMDB API. It allows users to browse popular movies and search for specific titles, displaying detailed information and images.

## Features

*   **Browse Popular Movies:**
    *   Loads and displays popular movies from the TMDB database across multiple pages.
    *   Presents movies with their posters, titles, and overview.

*   **Search Functionality:**
    *   Enables users to search for movies by their titles.
    *   Provides search results with movie posters and details.
    *   Shows an error when no movies are found.

*   **Movie Details:**
    *   Displays detailed information about a selected movie, including title, overview, and release date.
    *   Includes a large poster image for the movie.

*   **User Interface:**
    *   Responsive design that adapts to different screen sizes and orientations, as well as a full screen mode.
    *   Uses a clean and intuitive layout for easy navigation.
    *   Uses Kivy for a fluid and visually appealing user interface.
    *   Custom Clear Button to clear the search query
    *   Custom search bar using a horizontal box layout and custom text input and custom clear button
    *   All errors are displayed on the screen, rather than the console.

*   **Error Handling:**
    *   Handles errors with the TMDB API.
    *   Provides error messages to users if there is an issue with loading data or connection.

*  **Background Functionality:**
    * Uses logging to track and save program events.
    * Uses .env file to securely store API key
    * Uses multi-threading with Kivy clock to prevent freezing the UI on API calls.
*   **No Virtual Keyboard:**
    *   Has a custom text input where the virtual keyboard is disabled to prevent visual bugs.
## How to Use

1.  **Clone the Repository:**
    ```bash
    git clone [repository URL]
    cd [project directory]
    ```
2.  **Set Up Environment Variables:**
    *   Create a `.env` file in the project's root directory.
    *   Add your TMDB API key to the `.env` file:
        ```env
        TMDB_API_KEY=YOUR_TMDB_API_KEY
        ```
       * Remember to install the **python-dotenv** module by using the following command:
          ```bash
           pip install python-dotenv
          ```
3.  **Install Dependencies:**
    ```bash
    pip install tmdbv3api kivy python-dotenv requests
    ```
4.  **Run the App:**
    ```bash
    python main.py
    ```
   * Remember to rename the python file from the one provided above from main to the file you have.

5. **Using the App:**
   *  Use the text input at the top of the page to search for a movie.
   *  Click on any of the movie posters to see a more in depth overview of the movie.
   * Click the "back" button to return to the previous page.

## Technologies Used

*   **Python:** Programming language.
*   **Kivy:** For creating the cross platform UI.
*   **tmdbv3api:** TMDB API library for accessing movie data.
*  **requests:** The requests module to make HTTP requests
*   **python-dotenv:** To securely manage API key and other environment variables
* **logging** To log issues and events that happen within the program.

## Challenges Faced

*   **Asynchronous API Calls:** Managing API calls without freezing the user interface.
*  **Error Handling:** Implementing robust error handling for TMDB API failures.
*   **Responsive Layout:** Designing a user interface that scales and adapts across different screen sizes and resolutions.
*   **Correctly handling user input:** Managing text inputs without breaking other user input functionality
*   **Preventing duplicate movie listings** Ensuring all movie listings are unique
*   **Data Management:** Efficiently caching movie data and posters.

## Future Improvements

*   **Recommendation System:** Implement a more robust movie recommendation system based on user preferences.
*   **Improved Search:** Enhanced search with genre, actor, and director filters.
*   **User Authentication:** Add login and user accounts for saving favorites.
*   **Detail Views:** Improve detailed views with user reviews, ratings, and trailers.
*  **Offline Capability:** Enable offline access to cached movie data and images.
*   **More Loading States:** Improve feedback for the user on what state the application is in.

## License

This project is licensed under the [MIT License](https://opensource.org/licenses/MIT).
