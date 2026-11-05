# Ärzteabgleich

Single-user web app that matches an external doctor list to a validated Referenzliste (Ärztekammer master data). One person has one Evo-ID. A new reference file replaces the current version and leaves a short upload log.

## Run

```bash
cd arzt-abgleich
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Open http://127.0.0.1:5001/

On the first visit, create the only user. The password is hashed with Argon2 and is not stored in the repository. There is no second factor.

Optional environment variables:

- `PORT` (default `5001`)
- `HOST` (default `0.0.0.0`)
- `ARZT_DEBUG=1` turns on the Flask debugger. Leave it off outside a local session.

Sample files (fictional doctors):

- `samples/referenzliste.csv`
- `samples/externe_liste.csv`

The reference sample includes one duplicate Evo-ID so the upload log shows that the second row was skipped.

## Flow

1. **Referenzliste** — upload Excel (`.xlsx`) or CSV once. Replacing it asks for confirmation. Older versions stay in the upload log with date, file name, row count, and a short note.
2. **Externe Liste** — upload Excel or CSV with Titel, Vorname, Nachname, PLZ, Ort, and customer-id columns. ÖK-Nummer, One-Key-Nummer, and Hauptfach are used when the file has them.
3. **Prüfen** — rows are grouped into Automatisch, Sehr wahrscheinlich, Wahrscheinlich, Unsicher, Wahrscheinlich falsch, Kein Treffer, and Manuell. Each row shows only its best candidate. You can accept it, mark it as no match, or assign another Evo-ID.
4. **Export** — Excel is the primary download. CSV (UTF-8 with BOM) is next to it.

Accepted or manually assigned rows stay locked when you run “Offene Zeilen neu abgleichen”.

## Matching

Text is lowercased, `ä/ö/ü/ß` become `ae/oe/ue/ss`, and other punctuation becomes a space so double names (`Müller-Schmidt`, `Mueller Schmidt`) compare as tokens. rapidfuzz `token_set_ratio` and `token_sort_ratio` score those tokens.

- Exact ÖK-Nummer or One-Key-Nummer: 100 %, status **Automatisch**.
- If those two ids point at different people, the row stays **Unsicher**.
- Otherwise the score is a percentage of name (60 %), address (25 %), and specialty (15 %). Missing specialty or address is left out and the remaining weights are rescaled.
- Fuzzy score ≥ 92: **Sehr wahrscheinlich**. Score ≥ 85 and < 92: **Wahrscheinlich**. Score ≥ 75 and < 85: **Unsicher**. Score ≥ 40 and < 75: **Wahrscheinlich falsch** (the candidate is kept, but it is probably the wrong doctor). Below 40: **Kein Treffer**, with no candidate.

An external id that is not in the reference list keeps a name match from being automatic; the row is capped at **Unsicher**.

## Tests

```bash
cd arzt-abgleich
python -m unittest discover -s tests -t .
```

## Security

This is a single-user tool. Keep it on a trusted network. The session secret is written to `arzt-abgleich/instance/secret_key` on first start, and the database is `arzt-abgleich/instance/arzt.db`. Neither directory is meant to be committed.
