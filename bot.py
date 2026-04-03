import discord
from discord.ext import commands, tasks
import asyncio
import os
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from datetime import datetime
from scrapers.vlr import get_vlr_news, get_vlr_matches, get_vlr_results, get_all_matches

load_dotenv()

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

VLR_CHANNEL_ID   = int(os.getenv("VLR_CHANNEL_ID", 0))
MATCH_CHANNEL_ID = int(os.getenv("MATCH_CHANNEL_ID", 0))
VLR_LOGO         = "https://www.vlr.gg/img/vlr/logo_header.png"

REGIONS = {
    "ALL":     {"label": "🌍 Toutes",  "emoji": "🌍"},
    "EMEA":    {"label": "🇪🇺 EMEA",   "emoji": "🇪🇺"},
    "NA":      {"label": "🇺🇸 NA",     "emoji": "🇺🇸"},
    "PACIFIC": {"label": "🌏 Pacific", "emoji": "🌏"},
    "CHINA":   {"label": "🇨🇳 China",  "emoji": "🇨🇳"},
    "BR":      {"label": "🇧🇷 LATAM",  "emoji": "🇧🇷"},
}

# ─────────────────────────────────────────
# Persistance
# ─────────────────────────────────────────
def load_file(path):
    if not os.path.exists(path): return set()
    with open(path) as f: return set(l.strip() for l in f if l.strip())

def append_file(path, value):
    with open(path, "a") as f: f.write(value + "\n")

posted           = load_file("posted.txt")
notified_results = load_file("results.txt")

TEAMS = {
    "Sentinels":     "sentinels",
    "Team Liquid":   "team-liquid",
    "LOUD":          "loud",
    "NaVi":          "natus-vincere",
    "Fnatic":        "fnatic",
    "Cloud9":        "cloud9",
    "100 Thieves":   "100-thieves",
    "EDward Gaming": "edward-gaming",
    "ZETA DIVISION": "zeta-division",
    "Team Vitality": "team-vitality",
}

# ─────────────────────────────────────────
# Traduction
# ─────────────────────────────────────────
def translate_to_french(text):
    if not text: return text
    try:
        r = requests.get(
            "https://translate.googleapis.com/translate_a/single",
            params={"client":"gtx","sl":"auto","tl":"fr","dt":"t","q":text},
            timeout=5,
        )
        data = r.json()
        return "".join(p[0] for p in data[0] if p[0]) or text
    except:
        return text

# ─────────────────────────────────────────
# Filtre par région
# ─────────────────────────────────────────
def filter_by_region(matches: list, region: str) -> list:
    if region == "ALL":
        return matches
    return [m for m in matches if m.get("region") == region]

# ─────────────────────────────────────────
# Embeds
# ─────────────────────────────────────────
def make_vlr_embed(article):
    title = translate_to_french(article.get("title","Sans titre"))
    desc  = article.get("description","")
    desc  = translate_to_french(desc) if desc else "Clique sur le titre pour lire l'article complet."
    embed = discord.Embed(title=title, url=article.get("url",""), description=desc, color=0xFF4655)
    embed.set_author(name="VLR.gg — Valorant Esport", icon_url=VLR_LOGO)
    if article.get("image"): embed.set_thumbnail(url=article["image"])
    if article.get("date"):  embed.set_footer(text=f"📅 {article['date']}", icon_url=VLR_LOGO)
    return embed

def make_result_embed(match):
    t1, t2 = match.get("team1","?"), match.get("team2","?")
    score  = match.get("score","?")
    event  = match.get("event","")
    url    = match.get("url","")
    try:
        s1, s2 = score.split(" - ")
        winner = t1 if int(s1) > int(s2) else t2
        result_line = f"🏆 **{winner}** remporte le match !"
    except:
        result_line = ""
    embed = discord.Embed(
        title=f"📣 Résultat : {t1} vs {t2}", url=url,
        description=f"**{t1}  {score}  {t2}**\n{result_line}", color=0xFF4655,
    )
    embed.set_author(name="VLR.gg — Résultats", icon_url=VLR_LOGO)
    if event: embed.add_field(name="🎯 Événement", value=event, inline=False)
    embed.set_footer(text="Résultat Valorant Pro • VLR.gg", icon_url=VLR_LOGO)
    return embed

# ─────────────────────────────────────────
# Construction embed paginé
# ─────────────────────────────────────────
ITEMS_PER_PAGE = 8

def build_match_embed(data: dict, page: int, region: str = "ALL") -> discord.Embed:
    region_info = REGIONS.get(region, REGIONS["ALL"])
    region_label = region_info["label"]

    live     = filter_by_region(data["live"],     region)
    results  = filter_by_region(data["results"],  region)
    upcoming = filter_by_region(data["upcoming"], region)

    total_up_pages = max(1, -(-len(upcoming) // ITEMS_PER_PAGE))
    total_pages    = 2 + total_up_pages

    if page == 0:
        embed = discord.Embed(
            title       = f"🔴 Matchs en cours — {region_label}",
            description = f"**{len(live)}** match(s) en ce moment" if live else "Aucun match en cours pour l'instant.",
            color       = 0xFF4655,
        )
        if live:
            lines = []
            for m in live:
                line = f"🔴 **{m['team1']}** vs **{m['team2']}**"
                if m.get("score"): line += f" | `{m['score']}`"
                if m.get("event"): line += f"\n┗ *{m['event']}*"
                lines.append(line)
            embed.add_field(name="En cours", value="\n\n".join(lines), inline=False)

    elif page == 1:
        embed = discord.Embed(
            title       = f"✅ Résultats du jour — {region_label}",
            description = f"**{len(results)}** match(s) terminé(s) aujourd'hui" if results else "Aucun résultat pour cette région aujourd'hui.",
            color       = 0xFF4655,
        )
        by_event = {}
        for m in results:
            ev = m.get("event","Autre") or "Autre"
            by_event.setdefault(ev, []).append(m)
        for ev, ms in by_event.items():
            lines = []
            for m in ms:
                t1, t2, score = m["team1"], m["team2"], m.get("score","?")
                try:
                    s1, s2 = score.split(" - ")
                    winner = t1 if int(s1) > int(s2) else t2
                    lines.append(f"🏆 [{t1} **{score}** {t2}]({m['url']}) — *{winner}*")
                except:
                    lines.append(f"[{t1} **{score}** {t2}]({m['url']})")
            embed.add_field(name=f"🎯 {ev}", value="\n".join(lines), inline=False)

    else:
        up_page   = page - 2
        idx_start = up_page * ITEMS_PER_PAGE
        chunk     = upcoming[idx_start:idx_start + ITEMS_PER_PAGE]
        embed = discord.Embed(
            title       = f"📅 À venir — {region_label} ({up_page + 1}/{total_up_pages})",
            description = f"**{len(upcoming)}** match(s) prévus" if upcoming else "Aucun match prévu pour cette région.",
            color       = 0xFF4655,
        )
        if chunk:
            by_date = {}
            for m in chunk:
                d = m.get("date","") or "Date inconnue"
                by_date.setdefault(d, []).append(m)
            for d, ms in by_date.items():
                lines = []
                for m in ms:
                    line = f"🕐 `{m.get('time','?')}` — **{m['team1']}** vs **{m['team2']}**"
                    if m.get("event"): line += f"\n┗ *{m['event']}*"
                    lines.append(line)
                embed.add_field(name=f"📆 {d}", value="\n\n".join(lines), inline=False)

    embed.set_author(name="VLR.gg — Calendrier", icon_url=VLR_LOGO)
    embed.set_thumbnail(url=VLR_LOGO)
    embed.set_footer(text=f"Page {page + 1}/{total_pages} • Région : {region_label} • VLR.gg", icon_url=VLR_LOGO)
    return embed

def get_total_pages(data: dict, region: str = "ALL") -> int:
    upcoming = filter_by_region(data["upcoming"], region)
    return 2 + max(1, -(-len(upcoming) // ITEMS_PER_PAGE))

# ─────────────────────────────────────────
# Boutons de région
# ─────────────────────────────────────────
class RegionButton(discord.ui.Button):
    def __init__(self, region: str, view_ref):
        info = REGIONS[region]
        super().__init__(
            label  = info["label"],
            style  = discord.ButtonStyle.success if view_ref.region == region else discord.ButtonStyle.secondary,
            row    = 1,
        )
        self.region   = region
        self.view_ref = view_ref

    async def callback(self, interaction: discord.Interaction):
        self.view_ref.region      = self.region
        self.view_ref.page        = 0
        self.view_ref.total_pages = get_total_pages(self.view_ref.data, self.region)
        self.view_ref._rebuild()
        await interaction.response.edit_message(
            embed=build_match_embed(self.view_ref.data, 0, self.region),
            view=self.view_ref,
        )

# ─────────────────────────────────────────
# Vue principale avec pagination + régions
# ─────────────────────────────────────────
class MatchView(discord.ui.View):
    def __init__(self, data: dict, page: int = 0, region: str = "ALL"):
        super().__init__(timeout=180)
        self.data        = data
        self.page        = page
        self.region      = region
        self.total_pages = get_total_pages(data, region)
        self._rebuild()

    def _rebuild(self):
        self.clear_items()

        # ── Ligne 0 : navigation ──────────────────────────────
        prev = discord.ui.Button(
            label    = "◀ Précédent",
            style    = discord.ButtonStyle.primary,
            disabled = self.page == 0,
            row      = 0,
        )
        prev.callback = self._prev

        nxt_labels = {0: "Résultats ▶", 1: "À venir ▶"}
        nxt = discord.ui.Button(
            label    = nxt_labels.get(self.page, "Suivant ▶"),
            style    = discord.ButtonStyle.primary,
            disabled = self.page >= self.total_pages - 1,
            row      = 0,
        )
        nxt.callback = self._next

        refresh = discord.ui.Button(label="🔄 Actualiser", style=discord.ButtonStyle.success, row=0)
        refresh.callback = self._refresh

        self.add_item(prev)
        self.add_item(nxt)
        self.add_item(refresh)

        # ── Ligne 1 : filtres région ──────────────────────────
        for region in REGIONS:
            btn = discord.ui.Button(
                label    = REGIONS[region]["label"],
                style    = discord.ButtonStyle.success if self.region == region else discord.ButtonStyle.secondary,
                row      = 1,
            )
            btn.region = region
            btn.callback = self._make_region_callback(region)
            self.add_item(btn)

    def _make_region_callback(self, region: str):
        async def callback(interaction: discord.Interaction):
            self.region      = region
            self.page        = 0
            self.total_pages = get_total_pages(self.data, region)
            self._rebuild()
            await interaction.response.edit_message(
                embed=build_match_embed(self.data, 0, region),
                view=self,
            )
        return callback

    async def _prev(self, interaction: discord.Interaction):
        self.page -= 1
        self._rebuild()
        await interaction.response.edit_message(
            embed=build_match_embed(self.data, self.page, self.region), view=self)

    async def _next(self, interaction: discord.Interaction):
        self.page += 1
        self._rebuild()
        await interaction.response.edit_message(
            embed=build_match_embed(self.data, self.page, self.region), view=self)

    async def _refresh(self, interaction: discord.Interaction):
        await interaction.response.defer()
        self.data        = get_all_matches()
        self.total_pages = get_total_pages(self.data, self.region)
        self.page        = min(self.page, self.total_pages - 1)
        self._rebuild()
        await interaction.edit_original_response(
            embed=build_match_embed(self.data, self.page, self.region), view=self)

# ─────────────────────────────────────────
# Événements
# ─────────────────────────────────────────
@bot.event
async def on_ready():
    print(f"✅ Connecté en tant que {bot.user} (ID: {bot.user.id})")
    try:
        synced = await bot.tree.sync()
        print(f"🔄 {len(synced)} commande(s) slash synchronisée(s)")
    except Exception as e:
        print(f"❌ Erreur sync : {e}")
    check_news.start()
    check_results.start()

# ─────────────────────────────────────────
# Boucles automatiques
# ─────────────────────────────────────────
@tasks.loop(minutes=15)
async def check_news():
    await bot.wait_until_ready()
    if not VLR_CHANNEL_ID: return
    channel = bot.get_channel(VLR_CHANNEL_ID)
    if not channel: return
    for article in get_vlr_news(limit=15):
        url = article.get("url","")
        if not url or url in posted: continue
        date_str = article.get("date","")
        if "d ago" in date_str:
            try:
                if int(date_str.replace("d ago","").strip()) >= 3: continue
            except: pass
        posted.add(url)
        append_file("posted.txt", url)
        await channel.send(embed=make_vlr_embed(article))
        await asyncio.sleep(2)

@tasks.loop(minutes=5)
async def check_results():
    await bot.wait_until_ready()
    channel_id = MATCH_CHANNEL_ID or VLR_CHANNEL_ID
    if not channel_id: return
    channel = bot.get_channel(channel_id)
    if not channel: return
    for match in get_vlr_results():
        match_id = match.get("url","")
        if not match_id: continue
        if match.get("finished") and match_id not in notified_results:
            notified_results.add(match_id)
            append_file("results.txt", match_id)
            await channel.send(embed=make_result_embed(match))
            await asyncio.sleep(2)

# ─────────────────────────────────────────
# Commandes
# ─────────────────────────────────────────
@bot.tree.command(name="vlr", description="Affiche les dernières news Valorant depuis VLR.gg")
async def slash_vlr(interaction: discord.Interaction):
    await interaction.response.defer()
    articles = get_vlr_news(limit=5)
    if not articles:
        await interaction.followup.send("😕 Aucune news trouvée.")
        return
    for article in articles:
        await interaction.followup.send(embed=make_vlr_embed(article))

@bot.tree.command(name="match", description="Live 🔴 / Résultats ✅ / À venir 📅 avec filtres par région")
async def slash_match(interaction: discord.Interaction):
    await interaction.response.defer()
    data       = get_all_matches()
    start_page = 0 if data["live"] else (1 if data["results"] else 2)
    await interaction.followup.send(
        embed=build_match_embed(data, start_page, "ALL"),
        view=MatchView(data, start_page, "ALL"),
    )

@bot.tree.command(name="results", description="Récapitulatif des résultats du jour avec filtre région")
async def slash_results(interaction: discord.Interaction):
    await interaction.response.defer()
    data = get_all_matches()
    await interaction.followup.send(
        embed=build_match_embed(data, 1, "ALL"),
        view=MatchView(data, 1, "ALL"),
    )

@bot.tree.command(name="team", description="Roster, prochains matchs et résultats d'une équipe Valorant")
async def slash_team(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🔍 Recherche d'équipe",
        description="Sélectionne une équipe pour voir son roster, ses prochains matchs et ses résultats.",
        color=0xFF4655,
    )
    embed.set_thumbnail(url=VLR_LOGO)
    await interaction.response.send_message(embed=embed, view=TeamView())

class TeamSelect(discord.ui.Select):
    def __init__(self):
        options = [discord.SelectOption(label=name, value=tag) for name, tag in TEAMS.items()]
        super().__init__(placeholder="Choisis une équipe...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        team_tag  = self.values[0]
        team_name = next(k for k, v in TEAMS.items() if v == team_tag)
        try:
            headers   = {"User-Agent": "Mozilla/5.0"}
            search_r  = requests.get(f"https://www.vlr.gg/search/?q={team_tag}&type=teams", headers=headers, timeout=10)
            soup      = BeautifulSoup(search_r.text, "html.parser")
            team_link = soup.select_one("a.search-item")
            if not team_link:
                await interaction.followup.send(f"😕 Impossible de trouver **{team_name}**")
                return
            team_url  = "https://www.vlr.gg" + team_link.get("href","")
            team_page = requests.get(team_url, headers=headers, timeout=10)
            tsoup     = BeautifulSoup(team_page.text, "html.parser")

            logo_tag = tsoup.select_one(".team-header-logo img")
            logo_url = None
            if logo_tag:
                logo_url = logo_tag.get("src","")
                if logo_url.startswith("//"): logo_url = "https:" + logo_url

            players = []
            for player in tsoup.select(".team-roster-item")[:10]:
                alias = player.select_one(".team-roster-item-name-alias")
                real  = player.select_one(".team-roster-item-name-real")
                role  = player.select_one(".team-roster-item-name-role")
                if alias:
                    line = f"**{alias.get_text(strip=True)}**"
                    if real: line += f" — {real.get_text(strip=True)}"
                    if role: line += f" *({role.get_text(strip=True)})*"
                    players.append(line)

            past_matches = []
            for match in tsoup.select(".m-item")[:5]:
                teams = match.select(".m-item-team-name")
                score = match.select_one(".m-item-result")
                date  = match.select_one(".m-item-date")
                if teams and len(teams) >= 2:
                    t1 = teams[0].get_text(strip=True)
                    t2 = teams[1].get_text(strip=True)
                    sc = score.get_text(strip=True) if score else "vs"
                    dt = date.get_text(strip=True) if date else ""
                    past_matches.append(f"`{dt}` {t1} **{sc}** {t2}")

            upcoming_matches = []
            try:
                match_page = requests.get(team_url + "/matches", headers=headers, timeout=10)
                msoup      = BeautifulSoup(match_page.text, "html.parser")
                for match in msoup.select("a.wf-module-item")[:5]:
                    mteams = match.select(".match-item-vs-team-name")
                    time   = match.select_one(".match-item-time")
                    event  = match.select_one(".match-item-event")
                    if mteams and len(mteams) >= 2:
                        mt1   = mteams[0].get_text(strip=True)
                        mt2   = mteams[1].get_text(strip=True)
                        heure = time.get_text(strip=True) if time else "?"
                        ev    = event.get_text(strip=True) if event else ""
                        line  = f"🕐 `{heure}` — **{mt1}** vs **{mt2}**"
                        if ev: line += f"\n┗ *{ev}*"
                        upcoming_matches.append(line)
            except: pass

            embed = discord.Embed(title=f"🎮 {team_name}", url=team_url, color=0xFF4655)
            embed.set_author(name="VLR.gg", icon_url=VLR_LOGO)
            if logo_url: embed.set_thumbnail(url=logo_url)
            if players:          embed.add_field(name="👥 Roster",            value="\n".join(players),           inline=False)
            if upcoming_matches: embed.add_field(name="📆 Prochains matchs",  value="\n\n".join(upcoming_matches), inline=False)
            if past_matches:     embed.add_field(name="📊 Derniers résultats", value="\n".join(past_matches),      inline=False)
            embed.add_field(name="🔗 Page complète", value=f"[Voir sur VLR.gg]({team_url})", inline=False)
            embed.set_footer(text="Données récupérées depuis VLR.gg", icon_url=VLR_LOGO)
            await interaction.followup.send(embed=embed)
        except Exception as e:
            print(f"[TEAM] Erreur : {e}")
            await interaction.followup.send(f"❌ Erreur pour **{team_name}**.")

class TeamView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=60)
        self.add_item(TeamSelect())

@bot.tree.command(name="aide", description="Affiche l'aide du bot")
async def slash_aide(interaction: discord.Interaction):
    embed = discord.Embed(title="📰 Esport Actu — Aide", description="Toutes les commandes disponibles :", color=0xFF4655)
    embed.set_thumbnail(url=VLR_LOGO)
    embed.add_field(name="</vlr:0>",     value="Dernières news Valorant (traduites 🇫🇷)",                      inline=False)
    embed.add_field(name="</match:0>",   value="Live 🔴 / Résultats ✅ / À venir 📅 + filtre région",          inline=False)
    embed.add_field(name="</results:0>", value="Résultats du jour directement + filtre région",                 inline=False)
    embed.add_field(name="</team:0>",    value="Roster, prochains matchs & résultats d'une équipe",            inline=False)
    embed.add_field(name="</aide:0>",    value="Affiche ce message",                                           inline=False)
    embed.set_footer(text="Résultats envoyés automatiquement dès la fin d'un match • VLR.gg", icon_url=VLR_LOGO)
    await interaction.response.send_message(embed=embed)

bot.run(os.getenv("DISCORD_TOKEN"))
