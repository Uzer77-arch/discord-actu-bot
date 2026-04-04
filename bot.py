import discord
from discord.ext import commands, tasks
import asyncio
import os
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from datetime import datetime
from scrapers.vlr import get_vlr_news, get_vlr_results, get_all_matches

load_dotenv()

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

VLR_CHANNEL_ID   = int(os.getenv("VLR_CHANNEL_ID", 0))
MATCH_CHANNEL_ID = int(os.getenv("MATCH_CHANNEL_ID", 0))
VLR_LOGO         = "https://www.vlr.gg/img/vlr/logo_header.png"

REGIONS = {
    "ALL":     "🌍 Toutes les régions",
    "EMEA":    "🇪🇺 EMEA",
    "NA":      "🇺🇸 NA",
    "PACIFIC": "🌏 Pacific",
    "CHINA":   "🇨🇳 China",
    "BR":      "🇧🇷 LATAM",
}

ITEMS_PER_PAGE = 8

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

TEAMS_BY_REGION = {
    "EMEA": {
        "Team Vitality":  "team-vitality",
        "Team Liquid":    "team-liquid",
        "Fnatic":         "fnatic",
        "NaVi":           "natus-vincere",
        "BBL Esports":    "bbl-esports",
        "G2 Esports":     "g2-esports",
        "Gentle Mates":   "gentle-mates",
        "FUT Esports":    "fut-esports",
        "GIANTX":         "giantx",
        "KOI":            "koi",
    },
    "NA": {
        "Sentinels":      "sentinels",
        "Cloud9":         "cloud9",
        "100 Thieves":    "100-thieves",
        "NRG":            "nrg",
        "Evil Geniuses":  "evil-geniuses",
        "LOUD":           "loud",
        "FURIA":          "furia",
        "MIBR":           "mibr",
        "Leviatán":       "leviatan",
        "KRÜ Esports":    "kru-esports",
    },
    "PACIFIC": {
        "Paper Rex":      "paper-rex",
        "T1":             "t1",
        "Gen.G":          "gen-g",
        "DRX":            "drx",
        "ZETA DIVISION":  "zeta-division",
        "Global Esports": "global-esports",
        "Talon Esports":  "talon-esports",
        "Rex Regum Qeon": "rex-regum-qeon",
        "Team Secret":    "team-secret",
        "DetonatioN FM":  "detonation-focusme",
    },
    "CHINA": {
        "EDward Gaming":  "edward-gaming",
        "Bilibili Gaming":"bilibili-gaming",
        "FunPlus Phoenix":"funplus-phoenix",
        "Nova Esports":   "nova-esports",
        "Wolves Esports": "wolves-esports",
        "Dragon Ranger":  "dragon-ranger-gaming",
        "Trace Esports":  "trace-esports",
        "TYLOO":          "tyloo",
    },
    "BR": {
        "LOUD":           "loud",
        "FURIA":          "furia",
        "MIBR":           "mibr",
        "Leviatán":       "leviatan",
        "KRÜ Esports":    "kru-esports",
        "9z Team":        "9z-team",
        "Sentinels":      "sentinels",
        "100 Thieves":    "100-thieves",
    },
}

REGION_LABELS = {
    "EMEA":    "🇪🇺 EMEA",
    "NA":      "🇺🇸 NA / AMER",
    "PACIFIC": "🌏 Pacific",
    "CHINA":   "🇨🇳 China",
    "BR":      "🇧🇷 LATAM",
}

# ─────────────────────────────────────────
# /team — Étape 1 : choix région
# ─────────────────────────────────────────
async def fetch_team_info(interaction, team_tag, team_name):
    """Scrape et affiche les infos d'une équipe."""
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
        if logo_url:         embed.set_thumbnail(url=logo_url)
        if players:          embed.add_field(name="👥 Roster",            value="\n".join(players),           inline=False)
        if upcoming_matches: embed.add_field(name="📆 Prochains matchs",  value="\n\n".join(upcoming_matches), inline=False)
        if past_matches:     embed.add_field(name="📊 Derniers résultats", value="\n".join(past_matches),      inline=False)
        embed.add_field(name="🔗 Page complète", value=f"[Voir sur VLR.gg]({team_url})", inline=False)
        embed.set_footer(text="Données récupérées depuis VLR.gg", icon_url=VLR_LOGO)
        await interaction.followup.send(embed=embed)
    except Exception as e:
        print(f"[TEAM] Erreur : {e}")
        await interaction.followup.send(f"❌ Erreur pour **{team_name}**.")


class TeamSelectByRegion(discord.ui.Select):
    """Étape 2 : sélection de l'équipe dans la région choisie."""
    def __init__(self, region: str):
        teams = TEAMS_BY_REGION.get(region, {})
        options = [discord.SelectOption(label=name, value=tag) for name, tag in teams.items()]
        super().__init__(
            placeholder=f"Choisis une équipe {REGION_LABELS.get(region,'')}...",
            min_values=1, max_values=1, options=options, row=1,
        )
        self.region = region
        self.teams  = teams

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        team_tag  = self.values[0]
        team_name = next((k for k, v in self.teams.items() if v == team_tag), team_tag)
        await fetch_team_info(interaction, team_tag, team_name)


class RegionSelect(discord.ui.Select):
    """Étape 1 : sélection de la région."""
    def __init__(self):
        options = [
            discord.SelectOption(label=label, value=key)
            for key, label in REGION_LABELS.items()
        ]
        super().__init__(
            placeholder="1️⃣ Choisis d'abord une région...",
            min_values=1, max_values=1, options=options, row=0,
        )

    async def callback(self, interaction: discord.Interaction):
        region = self.values[0]
        # Met à jour la vue avec le menu équipes
        view = TeamRegionView(region)
        embed = discord.Embed(
            title       = f"🔍 Équipes — {REGION_LABELS[region]}",
            description = "2️⃣ Maintenant choisis une équipe dans le menu ci-dessous.",
            color       = 0xFF4655,
        )
        embed.set_thumbnail(url=VLR_LOGO)
        await interaction.response.edit_message(embed=embed, view=view)


class TeamRegionView(discord.ui.View):
    """Vue avec les deux menus : région + équipes."""
    def __init__(self, region: str = None):
        super().__init__(timeout=120)
        self.add_item(RegionSelect())
        if region:
            self.add_item(TeamSelectByRegion(region))


@bot.tree.command(name="team", description="Roster, prochains matchs et résultats d'une équipe Valorant")
async def slash_team(interaction: discord.Interaction):
    embed = discord.Embed(
        title       = "🔍 Recherche d'équipe",
        description = "1️⃣ Commence par choisir une **région** dans le menu ci-dessous.",
        color       = 0xFF4655,
    )
    embed.set_thumbnail(url=VLR_LOGO)
    await interaction.response.send_message(embed=embed, view=TeamRegionView())

@bot.tree.command(name="aide", description="Affiche l'aide du bot")
async def slash_aide(interaction: discord.Interaction):
    embed = discord.Embed(title="📰 Esport Actu — Aide", description="Toutes les commandes disponibles :", color=0xFF4655)
    embed.set_thumbnail(url=VLR_LOGO)
    embed.add_field(name="</vlr:0>",     value="Dernières news Valorant (traduites 🇫🇷)",             inline=False)
    embed.add_field(name="</match:0>",   value="Live 🔴 / Résultats ✅ / À venir 📅 + menu région",  inline=False)
    embed.add_field(name="</results:0>", value="Résultats du jour + menu région",                     inline=False)
    embed.add_field(name="</team:0>",    value="Roster, prochains matchs & résultats d'une équipe",   inline=False)
    embed.add_field(name="</aide:0>",    value="Affiche ce message",                                  inline=False)
    embed.set_footer(text="Résultats envoyés automatiquement dès la fin d'un match • VLR.gg", icon_url=VLR_LOGO)
    await interaction.response.send_message(embed=embed)

bot.run(os.getenv("DISCORD_TOKEN"))
