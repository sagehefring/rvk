#!/usr/bin/env python3
"""
generate_data.py  —  parse the RÚV election quiz HAR archive and emit data.js
                      containing window.ELECTION_DATA for the web frontend.

Usage:
  nix run nixpkgs#python3 -- generate_data.py \
      --har "kosningaprof.ruv.is_Archive [26-05-15 20-42-13].har" \
      --constituency 0000 \
      --out data.js
"""

import argparse
import json
import sys
import re
from pathlib import Path

# ── English translations ──────────────────────────────────────────────────────

PARTY_EN = {
    "Flokkur fólksins":                 "People's Party",
    "Framsóknarflokkur":                "Progressive Party",
    "Góðan daginn":                     "Good Morning",
    "Miðflokkur":                       "Centre Party",
    "Okkar borg":                       "Our City",
    "Píratar":                          "Pirate Party",
    "Samfylkingin - jafnaðarflokkur Íslands": "Social Democrats",
    "Sjálfstæðisflokkur":               "Independence Party",
    "Sósíalistaflokkur Íslands":        "Socialist Party",
    "Vinstrið":                         "Left Movement",
    "Viðreisn":                         "Reform Party",
}

# Icelandic range option text → English
RANGE_EN = {
    "Mun lægra": "Much lower",
    "Lægra":     "Lower",
    "Óbreytt":   "Unchanged",
    "Hærra":     "Higher",
    "Mun hærra": "Much higher",
}

# Priority category id → English label (from Q240 alternatives)
PRIORITY_EN = {
    "1":  "Public Transport",
    "2":  "Employment",
    "3":  "Local Character",
    "4":  "Municipal Finances",
    "5":  "Roads & Snow",
    "6":  "Housing",
    "7":  "Sports & Leisure",
    "8":  "Elderly Affairs",
    "9":  "Schools",
    "10": "Disability Affairs",
    "11": "Culture",
    "12": "Transport",
    "13": "Taxes & Fees",
    "14": "Waste Management",
}

# Question id → English translation (add more as needed)
QUESTION_EN = {
    "35":  "It is good to live in my municipality.",
    "38":  "I am satisfied with the services provided by the municipality.",
    "40":  "How should taxes and fees be compared to the current situation? (Range: Much lower → Much higher)",
    "42":  "When planning residential development, the emphasis should be on new neighbourhoods rather than densification.",
    "43":  "Citizen referendums should be more frequent so residents can participate in municipal decisions.",
    "45":  "Municipalities should be legally required to provide nursery school places from 12 months of age.",
    "47":  "The municipality should offer home-care payments so parents can stay home from end of parental leave until nursery school.",
    "49":  "Parents should be encouraged to shorten nursery school hours in return for fee discounts.",
    "50":  "The municipality should pursue further outsourcing of nursery and primary school operations.",
    "51":  "The municipality should subsidise children's sports and leisure activities more than it does now.",
    "52":  "More money should be spent supporting cultural life in the municipality.",
    "53":  "Child asylum-seekers should receive the same municipal services as other residents.",
    "54":  "Snow clearance and street cleaning is adequate in my municipality.",
    "55":  "The municipality should ease the way for new businesses with financial incentives.",
    "57":  "The municipality needs to increase financial assistance to residents living below the poverty line.",
    "59":  "Swimming pool opening hours should be extended, even if it costs the municipality money.",
    "60":  "Municipalities have gone too far in forcing residents to sort their waste.",
    "64":  "Municipalities should spend more on services for the elderly.",
    "239": "Municipalities should pay elderly citizens a leisure grant.",
    "69":  "The municipality should participate in the Capital Area Transport Accord.",
    "70":  "The Borgarlína (Bus Rapid Transit) project should be completed as currently planned.",
    "72":  "Car lanes should be reduced to make room for dedicated bus lanes.",
    "77":  "At least one parking space should accompany every dwelling in the municipality.",
    "78":  "There are too many private cars in traffic.",
    "79":  "It is right to restrict public access to the Heiðmörk nature reserve for water-source protection.",
    "28":  "[RVK] Reykjavík's neighbourhoods enjoy equal treatment in municipal services.",
    "29":  "[RVK] The so-called Reykjavík Model for nursery schools should be made permanent.",
    "30":  "[RVK] Planned changes to the layout of Suðurlandsbraut road must be prevented.",
    "31":  "[RVK] The planned Miklubraut tunnel should be cancelled.",
    "32":  "[RVK] Orkuveita Reykjavíkur (city energy utility) should be privatised.",
    "33":  "[RVK] Reykjavík Airport should remain at Vatnsmýri indefinitely.",
    "240": "Top priority issues (choose up to 3)",
}

# Question id → category for UI filtering
QUESTION_CAT = {
    "35":  "general",
    "38":  "general",
    "40":  "general",
    "42":  "housing",
    "43":  "general",
    "45":  "children",
    "47":  "children",
    "49":  "children",
    "50":  "children",
    "51":  "welfare",
    "52":  "welfare",
    "53":  "welfare",
    "54":  "general",
    "55":  "general",
    "57":  "welfare",
    "59":  "welfare",
    "60":  "environment",
    "64":  "welfare",
    "239": "welfare",
    "69":  "transport",
    "70":  "transport",
    "72":  "transport",
    "77":  "transport",
    "78":  "transport",
    "79":  "environment",
    "28":  "rvk",
    "29":  "rvk",
    "30":  "rvk",
    "31":  "rvk",
    "32":  "rvk",
    "33":  "rvk",
    "240": "general",
}


def slugify_name(name):
    """Simple slug for matching HAR URLs."""
    return re.sub(r"[^a-z0-9-]", "", name.lower().replace(" ", "-"))


def load_har(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def get_json_responses(har, url_substr):
    """Yield (url, parsed_json) for all HAR entries matching url_substr."""
    for entry in har["log"]["entries"]:
        url = entry["request"]["url"]
        if url_substr not in url:
            continue
        text = entry["response"]["content"].get("text", "")
        if not text:
            continue
        try:
            yield url, json.loads(text)
        except json.JSONDecodeError:
            pass


def extract_questions(har, constituency_id):
    """
    Return ordered list of question dicts applicable to the given constituency,
    plus a full dict of all questions by id.
    """
    for _, data in get_json_responses(har, "index.json"):
        try:
            qs = data["pageProps"]["app"]["questions"]
        except (KeyError, TypeError):
            continue
        if not qs:
            continue
        applicable = []
        for q in qs:
            ac = q.get("applicableConstituencies")
            if ac is None or constituency_id in ac:
                applicable.append(q)
        if applicable:
            return applicable
    return []


def extract_parties(har, constituency_id):
    """
    Return list of party dicts for the given constituency, deduplicated by name.
    Each dict: { name, abbr, color, slug, answers: {qid: {stringValue, important, value}} }
    """
    seen = {}
    for url, data in get_json_responses(har, "/flokkar/"):
        try:
            party = data["pageProps"]["party"]
        except (KeyError, TypeError):
            continue
        name = party.get("name", "")
        if not name or name in seen:
            continue
        # Only include parties running in target constituency
        running_in = [c["id"] for c in party.get("runningInConstituencies", [])]
        if constituency_id not in running_in:
            continue

        answers_raw = {}
        for ans in party.get("answers", []):
            qid = ans["questionId"]
            sv = ans.get("stringValue", "_")
            important = ans.get("important", False)
            val = ans.get("value")
            # For RANGE, resolve alternative text from English map
            qt = ans.get("questionType", "")
            if qt == "RANGE":
                alts = ans.get("question", {}).get("alternatives", [])
                alt_text = next((a["text"] for a in alts if a["id"] == str(val)), sv)
                answers_raw[qid] = {
                    "stringValue": alt_text + ("!" if important else ""),
                    "important": important,
                    "value": alt_text,
                    "type": "RANGE",
                }
            elif qt == "PRIORITY":
                answers_raw[qid] = {
                    "stringValue": sv,
                    "important": False,
                    "value": val if isinstance(val, list) else [],
                    "type": "PRIORITY",
                }
            else:
                # PROPOSITION
                clean = sv.rstrip("!") if isinstance(sv, str) else sv
                answers_raw[qid] = {
                    "stringValue": sv,
                    "important": important,
                    "value": clean,
                    "type": "PROPOSITION",
                }

        seen[name] = {
            "name": name,
            "nameEn": PARTY_EN.get(name, name),
            "abbr": party.get("abbreviation", "?"),
            "color": party.get("color", "#888"),
            "slug": party.get("slug", ""),
            "answers": answers_raw,
        }

    # Sort alphabetically by Icelandic name for deterministic output
    return sorted(seen.values(), key=lambda p: p["name"])


def build_data(har_path, constituency_id, reasoning_file="reasoning.json"):
    har = load_har(har_path)

    raw_questions = extract_questions(har, constituency_id)
    parties = extract_parties(har, constituency_id)

    # Build question list with English labels + categories
    questions = []
    for q in raw_questions:
        qid = q["id"]
        questions.append({
            "id": qid,
            "is": q.get("title", ""),           # Icelandic original
            "en": QUESTION_EN.get(qid, q.get("title", "")),  # English
            "type": q.get("type", "PROPOSITION"),
            "cat": QUESTION_CAT.get(qid, "general"),
        })

    # Build compact answers table: { qid: [ val_party0, val_party1, … ] }
    # val is the stringValue (already English for RANGE), or list for PRIORITY
    answers = {}
    for q in questions:
        qid = q["id"]
        row = []
        for p in parties:
            a = p["answers"].get(qid)
            if a is None:
                row.append("_")
            elif a["type"] == "PRIORITY":
                row.append(a["value"])          # list of category ids
            else:
                row.append(a["stringValue"])    # e.g. "C", "C!", "Lower", "Lower!"
        answers[qid] = row

    # Load translated reasonings if available
    # Structure: { party_name: { qid: "English reasoning text" } }
    reasoning_path = Path(reasoning_file)
    reasoning: dict = {}
    if reasoning_path.exists():
        with open(reasoning_path, encoding="utf-8") as f:
            reasoning = json.load(f)

    # Build reasoning table: { qid: [ reason_party0, … ] } — None if no reasoning
    reasonings = {}
    for q in questions:
        qid = q["id"]
        row = []
        for p in parties:
            r = reasoning.get(p["name"], {}).get(qid, None)
            row.append(r)
        # Only include if at least one party has a reasoning for this question
        if any(r for r in row):
            reasonings[qid] = row

    return {
        "meta": {
            "constituency": constituency_id,
            "source": "kosningaprof.ruv.is",
            "generated": __import__("datetime").datetime.utcnow().isoformat() + "Z",
        },
        "parties": [
            {k: v for k, v in p.items() if k != "answers"}
            for p in parties
        ],
        "questions": questions,
        "answers": answers,
        "reasonings": reasonings,
        "priorityCategories": PRIORITY_EN,
        "rangeEn": RANGE_EN,
    }


def main():
    parser = argparse.ArgumentParser(description="Generate data.js from a RÚV election quiz HAR file")
    parser.add_argument("--har",           default="kosningaprof.ruv.is_Archive [26-05-15 20-42-13].har",
                        help="Path to the .har file")
    parser.add_argument("--constituency",  default="0000",
                        help="Constituency ID to extract (default: 0000 = Reykjavík)")
    parser.add_argument("--out",           default="data.js",
                        help="Output JS file (default: data.js)")
    parser.add_argument("--reasoning",     default="reasoning.json",
                        help="Translated reasoning JSON (default: reasoning.json)")
    args = parser.parse_args()

    print(f"Loading HAR: {args.har}", file=sys.stderr)
    data = build_data(args.har, args.constituency, args.reasoning)

    n_parties   = len(data["parties"])
    n_questions = len(data["questions"])
    print(f"  Parties:   {n_parties}", file=sys.stderr)
    print(f"  Questions: {n_questions}", file=sys.stderr)
    print(f"  Writing:   {args.out}", file=sys.stderr)

    js = "// AUTO-GENERATED by generate_data.py — do not edit by hand.\n"
    js += "// Re-run:  nix run nixpkgs#python3 -- generate_data.py\n\n"
    js += "window.ELECTION_DATA = "
    js += json.dumps(data, ensure_ascii=False, indent=2)
    js += ";\n"

    Path(args.out).write_text(js, encoding="utf-8")
    print("Done.", file=sys.stderr)


if __name__ == "__main__":
    main()
