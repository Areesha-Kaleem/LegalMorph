# EasyLaw Web Scraper - Streamlit UI

A modern web-based interface for the EasyLaw case document scraper built with Streamlit.

## Features

- 🎯 **User-friendly Interface**: Clean, modern UI with real-time progress tracking
- ⚙️ **Configurable Settings**: Adjust case limits, output directory, and search keywords
- 📊 **Real-time Statistics**: Monitor scraping progress and statistics
- 📋 **Live Log Output**: View detailed logs in real-time
- 🔧 **Advanced Options**: Configure delays and timeouts
- 🛑 **Stop Control**: Ability to stop scraping at any time

## Installation

1. Install the required dependencies:
```bash
pip install -r requirements.txt
```

2. Make sure you have Chrome browser installed (required for Selenium)

## Usage

1. Navigate to the Extraction folder:
```bash
cd Extraction
```

2. Run the Streamlit app:
```bash
streamlit run main_run_easylaw.py
```

3. The app will open in your default web browser at `http://localhost:8501`

## Configuration

### Sidebar Options:
- **Number of Cases to Scrape**: Set the total number of unique cases to extract
- **Output Directory**: Specify where scraped case files will be saved
- **Search Keywords**: Select which legal keywords to search for on EasyLaw
- **Advanced Options**: Configure request delays and timeouts

### Main Interface:
- **Start Scraping**: Begin the scraping process
- **Stop Scraping**: Stop the current scraping operation
- **Clear Log**: Clear the log output display
- **Real-time Stats**: View current progress and statistics
- **Log Output**: Monitor detailed scraping logs

## File Structure

```
Extraction/
├── main_run_easylaw.py      # Streamlit UI application
├── Web_scraper_easyLaw.py   # Core scraping functionality
├── requirements.txt          # Python dependencies
└── README.md               # This file
```

## Output

Scraped case files are saved as `.txt` files in the specified output directory, named by their journal ID for deduplication.

## Notes

- The scraper automatically handles deduplication based on journal IDs
- Each case is saved as a separate text file
- The UI provides real-time feedback on scraping progress
- You can stop the scraping process at any time using the stop button 