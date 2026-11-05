export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    if (url.pathname !== "/search") {
      return new Response("Not found", { status: 404 });
    }
    const query = (url.searchParams.get("q") || "").trim().slice(0, 50);
    if (!query) {
      return Response.json({ data: [] });
    }

    const cache = caches.default;
    const cacheKey = new Request(`https://gif-cache/search?q=${encodeURIComponent(query.toLowerCase())}`);
    const cached = await cache.match(cacheKey);
    if (cached) {
      return cached;
    }

    const params = new URLSearchParams({ api_key: env.GIPHY_KEY, q: query, limit: "25", rating: "pg-13" });
    const giphy = await fetch(`https://api.giphy.com/v1/gifs/search?${params}`);
    if (!giphy.ok) {
      return Response.json({ error: `GIPHY ${giphy.status}` }, { status: 502 });
    }

    const body = await giphy.json();
    const data = [];
    for (const item of body.data || []) {
      const images = item.images || {};
      const thumb = (images.fixed_width_small_still || images.fixed_width_still || {}).url;
      const full = (images.downsized_large || images.original || {}).url;
      if (thumb && full) {
        data.push({ id: item.id, thumb, url: full });
      }
    }

    const response = Response.json({ data }, { headers: { "Cache-Control": "public, max-age=86400" } });
    ctx.waitUntil(cache.put(cacheKey, response.clone()));
    return response;
  },
};
