"""Synthetic connector: generates a realistic client dataset from the pack's `synthetic` section.
Risk signals are planted as exact customer lines and stored as ground truth; decoys are look-alike lines
that are NOT risks. Billing names are deliberately messy so identity matching has real work to do."""
from pathlib import Path
from typing import Optional
import datetime as dt
import random
from concurrent.futures import ThreadPoolExecutor

import yaml
from sqlalchemy import delete

from ..engine import llm
from ..engine.extract import staff_label
from ..models import (Account, Action, ActivityPoint, Brief, Contract, Conversation, PlantedLabel, Signal)
from .base import Connector, match_contracts

FIRST = ["Jonas", "Mia", "Felix", "Sara", "Lukas", "Hannah", "Emre", "Clara", "Tobias", "Nina", "David", "Lea",
         "Paul", "Amira", "Jan", "Sophie", "Can", "Julia", "Mateo", "Ida"]
LAST = ["Weber", "Schmidt", "Kaya", "Hoffmann", "Becker", "Novak", "Schulz", "Lange", "Krause", "Meyer",
        "Fischer", "Wolf", "Yilmaz", "Brandt", "Petrović", "Okafor"]


def messy(name: str, rng: random.Random) -> str:
    variants = [name.upper(), f"{name} GmbH", f"{name} GmbH & Co. KG", name.replace("ß", "ss").replace("ü", "ue")
                .replace("ö", "oe").replace("ä", "ae"), name.replace("&", "und"), f"{name} Group", name]
    typo = name[:len(name) // 2] + name[len(name) // 2 + 1:]          # one character missing
    variants += [f"{typo} GmbH", typo.upper()]
    return rng.choice(variants)


def line_pool(pack: dict) -> dict:
    """The pack's own lines first (the Analyze sample call uses the first two), then extra lines from plays/lines_<id>.yaml."""
    path = Path(__file__).resolve().parents[1] / "plays" / f"lines_{pack['id']}.yaml"
    extra = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else {}
    return {t: list(lines) + list(extra.get(t, [])) for t, lines in pack["synthetic"]["signal_lines"].items()}


def wipe(session, client_id: str):
    for model in (Action, Brief, Signal, PlantedLabel, Conversation, ActivityPoint, Contract, Account):
        session.execute(delete(model).where(model.client_id == client_id))
    session.commit()


class SyntheticConnector(Connector):
    name = "synthetic"

    def __init__(self, seed: int = 7, llm_transcripts: bool = False, n_in_window: Optional[int] = None):
        self.seed, self.llm_transcripts, self.n_in_window = seed, llm_transcripts, n_in_window

    def sync(self, session, client, pack: dict) -> dict:
        syn, v = pack["synthetic"], pack["vocabulary"]
        rng = random.Random(f"{self.seed}-{client.id}")
        today = dt.date.today()
        wipe(session, client.id)
        companies = syn["companies"]
        n = len(companies)
        n_in_window = self.n_in_window or round(n * 0.75)
        profiles = ["healthy"] * round(n * 0.4) + ["watch"] * round(n * 0.3)
        profiles += ["at_risk"] * (n - len(profiles))
        rng.shuffle(profiles)
        staff = f"{syn['product']} {v['owner_role']}"
        pool = line_pool(pack)
        lrng = random.Random(f"{self.seed}-{client.id}-lines")   # separate stream: the rest of the demo world stays identical
        specs = []

        for i, (company, prof) in enumerate(zip(companies, profiles)):
            contact, role = f"{rng.choice(FIRST)} {rng.choice(LAST)}", rng.choice(syn["roles"])
            acc = Account(client_id=client.id, name=company, segment=rng.choice(syn["segments"]),
                          employees=rng.randint(50, 200), contact_name=contact, contact_role=role, owner=client.user_name)
            session.add(acc)
            session.flush()
            lo, hi = syn["capacity"]
            cap = rng.randint(lo, hi)
            if prof == "at_risk":
                cap_prev = cap + rng.randint(2, max(3, cap // 4))
            elif prof == "watch":
                cap_prev = cap + rng.choice([0, 0, 1, 3])
            else:
                cap_prev = max(lo // 2, cap - rng.choice([0, 0, 2, 5]))
            renew_in = rng.randint(4, 90) if i < n_in_window else rng.randint(95, 300)
            session.add(Contract(client_id=client.id, billing_name=messy(company, rng), plan=rng.choice(syn["plans"]),
                                 capacity=cap, capacity_prev=cap_prev, monthly_value=cap * rng.choice(syn["unit_price"]),
                                 renewal_date=today + dt.timedelta(days=renew_in)))
            base = cap_prev * rng.uniform(*syn["activity_ratio"])
            drop = {"healthy": rng.uniform(-0.10, 0.05), "watch": rng.uniform(0.10, 0.25),
                    "at_risk": rng.uniform(0.30, 0.55)}[prof]
            for d in range(90):
                day = today - dt.timedelta(days=89 - d)
                factor = 1 - drop * ((d - 45) / 44) if d >= 45 else 1.0
                weekend = 0.45 if day.weekday() >= 5 else 1.0
                session.add(ActivityPoint(client_id=client.id, account_id=acc.id, day=day,
                                          value=round(max(0, base * factor * weekend * rng.uniform(0.9, 1.1)), 1)))

            n_sig = {"healthy": 0, "watch": 1, "at_risk": rng.randint(2, 3)}[prof]
            types = rng.sample(list(pack["signals"]), n_sig)
            n_calls = max(rng.randint(1, 3), 2 if prof == "at_risk" else 1)
            dates = sorted(rng.sample(range(3, 60), n_calls))
            calls = [{"account_id": acc.id, "company": company, "contact": contact, "role": role,
                      "date": today - dt.timedelta(days=d), "title": rng.choice(syn["titles"]), "types": []} for d in dates]
            for t in types:
                rng.choice(calls)["types"].append(t)
            fill = {"co": company, "nxt": f"{rng.choice(FIRST)} {rng.choice(LAST)}", "capacity": cap_prev,
                    **{k: rng.choice(vals) for k, vals in syn.get("fill", {}).items()}}
            for c in calls:
                options = [t for t in syn["decoys"] if t not in c["types"]]
                decoy = [rng.choice(options)] if options and rng.random() < 0.35 else []
                for t in c["types"]:
                    rng.choice(syn["signal_lines"][t])                  # keeps the main random stream unchanged
                c["sig_lines"] = [(t, lrng.choice(pool[t]).format(**fill)) for t in c["types"]]
                c["dec_lines"] = [(t, syn["decoys"][t].format(**fill)) for t in decoy]
                c["cust_lines"] = [l for _, l in c["sig_lines"] + c["dec_lines"]]
                specs.append(c)

        def render(spec):
            if self.llm_transcripts and llm.enabled():
                try:
                    out = llm_transcript(spec, syn, client.user_name, staff)
                    if out:
                        return out
                except Exception as e:  # noqa: BLE001
                    print("LLM transcript failed, using template:", e)
            return template_transcript(random.Random(f"{spec['date']}{spec['company']}"), spec, syn,
                                       client.user_name, staff)

        with ThreadPoolExecutor(max_workers=6) as pool:
            transcripts = list(pool.map(render, specs))
        for spec, text in zip(specs, transcripts):
            conv = Conversation(client_id=client.id, account_id=spec["account_id"], date=spec["date"],
                                title=spec["title"], transcript=text)
            session.add(conv)
            session.flush()
            for t, line in spec["sig_lines"]:
                session.add(PlantedLabel(client_id=client.id, conversation_id=conv.id, signal_type=t, line=line))
            for t, line in spec["dec_lines"]:
                session.add(PlantedLabel(client_id=client.id, conversation_id=conv.id, signal_type=t, line=line, is_decoy=True))
        session.commit()
        m = match_contracts(session, client.id)
        return {"accounts": n, "conversations": len(specs), **m}


def template_transcript(rng, spec, syn, owner, staff) -> str:
    cust = f"{spec['role']}, {spec['company']}"
    turns = [f"{owner} ({staff}): {rng.choice(syn['owner_open'])}",
             f"{spec['contact']} ({cust}): {rng.choice(syn['neutral'])}"]
    lines = spec["cust_lines"] + rng.sample(syn["neutral"], 2)
    rng.shuffle(lines)
    for line in lines:
        turns.append(f"{owner} ({staff}): {rng.choice(syn['owner_mid'])}")
        turns.append(f"{spec['contact']} ({cust}): {line}")
    turns.append(f"{owner} ({staff}): {rng.choice(syn['owner_close'])}")
    return "\n".join(turns)


def llm_transcript(spec, syn, owner, staff) -> Optional[str]:
    required = "\n".join(f"- {l}" for l in spec["cust_lines"]) or "- (none: an uneventful, positive call)"
    cust = f"{spec['role']}, {spec['company']}"
    prompt = (f"Write a realistic transcript of a {spec['title']} call between {owner} ({staff}) and "
              f"{spec['contact']} ({spec['role']} at {spec['company']}).\nFormat every turn on its own line exactly as:\n"
              f"{owner} ({staff}): text\n{spec['contact']} ({cust}): text\n"
              "Write 14-22 turns about ordinary work topics.\n"
              f"The customer must say each of these lines VERBATIM:\n{required}\n"
              "Do not add any other complaints, risks, budget issues, competitor names, departures or concerns.")
    out = llm.chat_text("You write realistic, plain business call transcripts. No markdown.", prompt)
    return out.strip() if all(l in out for l in spec["cust_lines"]) else None
