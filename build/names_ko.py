# 한국어 표기표 (구단 · 포스트시즌 라운드 · 수상 · 포지션 · 투타)
# 원본 코드 값은 Lahman 데이터 기준 (1990~2025, AL · NL)

# 구단: Lahman franchID → 현재 구단 한국어 이름
FRANCHISE_KO = {
    "ARI": "애리조나 다이아몬드백스", "ATL": "애틀랜타 브레이브스", "BAL": "볼티모어 오리올스",
    "BOS": "보스턴 레드삭스", "CHC": "시카고 컵스", "CHW": "시카고 화이트삭스",
    "CIN": "신시내티 레즈", "CLE": "클리블랜드 가디언스", "COL": "콜로라도 로키스",
    "DET": "디트로이트 타이거스", "FLA": "마이애미 말린스", "HOU": "휴스턴 애스트로스",
    "KCR": "캔자스시티 로열스", "ANA": "로스앤젤레스 에인절스", "LAD": "로스앤젤레스 다저스",
    "MIL": "밀워키 브루어스", "MIN": "미네소타 트윈스", "NYM": "뉴욕 메츠",
    "NYY": "뉴욕 양키스", "OAK": "애슬레틱스", "PHI": "필라델피아 필리스",
    "PIT": "피츠버그 파이리츠", "SDP": "샌디에이고 파드리스", "SEA": "시애틀 매리너스",
    "SFG": "샌프란시스코 자이언츠", "STL": "세인트루이스 카디널스", "TBD": "탬파베이 레이스",
    "TEX": "텍사스 레인저스", "TOR": "토론토 블루제이스", "WSN": "워싱턴 내셔널스",
}

LEAGUE_KO = {"AL": "아메리칸리그", "NL": "내셔널리그"}


def round_ko(round_code):
    """포스트시즌 라운드 코드(WS, ALCS, NLDS1, ALWC2 …) → 한국어"""
    if round_code == "WS":
        return "월드시리즈"
    league = LEAGUE_KO.get(round_code[:2], "")
    kind = round_code[2:4]
    if kind == "CS":
        return league + " 챔피언십시리즈"
    if kind == "DS":
        return league + " 디비전시리즈"
    if kind == "WC":
        return league + " 와일드카드"
    return round_code


# 라운드 깊이 (클수록 더 높이 올라감) — 팀 포스트시즌 최종 성적 판정용
def round_depth(round_code):
    if round_code == "WS":
        return 4
    kind = round_code[2:4]
    return {"CS": 3, "DS": 2, "WC": 1}.get(kind, 0)


# 주요 수상만 한국어로 표기 (그 외 주간 · 월간 상 등은 원문 그대로 awards_all 에만 보관)
AWARD_KO = {
    "Most Valuable Player": "MVP",
    "Cy Young Award": "사이영상",
    "Rookie of the Year": "신인왕",
    "Gold Glove": "골드글러브",
    "Platinum Glove": "플래티넘 글러브",
    "Silver Slugger": "실버슬러거",
    "World Series MVP": "월드시리즈 MVP",
    "ALCS MVP": "아메리칸리그 챔피언십시리즈 MVP",
    "NLCS MVP": "내셔널리그 챔피언십시리즈 MVP",
    "All-Star Game MVP": "올스타전 MVP",
    "Triple Crown": "타격 트리플 크라운",
    "Pitching Triple Crown": "투수 트리플 크라운",
    "Hank Aaron Award": "행크 에런상",
    "Roberto Clemente Award": "로베르토 클레멘테상",
    "Comeback Player of the Year": "올해의 재기상",
    "Reliever of the Year Award": "올해의 구원투수상",
    "Outstanding DH Award": "최우수 지명타자상",
    "All-MLB Team - First Team": "올-MLB 퍼스트 팀",
    "All-MLB Team - Second Team": "올-MLB 세컨드 팀",
}

# Appearances 포지션 열 → 한국어
POSITION_KO = {
    "G_p": "투수", "G_c": "포수", "G_1b": "1루수", "G_2b": "2루수", "G_3b": "3루수",
    "G_ss": "유격수", "G_lf": "좌익수", "G_cf": "중견수", "G_rf": "우익수", "G_dh": "지명타자",
}

# Fielding POS 코드 → 한국어
FIELD_POS_KO = {
    "P": "투수", "C": "포수", "1B": "1루수", "2B": "2루수", "3B": "3루수",
    "SS": "유격수", "LF": "좌익수", "CF": "중견수", "RF": "우익수", "OF": "외야수",
}

COUNTRY_KO = {
    "USA": "미국", "Dominican Republic": "도미니카 공화국", "Venezuela": "베네수엘라",
    "P.R.": "푸에르토리코", "Puerto Rico": "푸에르토리코", "Cuba": "쿠바", "Mexico": "멕시코",
    "Japan": "일본", "South Korea": "대한민국", "Canada": "캐나다", "Panama": "파나마",
    "Colombia": "콜롬비아", "Curacao": "퀴라소", "Taiwan": "대만", "Australia": "오스트레일리아",
    "Nicaragua": "니카라과", "Netherlands": "네덜란드", "Aruba": "아루바", "Bahamas": "바하마",
    "Brazil": "브라질", "Germany": "독일", "Honduras": "온두라스", "Jamaica": "자메이카",
    "V.I.": "미국령 버진아일랜드", "Virgin Islands": "미국령 버진아일랜드", "United Kingdom": "영국",
    "Italy": "이탈리아", "South Africa": "남아프리카 공화국", "Lithuania": "리투아니아", "Peru": "페루",
    # Lahman 표기 그대로인 값
    "D.R.": "도미니카 공화국", "México": "멕시코", "CAN": "캐나다", "Curaçao": "퀴라소",
    "Soviet Union": "소련", "West Germany": "서독", "U.S. Virgin Islands": "미국령 버진아일랜드", "Spain": "스페인",
}

BATS_KO = {"R": "우타", "L": "좌타", "B": "양타"}
THROWS_KO = {"R": "우투", "L": "좌투", "S": "양손"}
