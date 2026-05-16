import requests
from bs4 import BeautifulSoup


def get_game_sitemaps():
    index_url = "https://stopgame.ru/sitemap.xml"

    resp = requests.get(index_url)
    soup = BeautifulSoup(resp.text, "xml")

    game_sitemaps = [
        loc.text for loc in soup.find_all("loc")
        if "games_" in loc.text
    ]
    return game_sitemaps

def get_all_game_urls():
    all_urls = []
    for sitemap_url in get_game_sitemaps():
        resp = requests.get(sitemap_url)
        soup = BeautifulSoup(resp.text, "xml")
        urls = [loc.text for loc in soup.find_all("loc")]
        all_urls.extend(urls)
    return all_urls

def parse_game_page(url):
    resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
    soup = BeautifulSoup(resp.text, "html.parser")

    # Дата, разработчик, платформы
    dl = soup.find("dl", class_=lambda c: c and "_game-info__grid" in c)
    data = {}
    if dl:
        items = dl.find_all(["dt", "dd"])
        for i, tag in enumerate(items):
            if tag.name == "dt":
                key = tag.get_text(strip=True)
                if i + 1 < len(items) and items[i + 1].name == "dd":
                    data[key] = items[i + 1].get_text(strip=True)

    # Рейтинг и количество голосов
    rating_tag = soup.find("span", class_=lambda c: c and "_game-rating_" in c)
    votes_tag = soup.find("span", class_=lambda c: c and "_total-game-votes_" in c)

    return {
        "url": url,
        "date": data.get("Дата выхода"),
        "developer": data.get("Разработчик"),
        "platforms": data.get("Платформы"),
        "rating": rating_tag.get_text(strip=True) if rating_tag else None,
        "votes": votes_tag.get_text(strip=True) if votes_tag else None,
    }

def parse_all_games(game_urls):
    games = []
    for i, url in enumerate(game_urls):
        print("Parse url {url}".format(url=url))
        game = parse_game_page(url)
        games.append(game)
    return games

print(parse_all_games(get_all_game_urls())[:2])