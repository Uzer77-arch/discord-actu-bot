import discord
from discord.ext import commands, tasks
from discord import app_commands
import asyncio
import os
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from datetime import datetime, timezone, timedelta
from scrapers.vlr import get_vlr_news, get_vlr_matches

load_dotenv()

# ─────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

VLR_CHANNEL_ID   = int(os.getenv("VLR_CHANNEL_ID", 0))
MATCH_CHANNEL_ID = int(os.getenv("MATCH_CHANNEL_ID", 0))

VLR_LOGO = "https://www.vlr.gg/img/vlr/logo_header.png"

# ─────────────────────────────────────────
# Persistance (évite les doublons au redémarrage)
# ─────────────────────────────────────────
def load_file(path: str) -> set:
    if not os.path.exists(path):
        return set()
    with open(path, "r") as f:
        return set(line.strip() for line in f if line.strip())

def append_file(path: str, value: str):
    with open(path, "a") as f:
        f.write(value + "\n")

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
def translate_to_french(text: str) -> str:
    if not text:
        return text
    try:
        r = requests.get(
            "https://translate.googleapis.com/translate_a/single",
            params={"client": "gtx", "sl": "auto", "tl": "fr", "dt": "t", "q": text},
            timeout=5,
        )
        data = r.json()
        return "".join(p[0] for p in data[0] if p[0]) or text
    except:
        return text

# ─────────────────────────────────────────
# Embeds
# ─────────────────────────────────────────
def make_vlr_embed(article: dict) -> discord.Embed:
    title = translate_to_french(article.get("title", "Sans titre"))
    desc  = article.get("description", "")
    desc  = translate_to_french(desc) if desc else "Clique sur le titre pour lire l'article complet."
    embed = discord.Embed(title=title, url=article.get("url", ""), description=desc, color=0xFF4655)
    embed.set_author(name="VLR.gg — Valorant Esport", icon_url=VLR_LOGO)
    if article.get("image"):
        embed.set_thumbnail(url=article["image"])
    if article.get("date"):
        embed.set_footer(text=f"📅 {article['date']}", icon_url=VLR_LOGO)
    return embed

def make_result_embed(match: dict) -> discord.Embed:
    t1    = match.get("team1", "?")
    t2    = match.get("team2", "?")
    score = match.get("score", "?")
    event = match.get("event", "")
    url   = match.get("url", "")

    # Détermine le gagnant pour mettre en avant
    try:
        s1, s2 = score.split(" - ")
        if int(s1) > int(s2):
            result_line = f"🏆 **{t1}** remporte le match !"
        elif int(s2) > int(s1):
            result_line = f"🏆 **{t2}** remporte le match !"
        else:
            result_line = "Match nul"
    except:
        result_line = ""

    embed = discord.Embed(
        title       = f"📣 Résultat : {t1} vs {t2}",
        url         = url,
        description = f"**{t1}  {score}  {t2}**\n{result_line}",
        color       = 0xFF4655,
    )
    embed.set_author(name="VLR.gg — Résultats", icon_url=VLR_LOGO)
    if event:
        embed.add_field(name="🎯 Événement", value=event, inline=False)
    embed.set_footer(text="Résultat Valorant Pro • VLR.gg", icon_url=VLR_LOGO)
    return embed

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
    if not VLR_CHANNEL_ID:
        return
    channel = bot.get_channel(VLR_CHANNEL_ID)
    if not channel:
        return

    articles = get_vlr_news(limit=15)
    for article in articles:
        url = article.get("url", "")
        if not url or url in posted:
            continue
        date_str = article.get("date", "")
        if "d ago" in date_str:
            try:
                if int(date_str.replace("d ago", "").strip()) >= 3:
                    continue
            except:
                pass
        posted.add(url)
        append_file("posted.txt", url)
        await channel.send(embed=make_vlr_embed(article))
        await asyncio.sleep(2)

# ─────────────────────────────────────────
# Boucle résultats — toutes les 5 min
# Envoie automatiquement dans MATCH_CHANNEL
# ─────────────────────────────────────────
@tasks.loop(minutes=5)
async def check_results():
    await bot.wait_until_ready()
    channel_id = MATCH_CHANNEL_ID or VLR_CHANNEL_ID
    if not channel_id:
        return
    channel = bot.get_channel(channel_id)
    if not channel:
        return

    matches = get_vlr_matches()
    for match in matches:
        match_id = match.get("url", "")
        if not match_id:
            continue
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
# /match — matchs du jour
# ─────────────────────────────────────────
@bot.tree.command(name="match", description="Affiche les matchs Valorant du jour avec les horaires")
async def slash_match(interaction: discord.Interaction):
    await interaction.response.defer()
    matches = get_vlr_matches()

    if not matches:
        await interaction.followup.send("😕 Aucun match trouvé pour aujourd'hui.")
        return

    embed = discord.Embed(
        title       = "📅 Matchs Valorant du jour",
        description = "Horaires en heure locale",
        color       = 0xFF4655,
    )
    embed.set_author(name="VLR.gg — Calendrier", icon_url=VLR_LOGO)
    embed.set_thumbnail(url=VLR_LOGO)

    upcoming = [m for m in matches if not m.get("finished")]
    finished = [m for m in matches if m.get("finished")]

    if upcoming:
        lines = []
        for m in upcoming[:10]:
            line = f"🕐 `{m.get('time', '?')}` — **{m.get('team1','?')}** vs **{m.get('team2','?')}**"
            if m.get("event"):
                line += f"\n┗ *{m['event']}*"
            lines.append(line)
        embed.add_field(name="⏳ À venir", value="\n\n".join(lines), inline=False)

    if finished:
        lines = []
        for m in finished[:10]:
            lines.append(f"✅ **{m.get('team1','?')}** {m.get('score','?')} **{m.get('team2','?')}** — *{m.get('event','')}*")
        embed.add_field(name="✔️ Terminés", value="\n".join(lines), inline=False)

    embed.set_footer(text="Mis à jour en temps réel • VLR.gg", icon_url=VLR_LOGO)
    await interaction.followup.send(embed=embed)

# ─────────────────────────────────────────
# /results — récapitulatif des résultats du jour
# ─────────────────────────────────────────
@bot.tree.command(name="results", description="Récapitulatif de tous les résultats Valorant du jour")
async def slash_results(interaction: discord.Interaction):
    await interaction.response.defer()
    matches  = get_vlr_matches()
    finished = [m for m in matches if m.get("finished")]

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

    # Groupe les résultats par événement
    by_event: dict = {}
    for m in finished:
        event = m.get("event", "Autre") or "Autre"
        by_event.setdefault(event, []).append(m)

    for event, event_matches in by_event.items():
        lines = []
        for m in event_matches:
            t1    = m.get("team1", "?")
            t2    = m.get("team2", "?")
            score = m.get("score", "?")
            url   = m.get("url", "")
            # Détermine le gagnant
            try:
                s1, s2 = score.split(" - ")
                winner = t1 if int(s1) > int(s2) else t2
                line   = f"🏆 [{t1} **{score}** {t2}]({url}) — *{winner} gagne*"
            except:
                line = f"[{t1} **{score}** {t2}]({url})"
            lines.append(line)
        embed.add_field(
            name  = f"🎯 {event}",
            value = "\n".join(lines),
            inline= False,
        )

    now = datetime.now().strftime("%d/%m/%Y à %H:%M")
    embed.set_footer(text=f"Mis à jour le {now} • VLR.gg", icon_url=VLR_LOGO)
    await interaction.followup.send(embed=embed)

# ─────────────────────────────────────────
# /team avec menu déroulant + prochains matchs
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

            team_url  = "https://www.vlr.gg" + team_link.get("href", "")
            team_page = requests.get(team_url, headers=headers, timeout=10)
            tsoup     = BeautifulSoup(team_page.text, "html.parser")

            logo_tag = tsoup.select_one(".team-header-logo img")
            logo_url = None
            if logo_tag:
                logo_url = logo_tag.get("src", "")
                if logo_url.startswith("//"):
                    logo_url = "https:" + logo_url

            players = []
            for player in tsoup.select(".team-roster-item")[:10]:
                alias = player.select_one(".team-roster-item-name-alias")
                real  = player.select_one(".team-roster-item-name-real")
                role  = player.select_one(".team-roster-item-name-role")
                if alias:
                    line = f"**{alias.get_text(strip=True)}**"
                    if real:  line += f" — {real.get_text(strip=True)}"
                    if role:  line += f" *({role.get_text(strip=True)})*"
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
                    teams = match.select(".match-item-vs-team-name")
                    time  = match.select_one(".match-item-time") or match.select_one(".moment-tz-convert")
                    event = match.select_one(".match-item-event")
                    if teams and len(teams) >= 2:
                        t1    = teams[0].get_text(strip=True)
                        t2    = teams[1].get_text(strip=True)
                        heure = time.get_text(strip=True) if time else "?"
                        ev    = event.get_text(strip=True) if event else ""
                        line  = f"🕐 `{heure}` — **{t1}** vs **{t2}**"
                        if ev: line += f"\n┗ *{ev}*"
                        upcoming_matches.append(line)
            except:
                pass

            embed = discord.Embed(title=f"🎮 {team_name}", url=team_url, color=0xFF4655)
            embed.set_author(name="VLR.gg", icon_url=VLR_LOGO)
            if logo_url:
                embed.set_thumbnail(url=logo_url)
            if players:
                embed.add_field(name="👥 Roster", value="\n".join(players), inline=False)
            if upcoming_matches:
                embed.add_field(name="📆 Prochains matchs", value="\n\n".join(upcoming_matches), inline=False)
            if past_matches:
                embed.add_field(name="📊 Derniers résultats", value="\n".join(past_matches), inline=False)
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
    embed.add_field(name="</vlr:0>",     value="Dernières news Valorant (traduites 🇫🇷)",             inline=False)
    embed.add_field(name="</match:0>",   value="Matchs du jour avec horaires",                        inline=False)
    embed.add_field(name="</results:0>", value="Récapitulatif de tous les résultats du jour",         inline=False)
    embed.add_field(name="</team:0>",    value="Roster, prochains matchs & résultats d'une équipe",   inline=False)
    embed.add_field(name="</aide:0>",    value="Affiche ce message",                                  inline=False)
    embed.set_footer(text="Résultats envoyés automatiquement dès la fin d'un match • VLR.gg", icon_url=VLR_LOGO)
    await interaction.response.send_message(embed=embed)

bot.run(os.getenv("DISCORD_TOKEN"))
