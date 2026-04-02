# Report Quality Gap Analysis — 2026-03-30

> Snapshot analysis of run quality at 2026-03-30.
> Current scope note (2026-04-01): Liquisto focus in this repo is now the
> excess-inventory path; repurposing/idle-data service lanes are no longer
> first-class targets in current briefing guidance.

## Gegenstand

Vergleich zwischen dem Deep-Research-Referenzbericht (`research-report-detail-expectation.md`)
und dem tatsächlichen Run-Output `20260329T214800Z` (ZF Friedrichshafen, zf.com).

---

## 1. Quantitative Differenz

| Dimension | Deep Research | Run Output | Delta |
|-----------|-------------|------------|-------|
| **Umsatz** | €38,8 Mrd. (2025) + €41,4 Mrd. (2024) + €46,6 Mrd. (2023) — 3 Jahre | €46,6 Mrd. (2023) — 1 Jahr, veraltet | Kein aktuellstes Jahr, keine Zeitreihe |
| **EBIT-Marge** | 4,5% (2025), 3,6% (2024), 5,1% (2023) — Trend sichtbar | Nur 2023-Werte | Kein Trend |
| **Nettoverlust** | −2,1 Mrd. € (2025) inkl. 1,6 Mrd. Einmaleffekt | Nicht gefunden | Kritisches Signal fehlt komplett |
| **Vorräte (Bilanz)** | 4,998 Mrd. € aufgeschlüsselt (RHB 2,0 / WIP 1,8 / FG 1,1) + 324 Mio. Wertminderung | Nicht gefunden | **Zentraler Liquisto-Hebel fehlt** |
| **Eigentümerstruktur** | 93,8% Zeppelin-Stiftung, 6,2% Ulderup-Stiftung | Nicht gefunden | Governance-Kontext fehlt |
| **Divisionsstruktur** | 7 Divisionen einzeln beschrieben mit Produkten | 4 generische Produktkategorien | Keine Divisionstiefe |
| **ADAS-Verkauf** | Harman, EV 1,5 Mrd., H2 2026, 3.750 MA | Nicht gefunden | Carve-out-Opportunity fehlt |
| **Kontakte Zielunternehmen** | 9 namentliche ZF-Vorstände/-Führungskräfte mit Rolle + Meeting-Angle | 0 ZF-Kontakte | **Komplett fehlend** |
| **Kontakte Buyer-Seite** | Hypothesenbasiert, korrekt als solche markiert | 13 Kontakte, aber nur bei Bosch/Denso/Magna — keine bei ZF | Falsche Zielrichtung |
| **Buyer-Kandidaten (benannt)** | LKQ, Inter Cars, Genuine Parts, Ritchie Bros. | Fiat Chrysler, generische Kategorien | Keine echten Sekundärmarkt-Buyer |
| **Inventory-Signale** | 324 Mio. Wertminderung, Slow-Moving, Obsoleszenz | `inventory_signals: []` | **Null** |
| **Excess-Inventory-These** | Bilanz-, Working-Capital- und Buyer-Signale stützen einen Inventory-to-Cash-Fall | Teilweise generische Signale | Finanz- und Buyer-Substanz muss zusammenkommen |
| **Opportunity Assessment** | "Excess Inventory" klar begründet oder sauber als weitere Validierung markiert | Uneindeutige oder generische Empfehlung | Kein sauberer Leading Path |
| **Meeting-Angle** | "Inventory-to-Cash ohne OE-Risiko" + 5 konkrete Validierungsfragen | Generische Meeting Actions | Nicht meeting-actionable |
| **Quellenregister** | Gruppiert nach Typ, 30+ Quellen mit Kontext | Flache URL-Liste | Keine Quellenqualität |

---

## 2. Qualitative Kerndefizite

### A. Keine Bilanz-/Finanzdatenextraktion

Das Deep-Research-Ergebnis extrahiert aus dem ZF-Geschäftsbericht 2025:
- Vorräte aufgeschlüsselt nach RHB/WIP/FG
- Wertminderungen (324 Mio. €)
- Nettoverlust (−2,1 Mrd. €)
- Einmaleffekt E-Mobilität (1,6 Mrd. €)
- Net Debt (10,2 Mrd. €)

Der Run findet **nichts davon**. Grund: Die Worker-Queries sind zu generisch
("ZF Friedrichshafen revenue growth financial results") und die Suchtiefe
reicht nicht bis zu Geschäftsberichten/Konzernanhängen. Der LLM-Synthesizer
bekommt keine Bilanzseiten als Input.

**Auswirkung**: Der zentrale Liquisto-Hebel (Working-Capital-Monetization)
ist im Run-Output unsichtbar.

### B. Keine Zielunternehmen-Kontakte

Deep Research identifiziert 9 ZF-Führungskräfte (CEO, CFO, CHRO, CPO,
Divisionsleiter) mit konkreten Meeting-Angles pro Person.

Der Run sucht Kontakte **nur bei Buyer-Firmen** (Bosch, Denso, Magna) —
nicht beim Zielunternehmen selbst. Das ist ein fundamentaler Architektur-Fehler
im Contact-Department: Die Aufgabenstellung "Kontakte bei Buyer-Firmen" ist
korrekt für Buyer-seitige Intelligence, aber es fehlt komplett die
**Zielunternehmen-Kontakt-Discovery** (wer bei ZF ist der richtige
Ansprechpartner für Liquisto?).

**Auswirkung**: Das Briefing kann nicht beantworten, wen Liquisto bei ZF
ansprechen soll.

### C. Keine Transaktions-/Event-Intelligence

Deep Research findet:
- ADAS-Verkauf an Harman (1,5 Mrd. €, H2 2026)
- Foxconn-JV (Chassis Modules)
- Division-E-Restrukturierung (terminierte E-Mobility-Programme)
- IAS-8-Korrekturen

Der Run findet nur generische Restrukturierungssignale. Grund: Die Queries
suchen nicht gezielt nach M&A, Carve-outs, JVs oder regulatorischen Events.

**Auswirkung**: Carve-out-Bereinigung als Opportunity-Angle fehlt komplett.

### D. Keine Produkt-/Asset-Granularität

Deep Research liefert eine Tabelle mit 14 Asset-Kategorien, jeweils mit:
- hergestellt/distribuiert/gehalten
- Liquisto-Relevanz
- Evidenz + Confidence

Der Run liefert 4 generische Produktkategorien ohne Klassifikation nach
Monetization-Eignung.

**Auswirkung**: Keine Basis für Pilot-Scope-Definition.

### E. Opportunity Assessment ohne Priorisierung

Deep Research: "Mixed/Staged mit Start über Excess Inventory" — klar begründet
mit Vorratsdaten, Wertminderungen, Deleveraging-Fokus.

Run: Alle 3 Pfade "medium" — keine Differenzierung, keine Begründung warum
einer führt.

**Auswirkung**: Der Liquisto-Kollege weiß nicht, womit er anfangen soll.

---

## 3. Ursachenanalyse — Warum liefert das Repo diese Qualität nicht?

### U1. Suchtiefe und Quellenqualität

| Problem | Detail |
|---------|--------|
| **Zu wenige Queries pro Task** | Vor dem Fix lag das Default-Limit effektiv bei nur 4 Queries und maximal 5 eindeutigen Ergebnissen insgesamt. Deep Research durchsucht 30+ Quellen. |
| **Keine Geschäftsbericht-Extraktion** | Kein Query zielt auf "annual report", "Geschäftsbericht", "Konzernanhang", "Vorräte", "inventory". |
| **Keine PDF-/Dokument-Analyse** | Vor dem Fix holte der Page-Fetcher nur HTML-Seiten und nur die ersten 2 Result-URLs. Geschäftsberichte sind PDFs. |
| **Kein gezieltes Suchen nach Events** | Keine Queries für M&A, Carve-outs, JVs, regulatorische Meldungen. |
| **Search-Cache teilt Ergebnisse** | Mehrere Tasks teilen denselben Search-Cache → spätere Tasks bekommen keine neuen Ergebnisse. |

### U2. Prompt-Architektur

| Problem | Detail |
|---------|--------|
| **Worker-Prompts zu generisch** | "Build verified company fundamentals" statt "Extract balance sheet inventory positions, write-downs, debt levels from the latest annual report". |
| **Keine Bilanz-/Finanzdaten-Prompts** | Kein Task fragt explizit nach Vorräten, Working Capital, Wertminderungen, Net Debt. |
| **Keine Zielunternehmen-Kontakt-Prompts** | Contact-Tasks suchen nur bei Buyer-Firmen, nicht beim Zielunternehmen. |
| **Keine Event-/Transaktions-Prompts** | Kein Task sucht gezielt nach M&A, Carve-outs, JVs. |
| **Opportunity Assessment ohne Bilanz-Input** | Synthesis bewertet Pfade ohne Vorrats-/Finanzdaten → kann nicht priorisieren. |

### U3. Architektur-Lücken

| Problem | Detail |
|---------|--------|
| **Kein "Financial Deep Dive" Task** | Es fehlt ein dedizierter Task für Bilanz-/Finanzdatenextraktion. |
| **Kein "Target Company Contacts" Task** | Contact-Department sucht nur Buyer-Kontakte, nicht Zielunternehmen-Kontakte. |
| **Kein "Transaction/Event Intelligence" Task** | Kein Task für M&A, Carve-outs, JVs, regulatorische Events. |
| **Kein PDF-Fetcher** | Geschäftsberichte, Konzernanhänge, Investor-Presentations sind PDFs — der Fetcher kann sie nicht lesen. |
| **Kontextfluss zu eng** | Departments bekamen nur ihre aktuelle Section, nicht den bisher aufgebauten admitted Kontext anderer Sections. |
| **Peer-/Buyer-Vermischung im Contact-Input** | Contact-Queries wurden aus `peer_competitors` und `downstream_buyers` gespeist; damit wurden Wettbewerber fälschlich als Buyer-Kandidaten behandelt. |
| **Keine iterative Vertiefung** | Deep Research vertieft bei starken Signalen. Der Run macht einen Durchlauf pro Task. |
| **Synthesis ohne Bilanz-Grounding** | Opportunity Assessment hat keinen Zugang zu Vorrats-/Finanzdaten. |

### U4. Evidenz-Bewertung

| Problem | Detail |
|---------|--------|
| **Keine Confidence-Differenzierung pro Claim** | Deep Research trennt "Fakt: Hoch / Inferenz: Mittel". Der Run hat nur packet-level Confidence. |
| **Keine Fakt-vs-Inferenz-Trennung** | Alle Facts werden gleich behandelt — keine Markierung von Inferenzen. |
| **Keine Quellenqualität-Bewertung** | Wikipedia und Pressemitteilungen werden gleich gewichtet. |

### U5. Zusätzliche repo-validierte Erkenntnisse aus der Codeprüfung

| Befund | Detail |
|--------|--------|
| **Result-Cap war härter als im Report angenommen** | Nicht 12 Resultate pro Task, sondern im Default nur 5 eindeutige Treffer insgesamt. |
| **Page-Fetch war doppelt limitiert** | Selbst wenn die Suche mehr fand, wurden nur 2 Seiten weiterverarbeitet. |
| **Contact-Department hatte keinen Zielunternehmen-Pfad** | Es gab keinen eigenen Task und kein eigenes Schema für Kontakte beim Zielunternehmen. |
| **Synthesis war strukturell auf "medium/unclear" ausgerichtet** | Ohne Finanz-Grounding entstanden Pfade eher als unpriorisierte Service-Relevanz statt als evidenzbasierte Rangfolge. |
| **EvidencePacket war für Claim-Level-Qualität zu flach** | Es fehlten explizite Felder für `claim_type` und `source_quality`. |

---

## 4. Konkrete Maßnahmen (priorisiert)

### P1 — Neue Tasks im Backlog (Architektur)

| Neuer Task | Department | Ziel |
|-----------|-----------|------|
| `financial_deep_dive` | CompanyDepartment | Bilanz-/Finanzdaten: Vorräte, Working Capital, Wertminderungen, Net Debt, EBIT-Trend, Einmaleffekte |
| `target_company_contacts` | ContactDepartment | Führungskräfte beim Zielunternehmen: Vorstand, CPO, Divisionsleiter, Aftermarket-Head |
| `transaction_event_intelligence` | CompanyDepartment | M&A, Carve-outs, JVs, regulatorische Events, Programmbeendigungen |

### P2 — Suchtiefe erhöhen (Worker)

| Maßnahme | Detail |
|----------|--------|
| Queries pro Task von 4 auf 6–8 erhöhen | Besonders für financial_deep_dive und contacts |
| Geschäftsbericht-Queries hinzufügen | `"ZF Friedrichshafen" Geschäftsbericht 2025 Vorräte inventory` |
| Event-Queries hinzufügen | `"ZF Friedrichshafen" M&A acquisition divestiture carve-out 2024 2025` |
| Zielunternehmen-Kontakt-Queries | `"ZF Friedrichshafen" Vorstand CPO procurement officer site:linkedin.com` |
| Mehr Seiten nach Search weiterverarbeiten | Nicht nur 2 HTML-Seiten, sondern auch PDFs/Dokumente berücksichtigen |

### P3 — Prompt-Qualität (Worker LLM)

| Maßnahme | Detail |
|----------|--------|
| Financial-Task-Prompt | Explizit nach Vorräten, Wertminderungen, Net Debt, EBIT-Trend fragen |
| Contact-Task-Prompt | Zwischen Zielunternehmen-Kontakten und Buyer-Kontakten unterscheiden |
| Opportunity-Prompt | Bilanz-/Finanzdaten als Input für Pfad-Priorisierung verlangen |
| Fakt-vs-Inferenz | Im Prompt verlangen, dass jeder Claim als Fakt/Inferenz/Hypothese markiert wird |

### P4 — PDF-Fetcher (Infrastruktur)

| Maßnahme | Detail |
|----------|--------|
| PDF-Download + Text-Extraktion | Geschäftsberichte, Investor-Presentations, Konzernanhänge |
| Priorität: Hoch | Ohne PDF-Zugang fehlen die wichtigsten Finanzdaten |

### P5 — Synthesis-Grounding (Architektur)

| Maßnahme | Detail |
|----------|--------|
| Bilanz-/Finanzdaten als Synthesis-Input | Vorräte, Wertminderungen, Net Debt als strukturierte Felder |
| Opportunity-Priorisierung mit Finanzdaten | "Excess Inventory" nur als Leading Path wenn Vorratsdaten das stützen |
| Meeting-Angle aus Evidenz ableiten | Nicht generisch, sondern "Inventory-to-Cash" wenn Vorräte > X |

### P6 — Evidenz-Qualität (Runtime)

| Maßnahme | Detail |
|----------|--------|
| Confidence pro Claim (nicht nur pro Packet) | Fakt / starke Inferenz / schwaches Signal |
| Quellenqualität-Scoring | Geschäftsbericht > Pressemitteilung > Wikipedia > generische Suche |
| Fakt-vs-Inferenz-Flag im EvidencePacket | `claim_type: "fact" | "inference" | "hypothesis"` |

---

## 5. Umsetzungs-Checkliste im Repo

- [x] Neue Tasks ergänzt: `financial_deep_dive`, `transaction_event_intelligence`, `target_company_contacts`
- [x] Section-/Task-Schemas ergänzt für Finanzdaten, Event-Intelligence und Zielunternehmen-Kontakte
- [x] Worker-Queries und LLM-Prompts für Financial-, Event- und Target-Contact-Research vertieft
- [x] Query-/Fetch-Tiefe erhöht und PDF-Fetching mit Text-Extraktion ergänzt
- [x] Department-Kontextfluss erweitert und Peer-/Buyer-Vermischung im Contact-Input behoben
- [x] `EvidencePacket` um `claim_type` und `source_quality` erweitert
- [x] Synthesis-Grounding verbessert: Finanzsignale beeinflussen Pfad-Ranking und Opportunity-Summary
- [x] Architektur-/Smoke-Tests auf den neuen Vertragsstand angepasst und ausgeführt

## 6. Erwartete Wirkung

Wenn P1–P6 umgesetzt sind, sollte ein Run für ZF Friedrichshafen liefern:

- Vorräte 4,998 Mrd. € aufgeschlüsselt + 324 Mio. Wertminderung
- 5+ ZF-Führungskräfte mit Meeting-Angle
- ADAS-Verkauf an Harman als Carve-out-Opportunity
- "Excess Inventory / Stock Monetization" als klarer Leading Path
- "Inventory-to-Cash ohne OE-Risiko" als konkreter Meeting-Angle
- Confidence-Differenzierung pro Claim

Das entspricht dem Qualitätsniveau des Deep-Research-Referenzberichts.

---

## 7. Runtime-Update 2026-04-02 (department-spezifische KB und Gates)

Dieses Dokument bleibt eine historische Gap-Analyse (Stand 2026-03-30).
Seit 2026-04-02 wurden zusätzlich folgende Runtime-Mechanismen umgesetzt:

- Department-spezifische Source-KB:
  - `knowledge/sources/company.yaml`
  - `knowledge/sources/market.yaml`
  - `knowledge/sources/buyer.yaml`
  - `knowledge/sources/contact.yaml`
- Department-spezifische Policy-KB:
  - `knowledge/policies/company.yaml`
  - `knowledge/policies/market.yaml`
  - `knowledge/policies/buyer.yaml`
  - `knowledge/policies/contact.yaml`
- Acceptance-time Policy-Gates pro Department:
  - Pflichtfelder
  - Mindest-Evidenzregeln
  - strukturierte Blocker mit Owner und Next Step
- Kontakt-Lücken werden explizit als `keine freien Quellen` geführt, statt pauschal `n/v`.
- Conversable-Agent-Prinzip bleibt unverändert:
  - freie Department-Kommunikation bleibt erhalten
  - kein starrer Dialogablauf durch Policies
  - Gates greifen erst bei Package-Finalisierung und Readiness-Bewertung
