import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone, timedelta

VLR_NEWS_URL    = "https://www.vlr.gg/news"
VLR_MATCHES_URL = "https://www.vlr.gg/matches"
VLR_RESULTS_URL = "https://www.vlr.gg/matches/results"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}

def to_paris_time(utc_time_str: str) -> str:
    try:
        now      = datetime.now(timezone.utc)
        offset   = timedelta(hours=2) if 4 <= now.month <= 10 else timedelta(hours=1)
        tz_label = "CEST" if 4 <= now.month <= 10 else "CET"
        h, m     = map(int, utc_time_str.strip().split(":"))
        utc_dt   = now.replace(hour=h, minute=m, second=0, microsecond=0)
        paris_dt = utc_dt + offset
        return f"{paris_dt.strftime('%H:%M')} {tz_label}"
    except:
        return utc_time_str


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


def _parse_matches_from_url(url: str, default_status: str = "UPCOMING") -> list[dict]:
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        r.raise_for_status()
    except requests.RequestException as e:
        print(f"[VLR] Erreur matchs ({url}) : {e}")
        return []

    soup    = BeautifulSoup(r.text, "html.parser")
    matches = []

    for item in soup.select("a.wf-module-item"):
        try:
            href = item.get("href", "")
            murl = "https://www.vlr.gg" + href if href.startswith("/") else href

            teams = item.select(".match-item-vs-team-name")
            if len(teams) < 2:
                continue
            t1 = teams[0].get_text(strip=True)
            t2 = teams[1].get_text(strip=True)
            if not t1 or not t2:
                continue

            status_tag = item.select_one(".ml-status") or item.select_one(".match-item-status")
            status_raw = status_tag.get_text(strip=True).upper() if status_tag else ""

            if "COMPLETED" in status_raw or "FINAL" in status_raw:
                status = "COMPLETED"; finished = True; live = False
            elif "LIVE" in status_raw:
                status = "LIVE"; finished = False; live = True
            else:
                status = default_status
                finished = default_status == "COMPLETED"
                live = False

            score = ""
            score_tags = item.select(".match-item-vs-team-score")
            if len(score_tags) >= 2:
                s1 = score_tags[0].get_text(strip=True)
                s2 = score_tags[1].get_text(strip=True)
                if s1.isdigit() and s2.isdigit() and (finished or live):
                    score = f"{s1} - {s2}"

            time_tag   = item.select_one(".match-item-time") or item.select_one(".moment-tz-convert")
            time_raw   = time_tag.get_text(strip=True) if time_tag else ""
            time_paris = to_paris_time(time_raw) if time_raw and ":" in time_raw else time_raw

            # Date affichée (ex: "Today", "Tomorrow", "Fri, Apr 4")
            date_tag  = item.select_one(".match-item-date") or item.select_one(".wf-label")
            date_str  = date_tag.get_text(strip=True) if date_tag else ""

            event_tag = (
                item.select_one(".match-item-event .match-item-event-series")
                or item.select_one(".match-item-event")
            )
            event = event_tag.get_text(strip=True) if event_tag else ""

            matches.append({
                "team1":    t1,
                "team2":    t2,
                "score":    score,
                "time":     time_paris,
                "date":     date_str,
                "event":    event,
                "url":      murl,
                "status":   status,
                "finished": finished,
                "live":     live,
            })
        except Exception as e:
            print(f"[VLR] Erreur match : {e}")

    return matches


def get_vlr_matches() -> list[dict]:
    """Matchs à venir + LIVE sur /matches (jusqu'à 7 jours)."""
    matches = _parse_matches_from_url(VLR_MATCHES_URL, default_status="UPCOMING")
    print(f"[VLR] {len(matches)} match(s) récupéré(s)")
    return matches


def get_vlr_results() -> list[dict]:
    """Résultats du jour depuis /matches/results."""
    results = _parse_matches_from_url(VLR_RESULTS_URL, default_status="COMPLETED")
    print(f"[VLR] {len(results)} résultat(s) récupéré(s)")
    return results


def get_all_matches() -> dict:
    """
    Récupère tout en une fois et retourne un dict avec 3 clés :
    - live     : matchs en cours
    - results  : matchs terminés aujourd'hui
    - upcoming : matchs à venir (7 jours)
    """
    schedule = get_vlr_matches()
    results  = get_vlr_results()

    live     = [m for m in schedule if m["status"] == "LIVE"]
    upcoming = [m for m in schedule if m["status"] == "UPCOMING"]

    return {
        "live":     live,
        "results":  results,
        "upcoming": upcoming,
    }
