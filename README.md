# trakt-export-to-markdown

Convert your [Trakt](https://trakt.tv/) export into beautiful, chronological markdown notes (made mainly to work in Obsidian), with local poster images, genres, actors, and direct links for IMDb, Wikipedia, and Trakt.

---

## Features

- Markdown files grouped by year, with one entry per watch
- Local **poster images** saved for offline viewing (you can rerun the script without issue, they wont be re-downloaded)
- Shows top 3 genres (plus genre tags for quick search)
- Cast list (top-billed), with IMDb and Wikipedia lookup links
- Direct URLs for IMDb, Wikipedia, and Trakt, not behind link text
- Customizable and easy to extend
- Supports history, watchlists, and favorites

---

## Screenshots

(Made in Obsidian with the Catppuccin-Machiato color scheme)

### Movie

![movie](./screenshots/movie.png)

### TV Episode

![episode](./screenshots/episode.png)

---

## Usage

1. **Export your Trakt data** from [your settings page](https://trakt.tv/settings/data).
2. **Extract your Trakt data to a folder named bellow "trakt-export"
2. **Obtain a free OMDB API key:** [Get it here.](https://www.omdbapi.com/apikey.aspx)
3. **Install the dependency:**
   ```sh
   pip install requests
   ```
4. **Run the script:**
   ```sh
   export OMDB_API_KEY=your_api_key_here
   python trakt_to_markdown.py /path/to/your/trakt-export/
   ```
   - Output appears in `trakt-markdown/` with a `00-Posters/` folder for images.
   - `.md` files are ready!

Note: When moving the output to the software you're using, it is strongly encouraged that you also move the (hidden) `.omdb_cache.json` cache file. It will save you a massive amount of time.

---

## Scripts difference

- `trakt_to_markdown.py`: The normal script
- `trakt_to_markdown_fullsize.py`: A modification of the normal script to download the poster in the best quality possible, this seemed to be a good idea at first, but after trying it, I discovered that my "collection" of around 500 posters was more than 700MB compared to the 18MB of the normal script

---

## Example Output

### Movie

```markdown
### 2023-02-04 - Pulp Fiction (1994)

![cover](00-Posters/tt0110912.jpg)

- **Rating:** ⭐⭐⭐⭐⭐⭐⭐⭐⭐⭐ (10/10)

- **Genre:** Crime, Drama
- **Cast:** John Travolta ([IMDb](https://www.imdb.com/find/?q=John+Travolta&s=nm) - [Wikipedia](https://en.wikipedia.org/wiki/John_Travolta)), Uma Thurman ([IMDb](https://www.imdb.com/find/?q=Uma+Thurman&s=nm) - [Wikipedia](https://en.wikipedia.org/wiki/Uma_Thurman)), Samuel L. Jackson ([IMDb](https://www.imdb.com/find/?q=Samuel+L.+Jackson&s=nm) - [Wikipedia](https://en.wikipedia.org/wiki/Samuel_L._Jackson))

- **IMDb:** https://www.imdb.com/title/tt0110912/
- **Wikipedia:** https://en.wikipedia.org/wiki/Pulp_Fiction
- **Trakt:** https://trakt.tv/movies/pulp-fiction-1994

- **Date Tag:** #movie-2023
- **Genres Tags:** #movie-crime - #movie-drama
```

### TV Episode

```markdown
### 2025-08-02 - Santa Clarita Diet (2017) - S01E01 - So Then a Bat or a Monkey

![cover](00-Posters/tt5580540.jpg)

- **Episode Release Date:** 2017-02-03
- **Genre:** Comedy, Horror
- **Cast:** Drew Barrymore ([IMDb](https://www.imdb.com/find/?q=Drew+Barrymore&s=nm) - [Wikipedia](https://en.wikipedia.org/wiki/Drew_Barrymore)), Timothy Olyphant ([IMDb](https://www.imdb.com/find/?q=Timothy+Olyphant&s=nm) - [Wikipedia](https://en.wikipedia.org/wiki/Timothy_Olyphant)), Liv Hewson ([IMDb](https://www.imdb.com/find/?q=Liv+Hewson&s=nm) - [Wikipedia](https://en.wikipedia.org/wiki/Liv_Hewson))

- **IMDb:** https://www.imdb.com/title/tt5580540/
- **Wikipedia:** https://en.wikipedia.org/wiki/Santa_Clarita_Diet
- **Trakt:** https://trakt.tv/shows/santa-clarita-diet

- **Date Tag:** #tv-2025
- **Genres Tags:** #tv-comedy - #tv-horror
```

---

## About the number of API requests

I have decided to make the script get the episode original release date because this is often useful. This requires 1 OMDb API request for each episode. You might have to do it over multiple days or pay for a key with higher limit than 1000 if you've been using Trakt for a while. I personally had around 3500 episodes. If you don't want this feature, you can just edit the script and remove the whole logic to get and print it.

---

## AI Acknowledgement

This project was written and refined with **two different LLM "AI" models**: Claude Opus 4.6 and GPT-4.1 running in "GitHub Copilot Chat". 

I can't personally write Python from scratch, but I made those LLM do exactly what I wanted, and then I tweaked a lot of it by hand. There was a lot of back and forth, but this is, at its core still a project made using LLMs.

It took me more than 3-5 hours of work (minimum).

This was for personal use first and foremost, I just decided to release it.

Consider this provided as is, as the LICENSE says.

AI sucks, but I'm not a developer, have no interest in becoming one and I'm too poor to hire a contractor.
