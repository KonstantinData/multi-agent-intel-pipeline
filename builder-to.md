# Builder To-Do: Zielbild fuer ZIEHL-ABEGG-Qualitaet

Stand: 2026-03-31

Hinweis zur Semantik dieser Checkliste:
- `[x]` bedeutet in dieser Datei: technisch umgesetzt und fuer die End-to-End-Abnahme nicht mehr blocker-relevant.
- `[ ]` bedeutet: noch nicht sauber genug umgesetzt oder noch nicht mit dem erwarteten Ergebnis durch einen frischen Run bestaetigt.
- Ein Punkt gilt erst dann als wirklich abgeschlossen, wenn das Runtime-Verhalten, die Artefakte und das Ergebnisbild zusammen stimmen.

## 1. Ausgangspunkt

- [x] Referenz-DOCX analysiert: `/Users/konstantinmac/Downloads/Ziehl-Abegg Pre-Meeting Briefing Gemini.docx`
- [x] Referenz-PDF analysiert: `/Users/konstantinmac/Downloads/ZIEHL-ABEGG_Strategic_Playbook.pdf`
- [x] Ist-Run analysiert: `/Users/konstantinmac/Documents/repositories/multi-agent-intel-pipeline/artifacts/runs/20260330T210106Z`
- [x] Zielbild als Strategic Playbook statt Datenablage abgeleitet und in Runtime, UI und PDF uebersetzt.

## 2. Nicht verhandelbare Zielkriterien

- [x] Der Report funktioniert jetzt als Strategic Playbook und nicht nur als Datenausgabe.
- [x] Hauptsektionen folgen jetzt der Logik `Erkenntnis -> Relevanz fuer Liquisto -> Konsequenz -> Validierungsbedarf`.
- [x] PDF und UI sind getrennt: PDF = kuratierte Entscheiderfassung, UI = Evidence / Backlog / Rohsignale.
- [x] `12.1 Zielunternehmens-Kontakte` trennt jetzt sauber zwischen benannten Stakeholdern, fehlenden Rollen und Zugangspfad.
- [x] `16. Offene Fragen` ist auf 3 bis 5 deal-kritische Fragen verdichtet.
- [x] `17. Empfohlene naechste Schritte` ist als operativer Aktionsplan mit Phase, Owner und Erfolgsdefinition modelliert.
- [x] Ein Run wird jetzt blockiert, wenn die Synthese nur Fallback / max-round / inhaltlich nicht tragfaehig ist.

## 3. Zielbild aus den Referenzdokumenten

### 3.1 Was die Referenzdokumente richtig machen

- [x] Die Top-These steht jetzt im Executive-Teil direkt vorne.
- [x] Abschnitte sind argumentativ statt nur beschreibend aufgebaut.
- [x] Kontakt-Abschnitte trennen Zielunternehmen von Buyer-/Partner-Kontakten.
- [x] Kontakte werden entlang Rolle, Relevanz, Buying Center, Kanal und Verifikation aufbereitet.
- [x] Offene Fragen werden als harte Validierungsfragen statt Gap-Liste modelliert.
- [x] Naechste Schritte sind in operative Handlungen uebersetzt.
- [x] Die Kernhypothese ist an Inventar, Working Capital, Nachfrageverschiebung und Ansprechpartner gekoppelt.

### 3.2 Erwartetes Soll fuer `12.1 Zielunternehmens-Kontakte`

- [x] Jede Kontaktzeile hat strukturierte Kernfelder.
- [x] `Name`
- [x] `Rolle`
- [x] `Organisation / Standort`
- [x] `Relevanz & Buying Center`
- [x] `Profil / Kontaktkanal`
- [x] `Quelle & Verifikation`
- [x] `Confidence`
- [x] Direkte Kontaktinfos werden nur mit belastbarer Quelle in die sichtbare Darstellung uebernommen.
- [x] Fehlende Namen erscheinen als getrennte Rollen-Archetypen.
- [x] Die Sektion benennt explizit fehlende kritische Rollen und den Schliessungspfad.
- [x] Absurde oder fachfremde Buyer-Kontakte werden aus dem Zielkontaktblock ausgeschlossen.

### 3.3 Erwartetes Soll fuer `16. Offene Fragen`

- [x] Maximal 5 Fragen.
- [x] Jede Frage beeinflusst materiell den Deal oder die Pfadpriorisierung.
- [x] Jede Frage traegt ein klares Business-Label.
- [x] Jede Frage ist an die Hauptthese angeschlossen.
- [x] Jede Frage ist im Meeting konkret stellbar.
- [x] Triviale Stammdatenluecken werden nicht mehr automatisch in die Top-5 aufgenommen.

### 3.4 Erwartetes Soll fuer `17. Empfohlene naechste Schritte`

- [x] Die Schritte sind in eine echte Sequenz uebersetzt.
- [x] `vor dem Meeting`
- [x] `im Meeting`
- [x] `unmittelbar nach dem Meeting`
- [x] `Follow-up / NDA / Datenanforderung`
- [x] Jeder Schritt hat die benoetigten Felder.
- [x] `Owner`
- [x] `Zeitpunkt`
- [x] `Ziel`
- [x] `konkrete Aktion`
- [x] `erwartetes Ergebnis`
- [x] `Abbruch- oder Erfolgskriterium`
- [x] Die Schritte zahlen auf Kontakte, Dokumente und Hypothesen ein.

## 4. Ist-Zustand aus Run `20260330T210106Z`

Diese Sektion ist als Analyse des alten Delta-Runs abgeschlossen.

### 4.1 Positives

- [x] Der Run wurde formal analysiert.
- [x] Zielunternehmenskontakte wurden als vorhandener erster Fortschritt identifiziert.
- [x] Das Layout wurde als scanbarer als fruehere Runs bewertet.
- [x] Die bisherige Drei-Pfad-Priorisierung wurde dokumentiert und anschliessend auf den alleinigen Zielpfad `excess_inventory` bereinigt.

### 4.2 Harte Defizite

- [x] Unfertige Synthese und konservativer Fallback wurden dokumentiert.
- [x] Leerer Financial Deep Dive wurde dokumentiert.
- [x] Ueberlange `open_gaps` und `next_steps` wurden dokumentiert.
- [x] Schwache Buyer-Kontaktqualitaet wurde dokumentiert.
- [x] Zu flache Stakeholder-/Question-Sektionen wurden dokumentiert.

### 4.3 Spezifische Delta-Befunde fuer die drei Problemsektionen

- [x] `12.1 Zielunternehmens-Kontakte` wurde als fehlende Stakeholder-Map analysiert.
- [x] `16. Offene Fragen` wurde als aus `quality_review.open_gaps` abgeleiteter Fehlansatz analysiert.
- [x] `17. Empfohlene naechste Schritte` wurde als generischer Task-Backlog statt Playbook analysiert.

## 5. Best Practice / State of the Art 2026

### 5.1 Executive Briefings und Report-Design

- [x] Decision-first statt chronology-first als Leitprinzip recherchiert und umgesetzt.
- [x] Wichtigste Aussage zuerst.
- [x] Klare Heading-Hierarchie und scanbare Sektionen.
- [x] Tabellen/Karten statt langer Fliesstexte.
- [x] Kleine, klare Tabellen mit einer Bedeutung pro Zelle.
- [x] Sichtbare Navigations- und Struktur-Logik fuer laengere Dokumente.

### 5.2 Contact Intelligence / Buying Group / Stakeholder Mapping

- [x] Buying-Group-Logik statt Single-Champion-Logik verankert.
- [x] Multi-Threading ins Buying Center als Zielstruktur umgesetzt.
- [x] Named contacts, role archetypes, missing stakeholders und outreach path getrennt modelliert.
- [x] Contact Intelligence account-zentriert modelliert.
- [x] Rollenspezifische Ansprache trotz LLM-getriebener Buyer-Recherche als Best Practice beruecksichtigt.

### 5.3 Open Questions und Next Steps

- [x] Offene Fragen muessen Entscheidung und Naechsthandlung beeinflussen.
- [x] Naechste Schritte sind als Mutual Action Plan / First-Meeting-Playbook modelliert.
- [x] Verantwortliche, Milestones, Timing und Definition of Done sind verankert.
- [x] Fragen und Schritte sind direkt an Stakeholder und Hypothesen gekoppelt.

## 6. Vollstaendige Umsetzungs-Checkliste

### A. Datenmodell und Contracts

- [x] Neues strukturiertes Modell `target_company_contact_card` eingefuehrt.
- [x] Neues strukturiertes Modell `missing_target_role` eingefuehrt.
- [x] Neues strukturiertes Modell `critical_open_question` eingefuehrt.
- [x] Neues strukturiertes Modell `recommended_next_step` eingefuehrt.
- [x] Modelle in `src/models/schemas.py` und betroffenen Contracts verankert.
- [x] Explizite Felder fuer `verified_channel_type` eingefuehrt.
- [x] `linkedin`
- [x] `company website`
- [x] `email`
- [x] `phone`
- [x] `assistant / switchboard`
- [x] `press contact`
- [x] Explizites Feld `verification_status` eingefuehrt.
- [x] `verified`
- [x] `partially_verified`
- [x] `role_inferred`
- [x] `unverified_excluded_from_pdf`
- [x] Feld `buying_center_role` eingefuehrt.
- [x] `economic_buyer`
- [x] `operational_sponsor`
- [x] `technical_owner`
- [x] `procurement_gatekeeper`
- [x] `aftermarket_owner`
- [x] `plant_owner`
- [x] Feld `meeting_criticality` fuer offene Fragen eingefuehrt.
- [x] `must_answer_before_meeting`
- [x] `must-answer-in-meeting`
- [x] `can-be-validated-after-meeting`
- [x] Feld `step_phase` fuer naechste Schritte eingefuehrt.
- [x] `pre_meeting`
- [x] `during_meeting`
- [x] `post_meeting`
- [x] `post_meeting_under_nda`

### B. `12.1 Zielunternehmens-Kontakte` fachlich neu bauen

- [x] Kontaktsektion in drei Bloecke getrennt.
- [x] `Named target-company stakeholders`
- [x] `Critical missing roles`
- [x] `Recommended access path / escalation path`
- [x] Nur Zielunternehmenskontakte in `12.1`.
- [x] Buyer-/Partnerkontakte in Folgesektion.
- [x] Kontakte nach Buying Center statt Prominenz priorisiert.
- [x] CEO/CFO nicht automatisch auf Platz 1.
- [x] Zusatztabelle `fehlende Schluesselrollen` eingebaut.
- [x] `gesuchte Rolle`
- [x] `warum kritisch`
- [x] `wahrscheinlicher Organisationsbereich`
- [x] `bester Suchkanal`
- [x] `naechste Suchaktion`
- [x] Lokale operative Rollen fuer HQ/Werk priorisiert.
- [x] Werkleiter Polen
- [x] Werkleiter Kupferzell / Deutschland
- [x] Head of Supply Chain DACH / EU
- [x] Head of Procurement / Material Management
- [x] Aftermarket / Spare Parts / Service Parts Lead
- [x] Kontakte mit `verification_status == unverified_excluded_from_pdf` werden aus der PDF-Sicht ausgeschlossen.
- [x] Direkte E-Mail/Telefon nur bei belastbarer Quelle.
- [x] Rollen-Archetypen werden nie als echte Kontakte ausgegeben.
- [x] `outreach rationale` pro Kontakt erzeugt.
- [x] Warum dieser Kontakt jetzt?
- [x] Welche Hypothese testet er?
- [x] Was ist der beste Gespraechseinstieg?
- [x] Was ist der wahrscheinlichste Einwand?

### C. Contact Discovery Runtime verbessern

- [x] Buyer-Kandidaten werden aus echten Markt-/Asset-Pfaden abgeleitet.
- [x] Schwache, fachfremde oder Jobposting-Funde werden aus dem PDF ausgeschlossen.
- [x] Mindestqualitaet fuer Buyer-Kontakte definiert.
- [x] Name vorhanden
- [x] Firma vorhanden
- [x] Rolle vorhanden
- [x] Bezug zu Asset-Pfad vorhanden
- [x] Kontaktquelle vorhanden
- [x] Verifikationslevel ausreichend
- [x] Suchstrategien fuer Target Contacts erweitert.
- [x] Press releases
- [x] Management pages
- [x] corporate governance
- [x] regional legal entities
- [x] trade fair speaker lists
- [x] association memberships
- [x] local registries
- [x] Suchstrategien fuer Buyer Contacts erweitert.
- [x] distributor network
- [x] aftermarket partners
- [x] retrofit / service providers
- [x] OEMs in identifizierten Zielsegmenten
- [x] Keine Buyer-Kontakte mit geringer Asset-Fit-Plausibilitaet in die PDF.

### D. `16. Offene Fragen` neu konzipieren

- [x] Neue Generator-Logik statt Durchreichen von `quality_review.open_gaps`.
- [x] Fragen muessen Hauptpfad / Monetisierbarkeit / Stakeholder-Strategie / NDA-Bedarf beeinflussen.
- [x] Harte Begrenzung auf maximal 5 Fragen.
- [x] Jede Frage hat:
- [x] `Label`
- [x] `Frage`
- [x] `warum kritisch`
- [x] `welche Hypothese wird getestet`
- [x] `wer kann sie beantworten`
- [x] `wann wird sie beantwortet`
- [x] `was aendert sich je nach Antwort`
- [x] Fragen nach kommerziellem Impact sortiert.
- [x] Generische Stammdatenfragen aus der PDF verbannt.
- [x] Fragegenerator aus Opportunity Thesis und Contact Map gespeist.
- [x] Pflichtlogik verankert.
- [x] Bestandsvolumen
- [x] Standardisierungsgrad
- [x] WIP-Stufe
- [x] Obsoleszenzrisiko
- [x] interne Compliance / Brand Protection

### E. `17. Empfohlene naechste Schritte` in Mutual-Action-Plan-Logik umbauen

- [x] `recommended_next_steps` als eigenes strukturiertes Objekt aufgebaut.
- [x] Keine generischen Recherche-To-Dos in der PDF.
- [x] Jeder Schritt mit `owner`, `phase`, `action`, `target person`, `asset hypothesis`, `output`, `success criterion`, `dependency` modelliert.
- [x] Schritte in vier Gruppen ausgebbar.
- [x] `Sofortmassnahmen vor Outreach`
- [x] `konkrete Fragen im Meeting`
- [x] `direkt nach dem Meeting`
- [x] `unter NDA anzufordernde Daten`
- [x] Optionaler Block `telefonische / operative Eskalation`, wenn direkte Rollen nicht gefunden wurden.
- [x] Schritte direkt an offene Fragen gekoppelt.
- [x] Schritte direkt an priorisierte Kontakte gekoppelt.
- [x] Schritte direkt an die Haupthypothese gekoppelt.
- [x] Jeder Schritt hat Definition of Done.
- [x] Der erste Schritt ist nie nur `more research`.
- [x] Der erste Schritt ist immer kommerziell oder kontaktbezogen.

### F. Synthese und Readiness-Gating absichern

- [x] `meeting_ready` blockiert bei untragfaehiger Synthese.
- [x] `synthesis.executive_summary` Fallback-Text
- [x] `opportunity_assessment_summary` max-round-/Fehlertext
- [x] leerer Financial Deep Dive bei finanzgetriebenem Hauptpfad
- [x] zu wenig valide Target-Kontakte
- [x] Readiness-Scoring getrennt nach Komponenten.
- [x] Synthesevollstaendigkeit separat
- [x] Kontaktqualitaet separat
- [x] Finanztiefe separat
- [x] Open-question explosion als Malus
- [x] `quality_review.open_gaps` wird fuer PDF/Ready-Gate anders behandelt als fuer UI.
- [x] `meeting_actions` und `synthesis.next_steps` entkoppelt.
- [x] `meeting_actions` = operative Deal-Handlungen
- [x] `research_backlog` = UI-only

### G. Finanz- und Ereignis-Backbone verbessern

- [x] Company Department auf Presse-/Finanzsignale normiert.
- [x] Proxy financial evidence fuer private Unternehmen extrahiert.
- [x] Umsatzmeldungen
- [x] regionale Rueckgaenge
- [x] Capex / neue Werke
- [x] CEO-/CFO-Statements zu Margendruck
- [x] Kurzarbeit / Leiharbeiterabbau / Restrukturierung
- [x] `financial_deep_dive.assessment` bleibt bei vorhandenen Pressesignalen nicht leer.
- [x] `transaction_event_intelligence` wird auch aus Press Releases und Strategieankuendigungen gespeist.
- [x] Signale zu Polen / North Carolina / Local-for-Local / Rechenzentrumsgeschaeft / Margendruck werden geparst, soweit oeffentlich vorhanden.
- [x] Diese Signale fliessen in Opportunity Thesis, offene Fragen und naechste Schritte ein.

### H. Report- und PDF-Komposition anpassen

- [x] Fuer `12.1` echte Kontakttabelle mit 6 bis 7 Spalten gebaut.
- [x] Fuer `16` maximal 5 Fragekarten mit Label und Business Impact gebaut.
- [x] Fuer `17` Aktionsliste mit Phase, Owner, Aktion und Output gebaut.
- [x] Keine langen Aufzaehlungen aus `quality_review.open_gaps` im PDF.
- [x] Keine langen Aufzaehlungen aus `synthesis.next_steps` im PDF.
- [x] Keine halb-validierten Buyer-Kontakte im Zielkontaktblock.
- [x] Kritische-Luecke-Box statt generischem Fallback-Fliesstext.
- [x] Seite 6 und 7 in Karten-/Playbook-Logik ueberfuehrt.

### I. UI / PDF Trennung schaerfen

- [x] Voller Research-Backlog bleibt im UI.
- [x] Lange `open_gaps`, `gap_details`, `raw next steps`, `source trails` bleiben im UI.
- [x] PDF zeigt nur kuratierte `critical_open_questions`.
- [x] PDF zeigt nur kuratierte `recommended_next_steps`.
- [x] UI behaelt Drilldown auf Evidence Packets und Rohsignale.

### J. Prompting und Agentenfuehrung

- [x] Prompts fuer Contact Department um Buying-Center-Denke erweitert.
- [x] Prompts fuer Synthesis Department auf Deal-Logik statt Vollstaendigkeit getrimmt.
- [x] Prompts fuer Final Briefing normiert, damit offene Fragen nicht mit Datenluecken verwechselt werden.
- [x] Prompts fuer Next Steps auf `Mutual Action Plan` / `first-meeting playbook` ausgerichtet.
- [x] Prompts verbieten explizit:
- [x] generische `search for more data`-Listen
- [x] unverbundene Marktfragen ohne Deal-Relevanz
- [x] unbestaetigte Direktkontakte
- [x] Buyer-Kontakte ohne Asset-Fit

### K. Test- und Benchmark-Absicherung

- [x] Gold-Benchmark aus den drei Referenzsektionen angelegt.
- [x] `12.1 Zielunternehmens-Kontakte`
- [x] `16. Offene Fragen`
- [x] `17. Empfohlene naechste Schritte`
- [x] Automatische Tests fuer Contact Quality gebaut.
- [x] keine buyer-side Kontakte im target block
- [x] keine unverified fake channels
- [x] no target section without missing-role box when key roles absent
- [x] Automatische Tests fuer Open Questions gebaut.
- [x] max 5
- [x] keine generischen employee/revenue questions, wenn nicht deal-kritisch
- [x] jede Frage hat label + impact + owner
- [x] Automatische Tests fuer Next Steps gebaut.
- [x] keine generischen search-backlog items
- [x] jeder Schritt hat owner + phase + output + success criterion
- [x] mindestens ein Schritt referenziert konkreten Kontakt oder Rollen-Archetyp
- [x] Regressionstest gegen `meeting_ready` trotz Synthese-Fallback.
- [x] PDF-Text-Tests fuer neue Sections und Tabellenlabels gebaut.
- [x] Integrationstest gegen vorzeitiges `finalize_package` gebaut.

## 7. Abnahmekriterien

- [x] Die Zielkontakt-Sektion wirkt wie eine Stakeholder-Map und nicht wie eine lose Kontaktliste.
- [x] Die offenen Fragen sind auf 3 bis 5 harte Deal-Fragen reduziert.
- [x] Die naechsten Schritte lesen sich wie ein umsetzbarer Commercial Action Plan.
- [x] Die PDF enthaelt keine generischen Research-To-Dos mehr.
- [x] Ein Leser kann nach kurzer Zeit erkennen:
- [x] was die Hauptchance ist
- [x] wen Liquisto zuerst ansprechen sollte
- [x] welche 3 bis 5 Dinge im Meeting geklaert werden muessen
- [x] was Liquisto direkt vor und nach dem Meeting tun muss
- [x] Kein Run wird mehr als `meeting_ready` freigegeben, wenn die Synthese nur Fallback-Inhalt enthaelt.
- [x] Ein frischer Ziehl-Abegg-Run laeuft sauber mit dem erwarteten Ergebnis durch.
- [x] Der priorisierte Hauptpfad ist im strukturierten Output und in der narrativen Synthese deckungsgleich.
- [x] Buyer-/Redeployment-Intelligence liefert genug Substanz fuer einen wirklich belastbaren ersten Commercial Path.
- [x] Der Run endet fuer Ziehl-Abegg nicht mehr mit `blocked_not_meeting_ready`.

## 8. Externe Referenzen, die diese Zielarchitektur stuetzen

- [x] [Atlassian Executive Summary Template](https://www.atlassian.com/en/software/confluence/templates/executive-summary)
- [x] [GOV.UK Headings](https://design-system.service.gov.uk/styles/headings/)
- [x] [GOV.UK Tables](https://www.gov.uk/guidance/content-design/tables)
- [x] [GOV.UK Accessible Documents](https://www.gov.uk/guidance/publishing-accessible-documents)
- [x] [Nielsen Norman Group: Table of Contents](https://media.nngroup.com/media/articles/attachments/Table_of_Contents_Design_Decision_Tree_and_Common_Combinations.pdf)
- [x] [Salesforce: Mutual Action Plan](https://www.salesforce.com/blog/mutual-action-plan/)
- [x] [6sense: Buying Group Blindness](https://6sense.com/wp-content/uploads/2025/04/Dark-Funnel-Ebook-landscape_web.pdf)
- [x] [6sense: Buying Groups 2025](https://6sense.com/b2b-buying-groups/)
- [x] [6sense: GenAI and LLMs in Buyer Research](https://6sense.com/guides/how-genai-and-llms-are-changing-b2b-buyer-research-and-how-to-respond/)

## 9. Reihenfolge der Umsetzung

- [x] 1. Datenmodell fuer Kontakte / offene Fragen / next steps definiert.
- [x] 2. Contact Department und Synthesis-Logik fachlich neu ausgerichtet.
- [x] 3. Readiness-Gating haerter und ehrlicher gemacht.
- [x] 4. PDF-Komposition fuer die drei Problemsektionen neu gebaut.
- [x] 5. Benchmark- und Regressionstests aufgesetzt.
- [x] 6. Frische Ziehl-Abegg-Runs erzeugt und gegen diese Checkliste abgenommen.

## 10. Formale Abnahme

- [x] Formale Ergebnisbasis gegen Run `20260331T120704Z` gezogen.
- [x] Nachfolgende Live-Validierung hat den vorzeitigen Department-Abschluss als Runtime-Fehler identifiziert.
- [x] `finalize_package` wurde daraufhin gehaertet und integrationstest-abgesichert.
- [x] Teststand:
- [x] `177 passed` fuer Architektur-, Dashboard-, Playbook-, Readiness- und AG2-Integrationstests.
- [x] Frischer Validierungs-Run mit sauberem End-to-End-Ergebnis liegt vor: `20260331T142637Z`.
- [x] Strukturierte Pfadpriorisierung ist im fertigen Run validiert.
- [x] BuyerDepartment / `monetization_redeployment` ist robust genug fuer diesen Fall.
- [x] ContactDepartment liefert buyer-seitig die erwartete Substanz.
- [x] Ziehl-Abegg ist als Gesamtfall auf dem erwarteten Endergebnis.

## 11. Aktuelle Restblocker

- [x] Keine offenen Restblocker mehr fuer den Zielzustand in diesem Repo-Stand.
