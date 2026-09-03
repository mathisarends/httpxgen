# Fehlende OpenAPI-Unterstützung

Stand dieser Analyse: 2026-09-03. Grundlage sind die Implementierung unter
`httpxgen/`, die Tests und `specs/api.yaml`.

Wichtig: OpenAPI und JSON Schema haben sehr viele Erweiterungspunkte. Eine
absolut vollständige Liste aller denkbaren Hersteller-Erweiterungen (`x-*`) ist
nicht möglich. Die folgende Liste deckt aber die standardisierten und für einen
Python-Clientgenerator praktisch relevanten Fälle ab.

## Kurzfazit

Der Generator beherrscht derzeit einen bewusst kleinen Happy Path:

- OpenAPI 3.x als bereits geladenes Dokument
- Operationen mit eindeutiger `operationId`
- Path-, Query- und Header-Parameter mit `schema`
- ausschließlich JSON-Request-Bodies
- ausschließlich explizite numerische 2xx-Responses
- grundlegende Pydantic-Modelle, String-Enums und einige Schema-Typen
- einfache lokale Schema-`$ref`s, eingeschränktes `allOf`, `oneOf` und `anyOf`
- ausschließlich einen asynchronen `httpx`-Client

Viele Angaben der Referenz-Spec werden zwar eingelesen, aber stillschweigend
ignoriert. Besonders relevant sind Security, Nicht-JSON-Inhalte, Fehlerantworten,
korrekte Parameter-Serialisierung, rekursive Modelle und OpenAPI-3.1-/JSON-Schema-
Semantik.

## Bewertung der bisherigen Stichpunkte

| Thema | Status | Aktuelles Verhalten / Lücke |
| --- | --- | --- |
| HTTP-Methode und Pfad | Teilweise | GET, PUT, POST, DELETE, OPTIONS, HEAD und PATCH funktionieren. `TRACE`, Path-Item-`$ref`s und Server-Pfade fehlen. Path-Werte werden direkt in einen f-String eingesetzt und nicht korrekt URL-escaped. |
| `operationId` | Teilweise | Muss vorhanden sein, obwohl es in OpenAPI optional ist. Ableitung eines Namens fehlt. Kollisionen nach Python-Normalisierung werden nur global erkannt, nicht aufgelöst. |
| Tags / Gruppierung | Teilweise | Tag-Filterung existiert. Es gibt keine Clients/Module pro Tag; Root-Tag-Metadaten und Tag-Reihenfolge werden ignoriert. Die Filterlogik ist kaum getestet. |
| Path-, Query-, Header-, Cookie-Parameter | Teilweise | Cookie-Parameter werden abgelehnt. Serialization mit `style`, `explode`, `allowReserved`, `allowEmptyValue`, `content` und komplexen Werten fehlt. Parameter-`$ref`s fehlen. |
| Request Body | Teilweise | Nur ein JSON-Body als Argument `body` wird unterstützt. RequestBody-`$ref`, mehrere Medienvarianten und Body-spezifische Modelle fehlen. Ein optionaler Body kann als JSON `null` statt als vollständig fehlender Body gesendet werden. |
| JSON, Multipart, Binärdaten | Fehlt weitgehend | Nur exakt `application/json` wird erkannt. `application/*+json`, Form-URL-Encoding, Multipart inklusive `encoding`, Datei-/Byte-Uploads, Text und beliebige Binärdaten fehlen. |
| Alle Statuscodes | Fehlt | Nur explizite numerische 200–299-Codes werden generiert. `default`, Bereiche wie `2XX`, Redirects und dokumentierte 4xx/5xx-Antworten fehlen. |
| Unterschiedliche Response-Typen je Statuscode | Teilweise | Mehrere 2xx-Typen werden zu einem Return-Union zusammengefasst. Der Aufrufer erfährt nicht, welcher Status zurückkam. Fehlerantworten, Response-Header und Content Negotiation fehlen. |
| Nullable / optional / required | Fehlerhaft/teilweise | Optionale Felder werden meist nullable gemacht, obwohl „nicht vorhanden“ und `null` verschieden sind. `$ref` mit `nullable: true` wird wegen frühem `$ref`-Return falsch typisiert. Defaults und Required-Kombinationen sind nicht vollständig korrekt. |
| Arrays | Teilweise | Homogene Arrays funktionieren. Tuple-Schemas, `prefixItems`, `contains`, `uniqueItems` und weitere Array-Constraints fehlen. |
| Enums | Teilweise | Komponenten-Enums unterstützen nur Strings. Inline-Enums werden `Literal`; numerische/gemischte Komponenten-Enums, Null-Werte, leere Enums und Namenskollisionen von Enum-Membern sind nicht sauber behandelt. |
| Unions / `oneOf` / `anyOf` | Teilweise | Beide werden identisch als Python-Union umgesetzt. Exakt-eine-Semantik von `oneOf` wird nicht geprüft. Inline-Varianten, verschachtelte Discriminators und Mapping-only-Discriminators sind problematisch. |
| `allOf` | Stark eingeschränkt | Maximal eine `$ref`-Basis ist erlaubt. Mehrfachvererbung wird abgelehnt; Constraints und Keywords außerhalb von `properties`, `required` und `additionalProperties: false` gehen beim Merge verloren. Konflikte werden nicht erkannt. |
| `$ref` und rekursive Schemas | Fehlerhaft/teilweise | Nur lokale Schema-Refs im Stil `#/components/schemas/X` werden sinnvoll verarbeitet. Externe/relative Refs, andere Components, JSON-Pointer-Escaping und `$ref`-Geschwister fehlen. Selbst- und gegenseitig rekursive Modelle können wegen nicht aufgeschobener Annotationen beim Import scheitern. Fehlende Ziele werden nicht früh validiert. |
| Authentifizierung | Fehlt | `securitySchemes`, globale und operationale `security`, anonyme Overrides, OAuth2/OpenID Connect, API Keys, Basic/Bearer und mehrere alternative/kombinierte Anforderungen werden ignoriert. |
| Pagination | Fehlt als Feature | Cursor und Page-Modelle können zufällig als normale Parameter/Modelle erscheinen. Iteratoren, automatische Folgeseiten und Link/Header-basierte Pagination fehlen. |
| Date / Datetime / UUID / Formate | Teilweise | `date`, `date-time` und `uuid` werden typisiert. Formatvalidierung und u. a. `email`, `uri`, `hostname`, IPv4/IPv6, `duration`, `byte`, `binary`, `password`, `int32`, `int64`, `float`, `double` und Decimal fehlen. |
| Error Bodies | Fehlt | Alle Nicht-2xx-Schemas werden ignoriert. `ApiError` enthält nur Status und rohen Text, keine typisierte Payload, Header oder Response. Eine Komponente namens `ApiError` kollidiert mit der generierten Exception. |
| Streaming | Fehlt | Streaming-Requests/-Responses, Downloads, SSE, zeilenbasierte Antworten und kontrolliertes Schließen des Streams fehlen. |
| Sync vs. Async | Fehlt | Es wird ausschließlich ein Async-Client generiert. Das ist okay, falls dies eine bewusste Produktgrenze ist, sollte dann aber dokumentiert sein. |
| Python-Keyword- und Naming-Konflikte | Teilweise | Keywords und einige Top-Level-Kollisionen werden behandelt. Kollisionen zweier Properties/Parameter nach Normalisierung, reservierte Pydantic-Namen, Importnamen und Enum-Member-Kollisionen fehlen. |
| Unbekannte zusätzliche Felder | Fehlerhaft/teilweise | `additionalProperties: false` führt bei direkten Modellen zu `extra="forbid"`. Standardmäßig ignoriert Pydantic unbekannte Felder jedoch und verliert sie, obwohl OpenAPI sie erlaubt. Ein Schema in `additionalProperties` validiert Extras bei Modellen mit Properties nicht. |
| OpenAPI 3.0 vs. 3.1 | Fehlerhaft/teilweise | Jede Version mit Präfix `3.` wird akzeptiert, aber Dialektunterschiede werden nicht sauber behandelt. 3.0-`nullable` und 3.1-Type-Unions funktionieren teilweise; 3.1-`$ref`-Geschwister, Boolean-Schemas und vollständige JSON-Schema-2020-12-Semantik fehlen. |

## Weitere nicht abgedeckte Edge Cases

### 1. Parameter und URL-Erzeugung — hohe Priorität

- Path-Parameter werden nicht gegen Platzhalter im Pfad abgeglichen. Fehlende,
  zusätzliche oder doppelte Parameter fallen nicht zuverlässig bei der
  Generierung auf.
- Gleichnamige Path-Level- und Operation-Level-Parameter müssten anhand
  `(name, in)` überschrieben werden; aktuell werden beide an die Methode gehängt.
- Zwei Wire-Namen können zum gleichen Python-Identifier werden, zum Beispiel
  `foo-bar` und `foo_bar`; daraus entsteht eine ungültige Methodensignatur.
- Path-Segmente brauchen Percent-Encoding. Zeichen wie `/`, `?`, Leerzeichen und
  Unicode können aktuell die URL-Struktur verändern.
- Arrays und Objekte in Query-, Header- und Cookie-Parametern benötigen die
  OpenAPI-Serialisierungsregeln (`form`, `simple`, `matrix`, `label`,
  `spaceDelimited`, `pipeDelimited`, `deepObject`, `explode`).
- Parameter mit `content` statt `schema`, `deprecated`, `example`/`examples` und
  `allowReserved` werden ignoriert.
- Header-Namen sind case-insensitive; Duplikate und Kollisionen mit globalen
  Client-Headern sind nicht spezifiziert.
- Schema-Defaults und Constraints von Operationsparametern werden nicht in die
  Signatur/Validierung übernommen. `page_size` aus der Beispiel-Spec wird etwa
  `None` statt standardmäßig `25`.

### 2. Request- und Response-Inhalte — hohe Priorität

- Media-Type-Auswahl und Wildcards fehlen, insbesondere `application/*+json`.
- Unterschiedliche Schemas je Content Type können nicht als getrennte Eingaben
  oder Rückgaben dargestellt werden.
- Leere Responses (`204`, HEAD), JSON ohne Schema, ungültiges/leeres JSON und
  Responses mit Body trotz fehlendem Schema brauchen explizites Verhalten.
- Response-Header und Cookies werden nicht zurückgegeben oder typisiert.
- Die generierte Methode gibt nur den dekodierten Body zurück. Status, Header und
  Original-`httpx.Response` gehen verloren.
- `readOnly` und `writeOnly` erfordern oft getrennte Request-/Response-Modelle;
  aktuell gibt es nur ein gemeinsames Modell.
- `xml`, `encoding`, Multipart-Dateinamen und Content-Disposition werden ignoriert.
- Kompression, große Downloads/Uploads und Backpressure werden nicht behandelt.

### 3. Schema- und Modellsemantik — hohe Priorität

- Inline-Objekte mit `properties` werden lediglich als `dict[str, Any]` typisiert.
  Dadurch ist der „deeply nested object graph“ aus `specs/api.yaml` in Wahrheit
  nicht tief typisiert oder validiert.
- Objekt-Constraints fehlen: `minProperties`, `maxProperties`,
  `patternProperties`, `propertyNames`, `dependentRequired`,
  `dependentSchemas`, `unevaluatedProperties`.
- Zahlen-Constraints fehlen: `multipleOf`; außerdem unterscheidet sich die Form
  von `exclusiveMinimum`/`exclusiveMaximum` zwischen OAS 3.0 und 3.1. Ein
  boolescher 3.0-Wert würde aktuell fälschlich als Zahlenlimit an Pydantic gehen.
- String-Keywords wie `contentEncoding` und `contentMediaType` fehlen.
- Array-/Tuple-Keywords fehlen: `prefixItems`, `contains`, `minContains`,
  `maxContains`, `uniqueItems`, Boolean-`items`.
- `not`, `if`/`then`/`else`, `dependentSchemas` und Boolean-Schemas (`true` /
  `false`) fehlen.
- Bei `type: [string, integer, null]` wird nur der erste Nicht-Null-Typ verwendet.
- Constraints auf `$ref`, Union, Array-Items, zusätzliche Properties und
  Komponenten-Aliases werden teilweise verworfen oder nicht durch Pydantic
  erzwungen.
- Required Properties dürfen nullable sein; optionale Properties müssen nicht
  automatisch `null` akzeptieren. Diese zwei Dimensionen sind aktuell vermischt.
- `default` ist laut Schema keine Garantie, dass ein Server den Wert liefert.
  Mutable Defaults und Defaults, die nicht zum Schema passen, werden nicht
  geprüft.
- `examples`, `example`, `deprecated`, `title`, `description`, `readOnly`,
  `writeOnly` und `externalDocs` fließen nicht in Code oder Dokumentation ein.
- Freie Dictionaries, geschlossene Objekte und typed additional properties
  werden nicht in allen Kombinationen korrekt unterschieden.

### 4. `$ref`, Komponenten und Discriminators — hohe Priorität

- `$ref` fehlt für `parameters`, `requestBodies`, `responses`, `headers`,
  `examples`, `callbacks`, `links`, `securitySchemes` und `pathItems`.
- Relative Dateien, absolute URLs und Referenzen auf andere Dokumentbereiche
  werden nicht aufgelöst. Zyklen benötigen einen Resolver mit Cache und
  nachvollziehbaren Fehlermeldungen.
- JSON-Pointer-Tokens `~0` und `~1` werden nicht überall korrekt dekodiert.
- OpenAPI 3.0 ignoriert Geschwister neben `$ref`; OpenAPI 3.1 erlaubt bestimmte
  Geschwister nach JSON-Schema-Regeln. Der Generator unterscheidet das nicht.
- `discriminator.mapping` wird eingelesen, aber nicht verwendet. Der Generator
  versucht Werte nur aus `const`/`enum` der Zielschemas zu erraten.
- Discriminator-Werte, die vom Schemanamen abgeleitet werden, Inline-Varianten,
  vererbte Discriminator-Felder und uneindeutige Werte fehlen.
- `oneOf` muss genau eine passende Variante haben; eine gewöhnliche Pydantic-
  Union garantiert diese Semantik nicht in allen Fällen.

### 5. Responses und Fehler — hohe Priorität

- Antwortschlüssel `default`, `1XX` bis `5XX` und Wildcards wie `2XX` fehlen.
- Dokumentierte 3xx/4xx/5xx-Modelle sollten typisierten Exceptions oder einem
  Result-Typ zugeordnet werden können.
- Gleiches Schema mit verschiedenen Statuscodes, mehrere Content Types pro
  Status und statusabhängige Header sind nicht modelliert.
- Links (`links`) für Folgeoperationen und Response-`$ref`s fehlen.
- Unerwartete erfolgreiche Codes werden aktuell genauso zu `ApiError` wie echte
  Fehler, selbst wenn eine `2XX`-Range dokumentiert ist.

### 6. Security — hohe Priorität

- Globale Security und das operationale `security: []` werden ignoriert. In der
  Beispiel-Spec ist `getCustomer` explizit anonym; alle anderen Operationen
  verlangen Bearer Auth, doch der generierte Client behandelt sie identisch.
- API Keys in Header, Query oder Cookie, HTTP Basic/Digest/Bearer, OAuth2-Flows,
  Scopes, OpenID Connect und Mutual TLS fehlen.
- AND innerhalb eines Security-Requirement-Objekts und OR zwischen mehreren
  Objekten müssen korrekt unterschieden werden.
- Credential-Injection, Token-Refresh und das Verhindern versehentlicher
  Credential-Weitergabe an fremde Server fehlen.

### 7. OpenAPI-Struktur außerhalb normaler Operationen — mittlere Priorität

- `servers` auf Root-, Path- und Operationsebene sowie Servervariablen werden
  ignoriert. Die Base URL muss immer manuell übergeben werden.
- OpenAPI-3.1-`webhooks` fehlen.
- `callbacks` fehlen.
- `links` fehlen.
- Path-Item-`$ref`, `summary`, `description` und gemeinsame Server/Security-
  Angaben fehlen.
- Spezifikations-Erweiterungen (`x-*`) werden zwar durch Pydantics `extra="allow"`
  behalten, aber nicht nutzbar gemacht.
- Das veraltete OpenAPI-2.0/Swagger-Format wird bewusst abgelehnt; dafür gibt es
  keine klare Migrationsmeldung.

### 8. Client-Laufzeitverhalten — mittlere Priorität

- Nur Async wird generiert; eine synchrone Variante oder konfigurierbare Wahl
  fehlt.
- Kein konfigurierbarer Transport/Client, keine Dependency Injection und kein
  explizites Ownership-Modell für einen übergebenen `httpx`-Client.
- Retries, Backoff, Rate-Limit-Behandlung (`429`, `Retry-After`), Redirect-Policy,
  Proxies, TLS/mTLS und Limits fehlen.
- Per-Request-Header können globale Header überschreiben, aber es gibt keine
  klare Konflikt- oder Casefolding-Strategie.
- Timeouts sind nur ein einzelner Float; Connect/Read/Write/Pool-Timeouts fehlen.
- Cancellation und partielles Lesen bei Streams sind nicht berücksichtigt.
- Observability-Hooks, Logging und sichere Redaction sensibler Daten fehlen.
- Pagination wird nicht als Iterator/Generator angeboten.

### 9. Naming und erzeugbarer Python-Code — hohe Priorität

- Property-, Parameter-, Schema-, Discriminator- und Enum-Namen können jeweils
  nach Normalisierung kollidieren.
- Namen können mit importierten oder generierten Symbolen kollidieren, etwa
  `BaseModel`, `Field`, `TypeAdapter`, `Mapping`, `date`, `datetime` oder der
  Clientklasse. Nur `ApiError` und die Clientklasse werden partiell geprüft.
- Pydantic-reservierte beziehungsweise problematische Feldnamen wie
  `model_config` benötigen Sonderbehandlung.
- Rekursive Typen brauchen `from __future__ import annotations`, gequotete
  Forward References oder einen anschließenden `model_rebuild()`-Schritt.
- Sehr lange Namen, leere/sonderzeichenreiche Namen und Unicode-Identifier sind
  nicht umfassend getestet.
- Ein Komponenten-Enum kann nach Normalisierung doppelte Member erzeugen.

### 10. Laden, Validierung und Diagnose — mittlere Priorität

- `load_openapi()` lädt nur JSON, obwohl die Repository-Beispiel-Spec YAML ist.
  YAML, URLs, stdin und Byte Order Marks fehlen.
- Der Loader prüft im Wesentlichen nur die wenigen Pydantic-Felder. Viele
  strukturell oder semantisch ungültige OpenAPI-Dokumente werden akzeptiert und
  erst später falsch generiert.
- Versionen wie ein zukünftiges `3.2` würden ohne Kompatibilitätsprüfung
  akzeptiert, weil nur `startswith("3.")` geprüft wird.
- Fehlende Schema-Referenzen, falsche Response Keys, doppelte Parameter,
  Pfad-Platzhalterfehler und ungültige Discriminators sollten vor der
  Codegenerierung gesammelt diagnostiziert werden.
- Fehler enthalten teilweise keinen JSON-Pointer beziehungsweise keinen
  Operation-/Schema-Kontext.

### 11. Tests, die aktuell fehlen — hohe Priorität

Die acht vorhandenen Tests prüfen überwiegend, ob Code generiert und importiert
werden kann. Für belastbare Unterstützung fehlen mindestens:

- echte HTTP-Transporttests mit `httpx.MockTransport`, inklusive exakter URL,
  Query-, Header-, Cookie- und Body-Serialisierung
- Response-Parsing für jeden unterstützten Status und Content Type
- Tests für 204/HEAD, ungültiges JSON, unbekannte Codes und typisierte Fehler
- OpenAPI-3.0- und 3.1-Fixtures für dieselben semantischen Fälle
- rekursive und gegenseitig rekursive Modelle
- Alias- und Naming-Kollisionen auf jeder Ebene
- Path-/Operation-Parameter-Override und alle Serialization Styles
- Security-Vererbung, `security: []`, OR/AND-Kombinationen und Scopes
- `oneOf`-Exklusivität, `anyOf`, Discriminator-Mapping und Inline-Varianten
- Request/Response-Unterschiede durch `readOnly` und `writeOnly`
- `additionalProperties` in den Varianten `true`, `false` und Schema
- externe/lokale `$ref`s, escaped JSON Pointer, fehlende Ziele und Zyklen
- Tag-Selektion inklusive Schema-Closure und kanonischer Titelumbenennung
- CLI-/Loader-Tests für JSON, YAML und verständliche Fehlermeldungen

## Empfohlene Reihenfolge

1. Zuerst einen echten OpenAPI-Resolver und eine semantische Validierungsphase
   einführen; ohne diese Basis bleiben `$ref`, Overrides und Fehlermeldungen
   fragil.
2. Parameter-Serialisierung, Media Types, Statusranges/default Responses und
   typisierte Fehler korrekt modellieren.
3. Security-Vererbung und Credential-Konfiguration implementieren.
4. Schema-IR einführen, das required/nullable, OAS 3.0/3.1, rekursive Typen,
   Inline-Objekte und Compositions verlustfrei auseinanderhält.
5. Danach Multipart/Binary/Streaming, Sync-Client, Pagination und Komfortfeatures
   ergänzen.
6. Jeden Schritt mit Transport- und Importtests absichern; die Referenz-Spec
   allein beweist noch keine korrekte Laufzeitunterstützung.
