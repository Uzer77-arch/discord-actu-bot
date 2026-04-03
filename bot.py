import discord
from discord.ext import commands, tasks
import asyncio
import os
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from datetime import datetime, timezone, timedelta
from scrapers.vlr import get_vlr_news, get_vlr_matches, get_vlr_results, get_all_matches

load_dotenv()

# ─────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

VLR_CHANNEL_ID   = int(os.getenv("VLR_CHANNEL_ID", 0))
MATCH_CHANNEL_ID = int(os.getenv("MATCH_CHANNEL_ID", 0))
VLR_LOGO         = "https://www.vlr.gg/img/vlr/logo_header.png"

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
# Pagination /match — construit l'embed selon la page
# ─────────────────────────────────────────
def build_match_embed(data: dict, page: int) -> discord.Embed:
    live     = data["live"]
    results  = data["results"]
    upcoming = data["upcoming"]

    ITEMS_PER_PAGE = 8

    if page == 0:
        # ── Page 1 : LIVE ────────────────────────────────────────
        embed = discord.Embed(
            title       = "🔴 Matchs en cours — LIVE",
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
        # ── Page 2 : Résultats du jour ───────────────────────────
        total_pages = max(1, -(-len(results) // ITEMS_PER_PAGE))
        embed = discord.Embed(
            title       = "✅ Résultats du jour",
            description = f"**{len(results)}** match(s) terminé(s) aujourd'hui",
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
        # ── Page 3+ : À venir (par tranches de 8) ────────────────
        idx_start = (page - 2) * ITEMS_PER_PAGE
        idx_end   = idx_start + ITEMS_PER_PAGE
        chunk     = upcoming[idx_start:idx_end]
        total_up  = max(1, -(-len(upcoming) // ITEMS_PER_PAGE))

        embed = discord.Embed(
            title       = f"📅 Matchs à venir — Semaine ({page - 1}/{total_up})",
            description = f"**{len(upcoming)}** match(s) prévus",
            color       = 0xFF4655,
        )
        if chunk:
            # Groupe par date
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
        else:
            embed.description = "Aucun match prévu pour cette période."

    embed.set_author(name="VLR.gg — Calendrier", icon_url=VLR_LOGO)
    embed.set_thumbnail(url=VLR_LOGO)

    # Indicateur de page
    total_pages = 2 + max(1, -(-len(upcoming) // ITEMS_PER_PAGE))
    embed.set_footer(
        text=f"Page {page + 1}/{total_pages} • VLR.gg",
        icon_url=VLR_LOGO,
    )
    return embed

def get_total_pages(data: dict) -> int:
    ITEMS_PER_PAGE = 8
    upcoming_pages = max(1, -(-len(data["upcoming"]) // ITEMS_PER_PAGE))
    return 2 + upcoming_pages  # page LIVE + page résultats + pages upcoming

# ─────────────────────────────────────────
# Vue avec boutons de pagination
# ─────────────────────────────────────────
class MatchPaginationView(discord.ui.View):
    def __init__(self, data: dict, page: int = 0):
        super().__init__(timeout=120)
        self.data        = data
        self.page        = page
        self.total_pages = get_total_pages(data)
        self._update_buttons()

    def _update_buttons(self):
        self.prev_btn.disabled = self.page == 0
        self.next_btn.disabled = self.page >= self.total_pages - 1
        # Labels dynamiques
        if self.page == 0:
            self.next_btn.label = "Résultats ▶"
        elif self.page == 1:
            self.prev_btn.label = "◀ Live"
            self.next_btn.label = "À venir ▶"
        else:
            self.prev_btn.label = "◀ Précédent"
            self.next_btn.label = "Suivant ▶" if self.page < self.total_pages - 1 else "Suivant ▶"

    @discord.ui.button(label="◀ Précédent", style=discord.ButtonStyle.secondary, disabled=True)
    async def prev_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page -= 1
        self._update_buttons()
        await interaction.response.edit_message(
            embed=build_match_embed(self.data, self.page),
            view=self,
        )

    @discord.ui.button(label="Résultats ▶", style=discord.ButtonStyle.primary)
    async def next_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page += 1
        self._update_buttons()
        await interaction.response.edit_message(
            embed=build_match_embed(self.data, self.page),
            view=self,
        )

    @discord.ui.button(label="🔄 Actualiser", style=discord.ButtonStyle.success)
    async def refresh_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        self.data        = get_all_matches()
        self.total_pages = get_total_pages(self.data)
        self.page        = min(self.page, self.total_pages - 1)
        self._update_buttons()
        await interaction.edit_original_response(
            embed=build_match_embed(self.data, self.page),
            view=self,
        )

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
# Boucle news — toutes les 15 min
# ─────────────────────────────────────────
@tasks.loop(minutes=15)
async def check_news():
    await bot.wait_until_ready()
    if not VLR_CHANNEL_ID: return
    channel = bot.get_channel(VLR_CHANNEL_ID)
    if not channel: return
    articles = get_vlr_news(limit=15)
    for article in articles:
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

# ─────────────────────────────────────────
# Boucle résultats — toutes les 5 min
# ─────────────────────────────────────────
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
# /vlr
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

# ─────────────────────────────────────────
# /match — avec pagination
# ─────────────────────────────────────────
@bot.tree.command(name="match", description="Matchs en cours, résultats du jour et à venir (avec navigation)")
async def slash_match(interaction: discord.Interaction):
    await interaction.response.defer()
    data = get_all_matches()
    # Démarre sur la page LIVE si des matchs sont en cours, sinon résultats
    start_page = 0 if data["live"] else (1 if data["results"] else 2)
    embed = build_match_embed(data, start_page)
    view  = MatchPaginationView(data, start_page)
    await interaction.followup.send(embed=embed, view=view)

# ─────────────────────────────────────────
# /results
# ─────────────────────────────────────────
@bot.tree.command(name="results", description="Récapitulatif de tous les résultats Valorant du jour")
async def slash_results(interaction: discord.Interaction):
    await interaction.response.defer()
    finished = get_vlr_results()
    if not finished:
        await interaction.followup.send("😕 Aucun résultat disponible pour aujourd'hui.")
        return
    embed = discord.Embed(
        title       = "🏆 Résultats du jour — Valorant",
        description = f"**{len(finished)}** match(s) terminé(s) aujourd'hui",
        color       = 0xFF4655,
    )
    embed.set_author(name="VLR.gg — Résultats", icon_url=VLR_LOGO)
    embed.set_thumbnail(url=VLR_LOGO)
    by_event = {}
    for m in finished:
        ev = m.get("event","Autre") or "Autre"
        by_event.setdefault(ev, []).append(m)
    for ev, ms in by_event.items():
        lines = []
        for m in ms:
            t1, t2, score = m["team1"], m["team2"], m.get("score","?")
            url = m.get("url","")
            try:
                s1, s2 = score.split(" - ")
                winner = t1 if int(s1) > int(s2) else t2
                lines.append(f"🏆 [{t1} **{score}** {t2}]({url}) — *{winner} gagne*")
            except:
                lines.append(f"[{t1} **{score}** {t2}]({url})")
        embed.add_field(name=f"🎯 {ev}", value="\n".join(lines), inline=False)
    now = datetime.now().strftime("%d/%m/%Y à %H:%M")
    embed.set_footer(text=f"Mis à jour le {now} • VLR.gg", icon_url=VLR_LOGO)
    await interaction.followup.send(embed=embed)

# ─────────────────────────────────────────
# /team avec menu déroulant
# ─────────────────────────────────────────
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
                await interaction.followup.send(f"😕 Impossible de trouver **{team_name}** sur VLR.gg")
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
                    time   = match.select_one(".match-item-time") or match.select_one(".moment-tz-convert")
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
            if players:           embed.add_field(name="👥 Roster",           value="\n".join(players),           inline=False)
            if upcoming_matches:  embed.add_field(name="📆 Prochains matchs", value="\n\n".join(upcoming_matches), inline=False)
            if past_matches:      embed.add_field(name="📊 Derniers résultats",value="\n".join(past_matches),      inline=False)
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

@bot.tree.command(name="team", description="Roster, prochains matchs et résultats d'une équipe Valorant")
async def slash_team(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🔍 Recherche d'équipe",
        description="Sélectionne une équipe pour voir son roster, ses prochains matchs et ses résultats.",
        color=0xFF4655,
    )
    embed.set_thumbnail(url=VLR_LOGO)
    await interaction.response.send_message(embed=embed, view=TeamView())

# ─────────────────────────────────────────
# /aide
# ─────────────────────────────────────────
@bot.tree.command(name="aide", description="Affiche l'aide du bot")
async def slash_aide(interaction: discord.Interaction):
    embed = discord.Embed(title="📰 Esport Actu — Aide", description="Toutes les commandes disponibles :", color=0xFF4655)
    embed.set_thumbnail(url=VLR_LOGO)
    embed.add_field(name="</vlr:0>",     value="Dernières news Valorant (traduites 🇫🇷)",                    inline=False)
    embed.add_field(name="</match:0>",   value="Live 🔴 / Résultats ✅ / À venir 📅 avec navigation ◀▶",    inline=False)
    embed.add_field(name="</results:0>", value="Récapitulatif complet des résultats du jour",                inline=False)
    embed.add_field(name="</team:0>",    value="Roster, prochains matchs & résultats d'une équipe",         inline=False)
    embed.add_field(name="</aide:0>",    value="Affiche ce message",                                        inline=False)
    embed.set_footer(text="Résultats envoyés automatiquement dès la fin d'un match • VLR.gg", icon_url=VLR_LOGO)
    await interaction.response.send_message(embed=embed)

bot.run(os.getenv("DISCORD_TOKEN"))
