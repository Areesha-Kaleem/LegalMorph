from extractor.scraper import scrape_cases_from_eastlaw
from extractor.legal_deduper import deduper
def extractor(case_limit):
    scrape_cases_from_eastlaw(case_limit)
    deduper()