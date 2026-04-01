import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone

VLR_NEWS_URL   = "https://www.vlr.gg/news"
VLR_MATCHES_URL = "https://www.vlr.gg/matches"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}


def get_vlr_news(limit: int = 10) -> list[dict]:
    try:
        r = requests.get(VLR_NEWS_URL, headers=HEADERS, timeout=10)
        r.raise_for_status()
    except requests.RequestException as e:
        print(f"[VLR] Erreur news : {e}")
        return []

    soup     = BeautifulSoup(r.text, "html.parser")
    articles = []

    for item in soup.select("a.wf-module-item"):
        if len(articles) >= limit:
            break
        try:
            title_tag = (
                item.select_one(".wf-title")
                or item.select_one("h1") or item.select_one("h2") or item.select_one("h3")
                or item.select_one(".mod-large") or item.select_one(".article-title")
            )
            desc_tag = item.select_one(".ge-text-light") or item.select_one("p")
            date_tag = item.select_one(".ge-text") or item.select_one(".date")
            img_tag  = item.select_one("img")

            image = None
            if img_tag:
                image = img_tag.get("src") or img_tag.get("data-src")
                if image and image.startswith("//"):
                    image = "https:" + image

            href  = item.get("href", "")
            url   = "https://www.vlr.gg" + href if href.startswith("/") else href
            title = title_tag.get_text(strip=True) if title_tag else ""

            if not title or len(title) < 5:
                all_text = [t.get_text(strip=True) for t in item.find_all(["h1","h2","h3","h4","span","div"]) if len(t.get_text(strip=True)) > 10]
                title = max(all_text, key=len) if all_text else None

            if not title:
                continue

            articles.append({
                "title":       title,
                "url":         url,
                "description": desc_tag.get_text(strip=True)[:200] if desc_tag else "",
                "date":        date_tag.get_text(strip=True) if date_tag else "",
                "image":       image,
            })
        except Exception as e:
            print(f"[VLR] Erreur article : {e}")

    print(f"[VLR] {len(articles)} article(s) récupéré(s)")
    return articles


def get_vlr_matches() -> list[dict]:
    """Récupère les matchs du jour (à venir + terminés) depuis VLR.gg."""
    try:
        r = requests.get(VLR_MATCHES_URL, headers=HEADERS, timeout=10)
        r.raise_for_status()
    except requests.RequestException as e:
        print(f"[VLR] Erreur matchs : {e}")
        return []

    soup    = BeautifulSoup(r.text, "html.parser")
    matches = []

    for item in soup.select("a.wf-module-item"):
        try:
            href  = item.get("href", "")
            url   = "https://www.vlr.gg" + href if href.startswith("/") else href

            teams = item.select(".match-item-vs-team-name")
            if len(teams) < 2:
                continue

            t1    = teams[0].get_text(strip=True)
            t2    = teams[1].get_text(strip=True)
            if not t1 or not t2:
                continue

            time_tag  = item.select_one(".match-item-time")
            event_tag = item.select_one(".match-item-event .match-item-event-series") or item.select_one(".match-item-event")
            score_tag = item.select(".match-item-vs-team-score")
            status    = item.select_one(".ml-status") or item.select_one(".match-item-status")

            # Score et statut
            score    = ""
            finished = False
            if score_tag and len(score_tag) >= 2:
                s1 = score_tag[0].get_text(strip=True)
                s2 = score_tag[1].get_text(strip=True)
                if s1.isdigit() and s2.isdigit():
                    score    = f"{s1} - {s2}"
                    finished = True

            if status:
                st = status.get_text(strip=True).lower()
                if "completed" in st or "final" in st:
                    finished = True

            matches.append({
                "team1":    t1,
                "team2":    t2,
                "score":    score,
                "time":     time_tag.get_text(strip=True) if time_tag else "?",
                "event":    event_tag.get_text(strip=True) if event_tag else "",
                "url":      url,
                "finished": finished,
            })
        except Exception as e:
            print(f"[VLR] Erreur match : {e}")

    print(f"[VLR] {len(matches)} match(s) récupéré(s)")
    return matches
