# ⚖️ LegalMorph - Automated Legal Data Pipeline

A comprehensive automated pipeline for scraping, transforming, and deduplicating legal documents from multiple sources with a modern web-based interface.

## 🏗️ Architecture Overview

LegalMorph is a modular pipeline consisting of four main stages:

1. **🕸️ Extraction** - Web scraping from legal databases
2. **🔄 Transformation** - Converting raw text to structured JSON
3. **📊 Schema Unification** - Standardizing schemas across sources
4. **📊 Deduplication & Final Cleanup** - Removing duplicates and final validation

## 📁 Project Structure

```
LawGPT_data_pipeline/
├── homepage.py                                    # Main launcher dashboard
├── requirements.txt                               # Global dependencies
├── Extraction/                                    # Web scraping stage
│   ├── main_run_eastlaw.py                       # EastLaw scraper UI
│   ├── main_run_easylaw.py                       # EasyLaw scraper UI
│   ├── Web_scraper_eastlaw_combined.py           # EastLaw backend
│   ├── Web_scraper_easyLaw.py                    # EasyLaw backend
│   ├── backup/                                    # Backup versions
│   └── README.md                                 # Extraction documentation
├── Transformation/                                # Data transformation stage
│   ├── main_combined_ui.py                       # Transformation UI
│   ├── config/
│   │   └── prompts.py                            # AI prompts configuration
│   ├── cases/                                    # Case processing modules
│   │   ├── phase1_base.py                        # Base JSON generation
│   │   ├── phase2_custom.py                      # Custom JSON generation
│   │   └── phase3_merge.py                       # JSON merging
│   ├── statutes/                                 # Statute processing modules
│   │   ├── phase1_base.py                        # Base JSON generation
│   │   ├── phase2_custom.py                      # Custom JSON generation
│   │   └── phase3_merge.py                       # JSON merging
│   ├── shared/                                   # Shared utilities
│   └── deduplication/                            # Deduplication stage
│       ├── main_deduplication_ui.py              # Deduplication UI
│       ├── deduplication_engine.py               # Core deduplication logic
│       ├── unification_engine.py                 # Schema unification
│       ├── model_manager.py                      # AI model management
│       ├── verify_model.py                       # Model verification
│       └── README.md                            # Deduplication documentation
├── data/                                         # Data storage
│   ├── raw/                                      # Raw scraped data
│   │   ├── eastlaw/                              # EastLaw scraped files
│   │   └── easylaw/                              # EasyLaw scraped files
│   ├── custom/                                   # Custom JSON files
│   ├── base/                                     # Base JSON files
│   ├── merge/                                    # Merged JSON files
│   └── summarise/                                # Summarized data
└── venv/                                         # Virtual environment
```

## 🚀 Quick Start

### 1. Installation

```bash
# Clone the repository
git clone https://github.com/Areesha-Kaleem/LegalMorph.git
cd LegalMorph

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Launch the Pipeline

```bash
# Start the main launcher
streamlit run homepage.py
```

The homepage will open at `http://localhost:8501` and provide access to all pipeline components.

## 🕸️ Stage 1: Extraction (Web Scraping)

### Supported Sources
- **EastLaw** (`eastlaw.pk`) - Pakistani legal database
- **EasyLaw** - Additional legal source

### Features
- **Real-time UI** with progress tracking
- **Configurable limits** for cases and statutes
- **OCR support** for statute documents
- **Manual login handling** for secure access
- **Stop/Resume functionality**
- **Live log monitoring**

### Usage
1. Select scraper from homepage dropdown
2. Configure scraping parameters
3. Click "Launch Scraper"
4. Complete manual login in browser
5. Monitor progress in real-time

### Output
- **Raw text files** (.txt) for cases
- **Text files** (.txt) for statutes (OCR processed)
- **HTML files** (.html) for cases (optional)
- **MongoDB metadata** for tracking

## 🔄 Stage 2: Transformation

### Three-Phase Process

#### Phase 1: Base JSON Generation
- Converts raw text to standardized base JSON format
- Extracts key legal information
- Handles both cases and statutes

#### Phase 2: Custom JSON Generation
- Creates custom JSON schemas
- Applies domain-specific transformations
- Maintains legal context

#### Phase 3: Merge & Combine
- Merges base and custom JSONs
- Resolves conflicts and inconsistencies
- Creates unified document structure

### Features
- **Streamlit UI** with real-time progress
- **Configurable prompts** for AI processing
- **Error handling** and validation
- **Metadata tracking** in MongoDB
- **Stop/Resume functionality**

### Usage
1. Launch Transformation UI from homepage
2. Select data type (Cases/Statutes)
3. Choose source (EastLaw/EasyLaw)
4. Select phase (Individual/All)
5. Monitor progress and logs

## 📊 Stage 3: Schema Unification

### Features
- **Cross-source schema standardization** (EastLaw vs EasyLaw)
- **Field mapping and conflict resolution**
- **Consistent format generation**
- **Metadata preservation**
- **Real-time progress tracking**

## 📊 Stage 4: Deduplication & Final Cleanup

### Features
- **Semantic similarity analysis** using Sentence Transformers
- **Cross-source deduplication** (EastLaw vs EasyLaw)
- **Duplicate removal** with safe file handling (recycle bin)
- **Final schema validation**
- **Real-time progress tracking**

### Technical Details
- **Model**: `paraphrase-MiniLM-L3-v2` (~61MB)
- **Similarity threshold**: Configurable (0.5-0.95)
- **Dual criteria**: Title + Summary similarity
- **NumPy optimization** for speed

### Usage
1. Launch Transformation UI from homepage
2. Select "All" phases to include unification
3. Monitor progress and logs
4. Review unified schema output

### Usage (Deduplication)
1. Launch Deduplication UI from homepage
2. Configure similarity threshold
3. Start deduplication process
4. Monitor progress and results
5. Review logs and metadata

## 🛠️ Configuration

### Environment Variables
```bash
# MongoDB connection
MONGODB_URI=mongodb://localhost:27017/

# OpenAI API (for transformation)
OPENAI_API_KEY=your_api_key_here

# Tesseract OCR path (Windows)
TESSERACT_CMD=C:\Program Files\Tesseract-OCR\tesseract.exe
```

### Port Configuration
- **Homepage**: 8501
- **EastLaw Scraper**: 8502
- **EasyLaw Scraper**: 8505
- **Transformation**: 8503
- **Deduplication**: 8504

## 📊 Data Flow

```
Raw Legal Sources (EastLaw/EasyLaw)
           ↓
    Web Scraping (Extraction)
           ↓
    Raw Text Files (.txt/.html for Cases, .txt for Statutes)
           ↓
    JSON Transformation (3 Phases)
           ↓
    Structured JSON Files
           ↓
    Schema Unification & Standardization
           ↓
    Deduplication & Final Cleanup
           ↓
    Final Clean Dataset
```

## 🔧 Dependencies

### Core Dependencies
- `streamlit>=1.28.0` - Web UI framework
- `selenium>=4.15.0` - Web automation
- `pymongo>=4.5.0` - MongoDB integration
- `pytesseract>=0.3.10` - OCR processing
- `openai>=1.0.0` - AI processing
- `sentence-transformers>=2.2.2` - Semantic similarity

### Additional Dependencies
- `beautifulsoup4>=4.12.0` - HTML parsing
- `Pillow>=9.0.0` - Image processing
- `langdetect>=1.0.9` - Language detection
- `scikit-learn>=1.3.0` - Machine learning utilities
- `send2trash>=1.8.0` - Safe file deletion

## 🚨 Prerequisites

### System Requirements
- **Python 3.8+**
- **Chrome browser** (for Selenium)
- **MongoDB** (local or remote)
- **Tesseract OCR** (for statute processing)
- **OpenAI API key** (for transformation)

### One-Time Setup
```bash
# Download AI model for deduplication
cd Transformation/deduplication
python verify_model.py
```

## 📈 Performance

### Scraping Performance
- **EastLaw**: ~50-100 cases/hour
- **EasyLaw**: ~100-200 cases/hour
- **EastLaw Statutes**: ~20-40/hour (OCR dependent)
- **EasyLaw Statutes**: ~20-40/hour (OCR dependent)

### Transformation Performance
- **Base JSON**: ~100 documents/minute
- **Custom JSON**: ~50 documents/minute
- **Merge**: ~200 documents/minute

### Deduplication Performance
- **Model loading**: ~2-3 minutes (first time)
- **Processing**: ~10-30 seconds for 46 files
- **Memory usage**: ~200MB RAM

## 🔒 Security & Safety

### Data Protection
- **Manual login** for legal databases
- **No credentials stored** in code
- **Safe file operations** (recycle bin)
- **Metadata tracking** for audit trails

### Error Handling
- **Graceful failures** with detailed logs
- **Session state management** for UI stability
- **Thread safety** for concurrent operations
- **Validation** at each stage

## 🐛 Troubleshooting

### Common Issues

#### Chrome WebDriver Issues
```bash
# Ensure Chrome is installed and updated
# Check ChromeDriver compatibility
```

#### MongoDB Connection
```bash
# Verify MongoDB is running
# Check connection string in environment
```

#### Model Loading (Deduplication)
```bash
cd Transformation/deduplication
python verify_model.py
```

#### Port Conflicts
```bash
# Check if ports are in use
netstat -ano | findstr :8501
# Kill processes if needed
```

## 📝 Logging

### Log Files
- `deduplication.log` - Deduplication process logs
- `Streamlit logs` - UI application logs
- `MongoDB metadata` - Process tracking

### Log Locations
- **Application logs**: Console output
- **Deduplication logs**: `Transformation/deduplication/deduplication.log`
- **Metadata**: MongoDB collections

## 🤝 Contributing

### Development Setup
1. Fork the repository
2. Create feature branch
3. Make changes
4. Test thoroughly
5. Submit pull request

### Code Standards
- **Python**: PEP 8 compliance
- **Documentation**: Docstrings for all functions
- **Error handling**: Comprehensive try-catch blocks
- **Logging**: Detailed progress and error logs

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🙏 Acknowledgments

- **EastLaw** and **EasyLaw** for legal data access
- **OpenAI** for AI processing capabilities
- **Sentence Transformers** for semantic similarity
- **Streamlit** for the web interface framework

## 📞 Support

For issues and questions:
1. Check the troubleshooting section
2. Review the logs for error details
3. Create an issue with detailed information
4. Include system specifications and error messages

---

**LegalMorph** - Transforming legal data processing with AI-powered automation ⚖️
