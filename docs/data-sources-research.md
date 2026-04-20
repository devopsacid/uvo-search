# UVO Search -- Data Sources & API Research

**Date:** 2026-04-03
**Status:** Initial research complete

---

## 1. UVOstat.sk API

**Portal:** https://www.uvostat.sk
**API Base URL:** https://www.uvostat.sk/api
**Documentation:** https://github.com/MiroBabic/uvostat_api

### Overview
UVOstat.sk is a third-party portal that aggregates and presents Slovak public procurement data in a structured, searchable form. It sources data from the official UVO bulletin (vestnik) and the EKS (Elektronicky kontraktacny system). The database covers procurement results from 2014 onward (UVO bulletin) and 2016 onward (EKS).

### Authentication
- **Required:** All API requests require an `ApiToken` HTTP header
- **Without token:** Returns `401 Unauthorized`
- **How to obtain:** Not publicly documented; likely requires registration or Patreon support (the site has a Patreon-based support model)

### API Endpoints (Reconstructed from Documentation)

#### 1.1 Completed/Closed Procurements
```
GET https://www.uvostat.sk/api/ukoncene_obstaravania
```
**Parameters:**
| Parameter | Required | Description |
|---|---|---|
| `id[]` | No | Specific procurement IDs (comma-separated) |
| `obstaravatel_id[]` | No | Filter by contracting authority IDs |
| `dodavatel_ico[]` | No | Filter by supplier ICO (company ID) numbers |
| `cpv[]` | No | Filter by CPV codes (comma-separated) |
| `datum_zverejnenia_od` | No | Publication date from (YYYY-MM-DD) |
| `datum_zverejnenia_do` | No | Publication date to (YYYY-MM-DD) |
| `limit` | No | Max records per request (default/max: 100) |
| `offset` | No | Pagination offset |

#### 1.2 Contracting Authorities (Obstaravatelia)
```
GET https://www.uvostat.sk/api/obstaravatelia
```
**Parameters:**
| Parameter | Required | Description |
|---|---|---|
| `id[]` | No | Specific contracting authority IDs |
| `limit` | No | Max records (default/max: 100) |
| `offset` | No | Pagination offset |

#### 1.3 Suppliers (Dodavatelia)
```
GET https://www.uvostat.sk/api/dodavatelia
```
**Parameters:**
| Parameter | Required | Description |
|---|---|---|
| `id[]` | No | Specific supplier IDs |
| `ico[]` | No | Filter by ICO numbers |
| `limit` | No | Max records (default/max: 100) |
| `offset` | No | Pagination offset |

#### 1.4 CRZ Contracts (Zmluvy)
```
GET https://www.uvostat.sk/api/crz_zmluvy
```
**Parameters:** Similar filtering pattern (IDs, dates, limit, offset)

#### 1.5 Announced/New Procurements (Vyhlasene obstaravania)
```
GET https://www.uvostat.sk/api/vyhlasene_obstaravania
```
**Parameters:** Similar to closed procurements endpoint

### Response Format
- **Format:** JSON
- **Encoding:** UTF-8
- **Pagination:** Max 100 records per request; use `offset` for more

### Bulk Data Download
- **URL:** https://www.uvostat.sk/download
- **Format:** CSV (pipe `|` delimited, UTF-8)
- **Coverage:** All proclaimed procurement results from UVO bulletin (2014+) and EKS (2016+)
- **Update frequency:** Every 24 hours or 7 days depending on Patreon support tier

### Web Interface URL Patterns (Useful for scraping/linking)
- Procurement detail: `https://www.uvostat.sk/obstaravanie/{id}`
- Contracting authority: `https://www.uvostat.sk/obstaravatel/{id}`
- Supplier: `https://www.uvostat.sk/dodavatel/{id}`
- CPV code: `https://www.uvostat.sk/cpvkod/{id}`
- All procurements list: `https://www.uvostat.sk/obstaravania`
- All authorities list: `https://www.uvostat.sk/obstaravatelia`
- All suppliers list: `https://www.uvostat.sk/dodavatelia`
- CPV codes list: `https://www.uvostat.sk/cpvkody`
- RPVS partners list: `https://www.uvostat.sk/rpvspartneri`
- CRZ contracts: `https://www.uvostat.sk/registerzmluv`
- Announced procurements: `https://www.uvostat.sk/vyhlasene-obstaravania`

---

## 2. UVO.gov.sk -- Official Public Procurement Office

**Portal:** https://www.uvo.gov.sk
**Operator:** Urad pre verejne obstaravanie (Office for Public Procurement)

### Overview
UVO.gov.sk is the official Slovak government portal for public procurement. It publishes the Vestnik verejneho obstaravania (Public Procurement Journal/Bulletin) -- the legally mandated publication channel for all public procurement notices in Slovakia.

### Key Sections
| Section | URL | Description |
|---|---|---|
| Vestnik (Bulletin) | https://www.uvo.gov.sk/vestnik-a-registre/vestnik | Public procurement journal with all notices |
| Notice detail | https://www.uvo.gov.sk/vestnik/oznamenie/detail/{id} | Individual procurement notice |
| ESPD | https://www.uvo.gov.sk/espd/filter?lang=sk | European Single Procurement Document |
| Electronic procurement | https://www.uvo.gov.sk/otvorena-komunikacia/elektronicke-verejne-obstaravanie | E-procurement info |

### Document/Notice Types
The Vestnik publishes multiple types of notices per EU procurement directives:
1. **Oznamenie o vyhlaseni verejneho obstaravania** -- Contract notice (announcement of new procurement)
2. **Oznamenie o vysledku verejneho obstaravania** -- Contract award notice (result)
3. **Oznamenie o zmene zmluvy** -- Contract modification notice
4. **Oznamenie o zruseni** -- Cancellation notice
5. **Informacia o zmluve** -- Contract information
6. **Oprava** -- Corrigendum/correction
7. **Oznamenie o subdodavke** -- Subcontracting notice
8. **Predbezne oznamenie** -- Prior information notice (PIN)
9. **Oznamenie o koncesii** -- Concession notice
10. **Oznamenie o sutazi navrhov** -- Design contest notice

### Data Export / Open Data
- **XML format:** Published on open.slovensko.sk portal
- **Portal:** https://data.slovensko.sk (Narodny katalog otvorenych dat)
- **Also on:** https://data.gov.sk/dataset/vestnik-verejneho-obstaravania-{YYYYMM}
- **Coverage:** Published monthly, historical data being gradually added (2014-2015 confirmed, older being added)
- **Access:** Requires registration on open.slovensko.sk for bulk XML download
- **No official REST API** -- Data is published as static XML/dataset downloads, not via API

### Legislative Framework
- Act No. 347/2015 Z. z. on Public Procurement (Zakon o verejnom obstaravani)
- EU Directive 2014/24/EU (public sector)
- EU Directive 2014/25/EU (utilities)
- EU Directive 2014/23/EU (concessions)

---

## 2b. data.slovensko.sk — NKOD SPARQL Catalog

**Portal:** https://data.slovensko.sk
**SPARQL Endpoint:** `POST https://data.slovensko.sk/api/sparql`

### Overview
data.slovensko.sk replaced CKAN (data.gov.sk) with a React SPA backed by a **public SPARQL endpoint** conforming to DCAT-AP (EU standard for data catalogs).

The Vestník verejného obstarávania datasets are published as weekly bulletins with JSON downloads (~10 MB each, ~520 historical issues back to 2016).

### Dataset Discovery
```
POST https://data.slovensko.sk/api/sparql
Content-Type: application/x-www-form-urlencoded

query=PREFIX dcat: <http://www.w3.org/ns/dcat#>
PREFIX dct:  <http://purl.org/dc/terms/>
SELECT ?dataset ?title ?modified ?url WHERE {
  ?dataset a dcat:Dataset ;
           dct:publisher <https://data.gov.sk/id/legal-subject/31797903> ;
           dct:title ?title ;
           dcat:distribution ?dist .
  ?dist dcat:accessURL ?url .
  OPTIONAL { ?dataset dct:modified ?modified }
  FILTER (lang(?title) = "sk")
  FILTER (?modified >= "2026-01-01T00:00:00"^^xsd:dateTime)
} ORDER BY ?modified
```

Returns SPARQL JSON results with paginated datasets. Paginate via `LIMIT 200 OFFSET n`.

### Authentication
No authentication required for public catalogs.

### Update Frequency
Daily on working days. Each Vestník issue (weekly bulletin, numbered within the year) becomes one dataset.

### Data Format
**Outer format**: JSON envelope with `bulletinItemList[]`
**Item format**: eForms/UBL 2.3 (eForms SDK 1.13) in JSON, extracted via `itemData` string field

Key eForms Business Term (BT) codes used:
- `BT-02-notice` — Notice form type (e.g., `can-standard`)
- `BT-03-notice` — Notice purpose (`result`, `planning`, `change`)
- `BT-04-notice` — Notice UUID (stable across republications)
- `DL-Metadata-Partner` — Procuring organization
- `DL-Metadata-Order` — Procurement title
- `BT-262-Lot` — CPV code (main category)
- `BT-27-Lot`, `BT-720-Tender` — Monetary amounts (estimated/final value)

---

## 3. Open Source Projects

### 3.1 UVOstat API Documentation
- **Repo:** https://github.com/MiroBabic/uvostat_api
- **Description:** Documentation for UVOstat.sk API endpoints
- **Language:** Documentation only (Markdown)
- **Status:** Primary reference for API integration

### 3.2 CRZ-scraper (slovak-egov)
- **Repo:** https://github.com/slovak-egov/CRZ-scraper
- **Description:** Web scraping and filtering code for the Slovak contract database (crz.gov.sk). Downloads XML databases, creates CSV database of contracts, filters them, downloads files, extracts and cleans up tables.
- **Org:** https://github.com/slovak-egov (Slovak e-government repos)
- **Relevance:** HIGH -- directly works with contract data that overlaps with procurement

### 3.3 verejne.digital
- **Repo:** https://github.com/verejnedigital/verejne.digital
- **Website:** https://verejne.digital
- **Description:** Applies AI/ML to data published by Slovak public institutions. Provides normalized datasets, API backend, and CSV dumps for prototyping.
- **Data overview:** https://verejne.digital/data.html
- **API test page:** https://verejne.digital/test.html
- **Relevance:** HIGH -- comprehensive project analyzing Slovak public data including procurement

### 3.4 byrokrat-sk/register-parser
- **Repo:** https://github.com/byrokrat-sk/register-parser
- **Description:** PHP package for requesting structured data about business subjects from Slovak government websites. Parses HTML since no official APIs exist.
- **Language:** PHP (7.4+)
- **Version:** 2.0.1 (January 2021)
- **Sources parsed:** ORSR (business register), trade register (zivnostensky register), financial agent register
- **Caveat:** Depends on HTML structure; breaks if government sites change their markup
- **Relevance:** MEDIUM -- useful for entity enrichment (company data)

### 3.5 lubosdz/parser-orsr
- **Repo:** https://github.com/lubosdz/parser-orsr
- **Description:** Parser for the Slovak commercial register (ORSR)
- **Language:** PHP
- **Relevance:** MEDIUM -- business register data for entity enrichment

### 3.6 eway-crm/ORSR
- **Repo:** https://github.com/eway-crm/ORSR
- **Description:** ORSR.sk API PHP class for extracting data from the business register
- **Language:** PHP
- **Relevance:** MEDIUM -- another approach to ORSR data

### 3.7 slovensko-digital (Organization)
- **GitHub:** https://github.com/slovensko-digital
- **Key repos:**
  - `slovensko-sk-api` -- REST API proxy for slovensko.sk (citizen portal), Docker-based
  - `navody.digital` -- Digital guides for citizens
  - Various tools for Slovak digital governance

### 3.8 honzajavorek/cs-apis
- **Repo:** https://github.com/honzajavorek/cs-apis
- **Description:** Curated list of Czech and Slovak public APIs
- **Relevance:** Reference for discovering additional Slovak data APIs

### 3.9 FinStat Client Libraries
- **PHP:** https://github.com/finstat/ClientApi.PHP
- **C#:** https://github.com/finstat/ClientApi.CSharp
- **API docs repo:** https://github.com/finstat (organization)
- **Relevance:** MEDIUM -- commercial API but has open source client libs

### 3.10 OpenSanctions -- Slovak RPVS Crawler
- **Repo:** https://github.com/opensanctions/opensanctions
- **Dataset:** https://www.opensanctions.org/datasets/sk_rpvs/
- **Description:** Sources RPVS data directly from Ministry of Justice API; provides downloadable entity data in JSON/CSV
- **Relevance:** HIGH -- beneficial ownership and public sector partner data

---

## 4. Alternative Slovak Government Data Sources

### 4.1 CRZ -- Centralny register zmluv (Central Contract Register)
- **Portal:** https://www.crz.gov.sk
- **Also at:** https://www.zmluvy.gov.sk
- **Description:** Registry of all contracts concluded by ministries, central state admin bodies, and public-law institutions since January 1, 2011
- **Data access:**
  - **REST API (via Datahub):** `GET https://datahub.ekosystem.slovensko.digital/api/data/crz/contracts/:id`
  - **SQL API:** Available through ekosystem.slovensko.digital for analytical queries
  - **SQL dumps:** Weekly (Sundays at 4:00 AM) from ekosystem.slovensko.digital
  - **XML downloads:** Direct from crz.gov.sk
  - **Rate limit:** 60 req/min per IP (unauthenticated)
- **Data on data.gov.sk:** https://data.gov.sk/en/dataset/crz
- **Relevance:** CRITICAL -- core contract data source

### 4.2 ORSR -- Obchodny register (Business Register)
- **Portal:** https://www.orsr.sk
- **English:** https://www.orsr.sk/Default.asp?lan=en
- **Operator:** Ministry of Justice
- **Description:** Public register of all commercial companies in Slovakia (~480,000 entities since 2001)
- **API:** NO official API -- developers must scrape HTML
- **Third-party parsers:** byrokrat-sk/register-parser, lubosdz/parser-orsr, eway-crm/ORSR (all PHP)
- **Data fields:** Company name, ICO, registered address, directors, shareholders, share capital, legal form, founding date
- **Relevance:** HIGH -- for enriching supplier/authority entity data

### 4.3 FinStat.sk -- Company Financial Data
- **Portal:** https://finstat.sk
- **API:** https://finstat.sk/api (commercial, requires API key + private key)
- **Client libraries:** PHP, C#
- **Coverage:** Slovak and Czech companies
- **Data available:**
  - Company details by ICO
  - Financial statements and ratios
  - Revenue, profit, employee count
  - Autocomplete search
  - Daily data diffs / monitoring
  - RPVS partner data: https://finstat.sk/partneri-verejneho-sektora
- **Pricing:** Commercial (FinStat ULTIMATE tier for full API access)
- **API URL:** `https://www.finstat.sk/api/` (SK) / `https://cz.finstat.sk/api/` (CZ)
- **Relevance:** HIGH but COMMERCIAL -- best structured company financial data

### 4.4 RPVS -- Register partnerov verejneho sektora
- **Portal:** https://rpvs.gov.sk/rpvs
- **Operator:** Ministry of Justice
- **Description:** Register of public sector partners -- entities receiving public money above legal thresholds. Includes beneficial ownership information.
- **Data access:**
  - **Official API:** Ministry of Justice provides an API (used by OpenSanctions)
  - **OpenSanctions:** https://www.opensanctions.org/datasets/sk_rpvs/ (JSON/CSV downloads)
  - **Open Ownership:** https://bods-data.openownership.org/source/slovakia/ (BODS format)
  - **UVOstat view:** https://www.uvostat.sk/rpvspartneri
- **Data fields:** Partner name, ICO, address, beneficial owners, authorized persons
- **Relevance:** HIGH -- critical for transparency/ownership analysis

### 4.5 Ekosystem.Slovensko.Digital -- Datahub
- **Portal:** https://ekosystem.slovensko.digital
- **Open API docs:** https://ekosystem.slovensko.digital/otvorene-api
- **Premium API:** https://ekosystem.slovensko.digital/premiove-api
- **Pricing:** https://ekosystem.slovensko.digital/cennik (free for research/charity)
- **Description:** Aggregated, cleaned, structured data from multiple Slovak government sources
- **Data sources included:**
  1. Legal entity register (Register pravnickych osob)
  2. Central contract register (CRZ)
  3. Commercial bulletin (Obchodny vestnik)
  4. Accounting records register (Register uctovnych zavierok)
  5. Financial authority information lists
  6. Debtor lists from social insurance (Socialna poistovna)
- **API endpoints:**
  - Corporate bodies: `GET https://datahub.ekosystem.slovensko.digital/api/datahub/corporate_bodies/:id`
  - CRZ contracts: `GET https://datahub.ekosystem.slovensko.digital/api/data/crz/contracts/:id`
  - Sync endpoint: `GET https://datahub.ekosystem.slovensko.digital/api/datahub/<source>/sync`
- **Authentication:** Token-based or access_token parameter
- **Rate limit:** 60 req/min per IP (unauthenticated)
- **Data updates:** Continuous via API; weekly SQL dumps
- **Relevance:** CRITICAL -- best single source for structured entity and contract data

### 4.6 data.gov.sk / data.slovensko.sk -- National Open Data Portal
- **Portal (old):** https://data.gov.sk
- **Portal (new):** https://data.slovensko.sk
- **Description:** National catalog of open datasets from obligated Slovak government entities. 942+ datasets in machine-readable formats.
- **Procurement data:** Vestnik verejneho obstaravania published as monthly XML datasets
- **Format:** CKAN-based portal, datasets in XML, CSV, JSON
- **Relevance:** MEDIUM -- useful for bulk historical data; not real-time

### 4.7 EKS -- Elektronicky kontraktacny system
- **Portal:** https://www.eks.sk
- **E-auctions:** https://eaukcie.eks.sk
- **Contract list:** https://eo.eks.sk/Prehlady/ZakazkyVerejnost
- **Operator:** Consortium of ANASOFT, Slovak Telekom, TASR
- **Description:** Electronic marketplace for public procurement. Used for below-threshold procurements; provides anonymous competition with automatic contract generation.
- **API:** No known public API
- **Data:** Contract details viewable via web portal
- **Relevance:** MEDIUM -- data is partially captured by UVOstat

### 4.8 Tender.sk -- Procurement Aggregator
- **Portal:** https://www.tender.sk
- **Description:** Commercial aggregator of Slovak public procurement opportunities. Sources from EKS, electronic portals, and 10,000+ other sources.
- **CPV codes reference:** https://www.tender.sk/blog/cpv-kody
- **Procurement glossary:** https://www.tender.sk/slovnik
- **API:** No known public API (commercial service)
- **Relevance:** LOW for integration (commercial); useful as reference

### 4.9 TED -- Tenders Electronic Daily (EU-level)
- **Portal:** https://ted.europa.eu
- **API docs:** https://docs.ted.europa.eu/api/latest/index.html
- **Developer corner:** https://ted.europa.eu/en/simap/developers-corner-for-reusers
- **Description:** EU-wide procurement database. All Slovak above-threshold procurements are published here.
- **API v3:** Single domain `api.ted.europa.eu` for all services
- **Capabilities:**
  - Search API (anonymous, no auth required)
  - Notice retrieval and publication
  - Validation and compliance checking
  - PDF/HTML rendering
- **Bulk downloads:**
  - XML packages (registered users): TED website download page
  - CSV subset: https://data.europa.eu/euodp/en/data/dataset/ted-csv
- **Data on data.europa.eu:** https://data.europa.eu/data/datasets/ted-1
- **CPV reference:** https://ted.europa.eu/en/simap/cpv
- **Relevance:** HIGH -- EU-level cross-reference, above-threshold procurements

### 4.10 Statistical Office of the Slovak Republic
- **API:** https://data.statistics.sk/api/html/help-sk.html
- **Description:** Open data API for statistical data
- **Relevance:** LOW for procurement; useful for economic context

### 4.11 otvorenezmluvy.sk -- Open Contracts (Transparency International SK)
- **Portal:** https://otvorenezmluvy.sk
- **Operator:** Transparency International Slovakia
- **Description:** Analytics and red-flagging of government contracts
- **API:** Web scraping only
- **Relevance:** LOW-MEDIUM -- useful for contract analysis patterns and risk indicators

---

## 5. Data Model -- Key Entities in Slovak Procurement

### 5.1 Core Entities

```
+---------------------+       +----------------------+
| Obstaravatel        |       | Dodavatel            |
| (Contracting Auth.) |       | (Supplier)           |
+---------------------+       +----------------------+
| id                  |       | id                   |
| nazov (name)        |       | nazov (name)         |
| ico (company ID)    |       | ico (company ID)     |
| adresa (address)    |       | dic (tax ID)         |
| typ (type)          |       | adresa (address)     |
| pravna_forma        |       | krajina (country)    |
+---------------------+       +----------------------+
        |                              |
        |  1:N                    N:1  |
        v                              v
+------------------------------------------+
| Obstaravanie / Zakazka                   |
| (Procurement / Contract)                 |
+------------------------------------------+
| id                                       |
| nazov (title)                            |
| popis (description)                      |
| typ_postupu (procedure type)             |
| stav (status: announced/closed/cancelled)|
| datum_vyhlasenia (announcement date)     |
| datum_ukoncenia (closing date)           |
| datum_zverejnenia (publication date)     |
| predpokladana_hodnota (estimated value)  |
| konecna_hodnota (final value)            |
| mena (currency, typically EUR)           |
| cpv_kod (CPV code - primary)             |
| cpv_kody (CPV codes - additional)        |
| vestnik_cislo (bulletin number)          |
| oznamenie_cislo (notice number)          |
+------------------------------------------+
        |
        | 1:N
        v
+------------------------------------------+
| Zmluva (Contract from CRZ)              |
+------------------------------------------+
| id                                       |
| cislo_zmluvy (contract number)           |
| predmet (subject)                        |
| objednavatel (ordering party)            |
| dodavatel (supplier)                     |
| datum_podpisu (signing date)             |
| datum_ucinnosti (effective date)         |
| datum_platnosti (validity date)          |
| celkova_hodnota (total value)            |
| prilohy (attachments/documents)          |
+------------------------------------------+

+------------------------------------------+
| CPV Kod (CPV Code)                       |
+------------------------------------------+
| kod (code, e.g. 72700000-7)             |
| nazov (name/description)                 |
| uroven (level: division/group/class/...) |
| nadradeny_kod (parent code)              |
+------------------------------------------+

+------------------------------------------+
| Oznamenie (Notice/Announcement)          |
+------------------------------------------+
| id                                       |
| typ (type - see Section 2 notice types)  |
| vestnik_cislo (bulletin issue number)    |
| datum_zverejnenia (publication date)     |
| obstaravatel_id                          |
| obstaravanie_id                          |
| text (full text content)                 |
| prilohy (attachments)                    |
+------------------------------------------+

+------------------------------------------+
| RPVS Partner (Public Sector Partner)     |
+------------------------------------------+
| id                                       |
| nazov (name)                             |
| ico (company ID)                         |
| adresa (address)                         |
| konecni_uzivatelia_vyhod                 |
|   (beneficial owners)                    |
| opravnene_osoby (authorized persons)     |
| datum_zapisu (registration date)         |
+------------------------------------------+
```

### 5.2 Key Identifiers
| Identifier | Description | Format |
|---|---|---|
| ICO | Company identification number (unique in SK) | 8-digit number |
| DIC | Tax identification number | 10-digit number |
| IC DPH | VAT identification number | SK + 10 digits |
| CPV | Common Procurement Vocabulary code | XX000000-X (up to 9 digits) |
| Vestnik cislo | Bulletin issue number | NNN/YYYY |
| Oznamenie cislo | Notice number within bulletin | Integer |

### 5.3 Entity Relationships
```
Obstaravatel --[announces]--> Obstaravanie --[awarded to]--> Dodavatel
Obstaravanie --[classified by]--> CPV Kod(y)
Obstaravanie --[published in]--> Oznamenie --[in]--> Vestnik
Obstaravanie --[results in]--> Zmluva (CRZ)
Dodavatel --[may be]--> RPVS Partner
Obstaravatel --[registered in]--> ORSR
Dodavatel --[registered in]--> ORSR
Dodavatel --[financials in]--> FinStat
```

### 5.4 Procurement Procedure Types (Typ postupu)
1. Verejna sutaz (Open procedure)
2. Uzsia sutaz (Restricted procedure)
3. Rokovacie konanie so zverejnenim (Competitive procedure with negotiation)
4. Rokovacie konanie bez zverejnenia (Negotiated procedure without publication)
5. Sutazny dialog (Competitive dialogue)
6. Inovacne partnerstvo (Innovation partnership)
7. Priame rokovacie konanie (Direct negotiation)
8. Zakazka s nizkou hodnotou (Low-value contract)
9. Podlimitna zakazka (Below-threshold contract)
10. Nadlimitna zakazka (Above-threshold contract)

---

## 6. Recommended Integration Architecture

### Priority Tier 1 (Core -- implement first)
| Source | Method | Why |
|---|---|---|
| UVOstat.sk API | REST API (requires token) | Primary structured procurement data |
| UVOstat.sk CSV | Bulk download | Initial data load, backup/sync |
| Ekosystem.Slovensko.Digital | REST API | CRZ contracts + legal entity data |

### Priority Tier 2 (Enrichment -- implement second)
| Source | Method | Why |
|---|---|---|
| TED API | REST API (anonymous) | EU cross-reference for above-threshold |
| RPVS / OpenSanctions | API/download | Beneficial ownership data |
| CRZ (crz.gov.sk) | Via Datahub API | Direct contract access |

### Priority Tier 3 (Extended -- implement later)
| Source | Method | Why |
|---|---|---|
| UVO.gov.sk Vestnik XML | Bulk XML download | Full notice text and historical data |
| ORSR | HTML scraping (fragile) | Company register data enrichment |
| FinStat API | Commercial API | Financial data (if budget allows) |
| data.gov.sk | Dataset downloads | Historical/statistical analysis |

### Key Risks
1. **UVOstat API token availability** -- Not clear how to obtain; may require direct contact with operator or Patreon subscription
2. **ORSR has no API** -- Only HTML scraping available; brittle and maintenance-heavy
3. **Rate limits** -- Ekosystem.Slovensko.Digital limits to 60 req/min unauthenticated
4. **Data freshness** -- UVOstat updates every 24h-7d; real-time monitoring needs UVO.gov.sk vestnik
5. **FinStat cost** -- Commercial API may be expensive for full company data

### Open Questions
1. How to obtain UVOstat.sk API token? (Contact operator or Patreon?)
2. What is the exact schema of the UVOstat CSV download?
3. Does Ekosystem.Slovensko.Digital free tier suffice for our use case?
4. What is the XML schema of the Vestnik data on open.slovensko.sk?
5. Should we build our own UVO.gov.sk scraper as a fallback?
6. What is the FinStat API pricing for our expected volume?

---

## 7. Source URLs Summary

### APIs
- UVOstat API: https://www.uvostat.sk/api
- UVOstat API docs (GitHub): https://github.com/MiroBabic/uvostat_api
- Ekosystem Datahub Open API: https://ekosystem.slovensko.digital/otvorene-api
- Ekosystem Datahub Premium API: https://ekosystem.slovensko.digital/premiove-api
- TED API: https://docs.ted.europa.eu/api/latest/index.html
- TED Developer Corner: https://ted.europa.eu/en/simap/developers-corner-for-reusers
- FinStat API: https://finstat.sk/api
- OpenSanctions API: https://www.opensanctions.org/api/
- OpenSanctions RPVS dataset: https://www.opensanctions.org/datasets/sk_rpvs/
- SK Statistics API: https://data.statistics.sk/api/html/help-sk.html

### Government Portals
- UVO.gov.sk (Public Procurement Office): https://www.uvo.gov.sk
- UVO Vestnik (Procurement Bulletin): https://www.uvo.gov.sk/vestnik-a-registre/vestnik
- CRZ (Central Contract Register): https://www.crz.gov.sk
- CRZ alternate: https://www.zmluvy.gov.sk
- ORSR (Business Register): https://www.orsr.sk
- RPVS (Public Sector Partners): https://rpvs.gov.sk/rpvs
- EKS (Electronic Contracting): https://www.eks.sk
- data.gov.sk (Open Data): https://data.gov.sk
- data.slovensko.sk (National Catalog): https://data.slovensko.sk

### Third-Party Portals
- UVOstat.sk: https://www.uvostat.sk
- Tender.sk: https://www.tender.sk
- FinStat.sk: https://finstat.sk
- verejne.digital: https://verejne.digital
- otvorenezmluvy.sk: https://otvorenezmluvy.sk
- Open Ownership (SK): https://bods-data.openownership.org/source/slovakia/

### Open Source Repos
- UVOstat API docs: https://github.com/MiroBabic/uvostat_api
- CRZ scraper: https://github.com/slovak-egov/CRZ-scraper
- verejne.digital: https://github.com/verejnedigital/verejne.digital
- register-parser (PHP): https://github.com/byrokrat-sk/register-parser
- parser-orsr (PHP): https://github.com/lubosdz/parser-orsr
- ORSR API (PHP): https://github.com/eway-crm/ORSR
- slovensko.digital org: https://github.com/slovensko-digital
- slovensko-sk-api: https://github.com/slovensko-digital/slovensko-sk-api
- FinStat PHP client: https://github.com/finstat/ClientApi.PHP
- FinStat C# client: https://github.com/finstat/ClientApi.CSharp
- OpenSanctions: https://github.com/opensanctions/opensanctions
- CS APIs list: https://github.com/honzajavorek/cs-apis

### Data Downloads
- UVOstat CSV dump: https://www.uvostat.sk/download
- CRZ dataset on data.gov.sk: https://data.gov.sk/en/dataset/crz
- TED CSV subset: https://data.europa.eu/euodp/en/data/dataset/ted-csv
- TED bulk XML: https://ted.europa.eu (registered users)
- OpenSanctions RPVS: https://www.opensanctions.org/datasets/sk_rpvs/
- RPVS via Open Ownership: https://bods-data.openownership.org/source/slovakia/
- Ekosystem SQL dumps: https://ekosystem.slovensko.digital/otvorene-data

---

## 8. Technology Stack

### Databases

| Database | Role | Version | Connection |
|---|---|---|---|
| **MongoDB** | Primary document store — all notices, procurers, suppliers, pipeline state | 7.x | `MONGODB_URI` env var |
| **Neo4j** | Graph store — entity relationships (Procurer→Notice→Supplier) | 5.x | `NEO4J_URI` env var |

**MongoDB database name:** `uvo_search`

**Collections:**
| Collection | Purpose | Dedup key |
|---|---|---|
| `notices` | All procurement notices from all sources | `(source, source_id)` |
| `procurers` | Contracting authorities | `ico` (sparse) + `name_slug` |
| `suppliers` | Awarded suppliers | `ico` (sparse) + `name_slug` |
| `cross_source_matches` | Links same real-world events across sources | `canonical_id` |
| `pipeline_state` | ETL checkpoint state | `source` |
| `ckan_packages` | CKAN package metadata cache | `package_id` |

**Neo4j graph model:**
```cypher
(:Procurer)-[:ISSUED]->(:Notice)-[:AWARDED_TO]->(:Supplier)
(:Notice)-[:CLASSIFIED_BY]->(:CPVCode)
(:Notice)-[:SAME_AS]->(:Notice)  -- cross-source link
```
