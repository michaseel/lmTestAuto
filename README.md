# LLM Benchmark Suite

Ein umfassendes Benchmarking-Tool für Large Language Models (LLMs), das sowohl lokale Modelle (via LM Studio) als auch API-basierte Modelle (via OpenRouter) testet und vergleicht.

## 📋 Übersicht

Dieses Projekt ermöglicht es, LLMs systematisch zu benchmarken und detaillierte Performance-Metriken zu erfassen:

- **Lokale Modelle (LM Studio)**: Misst Ladezeit, Generierungszeit, Tokens/Sekunde, GPU/CPU-Leistung und Speicherverbrauch
- **API-Modelle (OpenRouter)**: Testet verschiedene Cloud-Modelle und erfasst Geschwindigkeit, Token-Nutzung und Kosten
- **Interaktive Reports**: Generiert HTML-Berichte mit Screenshots, sortierbaren Tabellen und Visualisierungen

## 🎯 Features

- ⚡ **Performance-Metriken**: Ladezeit, Generierungszeit, Tokens/Sekunde
- 💻 **Hardware-Monitoring**: CPU/GPU-Leistung, Speicherverbrauch (macOS)
- 💰 **Kosten-Tracking**: API-Nutzungskosten für OpenRouter-Modelle
- 📊 **Interaktive Reports**: Sortierbare Tabellen, Screenshots beim Hover, Diagramme
- 🔄 **Parallele Ausführung**: OpenRouter-Benchmarks laufen parallel für schnellere Ergebnisse
- 📝 **Detaillierte Logs**: JSON-Outputs mit allen Metriken und generierten HTML-Artefakten

## 🛠️ Installation

### Voraussetzungen

- Python 3.9 oder höher
- macOS (für Power-Metriken mit `powermetrics`)

### Schritt 1: Repository klonen

```bash
git clone <repository-url>
cd lmTestAuto
```

### Schritt 2: Python-Abhängigkeiten installieren

```bash
python3 -m pip install -r requirements.txt
```

### Schritt 3: Optional - Playwright für Screenshots installieren

Für die Screenshot-Funktion in den Reports:

```bash
pip install playwright
playwright install chromium
```

### Für LM Studio Benchmarks

1. **LM Studio installieren**: Version 0.3.6 oder höher von [lmstudio.ai](https://lmstudio.ai)
2. **CLI aktivieren**: In LM Studio Settings → Developer → Enable CLI
3. **Local Server aktivieren**: In LM Studio → Local Server starten (EULA akzeptieren)
4. **Modelle herunterladen**: Gewünschte Modelle in LM Studio herunterladen

### Für OpenRouter Benchmarks

1. **OpenRouter API Key erstellen**: Auf [openrouter.ai](https://openrouter.ai) registrieren und API-Key erstellen
2. **API Key als Umgebungsvariable setzen**:
   ```bash
   export OPENROUTER_API_KEY="your-api-key-here"
   ```

## 🚀 Verwendung

### 1. LM Studio Benchmarks (Lokale Modelle)

Benchmarkt alle lokal installierten Modelle:

```bash
# Mit sudo für Power-Metriken (empfohlen auf macOS)
sudo -E python3 bench_lmstudio_models.py

# Ohne sudo (keine Power-Metriken)
python3 bench_lmstudio_models.py
```

**Was wird gemacht:**
- Listet alle verfügbaren lokalen Modelle auf
- Lädt jedes Modell und misst die Ladezeit
- Generiert eine Test-Website mit jedem Modell
- Erfasst Performance-Metriken (Tokens/s, GPU/CPU-Leistung, RAM)
- Speichert HTML-Output und JSON-Metriken

**Output:** `reports/lmstudio-bench-YYYYMMDD-HHMMSS/`

### 2. OpenRouter Benchmarks (API-Modelle)

#### Schritt 1: Modell-Liste erstellen

Erstelle eine Textdatei mit Modellnamen (ein Modell pro Zeile):

```bash
# openrouter_models.txt
openai/gpt-4-turbo
anthropic/claude-3-opus
google/gemini-pro
```

Oder verwende eine vorgefertigte Liste:
- `openrouter_models.txt` - Kleine Auswahl für schnelle Tests
- `all_relevant_openrouter_models.txt` - Umfassende Liste vieler Modelle

#### Schritt 2: Benchmark ausführen

```bash
# Standard (4 parallele Requests)
python3 bench_openrouter_models.py --models_file openrouter_models.txt

# Mit mehr Parallelität (8 gleichzeitige Requests)
python3 bench_openrouter_models.py --models_file openrouter_models.txt --concurrency 8

# Große Liste testen
python3 bench_openrouter_models.py --models_file all_relevant_openrouter_models.txt --concurrency 6
```

**Was wird gemacht:**
- Sendet den gleichen Prompt an jedes Modell
- Misst Generierungszeit und Tokens/Sekunde
- Erfasst Token-Nutzung und Kosten
- Extrahiert HTML aus der Antwort
- Speichert JSON-Metriken und HTML-Output

**Output:** `docs/openrouter-bench-XXXXXXXX/`

### 3. Reports generieren

#### LM Studio Report

```bash
# Automatischer Report (wird beim Benchmark erstellt)
# Manuell neu generieren mit Screenshots:
python3 build_bench_report.py reports/lmstudio-bench-YYYYMMDD-HHMMSS

# Ohne Screenshots (schneller):
python3 build_bench_report.py reports/lmstudio-bench-YYYYMMDD-HHMMSS --no-screenshots

# Custom Output-Pfad:
python3 build_bench_report.py reports/lmstudio-bench-YYYYMMDD-HHMMSS --out my_report.html
```

#### OpenRouter Report

```bash
# Report aktualisieren (mit Screenshots):
python3 openrouter_report.py docs/openrouter-bench-XXXXXXXX

# Ohne Screenshots:
python3 openrouter_report.py docs/openrouter-bench-XXXXXXXX --no-screenshots
```

**Report-Features:**
- ✅ **Sortierbare Spalten**: Klick auf Spaltenüberschriften zum Sortieren
- 🖼️ **Screenshot-Preview**: Hover über Zeile zeigt Screenshot der generierten Seite
- 📊 **Diagramme**: Visualisierungen für Tokens/s vs. GPU-Leistung
- 🔍 **Filter**: Suchfeld für Modellnamen
- 👁️ **Spalten ein/ausblenden**: Toggles für jede Spalte
- 📅 **Timestamp**: Zeigt wann jeder Test durchgeführt wurde

## 📁 Projektstruktur

```
lmTestAuto/
├── bench_lmstudio_models.py      # LM Studio Benchmark-Skript
├── bench_openrouter_models.py    # OpenRouter Benchmark-Skript
├── build_bench_report.py         # Report-Generator für LM Studio
├── openrouter_report.py          # Report-Generator für OpenRouter
├── requirements.txt              # Python-Abhängigkeiten
├── prompt_kanban.md             # Beispiel-Prompt (Kanban Board)
├── prompt_skillManagement.md    # Beispiel-Prompt (Skill Management)
├── openrouter_models.txt        # Beispiel Modell-Liste
├── reports/                      # LM Studio Benchmark-Ergebnisse
│   └── lmstudio-bench-YYYYMMDD-HHMMSS/
│       ├── index.html           # Generierter Report
│       ├── MODEL_NAME.json      # Metriken pro Modell
│       ├── MODEL_NAME.html      # Generierte Website
│       ├── MODEL_NAME_screenshot.png  # Screenshot
│       └── MODEL_NAME_powermetrics.log
└── docs/                        # OpenRouter Benchmark-Ergebnisse
    └── openrouter-bench-XXXXXXXX/
        ├── index.html           # Generierter Report
        ├── MODEL_NAME.json      # Metriken pro Modell
        ├── MODEL_NAME.html      # Generierte Website
        └── MODEL_NAME_screenshot.png
```

## ⚙️ Konfiguration

### Prompt anpassen

Beide Skripte verwenden einen vordefinierten Prompt. Du kannst ihn direkt in den Skripten ändern:

```python
# In bench_lmstudio_models.py oder bench_openrouter_models.py
PROMPT = """
Dein eigener Prompt hier...
"""
```

Oder verwende eine externe Datei:

```bash
# prompt.txt erstellen mit deinem Prompt
python3 bench_openrouter_models.py --models_file models.txt --prompt "$(cat prompt.txt)"
```

### Parameter anpassen

In den Skripten am Anfang:

```python
# Temperature (Kreativität): 0.0 - 2.0
TEMP = 0.6

# Top P (Nucleus Sampling): 0.0 - 1.0
TOP_P = 0.95

# Max Tokens (Antwortlänge): -1 für unbegrenzt
MAX_TOKENS = -1

# GPU Setting (nur LM Studio): "max", "off"
GPU_SETTING = "max"
```

## 📊 Erfasste Metriken

### LM Studio (Lokale Modelle)

| Metrik | Beschreibung |
|--------|--------------|
| **load_time_seconds** | Zeit zum Laden des Modells |
| **generation_time_seconds** | Zeit für die Antwort-Generierung |
| **tokens_per_second** | Generierungsgeschwindigkeit |
| **prompt_tokens** | Anzahl Input-Tokens |
| **completion_tokens** | Anzahl generierte Tokens |
| **cpu_w_avg/max** | CPU-Leistungsaufnahme (Watt) |
| **gpu_w_avg/max/min** | GPU-Leistungsaufnahme (Watt) |
| **ane_w_avg** | Apple Neural Engine Leistung |
| **mem_after_load_lms** | RAM-Nutzung nach Laden |
| **mem_after_gen_lms** | RAM-Nutzung nach Generierung |
| **model_size** | Modellgröße (Parameter) |
| **quantization** | Quantisierung (4bit, 8bit, etc.) |

### OpenRouter (API-Modelle)

| Metrik | Beschreibung |
|--------|--------------|
| **generation_time_seconds** | API-Antwortzeit |
| **tokens_per_second** | Generierungsgeschwindigkeit |
| **prompt_tokens** | Anzahl Input-Tokens |
| **completion_tokens** | Anzahl generierte Tokens |
| **cost** | Kosten in USD |
| **timestamp** | Zeitpunkt des Tests |

## 🔧 Troubleshooting

### LM Studio

**Problem:** `lms` Kommando nicht gefunden
- **Lösung**: In LM Studio Settings → Developer → Enable CLI aktivieren

**Problem:** Server startet nicht
- **Lösung**: LM Studio öffnen und Local Server manuell starten
- Prüfen ob Port 1234 frei ist: `lsof -i :1234`

**Problem:** Keine Power-Metriken
- **Lösung**: Skript mit `sudo -E` ausführen
- Auf macOS: `powermetrics` sollte verfügbar sein (`which powermetrics`)

**Problem:** Keine Modelle gefunden
- **Lösung**: Modelle in LM Studio herunterladen
- Prüfen: `lms ls --llm` sollte Modelle auflisten

### OpenRouter

**Problem:** API-Fehler "Unauthorized"
- **Lösung**: `OPENROUTER_API_KEY` Environment Variable korrekt setzen
- Prüfen: `echo $OPENROUTER_API_KEY`

**Problem:** "Rate limit exceeded"
- **Lösung**: `--concurrency` reduzieren (z.B. auf 2 oder 3)
- Pausen zwischen Requests einbauen

**Problem:** Timeouts bei großen Modellen
- **Lösung**: Timeout in `bench_openrouter_models.py` erhöhen:
  ```python
  TIMEOUT = 600  # 10 Minuten statt 5
  ```

### Reports

**Problem:** Screenshots werden nicht erstellt
- **Lösung**: Playwright installieren:
  ```bash
  pip install playwright
  playwright install chromium
  ```

**Problem:** Report zeigt keine Daten
- **Lösung**: Prüfen ob JSON-Dateien im Verzeichnis vorhanden sind
- Pfad zum Report-Verzeichnis korrekt angegeben?

## 📚 Weitere Dokumentation

- `docs/Overview.md` - Detaillierte Projektübersicht
- `docs/Benchmarking.md` - Benchmark-Ablauf und Konfiguration
- `docs/Reporting.md` - Report-Struktur und Features
- `CHANGELOG.md` - Versionshistorie

## 🤝 Beitragen

Contributions sind willkommen! Bitte erstelle einen Pull Request oder öffne ein Issue für Verbesserungsvorschläge.

## 📝 Lizenz

[Lizenz hier einfügen]

## 🙏 Credits

Entwickelt für systematische LLM-Evaluierung und Performance-Vergleiche.

---

**Hinweis**: Für genaue Power-Metriken auf macOS werden Admin-Rechte benötigt (`sudo`). Das Skript funktioniert auch ohne, erfasst dann aber keine Power-Daten.
