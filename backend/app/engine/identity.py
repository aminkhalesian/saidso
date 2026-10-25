"""Identity matching: link billing records to CRM accounts when names don't match exactly
("Weißdorn Insurance" vs "WEISSDORN INSURANCE GMBH & CO. KG")."""
from typing import Optional
import re
import unicodedata
from difflib import SequenceMatcher

LEGAL_SUFFIXES = r"\b(gmbh|ag|ug|kg|co|se|ltd|inc|llc|group|holding|und|and)\b"


def normalize(name: str) -> str:
    s = name.lower().replace("ß", "ss").replace("&", " ")
    s = s.replace("ä", "ae").replace("ö", "oe").replace("ü", "ue")
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    s = re.sub(LEGAL_SUFFIXES, " ", s)
    return re.sub(r"\s+", " ", s).strip()


def similarity(a: str, b: str) -> float:
    na, nb = normalize(a), normalize(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    ta, tb = set(na.split()), set(nb.split())
    token = len(ta & tb) / len(ta | tb)
    return round(max(SequenceMatcher(None, na, nb).ratio(), token), 3)


def best_match(name: str, candidates: dict[int, str], threshold: float = 0.6) -> tuple[Optional[int], float]:
    """Return (account_id, confidence) of the best candidate, or (None, score) if below threshold."""
    scored = [(similarity(name, cand), cid) for cid, cand in candidates.items()]
    if not scored:
        return None, 0.0
    score, cid = max(scored)
    return (cid, score) if score >= threshold else (None, score)
