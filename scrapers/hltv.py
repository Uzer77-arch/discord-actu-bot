import requests
from bs4 import BeautifulSoup

# HLTV bloque les accès automatiques, on utilise escorenews.com à la place
# (news CS2 pro : résultats, transferts, tournois)
CS2_RSS_URL = "https://escorenews.com/en/csgo/rss"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}


def get_hltv_news(limit: int = 10) -> list[dict]:
    """
    Récupère les dernières news CS2 via escorenews.com (RSS).
    Retourne une liste de dicts : title, url, description, date, image.
    """
    try:
        response = requests.get(CS2_RSS_URL, headers=HEADERS, timeout=10)
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"[CS2] Erreur de requête : {e}")
        return []

    soup = BeautifulSoup(response.text, "xml")
    articles = []

    for item in soup.select("item")[:limit]:
        try:
            title       = item.find("title")
            url         = item.find("link")
            description = item.find("description")
            date        = item.find("pubDate")

            articles.append({
                "title":       title.get_text(strip=True) if title else "Sans titre",
                "url":         url.get_text(strip=True) if url else "",
                "description": BeautifulSoup(description.get_text(), "html.parser").get_text(strip=True)[:200] if description else "",
                "date":        date.get_text(strip=True) if date else "",
                "image":       None,
            })
        except Exception as e:
            print(f"[CS2] Erreur sur un article : {e}")
            continue

    print(f"[CS2] {len(articles)} article(s) récupéré(s)")
    return articles
