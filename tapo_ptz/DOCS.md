# Tapo PTZ

Steuerkreuz, gespeicherte Positionen und Zeitpläne für Tapo-Schwenkkameras
(getestet für TC70 / C200-Baureihe). Öffnen über **Tapo PTZ** in der Seitenleiste.

## Konfiguration

```yaml
cameras:
  - name: Wohnzimmer
    host: 192.168.0.50          # feste IP der Kamera (im Router reservieren!)
    username: admin             # immer "admin"
    password: "TAPO-KONTO-PASSWORT"
    entity_id: camera.wohnzimmer_hd_stream   # optional, für das Live-Bild
```

- **username/password:** `admin` + das Passwort deines **TP-Link/Tapo-Kontos**
  (nicht das Kamerakonto). Falls das nicht klappt: Kamerakonto aus der
  Tapo-App (Kamera → Einstellungen → Erweiterte Einstellungen → Kamerakonto)
  eintragen und zusätzlich `cloud_password` = Tapo-Konto-Passwort setzen.
- **entity_id:** Die Kamera-Entität, die du schon in Home Assistant hast.
  Dann zeigt die App ein Standbild, das alle 2 s aktualisiert wird.
- Mehrere Kameras: einfach weitere Einträge unter `cameras` anlegen.

## Bedienung

- **Pfeile:** Tippen = ein Schritt, Halten = weiterfahren. Schrittweite per Regler.
  Am PC gehen auch die Pfeiltasten.
- **Positionen:** werden direkt in der Kamera gespeichert (wie Presets in der
  Tapo-App, max. 8 bei der TC70).
- **Zeitpläne:** Uhrzeit + Wochentage + Position. Werden in der App gespeichert
  und laufen, solange die App läuft – unabhängig davon, ob die Seite offen ist.
  Es gilt die Zeitzone von Home Assistant.

## Hinweise

- Ist der Privatsphäre-Modus an, fährt die Kamera nicht.
- Läuft parallel die Tapo-Control-Integration, ist das kein Problem.
