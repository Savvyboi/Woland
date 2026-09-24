// Interface strings in English, Finnish and Swedish.
// Keys used in HTML via data-i18n="key" (text) or data-i18n-attr="attr:key;attr:key".

export const LANGS = { en: "English", fi: "Suomi", sv: "Svenska" };
export const LOCALES = { en: "en-GB", fi: "fi-FI", sv: "sv-SE" };

const S = {
  en: {
    "site.tagline": "A chronicle of the Russian state press",
    "nav.today": "Today", "nav.narratives": "Narratives", "nav.archive": "Archive", "nav.outlets": "Outlets", "nav.method": "Method",
    "theme.toggle": "Switch between night and day", "theme.night": "Night", "theme.day": "Day",
    "lang.label": "Language", "skip": "Skip to content", "chapter": "Chapter",
    "epigraph.cite": "— M. Bulgakov, The Master and Margarita",
    "plate": "Plate", "table.show": "Table", "table.hide": "Chart",
    "loading": "Consulting the archive",
    "error.load": "The archive could not be read. Please try again later.",
    "empty.nodata": "No articles have been collected yet. The first collection runs are under way.",
    "group.state": "State core", "group.official": "Official line", "group.mass": "Mass press",
    "group.foreign": "Foreign-facing", "group.hardline": "Hardline",
    "lang.ru": "Russian-language", "lang.en": "English-language",
    "series.all": "All outlets", "series.daily": "Daily share", "series.avg7": "7-day average",
    "unit.articles": "articles", "unit.article": "article",

    "today.title": "Black Magic and Its Exposure",
    "today.epigraph": "To speak the truth is easy and pleasant.",
    "today.lede": "On {day}, the monitored press published {total} articles from {outlets} outlets. {framed} of them invoked at least one of the propaganda framings Woland follows.",
    "today.lede.rising": "Against the previous {n} days, the framings gaining most ground were {list}.",
    "today.lede.norising": "There is not yet enough history (at least a week) to say which framings are rising.",
    "today.tiles.articles": "Articles collected", "today.tiles.outlets": "Outlets publishing",
    "today.tiles.framed": "Invoke a propaganda framing", "today.tiles.top": "Most-used framing",
    "today.narratives": "The day's framings",
    "today.narratives.hint": "Share of all articles that day · change against the average of the previous days (up to 28)",
    "today.topics": "Topics in the news",
    "col.framing": "Framing", "col.topic": "Topic", "col.articles": "Articles", "col.share": "Share",
    "col.change": "vs. {n} days", "col.change0": "Change", "col.trend": "30 days",
    "today.examples": "Examples", "today.more": "All {n} articles in the archive →",
    "today.rising": "Rising words",
    "today.rising.hint": "Headline words used far more often than in the previous 14 days",
    "today.rising.ru": "Russian-language outlets", "today.rising.en": "English-language outlets",
    "today.rising.explain": "{n} headlines, usually {base} a day",
    "today.rising.none": "Nothing unusual — or not enough history yet.",
    "today.volume": "Who published what", "today.volume.hint": "Articles per outlet on this day",
    "today.prev": "← Previous day", "today.next": "Next day →", "today.latest": "Latest day",
    "today.new": "new", "today.partial": "Collection for this day is still in progress.",

    "narratives.title": "There Were Doings at Griboyedov's",
    "narratives.epigraph": "A fact is the most stubborn thing in the world.",
    "narratives.framings": "Framings", "narratives.topics": "Topics",
    "range.label": "Period", "range.7": "7 days", "range.30": "30 days", "range.90": "90 days", "range.all": "All",
    "narratives.share": "Share of articles invoking {name}",
    "narratives.share.sub": "All outlets. Dots: daily share. Line: 7-day average.",
    "narratives.groups": "By type of outlet",
    "narratives.groups.sub": "Each panel: that group's daily share (gold) against all outlets (grey)",
    "narratives.audience": "At home and abroad",
    "narratives.audience.sub": "Russian-language outlets against English-language, foreign-facing outlets (7-day averages)",
    "narratives.heat": "Outlet by day", "narratives.heat.sub": "Share of each outlet's articles that invoke it",
    "narratives.byoutlet": "Who uses it most", "narratives.byoutlet.sub": "Share of each outlet's articles over the period",
    "narratives.examples": "Recent examples",
    "narratives.definition": "How Woland recognises it",
    "narratives.patterns.ru": "Russian patterns", "narratives.patterns.en": "English patterns",
    "narratives.patterns.note": "* stands for any ending. Checked in the headline, the lead and — where Woland can read the page — the full text.",
    "narratives.total": "{n} articles in the period",

    "archive.title": "Manuscripts Don't Burn",
    "archive.epigraph": "Manuscripts don't burn.",
    "archive.placeholder": "Search headlines and leads: нацисты, провокация, Finland…",
    "archive.go": "Search",
    "archive.syntax": "Every word you type must appear, in any grammatical form. Add * for any ending (нацист*), put - before a word to exclude it, and write OR between alternatives. English searches also cover the machine-translated Russian headlines.",
    "archive.from": "From", "archive.to": "To", "archive.outlets": "Outlets", "archive.alloutlets": "All outlets",
    "archive.language": "Language", "archive.alllangs": "All languages",
    "archive.narrative": "Framing or topic", "archive.any": "Any",
    "archive.sort": "Order", "archive.sort.new": "Newest first", "archive.sort.old": "Oldest first",
    "archive.results": "{n} articles", "archive.results.one": "1 article",
    "archive.idle": "Search the whole archive since {start}, or browse with the filters alone.",
    "archive.searching": "Searching the archive",
    "archive.none": "Nothing found. Try fewer words, or put * after a word stem.",
    "archive.timeline": "When it was said", "archive.timeline.sub": "Matching articles per day",
    "archive.count": "Count", "archive.share": "Share of all articles",
    "archive.byoutlet": "Where it was said",
    "archive.export": "Export CSV", "archive.export.note": "first {n}",
    "archive.more": "Show more", "archive.minchars": "Put at least 4 letters before a *",
    "archive.clear": "Clear",

    "article.original": "Original", "article.archive": "Archived copy", "article.cite": "Cite",
    "article.translate": "Translate page", "article.eu": "Blocked in the EU", "article.mt": "MT",
    "article.mt.title": "Machine translation", "article.body": "In the text", "article.feed": "feed only",
    "article.listed": "headline only",
    "article.listed.title": "So far Woland has only the headline from the outlet's own listing; it will try to read the page again.",
    "cite.title": "Cite this article", "cite.record": "Woland record", "cite.copy": "Copy", "cite.copied": "Copied",
    "cite.close": "Close", "cite.retrieved": "Retrieved by Woland on {date}", "cite.fingerprint": "content fingerprint",
    "cite.note": "Original links may be blocked in the EU. The Internet Archive link opens the nearest archived copy.",

    "outlets.title": "Satan's Great Ball",
    "outlets.epigraph": "Never talk to strangers.",
    "outlets.lede": "The guests at this ball: {n} outlets of the Russian state and pro-Kremlin press, in five groups. For each, who owns it, how Woland reads it, and what it tends to say.",
    "outlets.articles": "articles", "outlets.perday": "a day", "outlets.since": "since",
    "outlets.method.page": "Every article page is read", "outlets.method.feed": "Headlines from its own feed only",
    "outlets.method.feedtext": "Full texts from its own feed",
    "outlets.top": "Leans on", "outlets.top.hint": "framings it uses more than the press as a whole",
    "outlets.coverage": "Collection, last 21 days",
    "cov.c": "Complete", "cov.p": "Partial", "cov.f": "Feed only", "cov.m": "Missing",
    "outlets.health": "Recent collection runs", "health.when": "When", "health.mode": "Run",
    "health.new": "New articles", "health.problems": "Problems", "health.none": "none",
    "mode.daily": "Daily", "mode.poll": "Hourly feeds", "mode.backfill": "Backfill",
    "outlets.disabled": "Not collected",

    "method.title": "Epilogue", "method.epigraph": "No document, no person.",

    "footer.about": "Woland reads the Russian state and pro-Kremlin press every day and records what it says: headlines, leads, and the propaganda framings they invoke. It is made for researchers, journalists and activists.",
    "footer.updated": "Last updated {date}", "footer.data": "Data and code on GitHub",
    "footer.license": "Code: MIT. Woland's data: CC BY 4.0. Headlines and excerpts remain the property of their publishers and are quoted for research and reporting.",
    "footer.motto": "Manuscripts don't burn.",
  },

  fi: {
    "site.tagline": "Venäjän valtiollisen lehdistön kronikka",
    "nav.today": "Tänään", "nav.narratives": "Narratiivit", "nav.archive": "Arkisto", "nav.outlets": "Mediat", "nav.method": "Menetelmä",
    "theme.toggle": "Vaihda yön ja päivän välillä", "theme.night": "Yö", "theme.day": "Päivä",
    "lang.label": "Kieli", "skip": "Siirry sisältöön", "chapter": "Luku",
    "epigraph.cite": "— M. Bulgakov, Saatana saapuu Moskovaan",
    "plate": "Kuva", "table.show": "Taulukko", "table.hide": "Kaavio",
    "loading": "Arkistoa luetaan",
    "error.load": "Arkistoa ei voitu lukea. Yritä myöhemmin uudelleen.",
    "empty.nodata": "Artikkeleita ei ole vielä kerätty. Ensimmäiset keruuajot ovat käynnissä.",
    "group.state": "Valtiollinen ydin", "group.official": "Virallinen linja", "group.mass": "Joukkolehdistö",
    "group.foreign": "Ulkomaille suunnatut", "group.hardline": "Kovan linjan mediat",
    "lang.ru": "Venäjänkieliset", "lang.en": "Englanninkieliset",
    "series.all": "Kaikki mediat", "series.daily": "Päivittäinen osuus", "series.avg7": "7 päivän keskiarvo",
    "unit.articles": "artikkelia", "unit.article": "artikkeli",

    "today.title": "Musta magia ja sen paljastaminen",
    "today.epigraph": "Totuuden puhuminen on helppoa ja miellyttävää.",
    "today.lede": "Päivänä {day} seuratut mediat julkaisivat {total} artikkelia {outlets} eri mediassa. Niistä {framed} käytti vähintään yhtä Wolandin seuraamaa propagandanarratiivia.",
    "today.lede.rising": "Edellisiin {n} päivään verrattuna eniten kasvoivat {list}.",
    "today.lede.norising": "Historiaa ei ole vielä tarpeeksi (vähintään viikko), jotta voisi sanoa, mitkä narratiivit ovat nousussa.",
    "today.tiles.articles": "Kerättyjä artikkeleita", "today.tiles.outlets": "Julkaisevia medioita",
    "today.tiles.framed": "Käyttää propagandanarratiivia", "today.tiles.top": "Käytetyin narratiivi",
    "today.narratives": "Päivän narratiivit",
    "today.narratives.hint": "Osuus päivän kaikista artikkeleista · muutos edellisten päivien (enintään 28) keskiarvoon",
    "today.topics": "Uutisten aiheet",
    "col.framing": "Narratiivi", "col.topic": "Aihe", "col.articles": "Artikkelit", "col.share": "Osuus",
    "col.change": "vs. {n} pv", "col.change0": "Muutos", "col.trend": "30 pv",
    "today.examples": "Esimerkkejä", "today.more": "Kaikki {n} artikkelia arkistossa →",
    "today.rising": "Nousevat sanat",
    "today.rising.hint": "Otsikoiden sanat, joita käytettiin selvästi useammin kuin edellisten 14 päivän aikana",
    "today.rising.ru": "Venäjänkieliset mediat", "today.rising.en": "Englanninkieliset mediat",
    "today.rising.explain": "{n} otsikkoa, tavallisesti {base} päivässä",
    "today.rising.none": "Ei mitään tavallisuudesta poikkeavaa – tai historiaa ei ole vielä tarpeeksi.",
    "today.volume": "Kuka julkaisi mitä", "today.volume.hint": "Artikkelit medioittain tänä päivänä",
    "today.prev": "← Edellinen päivä", "today.next": "Seuraava päivä →", "today.latest": "Uusin päivä",
    "today.new": "uusi", "today.partial": "Tämän päivän keruu on vielä kesken.",

    "narratives.title": "Tapahtui Gribojedovin talossa",
    "narratives.epigraph": "Tosiasia on maailman itsepäisin asia.",
    "narratives.framings": "Narratiivit", "narratives.topics": "Aiheet",
    "range.label": "Ajanjakso", "range.7": "7 päivää", "range.30": "30 päivää", "range.90": "90 päivää", "range.all": "Kaikki",
    "narratives.share": "Osuus artikkeleista: {name}",
    "narratives.share.sub": "Kaikki mediat. Pisteet: päivittäinen osuus. Viiva: 7 päivän keskiarvo.",
    "narratives.groups": "Mediatyypeittäin",
    "narratives.groups.sub": "Jokaisessa ruudussa ryhmän päivittäinen osuus (kulta) verrattuna kaikkiin medioihin (harmaa)",
    "narratives.audience": "Kotimaassa ja ulkomailla",
    "narratives.audience.sub": "Venäjänkieliset mediat verrattuna englanninkielisiin, ulkomaille suunnattuihin medioihin (7 päivän keskiarvot)",
    "narratives.heat": "Media päivittäin", "narratives.heat.sub": "Osuus kunkin median artikkeleista, joissa narratiivi esiintyy",
    "narratives.byoutlet": "Ketkä käyttävät sitä eniten", "narratives.byoutlet.sub": "Osuus kunkin median artikkeleista ajanjaksolla",
    "narratives.examples": "Tuoreita esimerkkejä",
    "narratives.definition": "Miten Woland tunnistaa sen",
    "narratives.patterns.ru": "Venäjänkieliset hakuehdot", "narratives.patterns.en": "Englanninkieliset hakuehdot",
    "narratives.patterns.note": "* tarkoittaa mitä tahansa päätettä. Haetaan otsikosta, ingressistä ja – kun Woland voi lukea sivun – koko tekstistä.",
    "narratives.total": "{n} artikkelia ajanjaksolla",

    "archive.title": "Käsikirjoitukset eivät pala",
    "archive.epigraph": "Käsikirjoitukset eivät pala.",
    "archive.placeholder": "Hae otsikoista ja ingresseistä: нацисты, провокация, Finland…",
    "archive.go": "Hae",
    "archive.syntax": "Jokaisen kirjoittamasi sanan on esiinnyttävä jossakin taivutusmuodossa. Lisää * mille tahansa päätteelle (нацист*), kirjoita - sanan eteen sen poissulkemiseksi ja OR vaihtoehtojen väliin. Englanninkieliset haut kattavat myös konekäännetyt venäjänkieliset otsikot.",
    "archive.from": "Alkaen", "archive.to": "Asti", "archive.outlets": "Mediat", "archive.alloutlets": "Kaikki mediat",
    "archive.language": "Kieli", "archive.alllangs": "Kaikki kielet",
    "archive.narrative": "Narratiivi tai aihe", "archive.any": "Mikä tahansa",
    "archive.sort": "Järjestys", "archive.sort.new": "Uusimmat ensin", "archive.sort.old": "Vanhimmat ensin",
    "archive.results": "{n} artikkelia", "archive.results.one": "1 artikkeli",
    "archive.idle": "Hae koko arkistosta {start} alkaen tai selaa pelkillä suodattimilla.",
    "archive.searching": "Arkistosta haetaan",
    "archive.none": "Mitään ei löytynyt. Kokeile vähemmillä sanoilla tai lisää * sanan vartalon perään.",
    "archive.timeline": "Milloin se sanottiin", "archive.timeline.sub": "Osumat päivittäin",
    "archive.count": "Määrä", "archive.share": "Osuus kaikista artikkeleista",
    "archive.byoutlet": "Missä se sanottiin",
    "archive.export": "Vie CSV", "archive.export.note": "ensimmäiset {n}",
    "archive.more": "Näytä lisää", "archive.minchars": "Kirjoita vähintään 4 kirjainta ennen *-merkkiä",
    "archive.clear": "Tyhjennä",

    "article.original": "Alkuperäinen", "article.archive": "Arkistokopio", "article.cite": "Viittaa",
    "article.translate": "Käännä sivu", "article.eu": "Estetty EU:ssa", "article.mt": "KK",
    "article.mt.title": "Konekäännös", "article.body": "Tekstissä", "article.feed": "vain syöte",
    "article.listed": "vain otsikko",
    "article.listed.title": "Wolandilla on toistaiseksi vain otsikko median omasta listauksesta; se yrittää lukea sivun uudelleen.",
    "cite.title": "Viittaa artikkeliin", "cite.record": "Wolandin tietue", "cite.copy": "Kopioi", "cite.copied": "Kopioitu",
    "cite.close": "Sulje", "cite.retrieved": "Woland tallensi {date}", "cite.fingerprint": "sisällön tunniste",
    "cite.note": "Alkuperäiset linkit voivat olla estettyjä EU:ssa. Internet Archiven linkki avaa lähimmän arkistoidun kopion.",

    "outlets.title": "Saatanan suuret tanssiaiset",
    "outlets.epigraph": "Älkää koskaan puhuko tuntemattomien kanssa.",
    "outlets.lede": "Tanssiaisten vieraat: {n} Venäjän valtiollista ja Kremlin-myönteistä mediaa viidessä ryhmässä. Kustakin: kuka sen omistaa, miten Woland sitä lukee ja mitä se tapaa sanoa.",
    "outlets.articles": "artikkelia", "outlets.perday": "päivässä", "outlets.since": "alkaen",
    "outlets.method.page": "Jokainen artikkelisivu luetaan", "outlets.method.feed": "Vain otsikot median omasta syötteestä",
    "outlets.method.feedtext": "Koko tekstit median omasta syötteestä",
    "outlets.top": "Nojaa erityisesti", "outlets.top.hint": "narratiiveihin, joita se käyttää enemmän kuin lehdistö keskimäärin",
    "outlets.coverage": "Keruu, viimeiset 21 päivää",
    "cov.c": "Täydellinen", "cov.p": "Osittainen", "cov.f": "Vain syöte", "cov.m": "Puuttuu",
    "outlets.health": "Viimeisimmät keruuajot", "health.when": "Milloin", "health.mode": "Ajo",
    "health.new": "Uusia artikkeleita", "health.problems": "Ongelmat", "health.none": "ei ongelmia",
    "mode.daily": "Päivittäinen", "mode.poll": "Tunnin syötteet", "mode.backfill": "Takautuva keruu",
    "outlets.disabled": "Ei kerätä",

    "method.title": "Epilogi", "method.epigraph": "Ei asiakirjaa, ei ihmistä.",

    "footer.about": "Woland lukee Venäjän valtiollista ja Kremlin-myönteistä lehdistöä joka päivä ja tallentaa, mitä se sanoo: otsikot, ingressit ja niissä käytetyt propagandanarratiivit. Se on tehty tutkijoille, toimittajille ja aktivisteille.",
    "footer.updated": "Päivitetty viimeksi {date}", "footer.data": "Data ja koodi GitHubissa",
    "footer.license": "Koodi: MIT. Wolandin data: CC BY 4.0. Otsikot ja otteet kuuluvat julkaisijoilleen, ja niitä lainataan tutkimusta ja journalismia varten.",
    "footer.motto": "Käsikirjoitukset eivät pala.",
  },

  sv: {
    "site.tagline": "En krönika över den ryska statliga pressen",
    "nav.today": "I dag", "nav.narratives": "Narrativ", "nav.archive": "Arkiv", "nav.outlets": "Medier", "nav.method": "Metod",
    "theme.toggle": "Växla mellan natt och dag", "theme.night": "Natt", "theme.day": "Dag",
    "lang.label": "Språk", "skip": "Hoppa till innehållet", "chapter": "Kapitel",
    "epigraph.cite": "— M. Bulgakov, Mästaren och Margarita",
    "plate": "Plansch", "table.show": "Tabell", "table.hide": "Diagram",
    "loading": "Arkivet konsulteras",
    "error.load": "Arkivet kunde inte läsas. Försök igen senare.",
    "empty.nodata": "Inga artiklar har samlats in ännu. De första insamlingarna pågår.",
    "group.state": "Statlig kärna", "group.official": "Officiell linje", "group.mass": "Masspress",
    "group.foreign": "Utlandsriktade", "group.hardline": "Hårdföra",
    "lang.ru": "Ryskspråkiga", "lang.en": "Engelskspråkiga",
    "series.all": "Alla medier", "series.daily": "Daglig andel", "series.avg7": "Sjudagarsmedelvärde",
    "unit.articles": "artiklar", "unit.article": "artikel",

    "today.title": "Svart magi och dess avslöjande",
    "today.epigraph": "Att tala sanning är lätt och behagligt.",
    "today.lede": "Den {day} publicerade den bevakade pressen {total} artiklar från {outlets} medier. {framed} av dem använde minst ett av de propagandanarrativ som Woland följer.",
    "today.lede.rising": "Jämfört med de föregående {n} dagarna vann dessa narrativ mest mark: {list}.",
    "today.lede.norising": "Det finns ännu inte tillräckligt med historik (minst en vecka) för att säga vilka narrativ som ökar.",
    "today.tiles.articles": "Insamlade artiklar", "today.tiles.outlets": "Publicerande medier",
    "today.tiles.framed": "Använder ett propagandanarrativ", "today.tiles.top": "Mest använda narrativ",
    "today.narratives": "Dagens narrativ",
    "today.narratives.hint": "Andel av dagens alla artiklar · förändring mot genomsnittet för de föregående dagarna (högst 28)",
    "today.topics": "Ämnen i nyheterna",
    "col.framing": "Narrativ", "col.topic": "Ämne", "col.articles": "Artiklar", "col.share": "Andel",
    "col.change": "mot {n} d", "col.change0": "Förändring", "col.trend": "30 d",
    "today.examples": "Exempel", "today.more": "Alla {n} artiklar i arkivet →",
    "today.rising": "Ord på frammarsch",
    "today.rising.hint": "Rubrikord som användes betydligt oftare än under de föregående 14 dagarna",
    "today.rising.ru": "Ryskspråkiga medier", "today.rising.en": "Engelskspråkiga medier",
    "today.rising.explain": "{n} rubriker, normalt {base} per dag",
    "today.rising.none": "Inget ovanligt – eller ännu inte tillräckligt med historik.",
    "today.volume": "Vem publicerade vad", "today.volume.hint": "Artiklar per medium denna dag",
    "today.prev": "← Föregående dag", "today.next": "Nästa dag →", "today.latest": "Senaste dagen",
    "today.new": "ny", "today.partial": "Insamlingen för denna dag pågår fortfarande.",

    "narratives.title": "Det hände i Gribojedovhuset",
    "narratives.epigraph": "Ett faktum är det envisaste som finns.",
    "narratives.framings": "Narrativ", "narratives.topics": "Ämnen",
    "range.label": "Period", "range.7": "7 dagar", "range.30": "30 dagar", "range.90": "90 dagar", "range.all": "Alla",
    "narratives.share": "Andel artiklar: {name}",
    "narratives.share.sub": "Alla medier. Punkter: daglig andel. Linje: sjudagarsmedelvärde.",
    "narratives.groups": "Efter typ av medium",
    "narratives.groups.sub": "Varje ruta: gruppens dagliga andel (guld) mot alla medier (grått)",
    "narratives.audience": "Hemma och utomlands",
    "narratives.audience.sub": "Ryskspråkiga medier mot engelskspråkiga, utlandsriktade medier (sjudagarsmedelvärden)",
    "narratives.heat": "Medium per dag", "narratives.heat.sub": "Andel av varje mediums artiklar som använder det",
    "narratives.byoutlet": "Vilka använder det mest", "narratives.byoutlet.sub": "Andel av varje mediums artiklar under perioden",
    "narratives.examples": "Färska exempel",
    "narratives.definition": "Hur Woland känner igen det",
    "narratives.patterns.ru": "Ryska sökmönster", "narratives.patterns.en": "Engelska sökmönster",
    "narratives.patterns.note": "* står för valfri ändelse. Söks i rubriken, ingressen och – där Woland kan läsa sidan – hela texten.",
    "narratives.total": "{n} artiklar under perioden",

    "archive.title": "Manuskript brinner inte",
    "archive.epigraph": "Manuskript brinner inte.",
    "archive.placeholder": "Sök i rubriker och ingresser: нацисты, провокация, Finland…",
    "archive.go": "Sök",
    "archive.syntax": "Varje ord du skriver måste förekomma, i valfri böjningsform. Lägg till * för valfri ändelse (нацист*), sätt - framför ett ord för att utesluta det och skriv OR mellan alternativ. Engelska sökningar omfattar även de maskinöversatta ryska rubrikerna.",
    "archive.from": "Från", "archive.to": "Till", "archive.outlets": "Medier", "archive.alloutlets": "Alla medier",
    "archive.language": "Språk", "archive.alllangs": "Alla språk",
    "archive.narrative": "Narrativ eller ämne", "archive.any": "Valfritt",
    "archive.sort": "Ordning", "archive.sort.new": "Nyaste först", "archive.sort.old": "Äldsta först",
    "archive.results": "{n} artiklar", "archive.results.one": "1 artikel",
    "archive.idle": "Sök i hela arkivet sedan {start}, eller bläddra enbart med filtren.",
    "archive.searching": "Arkivet genomsöks",
    "archive.none": "Inget hittades. Försök med färre ord, eller sätt * efter en ordstam.",
    "archive.timeline": "När det sades", "archive.timeline.sub": "Träffar per dag",
    "archive.count": "Antal", "archive.share": "Andel av alla artiklar",
    "archive.byoutlet": "Var det sades",
    "archive.export": "Exportera CSV", "archive.export.note": "de första {n}",
    "archive.more": "Visa fler", "archive.minchars": "Skriv minst 4 bokstäver före *",
    "archive.clear": "Rensa",

    "article.original": "Original", "article.archive": "Arkiverad kopia", "article.cite": "Citera",
    "article.translate": "Översätt sidan", "article.eu": "Blockerad i EU", "article.mt": "MÖ",
    "article.mt.title": "Maskinöversättning", "article.body": "I texten", "article.feed": "endast flöde",
    "article.listed": "endast rubrik",
    "article.listed.title": "Woland har hittills bara rubriken från mediets egen lista; sidan försöker läsas igen.",
    "cite.title": "Citera artikeln", "cite.record": "Wolandpost", "cite.copy": "Kopiera", "cite.copied": "Kopierat",
    "cite.close": "Stäng", "cite.retrieved": "Hämtad av Woland {date}", "cite.fingerprint": "innehållets fingeravtryck",
    "cite.note": "Originallänkar kan vara blockerade i EU. Länken till Internet Archive öppnar närmaste arkiverade kopia.",

    "outlets.title": "Satans stora bal",
    "outlets.epigraph": "Tala aldrig med främlingar.",
    "outlets.lede": "Gästerna på denna bal: {n} medier ur den ryska statliga och Kremlvänliga pressen, i fem grupper. För varje medium: vem som äger det, hur Woland läser det och vad det brukar säga.",
    "outlets.articles": "artiklar", "outlets.perday": "per dag", "outlets.since": "sedan",
    "outlets.method.page": "Varje artikelsida läses", "outlets.method.feed": "Endast rubriker från mediets eget flöde",
    "outlets.method.feedtext": "Hela texter från mediets eget flöde",
    "outlets.top": "Lutar sig mot", "outlets.top.hint": "narrativ som det använder mer än pressen i stort",
    "outlets.coverage": "Insamling, senaste 21 dagarna",
    "cov.c": "Fullständig", "cov.p": "Delvis", "cov.f": "Endast flöde", "cov.m": "Saknas",
    "outlets.health": "Senaste insamlingskörningar", "health.when": "När", "health.mode": "Körning",
    "health.new": "Nya artiklar", "health.problems": "Problem", "health.none": "inga",
    "mode.daily": "Daglig", "mode.poll": "Flöden varje timme", "mode.backfill": "Efterinsamling",
    "outlets.disabled": "Samlas inte in",

    "method.title": "Epilog", "method.epigraph": "Inget dokument, ingen människa.",

    "footer.about": "Woland läser den ryska statliga och Kremlvänliga pressen varje dag och dokumenterar vad den säger: rubriker, ingresser och de propagandanarrativ de använder. Woland är gjort för forskare, journalister och aktivister.",
    "footer.updated": "Senast uppdaterad {date}", "footer.data": "Data och kod på GitHub",
    "footer.license": "Kod: MIT. Wolands data: CC BY 4.0. Rubriker och utdrag tillhör respektive utgivare och citeras för forskning och journalistik.",
    "footer.motto": "Manuskript brinner inte.",
  },
};

export const STRINGS = S;  // for the test-suite: every language must have every key

function detect() {
  const q = new URLSearchParams(location.search).get("lang");
  if (q && S[q]) return q;
  try {
    const saved = localStorage.getItem("woland.lang");
    if (saved && S[saved]) return saved;
  } catch (_) { /* storage may be unavailable */ }
  for (const l of navigator.languages || [navigator.language || "en"]) {
    const two = String(l).slice(0, 2).toLowerCase();
    if (S[two]) return two;
  }
  return "en";
}

export let lang = detect();

export function setLang(l) {
  if (!S[l]) return;
  lang = l;
  try { localStorage.setItem("woland.lang", l); } catch (_) { /* ignore */ }
}

export function t(key, vars) {
  let s = (S[lang] && S[lang][key]) ?? S.en[key] ?? key;
  if (vars) s = s.replace(/\{(\w+)\}/g, (m, k) => (k in vars ? vars[k] : m));
  return s;
}

/** Pick the right language from an {en, fi, sv} object coming from the data. */
export function tl(obj) {
  if (!obj) return "";
  if (typeof obj === "string") return obj;
  return obj[lang] || obj.en || Object.values(obj)[0] || "";
}

export function applyI18n(root = document) {
  document.documentElement.lang = lang;
  root.querySelectorAll("[data-i18n]").forEach((el) => { el.textContent = t(el.dataset.i18n); });
  root.querySelectorAll("[data-i18n-attr]").forEach((el) => {
    for (const pair of el.dataset.i18nAttr.split(";")) {
      const [attr, key] = pair.split(":");
      if (attr && key) el.setAttribute(attr.trim(), t(key.trim()));
    }
  });
}
