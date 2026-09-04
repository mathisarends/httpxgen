# Implementierungs-TODO

Ziel ist nicht, jedes theoretische OpenAPI-/JSON-Schema-Edge-Case abzudecken.
`httpxgen` soll eine gute, gewöhnliche OpenAPI-3.0-/3.1-Spezifikation zuverlässig
in einen lesbaren Async-Python-Client übersetzen. Nicht unterstützte Konstrukte
sollen mit einer verständlichen `GenerationError` abbrechen und dürfen nicht
stillschweigend falschen Code erzeugen.

Jeder erledigte Punkt braucht mindestens einen fokussierten Unit-Test. Verhalten,
das erst zur Laufzeit sichtbar wird, braucht zusätzlich einen Test mit
`httpx.MockTransport` oder einen Import-/Pydantic-Test des erzeugten Pakets.

## Erledigt

- [x] Path-, Query-, Header- und Cookie-Parameter einlesen
- [x] Path-Parameter gegen die Platzhalter des Pfads validieren
- [x] Path-Werte percent-encoden
- [x] Path-Level-Parameter durch Operation-Level-Parameter überschreiben
- [x] Namenskollisionen von Parametern nach Python-Normalisierung erkennen
- [x] gebräuchliche Parameter-Styles serialisieren: `simple`, `form`, `label`,
  `matrix`, `spaceDelimited`, `pipeDelimited`, `deepObject` und `explode`
- [x] Parameter-Defaults und zentrale Zahlen-/String-/Array-Constraints anwenden
- [x] JSON und `application/*+json` verarbeiten
- [x] optionale Bodies wirklich weglassen, statt JSON `null` zu senden
- [x] Text-, Binär- und JSON-Responses verarbeiten
- [x] explizite Statuscodes, Statusbereiche wie `2XX` und `default` behandeln
- [x] dokumentierte Fehler-Bodies validieren und über `ApiError.parsed_body`
  verfügbar machen
- [x] `Accept` und bei Vendor-JSON `Content-Type` passend setzen
- [x] globale und operationale Security inklusive `security: []` vererben
- [x] Bearer, Basic, OAuth-/OIDC-Bearer und API Keys in Header, Query oder Cookie
  injizieren
- [x] AND-/OR-Security-Anforderungen anhand vorhandener Credentials auswählen
- [x] lokale `$ref`s für Schemas, Parameter, Request Bodies, Responses und Path
  Items auflösen beziehungsweise früh validieren
- [x] fehlende und externe Referenzen verständlich ablehnen
- [x] Inline-Objekte in benannte Pydantic-Modelle heben
- [x] rekursive Objektmodelle importierbar und validierbar generieren
- [x] `nullable` neben `$ref` korrekt erhalten
- [x] OpenAPI-3.1-Type-Arrays mit mehreren Typen übersetzen
- [x] String- und numerische Komponenten-Enums unterstützen
- [x] Discriminator-Mappings und implizite Discriminator-Werte normalisieren
- [x] mehrere `allOf`-Basismodelle und eigene Properties unterstützen
- [x] `additionalProperties: false`, freie Extras und typisierte Extras behandeln
- [x] normalisierte Property-/Enum-/Schema-Namenskollisionen früh erkennen
- [x] OpenAPI-3.0-`exclusiveMinimum`/`exclusiveMaximum` korrekt normalisieren
- [x] JSON- und YAML-Dateien inklusive UTF-8-BOM laden
- [x] echte Transporttests für Serialisierung, Auth und Fehler ergänzen
- [x] Support-Code (Serialisierung, `ApiError`) aus `client.py` in eigene Module
  ziehen; bei mehreren `--tag` einmalig unter `shared/` generieren
- [x] Models beim Tag-Split dem Paket zuordnen, das sie nutzt; nur von mehreren
  Tags genutzte Schemas landen in `shared/models.py`

## Noch offen – hohe Priorität

Diese Punkte treten in normalen produktiven Spezifikationen auf und können noch
zu falschen Typen oder fehlendem Verhalten führen.

- [x] `readOnly` und `writeOnly` durch getrennte Request-/Response-Modelle
  abbilden. Ein gemeinsames Modell kann derzeit auf einer Seite zu viel verlangen.
- [x] Form-, Multipart- und Binär-Request-Bodies unterstützen
- [x] Mehrere Request-/Response-Content-Types derselben Operation explizit
  modellieren
- [x] `oneOf` als „genau eine Variante“ validieren
- [x] `allOf`-Property-Konflikte zwischen Basismodellen erkennen und mit
  Schema-Kontext melden
- [x] Response-Header als typisierte Daten verfügbar machen, ohne den einfachen
  Body-Return für Standardfälle unhandlich zu machen
- [x] Default-Werte von referenzierten Enums als echte Enum-Member in
  Methodensignaturen rendern; derzeit ist der Laufzeitwert korrekt, aber der
  statische Default kann noch der rohe String sein.
- [x] Alle Komponenten-Namensräume vor der Generierung gemeinsam auf Kollisionen
  prüfen, einschließlich synthetischer Inline- und Query-Modelle.
- [x] Lokale `$ref`-Geschwister exakt nach OpenAPI 3.0 versus 3.1 behandeln.
- [ ] Semantische Vorabvalidierung ausbauen: ungültige Discriminators,
  widersprüchliche Required-/Default-Angaben und ungültige Schema-Defaults.

### Aktueller Fortsetzungspunkt

Stand 4. September 2026: Bis einschließlich der typisierten Response-Header
sind die Punkte oben implementiert, getestet, in README und Referenz-Spezifikation
dokumentiert und in `preview/` sichtbar. Als Nächstes folgt isoliert das Rendern
referenzierter Enum-Defaults als echte Enum-Member in Methodensignaturen. Danach
folgen Namensraum-Kollisionen, versionsgenaue `$ref`-Geschwister und die übrige
semantische Vorabvalidierung. Jeder dieser Schritte erhält weiterhin Tests,
einen sichtbaren Preview-Fall soweit generierbarer Code betroffen ist, und einen
eigenen Commit.

## Bewusst später / außerhalb des Kernumfangs

- [ ] relative und externe `$ref`-Dokumente
- [ ] automatische OAuth-Token-Beschaffung und Token-Refresh
- [ ] Streaming, SSE und sehr große Upload-/Download-Flows
- [ ] automatische Pagination-Iteratoren
- [ ] synchroner Client
- [ ] Callbacks, Webhooks und Links als ausführbarer Client-Workflow
- [ ] vollständige JSON-Schema-2020-12-Unterstützung (`if`/`then`/`else`, `not`,
  `unevaluatedProperties`, komplexe Tuple-/Contains-Schemas)
- [ ] XML-spezifisches Mapping
- [ ] Retry-/Backoff-/Rate-Limit-Policy; dies bleibt voraussichtlich Aufgabe des
  injizierten `httpx.AsyncClient` beziehungsweise Transports

## Testregel pro Änderung

1. Parser-/IR-Test für die OpenAPI-Eingabe ergänzen.
2. Snapshot-artige Assertion auf den relevanten erzeugten Python-Code ergänzen.
3. Bei Serialisierung, Auth oder Response-Verhalten einen
   `httpx.MockTransport`-Test ergänzen.
4. Bei Modelländerungen das erzeugte Paket importieren und reale
   Pydantic-Validierung ausführen.
5. `uvx ruff check httpxgen tests`, `uvx ruff format --check httpxgen tests` und
   `uv run pytest` müssen vor dem Commit grün sein.
