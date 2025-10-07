# Legal Document Deduplication System

A robust deduplication system for legal documents using semantic similarity analysis with Sentence Transformers.

## 🚀 Quick Start

### 1. One-Time Setup (Model Download)

**First time only** - Download and verify the model:

```bash
python verify_model.py
```

This will:
- Download the `paraphrase-MiniLM-L3-v2` model (~61MB)
- Cache it locally for future use
- Verify it works correctly
- Show you the cache location

### 2. Run the Deduplication System

```bash
streamlit run main_deduplication_ui.py
```

Access the UI at: `http://localhost:8501`

## 📁 Project Structure

```
Transformation/deduplication/
├── deduplication_engine.py    # Core deduplication logic
├── model_manager.py           # Model loading & caching
├── main_deduplication_ui.py   # Streamlit UI
├── verify_model.py            # One-time model setup
├── requirements.txt           # Dependencies
└── README.md                  # This file
```

## 🔧 How It Works

### Model Caching
- **One-time download**: The model is downloaded once and cached locally
- **Automatic loading**: Future runs load from cache instantly
- **No re-downloads**: SentenceTransformers handles caching automatically
- **Robust verification**: Ensures model integrity

### Deduplication Process
1. **NumPy-optimized comparison**: Batch processing with vectorized operations
2. **Semantic similarity**: Uses Sentence Transformers for contextual matching
3. **Dual criteria**: Both `case_title` AND `summary_vector_notes` must be similar (≥85%)
4. **Schema-based selection**: Keeps document with fewer fields
5. **Safe deletion**: Moves files to recycle bin, not permanent deletion
6. **Real-time progress**: Live updates with estimated completion time

## ⚙️ Configuration

### Similarity Threshold
- **Default**: 0.85 (85%)
- **Range**: 0.5 to 0.95
- **Higher values**: More strict matching
- **Lower values**: More lenient matching

### Model Information
- **Model**: `paraphrase-MiniLM-L3-v2`
- **Size**: ~61MB
- **Dimensions**: 384
- **Purpose**: Semantic text similarity

## 🛠️ Troubleshooting

### Model Not Found
If you see "Model not found in cache":
```bash
python verify_model.py
```

### Cache Location
The model is cached in:
- **Windows**: `%LOCALAPPDATA%\huggingface\hub`
- **Linux/Mac**: `~/.cache/huggingface/hub`

### Performance
- **First run**: May take 2-3 minutes (model loading)
- **Subsequent runs**: Instant loading from cache
- **Processing speed**: 10-30 seconds for 46 files (NumPy optimized)
- **Memory usage**: ~200MB RAM
- **Auto-completion**: Stops automatically when done

## 📊 Expected Output

### Logs
```
🚀 Starting optimized deduplication with NumPy acceleration
📊 Configuration:
   - Similarity Threshold: 0.85
   - Model: paraphrase-MiniLM-L3-v2
   - Merge Directory: [path]

Starting vectorized duplicate detection...
EasyLaw docs: 5, EastLaw docs: 41
Processing 5 valid EasyLaw vs 41 valid EastLaw documents
Encoding EasyLaw documents...
Encoding EastLaw documents...
Calculating similarity matrices...
Finding duplicates...
Found duplicate: EasyLaw doc 0 ↔ EastLaw doc 15
   Title similarity: 0.892, Summary similarity: 0.876
Found 1 duplicate groups
```

### Results
- **Total documents compared**: 205 (5 × 41)
- **Duplicate groups found**: Variable
- **Duplicates removed**: Variable
- **Metadata saved**: MongoDB `lawgpt_metadata.deduplication_metadata`

## 🚀 Performance Optimizations

### NumPy Acceleration
- **Batch processing**: All documents encoded at once
- **Vectorized operations**: Matrix-based similarity calculations
- **Memory efficient**: Optimized data structures
- **Speed improvement**: 10x faster than individual comparisons

### Real-Time Progress
- **Live progress bars**: Real-time status updates
- **Estimated completion**: Time remaining calculations
- **Auto-completion**: Stops automatically when done
- **No infinite loops**: Proper session state management
- **Configuration locking**: Settings frozen during processing

## 🔒 Safety Features

- **Recycle bin**: Files moved to system recycle bin, not deleted
- **Metadata tracking**: Complete audit trail of all actions
- **Validation**: Model integrity checks
- **Error handling**: Graceful failure with detailed logs
- **Thread safety**: Proper Streamlit session management
- **Configuration protection**: Settings locked during processing
- **Single metadata entry**: Only one metadata entry per deduplication session

## 📝 Dependencies

See `requirements.txt` for complete list:
- `streamlit>=1.28.0`
- `pymongo>=4.5.0`
- `sentence-transformers>=2.2.2`
- `scikit-learn>=1.3.0`
- `send2trash>=1.8.0`

## 🎯 Use Cases

- **Legal document deduplication**
- **Cross-source document matching**
- **Semantic similarity analysis**
- **Document quality improvement**

## 💡 Tips

1. **Run verification first**: Always run `verify_model.py` on new systems
2. **Monitor logs**: Check the log output for detailed progress
3. **Adjust threshold**: Use 0.90+ for strict matching, 0.80+ for lenient
4. **Backup data**: Always backup before running deduplication
5. **Test small**: Start with small datasets to verify settings
