# 🎲 Game manuals / Manuels des jeux

Printable manuals for the console games suggested in the kids' coding guide.
*Manuels imprimables des jeux console proposés dans le guide enfant.*

> ⚖️ This folder hosts only **original French manuals we wrote** (educational, see below)
> and **links** to the official manuals. We do **not** re-host third-party copyrighted
> booklets — follow the links to the official sources.
> *Ce dossier ne contient que nos **manuels FR maison** et des **liens** vers les manuels
> officiels (on ne ré-héberge pas les livrets copyrightés).*

## 📥 Official manuals (links / liens)

| Game | Manual |
|------|--------|
| **NetHack** *(free/libre)* | [Guidebook (PDF)](https://www.nethack.org/download/3.6.5/nethack-365-Guidebook.pdf) |
| **Dungeon Crawl Stone Soup** *(free/libre)* | [Quickstart](https://crawl.akrasiac.org/docs/quickstart.pdf) · [Full manual](https://crawl.akrasiac.org/docs/crawl_manual.txt) |
| **Dwarf Fortress** | [Quickstart guide (wiki)](https://dwarffortresswiki.org/Quickstart_guide) · FR : [dwarffortress.fr](https://www.dwarffortress.fr/) |
| **Zork I / II / III** | [The Infocom Documentation Project](https://infodoc.plover.net/manuals/) (`zork1.pdf`, `zork2.pdf`, `zork3.pdf`) |
| **Zork Nemesis** | [archive.org](https://archive.org/details/manual_Zork_Nemesis) |
| **Zork: Grand Inquisitor** | [mocagh.org](https://www.mocagh.org/activision/zorkgi-manual.pdf) |
| **Hunt the Wumpus** | [manual (mocagh)](https://www.mocagh.org/ti994a/huntwumpus-manual.pdf) · [rules (Wikipedia)](https://en.wikipedia.org/wiki/Hunt_the_Wumpus) |
| **Colossal Cave Adventure** | [maps & guide](https://rickadams.org/adventure/) |

## 🇫🇷 Our French manuals (here / ici)

Original French player manuals we wrote (the games stay in English — these explain how to
play in French, with a FR↔EN command glossary). Open the `.html` and print double-sided,
or run `weasyprint file.html file.pdf`.

- [`zork1-manuel-fr.html`](zork1-manuel-fr.html) — **Zork I** (texte)
- [`zork2-manuel-fr.html`](zork2-manuel-fr.html) — **Zork II** : Le Sorcier de Frobozz
- [`zork3-manuel-fr.html`](zork3-manuel-fr.html) — **Zork III** : Le Maître du Donjon
- [`zork-graphiques-manuel-fr.html`](zork-graphiques-manuel-fr.html) — **Zork Nemesis & Grand Inquisitor** (graphiques, souris/ScummVM)
- [`df-quickstart-fr.html`](df-quickstart-fr.html) — **Dwarf Fortress** : démarrage rapide
- [`00-garde.html`](00-garde.html) — page de garde + sommaire du classeur

## 🏰 Zork — text & graphical, with a fun "unlock"

- **Text Zork (I/II/III)** play in `frotz` (terminal): `frotz zork1.z5` …
- **Graphical Zork (Nemesis, Grand Inquisitor)** play with **ScummVM** fullscreen via cage:
  `cage -- scummvm`.
- 🔒 **Fun gentle gate** ([`../games/zork-graphique.sh`](../games/zork-graphique.sh)): the kid must
  **finish a text Zork first** to unlock installing the graphical ones — an adult gives the
  "Dungeon Master password" (default `XYZZY`, set yours in `/etc/kidcode/zork-unlock`).

> 🎮 You need the **game data** you own (CD / GOG) for Zork — these manuals/scripts don't include game files.
