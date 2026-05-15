#!/usr/bin/env python3
"""
translate_reasoning.py  —  fetch reasoning texts from the HAR, translate
                            Icelandic → English via MyMemory, and write
                            reasoning.json used by the frontend.

Usage:
  nix run nixpkgs#python3 -- translate_reasoning.py \
      --har "kosningaprof.ruv.is_Archive [26-05-15 20-42-13].har" \
      --out reasoning.json

MyMemory free tier: ~1000 words/day without an API key.
Already-translated entries in --out are skipped (incremental).
"""

import argparse
import json
import sys
import time
import urllib.request
import urllib.parse
from pathlib import Path


# ── Translation ───────────────────────────────────────────────────────────────

def translate_mymemory(text: str, src="is", tgt="en") -> str:
    """Translate text via MyMemory free API. Returns translated string."""
    # MyMemory works best under ~500 chars; split longer texts at sentence boundaries
    chunks = split_text(text, max_len=480)
    parts = []
    for chunk in chunks:
        q = urllib.parse.quote(chunk)
        url = f"https://api.mymemory.translated.net/get?q={q}&langpair={src}|{tgt}"
        try:
            resp = urllib.request.urlopen(url, timeout=12)
            data = json.loads(resp.read())
            t = data["responseData"]["translatedText"]
            # MyMemory sometimes echoes back the source on failure
            if data["responseStatus"] == 200 and t and t.lower() != chunk.lower():
                parts.append(t)
            else:
                parts.append(chunk)  # fall back to original
        except Exception as ex:
            msg = str(ex)
            print(f"  [warn] translation error: {msg}", file=sys.stderr)
            if "429" in msg:
                print("  [rate limit] sleeping 60s...", file=sys.stderr)
                time.sleep(60)
                # retry once
                try:
                    resp = urllib.request.urlopen(url, timeout=12)
                    data = json.loads(resp.read())
                    t = data["responseData"]["translatedText"]
                    if data["responseStatus"] == 200 and t:
                        parts.append(t)
                        time.sleep(0.5)
                        continue
                except Exception:
                    pass
            parts.append(chunk)  # fall back to original
        time.sleep(0.35)  # be polite to the free API
    return " ".join(parts)


def split_text(text: str, max_len: int = 480):
    """Split text into chunks ≤ max_len at sentence boundaries."""
    if len(text) <= max_len:
        return [text]
    chunks, buf = [], ""
    for sentence in text.replace(".\n", ". ").split(". "):
        candidate = (buf + ". " + sentence).strip() if buf else sentence
        if len(candidate) <= max_len:
            buf = candidate
        else:
            if buf:
                chunks.append(buf.strip())
            buf = sentence
    if buf:
        chunks.append(buf.strip())
    return chunks or [text[:max_len]]


# ── HAR extraction ────────────────────────────────────────────────────────────

def extract_reasonings(har_path: str, constituency: str = "0000"):
    """
    Return dict: { party_name: { question_id: reasoning_is } }
    Only includes non-empty reasoning for parties running in given constituency.
    """
    with open(har_path, encoding="utf-8") as f:
        har = json.load(f)

    result = {}
    seen = set()

    for entry in har["log"]["entries"]:
        url = entry["request"]["url"]
        if "/flokkar/" not in url or ".json" not in url:
            continue
        text = entry["response"]["content"].get("text", "")
        if not text:
            continue
        try:
            data = json.loads(text)
            party = data["pageProps"]["party"]
        except Exception:
            continue

        name = party.get("name", "")
        if not name or name in seen:
            continue

        # Only parties running in target constituency
        running_in = [c["id"] for c in party.get("runningInConstituencies", [])]
        if constituency not in running_in:
            continue
        seen.add(name)

        party_reasons = {}
        for ans in party.get("answers", []):
            r = ans.get("reasoning", "") or ""
            if r.strip():
                party_reasons[ans["questionId"]] = r.strip()

        if party_reasons:
            result[name] = party_reasons

    return result


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--har", default="kosningaprof.ruv.is_Archive [26-05-15 20-42-13].har")
    parser.add_argument("--constituency", default="0000")
    parser.add_argument("--out", default="reasoning.json")
    args = parser.parse_args()

    # Load any already-translated data (incremental)
    out_path = Path(args.out)
    existing: dict = {}
    if out_path.exists():
        with open(out_path, encoding="utf-8") as f:
            existing = json.load(f)
        print(f"Loaded {sum(len(v) for v in existing.values())} existing translations from {args.out}", file=sys.stderr)

    print(f"Extracting from {args.har} ...", file=sys.stderr)
    reasonings = extract_reasonings(args.har, args.constituency)
    total = sum(len(v) for v in reasonings.values())
    print(f"Found {total} reasoning texts across {len(reasonings)} parties", file=sys.stderr)

    # Translate incrementally
    translated = {p: dict(qs) for p, qs in existing.items()}
    done = 0
    skipped = 0

    for party, qmap in sorted(reasonings.items()):
        t_party = translated.setdefault(party, {})
        for qid, text_is in sorted(qmap.items(), key=lambda x: int(x[0])):
            if qid in t_party:
                # Re-translate if the "translation" still looks Icelandic
                existing_t = t_party[qid]
                if not any(c in existing_t for c in 'þðæöÞÐÆÖ'):
                    skipped += 1
                    continue
                # else fall through and re-translate
            done += 1
            print(f"  [{done}/{total-skipped}] {party[:30]:30s} Q{qid}: {text_is[:50]}…", file=sys.stderr)
            t_party[qid] = translate_mymemory(text_is)
            # Save after every translation so we don't lose progress on crash
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(translated, f, ensure_ascii=False, indent=2)

    print(f"\nDone: {done} translated, {skipped} already cached → {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
