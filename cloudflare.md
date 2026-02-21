# Cloudflare setup

- Account: [2c483e1dd66869c9554c6949a2d17d96](https://dash.cloudflare.com/2c483e1dd66869c9554c6949a2d17d96)

## Email

- [s-anand.net](https://dash.cloudflare.com/2c483e1dd66869c9554c6949a2d17d96/email-service/routing/7aa8849beed153efddeea4f007aae174/overview):
  - *@s-anand.net (catch-all) and sanand@s-anand.net (custom) are sent to root.node@gmail.com
  - Subaddressing enabled

## R2

- [files](https://dash.cloudflare.com/2c483e1dd66869c9554c6949a2d17d96/r2/default/buckets/files)
  - Public files shared at <https://files.s-anand.net/>
- [private](https://dash.cloudflare.com/2c483e1dd66869c9554c6949a2d17d96/r2/default/buckets/private)
  - Private files shared at <https://private.s-anand.net/>
  - [Access control](https://one.dash.cloudflare.com/2c483e1dd66869c9554c6949a2d17d96/access-controls/apps/self-hosted/a9669222-3dee-4770-82e5-fd8818fec575)
- [talks](https://dash.cloudflare.com/2c483e1dd66869c9554c6949a2d17d96/r2/default/buckets/talks): Private storage for talk videos
- [exam](https://dash.cloudflare.com/2c483e1dd66869c9554c6949a2d17d96/r2/default/buckets/exam): Private storage for IITM TDS files

## Auth via CloudFlare One

[Apps](https://one.dash.cloudflare.com/2c483e1dd66869c9554c6949a2d17d96/access-controls/apps):

- https://notes.s-anand.net/ has private notes restricted to me
- https://private.s-anand.net/ has static apps restricted a private group
- https://llmdemos.s-anand.net/ has private LLM demos restricted to a small group. #TODO Move to private.s-anand.net

## Rules

[Cloudflare rules](https://dash.cloudflare.com/2c483e1dd66869c9554c6949a2d17d96/s-anand.net/rules/overview)

- [Rewrite */ to */index.html](https://dash.cloudflare.com/2c483e1dd66869c9554c6949a2d17d96/s-anand.net/rules/transform-rules/rewrite-url/d8f72b109d9249d8a50dd562da447a4e)
