"""
Sleeve badge option vs team/league — case 'sleeve-badge-league', all 4 sites.

The same file sits in CFS/, KFK/, RFS/ and RFK/ (each site deploys from its
own folder): edit CFS/sleeve_badge.py, then copy it over the other three.
CFS/tests/test_sleeve_badge_league.py fails while the copies differ.

What a site passes in:
  - title: the product name (team + season are read from it, never guessed);
  - badges: one entry per badge option, either the label string or
    {'label': ..., 'images': [alt or filename of each badge picture]}.
    CFS (PPOM) reads the label from the checkbox's `data-label`; KFK/RFS/RFK
    (TM Extra Product Options) from `.tm-epo-element-label`. Labels that don't
    name the league ("Add  Badge", "Add Combo Argentina Home 2026 Badge",
    "Add Sleeve Badge") fall back on the badge picture;
  - description: the description text ("Sleeve badge: X can be added ...",
    "Badge options: ...", "EPL badges: ...").

From the CFS audit of 28 Oct 2026 (89 of 994 products with a badge for the
wrong team/league) and a sample of KFK/RFS/RFK pages the same day.
"""

import html
import re
import unicodedata

CASE = 'sleeve-badge-league'
GENERIC_BADGE = 'GENERIC'

# Club -> domestic league. Keys are what titles say; CLUB_ALIASES holds the
# other spellings, including the sites' brand-safe names (KFK 'Lvr^_^pooI',
# 'North London Red', RFK 'Arsn@l'). The longest match wins ('Queens Park
# Rangers' over 'Rangers').
CLUB_LEAGUES = {
    'Premier League': ['Arsenal', 'Aston Villa', 'Bournemouth', 'Brentford', 'Brighton', 'Chelsea',
        'Crystal Palace', 'Everton', 'Fulham', 'Leeds', 'Liverpool', 'Manchester City',
        'Manchester United', 'Newcastle', 'Nottingham Forest', 'Sunderland', 'Tottenham',
        'West Ham', 'Wolves', 'Southampton', 'Leicester'],
    'La Liga': ['Barcelona', 'Real Madrid', 'Atletico Madrid', 'Athletic Bilbao', 'Real Betis',
        'Sevilla', 'Villarreal'],
    'Serie A': ['AC Milan', 'Inter Milan', 'Juventus', 'Roma', 'Napoli', 'Fiorentina', 'Lazio'],
    'Bundesliga': ['Bayern Munich', 'Dortmund', 'Eintracht Frankfurt', 'RB Leipzig', 'Wolfsburg',
        'Bayer Leverkusen', 'Hertha Berlin'],
    'Ligue 1': ['PSG', 'Marseille', 'Lyon', 'Monaco'],
    'Saudi Pro League': ['Al Nassr', 'Al Hilal'],
    'MLS': ['Inter Miami', 'LA Galaxy', 'Los Angeles FC', 'Minnesota United', 'New York City',
        'New York Red Bulls', 'Orlando City', 'Toronto'],
    'Eredivisie': ['Ajax', 'PSV', 'Feyenoord'],
    'Scottish Premiership': ['Celtic', 'Rangers'],
    'Super Lig': ['Galatasaray', 'Besiktas'],
    'Primeira Liga': ['Porto', 'Benfica', 'Sporting CP'],
    # EFL is NOT the Premier League. QPR is here so 'Queens Park Rangers' is
    # never read as Rangers.
    'EFL': ['Barnsley', 'Charlton', 'Reading', 'Derby', 'Millwall', 'Coventry', 'Queens Park Rangers'],
}
CLUB_ALIASES = {
    'Arsenal': ['Arsn@l', 'Arsen^_^aI', 'North London Red'],
    'Liverpool': ['Lvrp00l', 'Lvr^_^pooI'],
    'Leeds': ['Leeds United'], 'Manchester City': ['Man City'],
    'Manchester United': ['Man Utd', 'Man United', 'Man^U^nited'],
    'Tottenham': ['Tottenham Hotspur', 'Spurs'], 'West Ham': ['West Ham United'],
    'Wolves': ['Wolverhampton'], 'Leicester': ['Leicester City'],
    'Atletico Madrid': ['Atletico de Madrid'], 'Athletic Bilbao': ['Athletic Club'],
    'Inter Milan': ['Internazionale'], 'Roma': ['AS Roma'], 'Napoli': ['SSC Napoli'],
    'Lazio': ['SS Lazio'], 'Fiorentina': ['ACF Fiorentina'],
    'Bayern Munich': ['Bayern', 'Bay^_^rn'], 'Dortmund': ['Borussia Dortmund', 'D0rt^_^mund'],
    'Eintracht Frankfurt': ['Frankfurt'], 'RB Leipzig': ['Leipzig'], 'Hertha Berlin': ['Hertha BSC'],
    'Bayer Leverkusen': ['Leverkusen'],
    'PSG': ['Paris Saint-Germain', 'Paris Saint Germain', 'P^_^SG'], 'Marseille': ['Olympique Marseille'],
    'Lyon': ['Olympique Lyonnais'], 'Monaco': ['AS Monaco'], 'Al Nassr': ['Al-Nassr'],
    'Al Hilal': ['Al-Hilal'], 'Inter Miami': ['Inter Miami CF'],
    'Los Angeles FC': ['LAFC', 'Los Angeles'], 'New York City': ['NYCFC'],
    'Orlando City': ['Orlando City SC'], 'Toronto': ['Toronto FC'], 'PSV': ['PSV Eindhoven'],
    'Celtic': ['Celtics'], 'Porto': ['FC Porto'], 'Sporting CP': ['Sporting Lisbon'],
    'Charlton': ['Charlton Athletic'], 'Derby': ['Derby County'], 'Coventry': ['Coventry City'],
    'Queens Park Rangers': ['QPR'],
}
CLUB_TO_LEAGUE = {club: league for league, clubs in CLUB_LEAGUES.items() for club in clubs}

# League by season start year (2024/25 = 2024) for promoted/relegated clubs.
# A later season than the last one listed is unknown (club_league_unknown, not
# a FAIL): promotions/relegations for it are not in the table yet.
CLUB_LEAGUE_BY_SEASON = {
    'Southampton': {2022: 'Premier League', 2023: 'EFL', 2024: 'Premier League', 2025: 'EFL'},
    'Leicester': {2022: 'Premier League', 2023: 'EFL', 2024: 'Premier League', 2025: 'EFL'},
    'Leeds': {2022: 'Premier League', 2023: 'EFL', 2024: 'EFL', 2025: 'Premier League'},
    'Sunderland': {2022: 'EFL', 2023: 'EFL', 2024: 'EFL', 2025: 'Premier League'},
    'Hertha Berlin': {2022: 'Bundesliga', 2023: '2. Bundesliga'},
}

# Domestic champions by the season they won (2024 = 2024/25; MLS by calendar
# year). A Champion badge on a 2025/26 shirt belongs to the 2024/25 champion.
# Seasons not listed give champion_badge_review until added. Arsenal 2025/26
# confirmed by Clara (29 Oct 2026).
LEAGUE_CHAMPIONS = {
    'Premier League': {2021: 'Manchester City', 2022: 'Manchester City', 2023: 'Manchester City',
                       2024: 'Liverpool', 2025: 'Arsenal'},
    'La Liga': {2021: 'Real Madrid', 2022: 'Barcelona', 2023: 'Real Madrid', 2024: 'Barcelona'},
    'Serie A': {2022: 'Napoli', 2023: 'Inter Milan', 2024: 'Napoli'},
    'Bundesliga': {2022: 'Bayern Munich', 2023: 'Bayer Leverkusen', 2024: 'Bayern Munich'},
    'Ligue 1': {2022: 'PSG', 2023: 'PSG', 2024: 'PSG'},
    'MLS': {2024: 'LA Galaxy', 2025: 'Inter Miami'},
}
# National champion badges: (holder, shirt years it is worn on). Tournaments
# whose new winner is not in the table yet: a champion badge on that year's
# shirt for another team is reported as "winner not in the table".
NATIONAL_CHAMPIONS_PENDING = {'World Cup': 2026}
NATIONAL_CHAMPIONS = {
    'World Cup': [('Argentina', range(2023, 2027))],
    'Euro': [('Italy', range(2021, 2025)), ('Spain', range(2024, 2029))],
    "UEFA Women's Euro": [('England', range(2022, 2030))],
}

# Countries read from titles (sites add their own taxonomy lists on top).
COUNTRIES = [
    'Albania', 'Algeria', 'Argentina', 'Australia', 'Austria', 'Belgium', 'Bolivia', 'Bosnia',
    'Brazil', 'Cameroon', 'Canada', 'Chile', 'China', 'Colombia', 'Costa Rica', 'Croatia',
    'Curacao', 'Czech', 'Czechia', 'Denmark', 'Ecuador', 'Egypt', 'El Salvador', 'England',
    'Finland', 'France', 'Germany', 'Ghana', 'Greece', 'Guatemala', 'Haiti', 'Honduras',
    'Hungary', 'Iceland', 'Iran', 'Iraq', 'Ireland', 'Italy', 'Ivory Coast', 'Jamaica', 'Japan',
    'Mexico', 'Morocco', 'Netherlands', 'New Zealand', 'Nigeria', 'Northern Ireland',
    'Norway', 'Palestine', 'Panama', 'Paraguay', 'Peru', 'Poland', 'Portugal', 'Qatar',
    'Romania', 'Russia', 'Saudi Arabia', 'Scotland', 'Senegal', 'Serbia', 'Slovakia',
    'Slovenia', 'South Africa', 'South Korea', 'Spain', 'Sweden', 'Switzerland', 'Tunisia',
    'Turkey', 'Ukraine', 'Uruguay', 'USA', 'Uzbekistan', 'Venezuela', 'Wales',
]
UEFA_COUNTRIES = {
    'Albania', 'Austria', 'Belgium', 'Bosnia', 'Croatia', 'Czech', 'Czechia', 'Denmark', 'England',
    'Finland', 'France', 'Germany', 'Greece', 'Hungary', 'Iceland', 'Ireland', 'Italy',
    'Netherlands', 'Northern Ireland', 'Norway', 'Poland', 'Portugal', 'Romania', 'Russia',
    'Scotland', 'Serbia', 'Slovakia', 'Slovenia', 'Spain', 'Sweden', 'Switzerland', 'Turkey',
    'Ukraine', 'Wales',
}

NATIONAL_TOURNAMENTS = {'Euro', 'World Cup', "UEFA Women's Euro"}
EUROPEAN_CLUB_CUPS = {'UEFA Europa League', 'UEFA Champions League', 'UEFA Conference League'}
CLUB_WORLD_CUP = 'FIFA Club World Cup'
CLUB_COMPETITIONS = set(CLUB_LEAGUES) | {'2. Bundesliga', CLUB_WORLD_CUP} | EUROPEAN_CLUB_CUPS

_PRICE_RE = re.compile(r'\s*\[\s*\+?\s*(?:£|&pound;)?\s*[\d.,]+\s*\]\s*', re.I)
# 'Euro' as a whole word only: 'Europa League' must not read as Euro (the
# first CFS audit missed 7 Europa League national-team listings this way).
_EURO_RE = re.compile(r'\bEuro\b(?!pa)', re.I)
_CHAMPION_RE = re.compile(r'champion|scudetto|winners?\b', re.I)
_LEAGUE_PATTERNS = [
    (re.compile(r'europa\s+league', re.I), 'UEFA Europa League'),
    (re.compile(r'conference\s+league', re.I), 'UEFA Conference League'),
    (re.compile(r'champions\s+league', re.I), 'UEFA Champions League'),
    (re.compile(r'club\s+world\s+cup', re.I), CLUB_WORLD_CUP),
    (re.compile(r'uefa\s+european\s+champions|women.?s\s+euro', re.I), "UEFA Women's Euro"),
    (re.compile(r'world\s*cup', re.I), 'World Cup'),
    (re.compile(r'scottish|premiership', re.I), 'Scottish Premiership'),
    (re.compile(r'premier|\bEPL\b', re.I), 'Premier League'),
    (re.compile(r'la\s*liga', re.I), 'La Liga'),
    (re.compile(r'serie\s*a\b', re.I), 'Serie A'),
    (re.compile(r'bundesliga', re.I), 'Bundesliga'),
    (re.compile(r'ligue\s*1\b', re.I), 'Ligue 1'),
    (re.compile(r'saudi|roshn', re.I), 'Saudi Pro League'),
    (re.compile(r'\bMLS\b|major\s+league\s+soccer', re.I), 'MLS'),
    (re.compile(r'eredivisie', re.I), 'Eredivisie'),
    (re.compile(r'primeira', re.I), 'Primeira Liga'),
    (re.compile(r's[uü]per\s*lig', re.I), 'Super Lig'),
]
# "Sleeve badge: X can be added ..." (CFS, KFK), "Badge options: X ..." and
# "EPL badges: X ..." (KFK gift packs).
DESCRIPTION_BADGE_RE = re.compile(
    r'\b(?:sleeve\s+badges?|badge\s+options?|[A-Z]{3}\s+badges?)\s*:\s*(.{0,160}?\bcan\s+be\s+added\b)', re.I)


def clean_label(label):
    """'Add Premier Badge [+£2.99]' -> 'Add Premier Badge'."""
    return re.sub(r'\s+', ' ', _PRICE_RE.sub(' ', html.unescape(label or ''))).strip()


def normalize_badge(text):
    """(league, champion) for a badge label, picture alt/filename or
    description line; (GENERIC_BADGE, False) for the bare 'Add Sleeve Badge'
    / 'Add Badge'; (None, False) when no league can be read."""
    text = clean_label(re.sub(r'[-_]+', ' ', text or ''))  # picture filenames: Laliga-Champion-Badge
    # GENERIC only for exactly "Add Sleeve Badge": "Add UEFA European
    # Champions 2025 Sleeve Badge" names its tournament (CFS 33058)
    if re.fullmatch(r'(?:add(?:ing)?\s+)?(?:sleeve\s+)?badges?', text, re.I):
        return GENERIC_BADGE, False
    champion = bool(_CHAMPION_RE.search(text))
    for pattern, league in _LEAGUE_PATTERNS:
        if pattern.search(text):
            if league in EUROPEAN_CLUB_CUPS:
                return league, False
            if league == "UEFA Women's Euro":
                return league, True
            return league, champion
    if _EURO_RE.search(text):
        return 'Euro', champion
    return None, False


normalize_badge_label = normalize_badge


def badge_display(league, champion):
    return f'{league} (champion)' if champion else league


def _strip_accents(text):
    return ''.join(c for c in unicodedata.normalize('NFKD', text or '') if not unicodedata.combining(c))


def _name_pattern(name):
    words = [w for w in re.split(r'[\s-]+', _strip_accents(name.strip()))
             if w and w.lower() not in {'de', 'of', 'the', 'fc', 'cf', 'sc'}] or [name.strip()]
    return re.compile(r'(?<![\w@^])' + r'[\s-]+(?:de|of|the)?[\s-]*'.join(re.escape(w) for w in words)
                      + r'(?![\w@^])', re.I)


def title_season(title):
    """Season start year: '2024/25' -> 2024, '25/26' -> 2025, '2026' -> 2026."""
    m = re.search(r'\b((?:19|20)\d{2})(?:\s*/\s*\d{2,4})?\b', title or '')
    if m:
        return int(m.group(1))
    m = re.search(r'\b(\d{2})\s*/\s*(\d{2})\b', title or '')
    return 2000 + int(m.group(1)) if m else None


def season_label(season):
    return f'{season}/{str(season + 1)[-2:]}' if season else '?'


def find_teams(title, site_clubs=(), site_countries=()):
    """[(team, 'club' | 'national')] named in the title, in title order
    (bundles can name two). The league map wins over a site's own category
    list ('Olympique Marseille' is Marseille, not the category 'Olympique
    de Marseille' with no league); a club wins over a country."""
    title = _strip_accents(title or '')
    names = {}
    for club in CLUB_TO_LEAGUE:
        for name in [club] + CLUB_ALIASES.get(club, []):
            names[name] = (club, 'club', 0)
    for club in site_clubs:
        names.setdefault(club, (club, 'club', 1))
    for country in list(site_countries) + COUNTRIES:
        names.setdefault(country, (country, 'national', 2))
    hits = []
    for name, (team, kind, rank) in names.items():
        for m in _name_pattern(name).finditer(title):
            hits.append((m.start(), m.end(), rank, team, kind))
    # longest match first, then the league map before site lists/countries
    hits.sort(key=lambda h: (-(h[1] - h[0]), h[2]))
    taken, teams = [], []
    for start, end, _, team, kind in hits:
        if any(start < e and s < end for s, e in taken):
            continue
        taken.append((start, end))
        teams.append((start, team, kind))
    seen, out = set(), []
    for _, team, kind in sorted(teams):
        if team not in seen:
            seen.add(team)
            out.append((team, kind))
    return out


def find_badge_team(title, site_clubs=(), site_countries=()):
    teams = find_teams(title, site_clubs, site_countries)
    return teams[0] if teams else (None, None)


def club_league(club, season):
    by_season = CLUB_LEAGUE_BY_SEASON.get(club, {})
    if season in by_season:
        return by_season[season]
    if by_season and season is not None and season > max(by_season):
        return None
    return CLUB_TO_LEAGUE.get(club)


def _national_expected(country):
    return 'Euro hoặc World Cup' if country in UEFA_COUNTRIES else 'World Cup'


def _read_badge(badge):
    """(label, [(league, champion)] from the label, or from the pictures when
    the label names none, label_names_league, picture leagues)."""
    if isinstance(badge, str):
        badge = {'label': badge}
    label = clean_label(badge.get('label'))
    from_label = normalize_badge(label)
    pictures = []
    for img in badge.get('images') or []:
        league = normalize_badge(img)
        if league[0] not in (None, GENERIC_BADGE) and league not in pictures:
            pictures.append(league)
    if from_label[0] not in (None, GENERIC_BADGE):
        return label, [from_label], True, pictures
    return label, pictures, False, pictures


def sleeve_badge_league_check(title, badges, description='', site_clubs=(), site_countries=(),
                              description_lists_badge=True):
    """Case 'sleeve-badge-league'. Returns {case, status: PASS|WARNING|FAIL,
    findings: [{level, issue, team, team_type, badge_label, expected,
    message}]}. `description_lists_badge`: the site's description template
    names the badge (CFS, KFK), so a badge option missing from it is
    flagged; RFS/RFK templates don't."""
    findings = []
    teams = find_teams(title, site_clubs, site_countries)
    team, team_type = teams[0] if teams else (None, None)
    season = title_season(title)
    read = [_read_badge(b) for b in badges or []
            if 'badge' in clean_label(b if isinstance(b, str) else b.get('label')).lower()]

    def add(level, issue, label, expected, message, who=None):
        t, k = who or (team, team_type)
        findings.append({'level': level, 'issue': issue, 'team': t, 'team_type': k,
                         'badge_label': label, 'expected': expected, 'message': message})

    if read and not teams:
        add('WARNING', 'team_unresolved', ', '.join(r[0] for r in read), None,
            'Không xác định được đội/CLB từ tên sản phẩm → cần người check option badge.')
    for club, kind in teams:
        if read and kind == 'club' and club_league(club, season) is None:
            known = club in CLUB_TO_LEAGUE or club in CLUB_LEAGUE_BY_SEASON
            add('WARNING', 'club_league_unknown', ', '.join(r[0] for r in read), None,
                (f'Chưa có dữ liệu {club} đá giải nào mùa {season_label(season)} ' if known else
                 f'{club} chưa có trong bảng CLB → giải ') + '→ cần người check option badge.', (club, kind))

    for label, leagues, label_named, pictures in read:
        if not label_named:
            hint = ', '.join(badge_display(*l) for l in leagues) or _team_hint(teams, season)
            add('WARNING', 'badge_label_missing_league', label, hint or None,
                f'Option "{label}" không ghi tên giải' + (f' (ảnh/gợi ý: {hint}).' if hint else '.'))
        elif pictures and leagues[0] not in pictures and not _champion_picture_ok(teams, season, leagues[0], pictures):
            add('WARNING', 'badge_image_mismatch', label, ', '.join(badge_display(*p) for p in pictures),
                f'Option "{label}" nhưng ảnh badge là {", ".join(badge_display(*p) for p in pictures)} '
                '→ sửa tên option hoặc ảnh cho khớp.')
        for league, champion in leagues:
            _check_league(add, teams, season, label, league, champion)

    named = {l for _, leagues, _, _ in read for l in leagues}
    if len({league for league, _ in named}) > 1 and len(read) > 1:
        add('WARNING', 'multiple_badge_options', ', '.join(r[0] for r in read), None,
            f'Có {len(read)} option badge khác giải ({", ".join(r[0] for r in read)}) → kiểm tra lại.')

    _description_checks(add, read, named, description, description_lists_badge)

    status = 'FAIL' if any(f['level'] == 'FAIL' for f in findings) else 'WARNING' if findings else 'PASS'
    return {'case': CASE, 'status': status, 'findings': findings}


def _champion_picture_ok(teams, season, league, pictures):
    """'Adding Premier League Badge' showing the Champion badge is right on
    the reigning champion's shirt (RFS Arsenal 2026/27, confirmed by Clara)."""
    if league[1] or (league[0], True) not in pictures:
        return False
    holder = LEAGUE_CHAMPIONS.get(league[0], {}).get(season - 1 if season else None)
    return holder is not None and any(team == holder for team, _ in teams)


def _team_hint(teams, season):
    for team, kind in teams:
        hint = club_league(team, season) if kind == 'club' else _national_expected(team)
        if hint:
            return hint
    return ''


def _league_problem(team, kind, season, league):
    """None when `league` fits this team, else (level, issue, expected, message)."""
    if kind == 'national':
        if league in CLUB_COMPETITIONS:
            expected = _national_expected(team)
            return ('FAIL', 'national_team_league_badge', expected,
                    f'{team} là đội tuyển quốc gia nhưng option badge là {league} '
                    f'→ bỏ option hoặc đổi sang {expected}.')
        return None
    expected = club_league(team, season)
    if league in NATIONAL_TOURNAMENTS:
        return ('FAIL', 'club_with_national_tournament_badge', expected,
                f'{team} là CLB nhưng option badge là {league} (giải đội tuyển) → bỏ option'
                + (f' hoặc đổi sang {expected}.' if expected else '.'))
    if league in EUROPEAN_CLUB_CUPS:
        return ('WARNING', 'european_badge_review', None,
                f'{team} có option {league} → chỉ đúng nếu CLB dự/vô địch giải này mùa đó, cần người check.')
    if league == CLUB_WORLD_CUP:
        return ('WARNING', 'club_world_cup_badge_review', None,
                f'{team} có option {league} → chỉ đúng nếu CLB dự giải này, cần người check.')
    if expected and league != expected:
        return ('FAIL', 'badge_league_mismatch', expected, None)
    return None


def _check_league(add, teams, season, label, league, champion):
    problems = []
    for team, kind in teams:
        problem = _league_problem(team, kind, season, league)
        if problem is None:
            if champion:
                _champion_review(add, team, kind, league, season, label)
            return
        problems.append((team, kind, problem))
    if problems:  # the badge fits none of the teams in the name: report the first
        team, kind, (level, issue, expected, message) = problems[0]
        if issue == 'badge_league_mismatch':
            message = f'{team} đá {expected} nhưng option là {label}.'
        add(level, issue, label, expected, message, (team, kind))


def _champion_review(add, team, kind, league, season, label):
    who = (team, kind)
    if kind == 'national':
        holders = [h for h, years in NATIONAL_CHAMPIONS.get(league, []) if season in years]
        if not holders:
            add('WARNING', 'champion_badge_review', label, None,
                f'Chưa có dữ liệu nhà vô địch {league} cho năm {season} → cần người check badge champion của {team}.',
                who)
        elif team not in holders and NATIONAL_CHAMPIONS_PENDING.get(league) == season:
            add('WARNING', 'champion_badge_review', label, None,
                f'Chưa có dữ liệu nhà vô địch {league} {season} (đương kim trước đó: {", ".join(holders)}) '
                f'→ cần người check badge champion của {team}.', who)
        elif team not in holders:
            add('WARNING', 'champion_badge_review', label, ', '.join(holders),
                f'{team} có badge vô địch {league} nhưng nhà vô địch là {", ".join(holders)} → cần người check.',
                who)
        return
    previous = season - 1 if season else None
    holder = LEAGUE_CHAMPIONS.get(league, {}).get(previous)
    won = season_label(previous) if league != 'MLS' else str(previous)
    if holder is None:
        add('WARNING', 'champion_badge_review', label, None,
            f'Chưa có dữ liệu vô địch {league} {won} → cần người check badge champion của {team}.', who)
    elif holder != team:
        add('WARNING', 'champion_badge_review', label, holder,
            f'{team} có badge vô địch {league} nhưng {holder} mới là nhà vô địch {won} → cần người check.', who)


def _description_checks(add, read, named, description, description_lists_badge):
    """The description's badge line must name the same league as the option."""
    mentioned = [m.group(1).strip() for m in DESCRIPTION_BADGE_RE.finditer(description or '')]
    labels = ', '.join(r[0] for r in read)
    if mentioned and not read:
        add('FAIL', 'description_badge_without_option', None, None,
            f'Description ghi sleeve badge "{mentioned[0]}" nhưng trang không có option badge '
            '→ thêm option hoặc bỏ dòng này.')
        return
    if read and not mentioned:
        if description_lists_badge:
            add('WARNING', 'option_not_in_description', labels, None,
                'Có option badge nhưng description không có dòng sleeve badge → thêm vào description.')
        return
    if not named:
        return
    for text in mentioned:
        league = normalize_badge(text)
        if league[0] in (None, GENERIC_BADGE):
            continue
        if league in named:
            continue
        options = ', '.join(badge_display(*b) for b in sorted(named))
        if league[0] in {n[0] for n in named}:  # same league, only "Champions" differs
            add('WARNING', 'description_badge_champion_mismatch', labels, options,
                f'Description ghi sleeve badge "{text}" nhưng option là {options} (lệch chữ Champions) → sửa cho khớp.')
        else:
            add('FAIL', 'description_badge_mismatch', labels, options,
                f'Description ghi sleeve badge "{text}" nhưng option là {options} → sửa cho khớp.')


def tm_epo_badges(soup):
    """Badge options rendered by TM Extra Product Options (KFK, RFS, RFK):
    [{'label', 'images'}] where images are the alt text and filename of each
    picture in the option's own block (the league when the label has none)."""
    badges = []
    for el in soup.find_all(class_=re.compile(r'\btm-epo-element-label\b')):
        label = el.get_text(' ', strip=True)
        if 'badge' not in label.lower():
            continue
        box = el.find_parent(class_=re.compile(r'\btc-element-inner-wrap\b')) or el.parent
        images = []
        for img in box.find_all('img') if box else []:
            src = img.get('data-src') or img.get('data-lazy-src') or img.get('src') or ''
            images += [x for x in (img.get('alt', '').strip(), src.rsplit('/', 1)[-1]) if x and not x.startswith('data:')]
        badges.append({'label': label, 'images': images})
    return badges
