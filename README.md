# ⚖️ LegalMorph Case Pipeline

## 📄 Description

**LegalMorph** is an end-to-end ETL (Extract, Transform, Load) pipeline for legal case data, designed to automate the collection, structuring, and storage of legal judgments from the EastLaw platform. It combines web scraping, natural language processing, and database integration to turn unstructured legal text into structured, queryable data.

---

## 🚀 Features

- **Automated scraping** of legal case documents from EastLaw using Selenium.
- **Text cleaning and deduplication** to ensure high-quality, non-redundant data.
- **Schema-based transformation** of raw text into structured JSON using OpenAI's GPT models.
- **Custom and base JSON merging** for comprehensive data representation.
- **Summarization and key issue extraction** using LLMs.
- **MongoDB integration** for scalable storage and downstream analytics.
- **Streamlit web UI** for easy, step-by-step pipeline execution.

---

## 🛠️ External Libraries & Frameworks

| Library/Framework      | Purpose                                                                                   |
|-----------------------|-------------------------------------------------------------------------------------------|
| **streamlit**         | Provides the web-based UI for running the pipeline interactively.                         |
| **selenium**          | Automates browser actions to scrape legal case data from EastLaw.                         |
| **pymongo**           | Connects to and inserts data into a MongoDB database.                                     |
| **openai**            | Accesses Azure OpenAI (GPT-4o) for text summarization and schema-based transformation.    |
| **python-dotenv**     | Loads environment variables (API keys, etc.) from `.env` files.                           |
| **langdetect**        | Detects the language of scraped text for cleaning and filtering.                          |
| **beautifulsoup4**    | Parses and cleans HTML content from scraped web pages.                                    |
| **scikit-learn**      | Used for text deduplication via TF-IDF and cosine similarity.                             |
| **fuzzywuzzy**        | Compares and merges JSONs using fuzzy string matching.                                    |
| **tiktoken**          | Token counting for managing LLM input/output size.                                        |
| **json5**             | Parses flexible JSON formats.                                                             |
| **send2trash**        | Safely moves duplicate files to trash during deduplication.                               |

---

## 🏗️ Project Structure & Module Roles

```
LegalMorph/
│
├── app.py                  # Streamlit UI: Orchestrates the ETL pipeline via buttons
│
├── extractor/
│   ├── scraper.py          # Core web scraping logic using Selenium
│   ├── main_extraction.py  # Entrypoint: runs the scraping process
│   ├── text_cleaner.py     # Cleans HTML and detects language
│   ├── legal_deduper.py    # Deduplicates similar/identical case files
│
├── transformer/
│   ├── main_transform.py   # Entrypoint: runs the transformation pipeline
│   ├── phase1_phase2_func.py # Summarizes, structures, and parses text using LLMs
│   ├── phase3_merge_json.py  # Merges base and custom JSONs, resolves conflicts
│   └── base_schema_template.json # Example schema template
│
├── loader/
│   ├── main_load.py        # Entrypoint: loads final JSONs into MongoDB
│   └── load_json.py        # Handles MongoDB connection and insertion
│
├── data/                   # Raw scraped case text files
├── base_json/              # Base structured JSON outputs
├── custom_json/            # Custom structured JSON outputs
├── final_json/             # Final merged JSONs for DB loading
├── summarized_text/        # Summarized case texts
├── issues_base/            # [TODO: Describe usage]
├── issues_custom/          # [TODO: Describe usage]
└── venv/                   # Python virtual environment (not for production)
```

---

## 🔬 Module & Function Overview

### `app.py`
- **Role:** Streamlit UI for the pipeline. Lets users trigger extraction, transformation, and loading steps interactively.

### `extractor/`
- **scraper.py**
  - `scrape_cases_from_eastlaw(case_limit)`: Automates Chrome to log in to EastLaw, navigates to case lists, and scrapes up to `case_limit` cases. Each case is opened, its HTML is cleaned, and the text is saved.
  - `extract_case_data(driver, title, index)`: Extracts and saves the text for a single case.
- **main_extraction.py**
  - `extractor(case_limit)`: Entrypoint for scraping; calls `scrape_cases_from_eastlaw`.
- **text_cleaner.py**
  - `extract_clean_text_from_html(html_content)`: Cleans HTML and extracts readable text.
- **legal_deduper.py**
  - Deduplicates files using TF-IDF and cosine similarity; moves duplicates to trash.
- **URL_parser.py**
  - Parses URLs to extract case metadata.

### `transformer/`
- **main_transform.py**
  - `transform()`: Orchestrates the transformation pipeline: sets up OpenAI client, runs custom and base JSON extraction, resolves issues, and merges results.
- **phase1_phase2_func.py**
  - `base_json_gpt`, `custom_json_gpt`: Use LLMs to convert raw text into structured JSON (base and custom schemas).
  - `base_issue_resolver`, `custom_issue_resolver`: Use LLMs to resolve issues or fill missing fields in JSONs.
- **phase3_merge_json.py**
  - `merge_json_gpt`: Merges base and custom JSONs, resolving conflicts using LLMs and fuzzy matching.
  - `merge_issue_resolver`: Further resolves merge conflicts.
- **base_json_schema.py**
  - Defines the canonical schema for legal cases.
- **json_comparator.py**
  - Compares two JSON files for similarity using fuzzy string matching.

### `loader/`
- **main_load.py**
  - `load()`: Entrypoint for loading; calls `load_json` on the final JSON directory.
- **load_json.py**
  - `load_json(json_dir)`: Connects to MongoDB and inserts all JSON files in the given directory.

---

## 🔄 Pipeline Workflow

**Step-by-step technical flow:**

1. **Extraction (Scraping)**
   - User starts the pipeline via Streamlit UI.
   - `extractor()` (in `main_extraction.py`) calls `scrape_cases_from_eastlaw()`.
   - Selenium opens Chrome, user logs into EastLaw manually. Then press "Enter" on terminal to handover controls to selenium.
   - The script navigates to the "Judgments" section, scrapes up to N cases, cleans HTML, and saves each as a `.txt` file in `/data`.

2. **Deduplication (Optional)**
   - `legal_deduper.py` can be run to remove duplicate or near-duplicate case files using TF-IDF and cosine similarity.

3. **Transformation**
   - User clicks "Transform & Merge JSON" in the UI.
   - `transform()` (in `main_transform.py`) is called.
   - For each raw case text:
     - **Custom JSON Extraction:** LLM (Azure OpenAI) generates a shallow, flat JSON structure.
     - **Base JSON Extraction:** LLM fills a canonical schema with extracted data.
     - **Issue Resolution:** LLMs are used to fill missing fields or resolve ambiguities in both custom and base JSONs.
   - **Merging:** Base and custom JSONs are merged using LLMs and fuzzy matching to produce a final, comprehensive JSON for each case.

4. **Loading**
   - User clicks "Load into MongoDB" in the UI.
   - `load()` (in `main_load.py`) is called, which runs `load_json()` on the all json directories.
   - Each JSON is inserted as a document into the respective collection in MongoDB.

---

## 📦 Installation

```bash
pip install streamlit selenium pymongo python-dotenv openai langdetect beautifulsoup4 scikit-learn fuzzywuzzy tiktoken json5 send2trash
```

- **ChromeDriver** is required for Selenium. Download it from [here](https://sites.google.com/chromium.org/driver/).
- **MongoDB** should be running locally at `mongodb://localhost:27017` (or update the URI in `loader/load_json.py`).

---

## ⚙️ Usage

1. **Start MongoDB** (if not already running):

   ```bash
   mongod
   ```

2. **Run the Streamlit App:**

   ```bash
   streamlit run LegalMorph/app.py
   ```

3. **Follow the UI Steps:**
   - Enter the number of cases to scrape.
   - Click **Extract Case Files** (manual login to EastLaw required in the opened Chrome window).
   - Click **Transform & Merge JSON** to process and summarize the data.
   - Click **Load into MongoDB** to store the results.

> **Note:** The extraction step requires manual login to EastLaw in the browser window that opens

---

## 🙌 Contributing

Contributions are welcome!  
- Fork the repo and create a new branch for your feature or bugfix.
- Submit a pull request with a clear description of your changes.
- Please add tests if you introduce new features.

### Example UI (Streamlit):

```
⚖️ LegalMorph Data Pipeline


```

### Example JSON Schema (from `transformer/base_json_schema.py`):

```json
{
  "case_title": "",
  "reference_no_or_id": "",
  "judgment_date": "",
  "first_hearing_date": "",
  "court": "",
  "bench_type": "",
  "judges": [],
  "appellant": [],
  "respondant": [],
  "accussed_details": [
    {
      "name": "",
      "age": "",
      "gender": "",
      "designation": "",
      "allegation": []
    }
  ],
  "lawyers": {
    "prosecution": [],
    "defense": []
  },
  "complaint_summary": "",
  "investigation_summary": "",
  "judgment_summary": "",
  "punishment": "",
  "Decision_or_verdict": "",
  "arguments": {},
  "assets": [],
  "statutes": [],
  "sections": [],
  "citations": [],
  "witnesses": [],
  "witness_statement": {},
  "appeal_number": "",
  "legal_categories": [],
  "key_issues": [],
  "maxims": {},
  "legal_terms": {},
  "words_and_phrases": {},
  "metadata": {},
  "source": "",
  "summary_vector_notes": ""
}
```

# ⚖️ LegalMorph Statutes Pipeline

## 📄 Description

**LegalMorph Statutes Pipeline** is an end-to-end ETL (Extract, Transform, Load) system for legal statutes. It automates the scraping, structuring, and storage of statutes from online sources, turning unstructured legal text into structured, queryable data using web scraping, NLP, and database integration.

---

## 🚀 Features

- Automated scraping of legal statutes (with OCR for scanned documents)
- Schema-based transformation of raw text into structured JSON using LLMs
- Merging of custom and base JSONs for comprehensive data
- MongoDB integration for scalable storage
- Streamlit web UI for step-by-step pipeline execution

---

## 🛠️ External Libraries & Frameworks

| Library/Framework      | Purpose                                                                                   |
|-----------------------|-------------------------------------------------------------------------------------------|
| **streamlit**         | Web UI for running the pipeline                                                           |
| **selenium**          | Automates browser actions for scraping                                                    |
| **pymongo**           | MongoDB integration                                                                       |
| **openai**            | Accesses Azure OpenAI (GPT-4o) for text transformation                                    |
| **python-dotenv**     | Loads environment variables                                                               |
| **pytesseract**       | OCR for scanned statute images                                                            |
| **Pillow**            | Image processing for OCR                                                                  |
| **tiktoken**          | Token counting for LLM input/output                                                       |
| **json5**             | Parses flexible JSON formats                                                              |

---

## 🏗️ Project Structure & Module Roles

```
LegalMorph/
│
├── statutes_app.py                # Streamlit UI for statutes pipeline
│
├── extractor/
│   ├── scraper_statutes.py        # Scrapes statutes (Selenium + OCR)
│   ├── main_statutes_extractor.py # Entrypoint for statute scraping
│
├── transformer/
│   ├── statutes_transformation.py     # Cleans, parses, and transforms statutes
│   ├── main_statutes_transform.py     # Entrypoint for statute transformation
│   └── base_schema_statute.json       # Statute JSON schema
│
└── venv/                        # Python virtual environment (not for production)
```

---

## 🔬 Module & Function Overview

### `statutes_app.py`
- **Role:** Streamlit UI for the statutes pipeline. Lets users trigger extraction and transformation steps interactively.

### `extractor/`
- **scraper_statutes.py**
  - `scrape_statutes(statute_limit)`: Scrapes statutes from the web, including OCR for scanned pages, and stores them in MongoDB.
- **main_statutes_extractor.py**
  - `run_statute_scraper(limit)`: Entrypoint for scraping; calls `scrape_statutes`.

### `transformer/`
- **statutes_transformation.py**
  - Cleans, parses, and transforms raw statute text into structured JSON using LLMs.
- **main_statutes_transform.py**
  - `transform_statute()`: Orchestrates the transformation pipeline, including merging and issue resolution.

---

## 🔄 Pipeline Workflow

1. **Extraction:** Scrape statutes and store in MongoDB.
2. **Transformation:** Process and convert raw text to structured JSON (base and custom schema).
3. **Merging:** Merge and resolve JSONs for completeness.
4. **Interface:** Use the Streamlit app to run and monitor each phase.

```
## Flow of Pipeline
  

```
## Flow of scraper

---

## 📦 Installation

> No `requirements.txt` is included. Install dependencies manually:

```bash
pip install streamlit selenium pymongo python-dotenv openai pytesseract pillow tiktoken json5
```
- Install [Tesseract OCR](https://github.com/tesseract-ocr/tesseract) and update its path in `scraper_statutes.py` if needed.
- Ensure MongoDB is running locally (`mongodb://localhost:27017/` by default).

---

## ⚙️ Usage

1. **Start MongoDB** (if not already running).
2. **Run the Streamlit App:**
   ```bash
   streamlit run statutes_app.py
   ```
3. **Follow the UI:**
   - Set the number of statutes to scrape.
   - Click **Extract Statutes** (manual login may be required in the browser window).
   - Click **Transform Statutes** to process and structure the data.


---

## 🙌 Contributing

Contributions are welcome!  
- Fork the repo and create a new branch.
- Submit a pull request with a clear description.

---

## 📝 Example Statute JSON Schema

```json
{
  "Statute_Name": "",
  "Act_Ordinance_Name": "",
  "Enactment_Date": "",
  "Promulgation_Date": "",
  "Province": "",
  "Statute_Type": "",
  "Year": "",
  "Sections": [
    {
      "Section": "",
      "Definition": "",
      "Statute": "",
      "Citations": [
        {
          "Citation_Name": ""
        }
      ],
      "Metadata": {},
      "Bookmark_ID": ""
    }
  ]
}
```

---

--- 

---

> _For missing sections (tests, license, contact), please update this README as your project evolves!_

--- 
