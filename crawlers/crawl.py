# main.py
from crawlers.multi_crawler import MultiSiteCrawler

if __name__ == "__main__":
    crawler = MultiSiteCrawler()
    results = crawler.search_web("python machine learning", max_results_per_site=3)

    print(f"Found {len(results)} results:")
    for i, result in enumerate(results, 1):
        print(f"\n{i}. {result['title']}")
        print(f"   URL: {result['url']}")
        print(f"   Snippet: {result['snippet'][:100]}...")
        print(f"   Source: {result['source']}")
        
        if i == 1:
            content = crawler.get_article_content(result['url'])
            if content:
                print(f"   Content preview: {content[:200]}...")
