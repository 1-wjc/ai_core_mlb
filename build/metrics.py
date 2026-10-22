# 지표 계산 함수 (로컬 Python, LLM 미사용)
# 정의 · 계산식 · 근거 문서는 build/metrics.json (지표 사전) 에 정리되어 있다.
# 분모가 0이면 None (화면 · 답변에서는 "계산 불가")


def div(a, b):
    if b is None or b == 0 or a is None:
        return None
    return a / b


def rnd(value, digits):
    if value is None:
        return None
    return round(value, digits)


def ip_text(ipouts):
    """아웃카운트 → '182⅔' 같은 이닝 표기"""
    whole = ipouts // 3
    rest = ipouts % 3
    return str(whole) + {0: "", 1: "⅓", 2: "⅔"}[rest]


# ---------------- 리그 기준값 ----------------
def league_rates(league_total):
    """리그 OBP · SLG · ERA · FIP 상수 (OPS+ · ERA+ · FIP 계산용)"""
    b = league_total["bat"]
    p = league_total["pit"]
    tb = b["H"] + b["2B"] + 2 * b["3B"] + 3 * b["HR"]
    lg_obp = div(b["H"] + b["BB"] + b["HBP"], b["AB"] + b["BB"] + b["HBP"] + b["SF"])
    lg_slg = div(tb, b["AB"])
    ip = p["IPouts"] / 3
    lg_era = div(9 * p["ER"], ip)
    fip_core = div(13 * p["HR"] + 3 * (p["BB"] + p["HBP"]) - 2 * p["SO"], ip)
    fip_const = lg_era - fip_core if lg_era is not None and fip_core is not None else None
    return {"lg_obp": lg_obp, "lg_slg": lg_slg, "lg_era": lg_era, "fip_const": fip_const}


# ---------------- 타격 ----------------
def batting_metrics(s, rates=None, park=None):
    AB, H, BB, HBP, SF, SH = s["AB"], s["H"], s["BB"], s["HBP"], s["SF"], s["SH"]
    D2, D3, HR, SO, SB, CS = s["2B"], s["3B"], s["HR"], s["SO"], s["SB"], s["CS"]
    PA = AB + BB + HBP + SF + SH
    TB = H + D2 + 2 * D3 + 3 * HR

    avg = div(H, AB)
    obp = div(H + BB + HBP, AB + BB + HBP + SF)
    slg = div(TB, AB)
    ops = obp + slg if obp is not None and slg is not None else None
    iso = slg - avg if slg is not None and avg is not None else None
    babip = div(H - HR, AB - SO - HR + SF)

    # 득점 생산 계열
    rc = div((H + BB) * TB, AB + BB)                              # Runs Created (기본형)
    outs = AB - H + CS + SH + SF + s["GIDP"]
    rc27 = div(rc * 27, outs) if rc is not None else None
    a = H + BB + HBP - HR                                         # Base Runs (기본형)
    b = (1.4 * TB - 0.6 * H - 3 * HR + 0.1 * (BB + HBP)) * 1.02
    c = AB - H
    bsr = div(a * b, b + c)
    bsr = bsr + HR if bsr is not None else None

    gpa = (1.8 * obp + slg) / 4 if obp is not None and slg is not None else None

    ops_plus = None
    if rates and park and obp is not None and slg is not None and rates["lg_obp"] and rates["lg_slg"]:
        ops_plus = 100 * (obp / rates["lg_obp"] + slg / rates["lg_slg"] - 1) / (park / 100)

    return {
        "PA": PA, "TB": TB, "XBH": D2 + D3 + HR,
        "AVG": rnd(avg, 3), "OBP": rnd(obp, 3), "SLG": rnd(slg, 3), "OPS": rnd(ops, 3),
        "ISO": rnd(iso, 3), "BABIP": rnd(babip, 3),
        "BB_pct": rnd(div(BB, PA) * 100 if PA else None, 1),
        "K_pct": rnd(div(SO, PA) * 100 if PA else None, 1),
        "BB_K": rnd(div(BB, SO), 2),
        "SB_pct": rnd(div(SB, SB + CS) * 100 if SB + CS else None, 1),
        "SecA": rnd(div(TB - H + BB + SB - CS, AB), 3),
        "PSN": rnd(div(2 * HR * SB, HR + SB), 1),
        "GPA": rnd(gpa, 3),
        "RC": rnd(rc, 1), "RC27": rnd(rc27, 2), "BsR": rnd(bsr, 1),
        "OPS_plus": rnd(ops_plus, 0),
    }


# ---------------- 투구 ----------------
def pitching_metrics(s, rates=None, park=None):
    ip = s["IPouts"] / 3
    H, ER, HR, BB, SO, HBP, BFP, SH = s["H"], s["ER"], s["HR"], s["BB"], s["SO"], s["HBP"], s["BFP"], s["SH"]

    era = div(9 * ER, ip)
    fip = None
    if rates and rates["fip_const"] is not None and ip:
        fip = (13 * HR + 3 * (BB + HBP) - 2 * SO) / ip + rates["fip_const"]

    era_plus = era_minus = fip_minus = None
    if rates and park and rates["lg_era"]:
        lg_era_park = rates["lg_era"] * park / 100
        if era:
            era_plus = 100 * lg_era_park / era
        if era is not None:
            era_minus = 100 * era / lg_era_park
        if fip is not None:
            fip_minus = 100 * fip / lg_era_park

    k_pct = div(SO, BFP)
    bb_pct = div(BB, BFP)
    return {
        "IP": ip_text(s["IPouts"]),
        "ERA": rnd(era, 2),
        "WHIP": rnd(div(BB + H, ip), 2),
        "K9": rnd(div(9 * SO, ip), 2), "BB9": rnd(div(9 * BB, ip), 2),
        "HR9": rnd(div(9 * HR, ip), 2), "H9": rnd(div(9 * H, ip), 2),
        "K_BB": rnd(div(SO, BB), 2),
        "K_pct": rnd(k_pct * 100 if k_pct is not None else None, 1),
        "BB_pct": rnd(bb_pct * 100 if bb_pct is not None else None, 1),
        "K_BB_pct": rnd((k_pct - bb_pct) * 100 if k_pct is not None and bb_pct is not None else None, 1),
        "BABIP": rnd(div(H - HR, BFP - SO - HR - BB - HBP - SH), 3),
        # 피안타율 · 피출루율 (타격방해 출루는 데이터에 없어 빼지 못함). 피장타율은 피2루타 · 피3루타가 없어 계산 불가
        "BAA": rnd(div(H, BFP - BB - HBP - SH - s["SF"]), 3),
        "OBP_against": rnd(div(H + BB + HBP, BFP), 3),
        "FIP": rnd(fip, 2),
        "ERA_plus": rnd(era_plus, 0), "ERA_minus": rnd(era_minus, 0), "FIP_minus": rnd(fip_minus, 0),
    }


# ---------------- 수비 ----------------
def fielding_metrics(f):
    chances = f["PO"] + f["A"] + f["E"]
    innings = f["InnOuts"] / 3
    return {
        "FPCT": rnd(div(f["PO"] + f["A"], chances), 3),
        "RF9": rnd(div(9 * (f["PO"] + f["A"]), innings), 2),
    }


# ---------------- 팀 ----------------
def team_metrics(t):
    W, L, G = int(t["W"]), int(t["L"]), int(t["G"])
    R, RA = int(t["R"]), int(t["RA"])
    pyth = div(R ** 2, R ** 2 + RA ** 2)
    exponent = ((R + RA) / G) ** 0.287 if G else None              # Pythagenpat
    pyth_pat = div(R ** exponent, R ** exponent + RA ** exponent) if exponent else None
    expected_w = pyth_pat * (W + L) if pyth_pat is not None else None
    return {
        "W_pct": rnd(div(W, W + L), 3),
        "RD": R - RA,
        "Pyth_pct": rnd(pyth, 3),
        "Pythagenpat_pct": rnd(pyth_pat, 3),
        "Expected_W": rnd(expected_w, 1),
        "Luck": rnd(W - expected_w if expected_w is not None else None, 1),
    }
