#!/usr/bin/env python3
"""Convert a Trakt export to chronological markdown files."""

import glob
import json
import os
import re
import sys
import time
import urllib.parse
from collections import defaultdict
from datetime import datetime

import requests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
OMDB_API_KEY = os.environ.get("OMDB_API_KEY", "")
OMDB_CACHE_FILE = ".omdb_cache.json"
OUTPUT_DIR = "trakt-markdown"
POSTER_DIR = os.path.join(OUTPUT_DIR, "00-Posters")
RATE_LIMIT_DELAY = 0.12  # OMDB free tier: 1000/day
MAX_GENRES = 3

# ---------------------------------------------------------------------------
# OMDB cache (maps imdb_id -> {poster, actors, genres} or None), plus per-episode releases
# ---------------------------------------------------------------------------
def load_cache():
    if os.path.exists(OMDB_CACHE_FILE):
        with open(OMDB_CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_cache(cache):
    with open(OMDB_CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2)

def fetch_omdb_data(imdb_id, cache, progress=None):
    """Fetch poster URL, actor list, and genres from OMDB for movies/shows."""
    if not imdb_id:
        return None
    if imdb_id in cache:
        return cache[imdb_id]
    if not OMDB_API_KEY:
        return None

    if progress:
        current, total, title = progress
        print(f"  [{current}/{total}] Fetching data for {title} ({imdb_id})...")

    url = "https://www.omdbapi.com/"
    try:
        time.sleep(RATE_LIMIT_DELAY)
        r = requests.get(url, params={"apikey": OMDB_API_KEY, "i": imdb_id}, timeout=10)
        r.raise_for_status()
        data = r.json()

        poster = data.get("Poster")
        if poster == "N/A":
            poster = None

        actors_raw = data.get("Actors", "")
        if actors_raw and actors_raw != "N/A":
            actors = [a.strip() for a in actors_raw.split(",") if a.strip()]
        else:
            actors = []

        genre_raw = data.get("Genre", "")
        if genre_raw and genre_raw != "N/A":
            genres = [g.strip() for g in genre_raw.split(",") if g.strip()][:MAX_GENRES]
        else:
            genres = []

        entry = {"poster": poster, "actors": actors, "genres": genres}
        cache[imdb_id] = entry
        return entry
    except Exception as e:
        print(f"  ⚠ OMDB lookup failed for {imdb_id}: {e}")
        cache[imdb_id] = None
        return None

def parse_omdb_released(date_str):
    # OMDb returns e.g. '20 Aug 2017' or 'N/A'
    if not date_str or date_str == "N/A":
        return None
    try:
        return datetime.strptime(date_str, "%d %b %Y")
    except Exception:
        return None

def fetch_omdb_episode_released(show_imdb_id, season, episode, cache):
    cache_key = f"{show_imdb_id}_S{season}E{episode}"
    if cache_key in cache:
        return cache[cache_key]
    if not OMDB_API_KEY or not show_imdb_id:
        return None
    url = "https://www.omdbapi.com/"
    try:
        time.sleep(RATE_LIMIT_DELAY)
        r = requests.get(
            url,
            params={"apikey": OMDB_API_KEY, "i": show_imdb_id, "Season": season, "Episode": episode},
            timeout=10
        )
        r.raise_for_status()
        data = r.json()
        released = data.get("Released", "N/A")
        cache[cache_key] = {"released": released}
        return cache[cache_key]
    except Exception as e:
        print(f"  ⚠ OMDB episode lookup failed for {show_imdb_id} S{season}E{episode}: {e}")
        cache[cache_key] = None
        return None

# ---------------------------------------------------------------------------
# High-resolution poster utilities
# ---------------------------------------------------------------------------
def original_poster_url(poster_url):
    """Return high resolution version of the OMDB poster URL by stripping size modifiers."""
    if not poster_url:
        return None
    # Replace anything like _V1_SX300 or _V1_SY500 etc (and anything after _V1_) with just _V1_
    return re.sub(r'(_V1_)[^\.]*', r'\1', poster_url)

def poster_filename(imdb_id, poster_url):
    """Derive the local filename for a poster."""
    ext = os.path.splitext(poster_url.split("?")[0])[-1] or ".jpg"
    return f"{imdb_id}{ext}"

def download_poster(imdb_id, poster_url):
    """Download the highest resolution OMDB poster image."""
    if not imdb_id or not poster_url:
        return None
    orig_url = original_poster_url(poster_url)
    filename = poster_filename(imdb_id, poster_url)
    filepath = os.path.join(POSTER_DIR, filename)
    if os.path.exists(filepath):
        return f"00-Posters/{filename}"
    try:
        r = requests.get(orig_url, timeout=15)
        r.raise_for_status()
        with open(filepath, "wb") as f:
            f.write(r.content)
        return f"00-Posters/{filename}"
    except Exception as e:
        print(f"  ⚠ Failed to download poster for {imdb_id}: {e}")
        return None

# ---------------------------------------------------------------------------
# JSON helpers
# ---------------------------------------------------------------------------
def load_json(path):
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def load_json_multi(pattern):
    all_data = []
    for path in sorted(glob.glob(pattern)):
        all_data.extend(load_json(path))
    return all_data

def parse_date(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None

# ---------------------------------------------------------------------------
# Ratings & comments lookup builders
# ---------------------------------------------------------------------------
def build_ratings_map(export_dir):
    m = {}
    for kind, filename in [
        ("movie", "ratings-movies.json"),
        ("show", "ratings-shows.json"),
        ("season", "ratings-seasons.json"),
        ("episode", "ratings-episodes.json"),
    ]:
        data = load_json(os.path.join(export_dir, filename))
        for item in data:
            rating = item.get("rating")
            obj = item.get(kind, {})
            trakt_id = obj.get("ids", {}).get("trakt")
            if trakt_id and rating:
                m[(kind, trakt_id)] = rating
    return m

def build_comments_map(export_dir):
    m = {}
    for kind, filename in [
        ("movie", "comments-movies.json"),
        ("show", "comments-shows.json"),
        ("season", "comments-seasons.json"),
        ("episode", "comments-episodes.json"),
    ]:
        data = load_json(os.path.join(export_dir, filename))
        for item in data:
            comment_text = item.get("comment", {}).get("comment", "")
            obj = item.get(kind, {})
            trakt_id = obj.get("ids", {}).get("trakt")
            if trakt_id and comment_text:
                m[(kind, trakt_id)] = comment_text
    return m

# ---------------------------------------------------------------------------
# Batch OMDB fetching + poster downloading with progress
# ---------------------------------------------------------------------------
def fetch_all_data(history, list_data_sets, cache):
    """Pre-fetch all unique OMDB data, then download poster images, plus fetch episode air dates."""
    unique = {}

    for item in history:
        if item.get("type") == "movie":
            ids = item.get("movie", {}).get("ids", {})
            imdb_id = ids.get("imdb")
            if imdb_id and imdb_id not in cache:
                unique[imdb_id] = item.get("movie", {}).get("title", "?")
        elif item.get("type") == "episode":
            ids = item.get("show", {}).get("ids", {})
            imdb_id = ids.get("imdb")
            if imdb_id and imdb_id not in cache:
                unique[imdb_id] = item.get("show", {}).get("title", "?")

    for data in list_data_sets:
        for item in data:
            for kind in ("movie", "show"):
                obj = item.get(kind, {})
                if obj:
                    ids = obj.get("ids", {})
                    imdb_id = ids.get("imdb")
                    if imdb_id and imdb_id not in cache:
                        unique[imdb_id] = obj.get("title", "?")

    if not unique:
        print(f"All {len(cache)} entries already cached, no API calls needed.")
    else:
        print(f"\nFetching {len(unique)} entries from OMDB ({len(cache)} already cached)...\n")
        for i, (imdb_id, title) in enumerate(unique.items(), 1):
            fetch_omdb_data(imdb_id, cache, progress=(i, len(unique), title))
        print(f"\n✓ OMDB fetching complete.\n")

    # --- Download poster images (skip existing) ---
    os.makedirs(POSTER_DIR, exist_ok=True)
    to_download = {}
    for imdb_id, entry in cache.items():
        if not entry or not isinstance(entry, dict):
            continue
        poster_url = entry.get("poster")
        if not poster_url:
            continue
        filename = poster_filename(imdb_id, poster_url)
        filepath = os.path.join(POSTER_DIR, filename)
        if not os.path.exists(filepath):
            to_download[imdb_id] = poster_url

    if not to_download:
        print(f"All poster images already downloaded.\n")
        return

    print(f"Downloading {len(to_download)} poster images ({len(cache) - len(to_download)} already on disk)...\n")
    for i, (imdb_id, url) in enumerate(to_download.items(), 1):
        print(f"  [{i}/{len(to_download)}] Downloading {imdb_id}...")
        download_poster(imdb_id, url)

    print(f"\n✓ Poster downloads complete.\n")

    # --- Prefetch OMDb episode air dates ---
    episode_keys = set()
    for item in history:
        if item.get("type") == "episode":
            show = item.get("show", {})
            ep = item.get("episode", {})
            show_imdb_id = show.get("ids", {}).get("imdb")
            season, epnum = ep.get("season"), ep.get("number")
            if show_imdb_id and season and epnum:
                episode_keys.add((show_imdb_id, season, epnum))

    MAX_EPISODES_OMDB = 400  # set your comfort level
    if episode_keys:
        print(f"\nFetching OMDb release dates for {len(episode_keys)} unique episodes...\n", flush=True)
        if len(episode_keys) > MAX_EPISODES_OMDB:
            print(f"Too many episodes ({len(episode_keys)}), will only fetch {MAX_EPISODES_OMDB}.")
            episode_keys = list(episode_keys)[:MAX_EPISODES_OMDB]
        for idx, (show_imdb_id, season, epnum) in enumerate(episode_keys, 1):
            print(f"  [{idx}/{len(episode_keys)}] Fetching OMDb episode release date for {show_imdb_id} S{season}E{epnum}...", flush=True)
            fetch_omdb_episode_released(show_imdb_id, season, epnum, cache)

def get_cached_poster_path(imdb_id, cache):
    if not imdb_id:
        return None
    entry = cache.get(imdb_id)
    if not entry or not isinstance(entry, dict):
        return None
    poster_url = entry.get("poster")
    if not poster_url:
        return None
    filename = poster_filename(imdb_id, poster_url)
    filepath = os.path.join(POSTER_DIR, filename)
    if os.path.exists(filepath):
        return f"00-Posters/{filename}"
    return None

def get_cached_actors(imdb_id, cache):
    if not imdb_id:
        return []
    entry = cache.get(imdb_id)
    if not entry or not isinstance(entry, dict):
        return []
    return entry.get("actors", [])

def get_cached_genres(imdb_id, cache):
    if not imdb_id:
        return []
    entry = cache.get(imdb_id)
    if not entry or not isinstance(entry, dict):
        return []
    return entry.get("genres", [])

# ---------------------------------------------------------------------------
# Link helpers
# ---------------------------------------------------------------------------
def wikipedia_url(title):
    encoded = urllib.parse.quote(title.replace(" ", "_"))
    return f"https://en.wikipedia.org/wiki/{encoded}"

def imdb_name_search_url(actor_name):
    encoded = urllib.parse.quote_plus(actor_name)
    return f"https://www.imdb.com/find/?q={encoded}&s=nm"

def actor_markdown(actor_name):
    imdb = imdb_name_search_url(actor_name)
    wiki = wikipedia_url(actor_name)
    return f"{actor_name} ([IMDb]({imdb}) - [Wikipedia]({wiki}))"

def genre_tags_line(genres, media_type):
    tags = []
    for g in genres[:MAX_GENRES]:
        slug = g.lower().replace(" ", "-").replace("/", "-")
        tags.append(f"#{media_type}-{slug}")
    return " - ".join(tags)

def genre_nice_line(genres):
    return ", ".join(genres[:MAX_GENRES]) if genres else ""

def year_tag(year, media_type):
    if not year:
        return ""
    return f"#{media_type}-{year}"

# ---------------------------------------------------------------------------
# History parsing
# ---------------------------------------------------------------------------
def parse_history(history, ratings_map, comments_map, cache):
    movie_entries = []
    tv_entries = []

    for item in history:
        watched_at = parse_date(item.get("watched_at", ""))
        item_type = item.get("type", "")

        if item_type == "movie":
            movie = item.get("movie", {})
            ids = movie.get("ids", {})
            trakt_id = ids.get("trakt")
            imdb_id = ids.get("imdb")
            slug = ids.get("slug", "")
            title = movie.get("title", "Unknown")
            year = movie.get("year", "")

            movie_entries.append({
                "title": title,
                "year": year,
                "watched_at": watched_at,
                "rating": ratings_map.get(("movie", trakt_id)),
                "comment": comments_map.get(("movie", trakt_id)),
                "poster": get_cached_poster_path(imdb_id, cache),
                "actors": get_cached_actors(imdb_id, cache),
                "genres": get_cached_genres(imdb_id, cache),
                "imdb_id": imdb_id,
                "trakt_url": f"https://trakt.tv/movies/{slug}" if slug else "",
            })

        elif item_type == "episode":
            show = item.get("show", {})
            episode = item.get("episode", {})
            show_ids = show.get("ids", {})
            ep_ids = episode.get("ids", {})
            imdb_id = show_ids.get("imdb")
            slug = show_ids.get("slug", "")
            show_title = show.get("title", "Unknown")
            show_year = show.get("year", "")
            season = episode.get("season", 0)
            ep_number = episode.get("number", 0)
            ep_title = episode.get("title", "")

            # OMDb episode lookup cache key and fetch release date if available
            omdb_episode_key = f"{imdb_id}_S{season}E{ep_number}"
            omdb_ep = cache.get(omdb_episode_key, {})
            released_str = omdb_ep.get("released")
            released_at = parse_omdb_released(released_str)

            tv_entries.append({
                "title": show_title,
                "year": show_year,
                "season": season,
                "episode": ep_number,
                "episode_title": ep_title,
                "watched_at": watched_at,
                "released_at": released_at,
                "rating": ratings_map.get(("episode", ep_ids.get("trakt"))),
                "comment": comments_map.get(("episode", ep_ids.get("trakt"))),
                "poster": get_cached_poster_path(imdb_id, cache),
                "actors": get_cached_actors(imdb_id, cache),
                "genres": get_cached_genres(imdb_id, cache),
                "imdb_id": imdb_id,
                "trakt_url": f"https://trakt.tv/shows/{slug}" if slug else "",
            })

    return movie_entries, tv_entries

# ---------------------------------------------------------------------------
# Watchlist & Favorites parsing
# ---------------------------------------------------------------------------
def parse_list_file(data, ratings_map, comments_map, cache):
    movie_entries = []
    tv_entries = []

    for item in data:
        listed_at = parse_date(item.get("listed_at", "") or item.get("added_at", ""))
        item_type = item.get("type", "")

        if item_type == "movie":
            movie = item.get("movie", {})
            ids = movie.get("ids", {})
            imdb_id = ids.get("imdb")
            slug = ids.get("slug", "")
            trakt_id = ids.get("trakt")
            movie_entries.append({
                "title": movie.get("title", "Unknown"),
                "year": movie.get("year", ""),
                "watched_at": listed_at,
                "rating": ratings_map.get(("movie", trakt_id)),
                "comment": comments_map.get(("movie", trakt_id)),
                "poster": get_cached_poster_path(imdb_id, cache),
                "actors": get_cached_actors(imdb_id, cache),
                "genres": get_cached_genres(imdb_id, cache),
                "imdb_id": imdb_id,
                "trakt_url": f"https://trakt.tv/movies/{slug}" if slug else "",
            })

        elif item_type == "show":
            show = item.get("show", {})
            ids = show.get("ids", {})
            imdb_id = ids.get("imdb")
            slug = ids.get("slug", "")
            trakt_id = ids.get("trakt")
            tv_entries.append({
                "title": show.get("title", "Unknown"),
                "year": show.get("year", ""),
                "season": None,
                "episode": None,
                "episode_title": "",
                "watched_at": listed_at,
                "rating": ratings_map.get(("show", trakt_id)),
                "comment": comments_map.get(("show", trakt_id)),
                "poster": get_cached_poster_path(imdb_id, cache),
                "actors": get_cached_actors(imdb_id, cache),
                "genres": get_cached_genres(imdb_id, cache),
                "imdb_id": imdb_id,
                "trakt_url": f"https://trakt.tv/shows/{slug}" if slug else "",
            })

    return movie_entries, tv_entries

# ---------------------------------------------------------------------------
# Markdown generation
# ---------------------------------------------------------------------------
def rating_stars(rating):
    if rating is None:
        return ""
    return f"{'⭐' * rating} ({rating}/10)"

def movie_entry_md(e):
    lines = []
    date_str = e["watched_at"].strftime("%Y-%m-%d") if e.get("watched_at") else "Unknown date"
    year_str = f" ({e['year']})" if e.get("year") else ""
    lines.append(f"### {date_str} - {e['title']}{year_str}\n")
    if e.get("poster"):
        lines.append(f"![cover]({e['poster']})\n")
    if e.get("rating"):
        lines.append(f"- **Rating:** {rating_stars(e['rating'])}\n")
    if e.get("genres"):
        lines.append(f"- **Genre:** {genre_nice_line(e['genres'])}")
    if e.get("actors"):
        actor_links = ", ".join(actor_markdown(a) for a in e["actors"])
        lines.append(f"- **Cast:** {actor_links}\n")
    if e.get("imdb_id"):
        lines.append(f"- **IMDb:** https://www.imdb.com/title/{e['imdb_id']}/")
    lines.append(f"- **Wikipedia:** {wikipedia_url(e['title'])}")
    if e.get("trakt_url"):
        lines.append(f"- **Trakt:** {e['trakt_url']}\n")
    if e.get("comment"):
        lines.append(f"\n> {e['comment']}\n")
    year_tag_val = f"#movie-{e['watched_at'].year}" if e.get("watched_at") else "movie-unknown"
    lines.append(f"- **Date Tag:** {year_tag_val}")
    lines.append(f"- **Genres Tags:** {genre_tags_line(e.get('genres', []), 'movie')}\n")
    lines.append("\n---\n")
    return "\n".join(lines)

def tv_entry_md(e):
    lines = []
    date_str = e["watched_at"].strftime("%Y-%m-%d") if e.get("watched_at") else "Unknown date"
    year_str = f" ({e['year']})" if e.get("year") else ""
    if e.get("season") is not None and e.get("episode") is not None:
        se = f" - S{e['season']:02d}E{e['episode']:02d}"
        ep_title = f" - {e['episode_title']}" if e.get("episode_title") else ""
        lines.append(f"### {date_str} - {e['title']}{year_str}{se}{ep_title}\n")
    else:
        lines.append(f"### {date_str} - {e['title']}{year_str}\n")
    if e.get("poster"):
        lines.append(f"![cover]({e['poster']})\n")
    if e.get("rating"):
        lines.append(f"- **Rating:** {rating_stars(e['rating'])}\n")
    release_str = e.get("released_at").strftime("%Y-%m-%d") if e.get("released_at") else "Unknown release date"
    lines.append(f"- **Episode Release Date:** {release_str}")
    if e.get("genres"):
        lines.append(f"- **Genre:** {genre_nice_line(e['genres'])}")
    if e.get("actors"):
        actor_links = ", ".join(actor_markdown(a) for a in e["actors"])
        lines.append(f"- **Cast:** {actor_links}\n")
    if e.get("imdb_id"):
        lines.append(f"- **IMDb:** https://www.imdb.com/title/{e['imdb_id']}/")
    lines.append(f"- **Wikipedia:** {wikipedia_url(e['title'])}")
    if e.get("trakt_url"):
        lines.append(f"- **Trakt:** {e['trakt_url']}\n")
    if e.get("comment"):
        lines.append(f"\n> {e['comment']}\n")
    # New Date Tag ("tv-YYYY")
    year_tag_val = f"#tv-{e['watched_at'].year}" if e.get("watched_at") else "tv-unknown"
    lines.append(f"- **Date Tag:** {year_tag_val}")
    lines.append(f"- **Genres Tags:** {genre_tags_line(e.get('genres', []), 'tv')}\n")
    lines.append("\n---\n")
    return "\n".join(lines)

def write_markdown_files(entries, entry_type, label_prefix):
    by_year = defaultdict(list)
    no_date = []
    for e in entries:
        if e["watched_at"]:
            by_year[e["watched_at"].year].append(e)
        else:
            no_date.append(e)
    formatter = movie_entry_md if entry_type == "movie" else tv_entry_md
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    for year in sorted(by_year):
        items = sorted(by_year[year], key=lambda x: x["watched_at"])
        filename = os.path.join(OUTPUT_DIR, f"{label_prefix}-{year}.md")
        with open(filename, "w", encoding="utf-8") as f:
            f.write(f"# {label_prefix} - {year}\n\n")
            f.write(f"_{len(items)} entries_\n\n---\n\n")
            for item in items:
                f.write(formatter(item))
        print(f"  ✓ {filename} ({len(items)} entries)")
    if no_date:
        filename = os.path.join(OUTPUT_DIR, f"{label_prefix}-Undated.md")
        with open(filename, "w", encoding="utf-8") as f:
            f.write(f"# {label_prefix} - Undated\n\n")
            f.write(f"_{len(no_date)} entries_\n\n---\n\n")
            for item in no_date:
                f.write(formatter(item))
        print(f"  ✓ {filename} ({len(no_date)} entries)")

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    if not OMDB_API_KEY:
        print("⚠ OMDB_API_KEY not set — posters, cast, and genres will be skipped.")
        print("  Get a free key at: https://www.omdbapi.com/apikey.aspx")
        print("  Set it with: export OMDB_API_KEY=your_key_here\n")
    export_dir = sys.argv[1] if len(sys.argv) > 1 else "."
    print(f"Reading Trakt export from: {export_dir}\n")
    ratings_map = build_ratings_map(export_dir)
    print(f"Loaded {len(ratings_map)} ratings")
    comments_map = build_comments_map(export_dir)
    print(f"Loaded {len(comments_map)} comments")
    cache = load_cache()
    history = load_json_multi(os.path.join(export_dir, "watched-history-*.json"))
    print(f"Loaded {len(history)} history events")
    watchlist_path = os.path.join(export_dir, "lists-watchlist.json")
    fav_path = os.path.join(export_dir, "lists-favorites.json")
    watchlist_data = load_json(watchlist_path) if os.path.exists(watchlist_path) else []
    fav_data = load_json(fav_path) if os.path.exists(fav_path) else []
    if watchlist_data:
        print(f"Loaded {len(watchlist_data)} watchlist items")
    if fav_data:
        print(f"Loaded {len(fav_data)} favorite items")
    fetch_all_data(history, [watchlist_data, fav_data], cache)
    save_cache(cache)
    movie_entries, tv_entries = parse_history(
        history, ratings_map, comments_map, cache
    )
    print(f"Parsed {len(movie_entries)} movie watches, {len(tv_entries)} episode watches")
    if movie_entries:
        print("\nWriting movie history...")
        write_markdown_files(movie_entries, "movie", "Movies")
    if tv_entries:
        print("\nWriting TV history...")
        write_markdown_files(tv_entries, "tv", "TV")
    if watchlist_data and len(watchlist_data) > 0:
        wl_movies, wl_tv = parse_list_file(
            watchlist_data, ratings_map, comments_map, cache
        )
        print(f"\nParsed watchlist: {len(wl_movies)} movies, {len(wl_tv)} shows")
        if wl_movies:
            print("Writing watchlist movies...")
            write_markdown_files(wl_movies, "movie", "Watchlist-Movies")
        if wl_tv:
            print("Writing watchlist TV...")
            write_markdown_files(wl_tv, "tv", "Watchlist-TV")
    if fav_data and len(fav_data) > 0:
        fav_movies, fav_tv = parse_list_file(
            fav_data, ratings_map, comments_map, cache
        )
        print(f"\nParsed favorites: {len(fav_movies)} movies, {len(fav_tv)} shows")
        if fav_movies:
            print("Writing favorite movies...")
            write_markdown_files(fav_movies, "movie", "Favorites-Movies")
        if fav_tv:
            print("Writing favorite TV...")
            write_markdown_files(fav_tv, "tv", "Favorites-TV")
    save_cache(cache)
    total_posters = len([f for f in os.listdir(POSTER_DIR) if not f.startswith(".")]) if os.path.exists(POSTER_DIR) else 0
    print(f"\n✅ Done! Markdown files written to ./{OUTPUT_DIR}/")
    print(f"   {total_posters} posters saved to ./{POSTER_DIR}/")
    print(f"   OMDB cache saved to {OMDB_CACHE_FILE} ({len(cache)} entries)")

if __name__ == "__main__":
    main()