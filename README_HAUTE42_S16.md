# Haute42 S16 — All-in-One Paket (10 Makro-Slots x 25 Inputs + Web-Build)

Dieses Paket enthält alles, um aus deinem GP2040-CE-Repository eine **stabile 32-KB-EEPROM-Firmware** für den **Haute42 S16** (`Haute42COSMOX`) inklusive komplettem **Web-Configurator-Build** zu erstellen.

## Enthaltene Dateien

| Datei | Zweck |
|---|---|
| `scripts/patch_haute42_s16_10macros.py` | Patcht Protobuf (`enums.proto`, `config.options`/`config.proto`), C++ (`input_macro.h/.cpp`, `config_utils.cpp`), HTTP/JSON-Puffer (`webconfig.cpp`, `lwipopts.h`) und die gesamte React Web-UI (`www/src/`) inklusive Pin-Mapping & Lokalisierung. |
| `.github/workflows/haute42_s16_10macros.yml` | Fertiger GitHub-Actions-Workflow: patcht, kompiliert `www/` (`npm run build`), baut die `Haute42COSMOX`-`.uf2` und stellt sie als Artifact bereit. |
| `scripts/build_local_haute42_s16.sh` | Optionales Skript zum lokalen Bauen unter Linux/WSL2. |

---

## Schnellstart (GitHub Actions — empfohlen)

1. **ZIP ins Repository-Root entpacken**, sodass die Ordner `.github/` und `scripts/` direkt im Hauptverzeichnis deines GP2040-CE-Forks liegen.
2. **Committen & pushen:**
   ```bash
   git add .github/workflows/haute42_s16_10macros.yml scripts/ README_HAUTE42_S16.md
   git commit -m "Add Haute42 S16 All-in-One 10-Macro x 25-Input build"
   git push
   ```
3. **Workflow starten:**
   - Auf GitHub den Tab **Actions** öffnen.
   - Links **Build Haute42 S16 (10 Macros x 25 Inputs + Web-Build)** auswählen.
   - Auf **Run workflow** klicken (Standardwerte: `Haute42COSMOX`, `10`, `25`, Pico SDK `2.1.1`).
4. **Firmware herunterladen:**
   - Nach erfolgreichem Durchlauf unter **Artifacts** das Archiv herunterladen.
   - Darin liegt die fertige `GP2040-CE_Haute42COSMOX_10Macros_25Inputs_WebUI.uf2`.

---

## Wichtige Schritte beim Flashen auf den Haute42 S16

1. **Alte Einstellungen sichern** (falls gewünscht im bisherigen Web-Configurator unter *Data Backup and Restoration* exportieren — Hinweis: alte 6-Slot-Makro-Backups sollten wegen der geänderten Struktur besser über den Advanced-Tab als Text gesichert und neu eingefügt werden).
2. **Pflichtschritt — `flash_nuke.uf2` flashen:**
   - Haute42 S16 im **BOOTSEL-Modus** anschließen (`RPI-RP2` Laufwerk erscheint).
   - Zuerst die offizielle **`flash_nuke.uf2`** auf `RPI-RP2` kopieren und warten, bis der Controller neu startet und wieder als `RPI-RP2` erscheint.
   - *Warum?* Durch die Erweiterung von 6 auf 10 Makro-Slots ändert sich die Protobuf-Konfigurationsstruktur im 32-KB-EEPROM. Alte Flash-Reste führen sonst dazu, dass der Controller an der Konsole (z. B. PS4) nicht reagiert.
3. **Neue Firmware flashen:**
   - `GP2040-CE_Haute42COSMOX_10Macros_25Inputs_WebUI.uf2` auf das `RPI-RP2`-Laufwerk kopieren.
4. **Web-Configurator testen:**
   - Mit gedrückter **S2-Taste** am PC anstecken und im Browser `http://192.168.7.1` öffnen.
   - Unter **Configuration → Macros** prüfen, ob **alle 10 Slots** mit je bis zu **25 Zeilen** sichtbar sind.
   - Alle 10 Slots idealerweise über **Uses Button** (Macro-Trigger-Taste + Aktionstaste) belegen und einmal testweise mit vollen Makros speichern, um sicherzustellen, dass Speichern & Neustart sauber durchlaufen.
