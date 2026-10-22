# 답변 문장별 근거 점검 (C1) — LLM 없이 코드로 대조한다
#   1) 답변을 문장으로 나누고 문장마다 [근거 N] 번호를 읽는다
#   2) 문장 속 수치(2.32 · .315 · 1,013 · 182⅔ · 22.5%)가 근거 본문 어딘가에 실제로 있는지 확인한다
#      → 근거에서 찾지 못한 수치는 LLM 이 계산했거나 지어냈을 가능성이 있어 화면에 표시한다
#   3) 근거 번호가 없는 문장(판정 줄 · "확인되지 않는다" 문장 제외)을 따로 알린다
#   한 자리 정수(경기 수 · 항목 수 등)와 질문에 나온 수치(사실 확인의 주장 값 등)는 점검하지 않는다.

import re

CITE = re.compile(r"\[근거\s*[\d,\s]+\]")
CITE_NUM = re.compile(r"\[근거\s*([\d,\s]+)\]")
# 문장 끝: 마침표 · 물음표 · 느낌표(소수점 제외) 뒤에 붙은 [근거 N] 까지 한 문장
SENTENCE = re.compile(r"[^\n]*?(?:[.!?](?!\d)|$)(?:\s*\[근거\s*[\d,\s]+\])*")
NUMBER = re.compile(r"(?<![\w.])(\d[\d,]*(?:\.\d+)?|\.\d+)([⅓⅔])?")
FRACTION = {"⅓": 1 / 3, "⅔": 2 / 3}
SKIP = re.compile(r"^\s*(?:판정\s*:|[#>-]*\s*$)|확인되지 않")


def numbers_in(text):
    """[(원래 표기, 값)] — 근거 번호는 빼고"""
    out = []
    for m in NUMBER.finditer(CITE.sub(" ", text)):
        raw = m.group(1).rstrip(",")
        try:
            value = float(raw.replace(",", ""))
        except ValueError:
            continue
        if m.group(2):
            value += FRACTION[m.group(2)]
        out.append((m.group(0), value))
    return out


def check(answer, evidence, question=""):
    """{"sentences": [{text, cites, missing, uncited}], "numbers", "found", "missing": [표기], "uncited": 문장 수}"""
    asked = {round(v, 3) for _, v in numbers_in(question)}
    pool = set()
    for e in evidence:
        pool.update(round(v, 3) for _, v in numbers_in(e.get("text", "")))
    sentences, total, found, missing_all, uncited = [], 0, 0, [], 0
    for line in answer.split("\n"):
        for m in SENTENCE.finditer(line):
            text = m.group(0).strip()
            if not text or not re.search(r"[가-힣A-Za-z0-9]", text):
                continue
            cites = sorted({int(n) for g in CITE_NUM.findall(text) for n in g.split(",") if n.strip().isdigit()})
            missing = []
            for raw, value in numbers_in(text):
                if (value < 10 and value == int(value)) or round(value, 3) in asked:
                    continue                                # 한 자리 정수 · 질문에 나온 수치는 점검하지 않음
                total += 1
                if round(value, 3) in pool:
                    found += 1
                else:
                    missing.append(raw)
            is_uncited = not cites and not SKIP.search(text) and len(CITE.sub("", text).strip()) > 8
            uncited += is_uncited
            missing_all += missing
            sentences.append({"text": text, "cites": cites, "missing": missing, "uncited": is_uncited})
    return {"sentences": sentences, "numbers": total, "found": found,
            "missing": list(dict.fromkeys(missing_all)), "uncited": uncited}
