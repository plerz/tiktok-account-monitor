SCRAPECREATORS VERSION

1. Replace the old repository files with this package.
2. In Render > Environment add:
   SCRAPECREATORS_API_KEY = your ScrapeCreators API key
3. Remove FETCHLAYER_API_KEY after confirming the new deployment works.
4. Deploy/redeploy.
5. Open /health. It should show provider=ScrapeCreators and api_configured=true.
6. Test one TikTok username before using Check All.

SCRAPECREATORS_CACHE_MAX_AGE defaults to 1 day. The provider documents cached responses within this age as potentially zero-credit responses. Set to 0 if you always require a live refresh.

IMPORTANT: Render Free local SQLite storage is ephemeral and can be lost on restart/redeploy.
