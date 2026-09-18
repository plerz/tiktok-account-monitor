Upload all files/folders to one GitHub repository.

Render:
1. New > Blueprint (or Web Service)
2. Connect the repository.
3. If Blueprint, Render reads render.yaml.
4. Add FETCHLAYER_API_KEY as a secret environment variable when requested.
5. Deploy.
6. Test /health.
7. Add custom domain tiktok.islammoderat.my.id in Render Settings > Custom Domains.
8. Update the DNS record according to the exact target Render displays.

IMPORTANT: Render Free local filesystem is ephemeral. SQLite is suitable for initial testing, but database contents can be lost on restart/redeploy. Use a persistent external database for permanent history.
