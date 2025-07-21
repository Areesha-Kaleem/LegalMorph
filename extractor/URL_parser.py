from urllib.parse import urlparse, parse_qs


def parse_case_url(url):
    parsed = urlparse(url)
    domain = parsed.netloc.replace("www.", "")
    query = parse_qs(parsed.query)
    query_key = list(query.keys())[0] if query else None
    case_id = list(query.values())[0][0] if query else None
    return {
        "domain": domain,
        "case_id": case_id,
        "query_key": query_key,
        "url": url
    }