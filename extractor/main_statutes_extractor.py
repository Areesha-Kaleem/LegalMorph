from extractor.scraper_statutes import scrape_statutes

def run_statute_scraper(limit):
    scrape_statutes(statute_limit=limit)

# if __name__ == "__main__":
#     run_statute_scraper()