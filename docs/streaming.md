# Module streaming

Ce document décrit la mise en place du module de streaming temps réel couvrant les services `streaming_gateway`, `overlay_renderer`, `obs_controller` et `streaming_bus` ainsi que les intégrations OAuth et TradingView.

## 1. Connexion aux plateformes (Twitch, YouTube, Discord)

1. Rendez-vous dans le portail développeur de chaque plateforme pour récupérer l'identifiant et le secret OAuth.
2. Configurez les variables d'environnement suivantes pour le service FastAPI `streaming_gateway` :
   - `STREAMING_GATEWAY_TWITCH_CLIENT_ID`
   - `STREAMING_GATEWAY_TWITCH_CLIENT_SECRET`
   - `STREAMING_GATEWAY_YOUTUBE_CLIENT_ID`
   - `STREAMING_GATEWAY_YOUTUBE_CLIENT_SECRET`
   - `STREAMING_GATEWAY_DISCORD_CLIENT_ID`
   - `STREAMING_GATEWAY_DISCORD_CLIENT_SECRET`
   - `STREAMING_GATEWAY_DISCORD_BOT_TOKEN`
3. Démarrez le service et appelez `GET /auth/<provider>/start` pour obtenir l'URL d'autorisation. Redirigez l'utilisateur vers cette URL et complétez le consentement.
4. Après le consentement, la plateforme redirige vers `/auth/<provider>/callback`. Le service échange le `code` contre des jetons chiffrés dans `EncryptedTokenStore`.
5. Vérifiez les entitlements : les requêtes doivent inclure `X-User-Id` / `X-Customer-Id`. L'accès est refusé si l'utilisateur ne dispose pas de la capacité `can.stream`.

## 2. Ajouter l'overlay à OBS

1. Créez un overlay via `POST /overlays`. La réponse inclut un `signedUrl` et un `overlayId`.
2. Appelez le service `obs_controller` pour créer automatiquement une source navigateur :
   ```json
   POST /obs/sources
   {
     "scene": "Live",
     "url": "<signedUrl>",
     "w": 1920,
     "h": 1080,
     "x": 0,
     "y": 0
   }
   ```
3. L'overlay React (`overlay_renderer`) charge les indicateurs configurés et écoute le WebSocket `/ws/overlay/{overlayId}` pour mettre à jour le canvas 60 fps.
4. En cas de besoin, un overlay peut être re-signé via `GET /overlays/{overlayId}`.

## 3. Alertes TradingView

1. Dans TradingView, créez une alerte et renseignez l'URL du webhook `POST /webhooks/tradingview`.
2. (Optionnel) Configurez `STREAMING_GATEWAY_TRADINGVIEW_HMAC_SECRET` pour valider la signature `X-Signature` (HMAC SHA256 base64).
3. Utilisez l'en-tête `X-Idempotency-Key` pour garantir l'idempotence. Les doublons sont ignorés.
4. Les champs pris en charge : `symbol`, `side`, `timeframe`, `note`, `price`, `extras`.

## 4. Quotas & offres

- `can.stream` : autorise l'accès aux endpoints.
- `limit.stream_overlays` : nombre maximum d'overlays actifs.
- `limit.stream_bitrate` : limite la résolution/bitrate côté pipeline (à appliquer dans `streaming_bus`).
- Les entitlements proviennent du service de billing (Stripe webhooks) et sont mis en cache dans `entitlements_cache`.
- Le portail client Stripe permet à l'utilisateur de changer de plan, ce qui déclenche la mise à jour des droits.

## 5. Pipeline temps réel

- `streaming_bus` publie les mises à jour sur `overlay.*` et `chat.*` via Redis Streams ou NATS JetStream.
- `streaming_gateway` consomme ces flux pour pousser les indicateurs dans `/ws/overlay/{id}`.
- `overlay_renderer` agrège les messages et les rend via Lightweight Charts (Apache-2.0).
- Les métriques clés : latence webhook → overlay, latence WS, nombre de reconnexions EventSub, débit JetStream/Redis.

## 6. Observabilité & tests

- Tests unitaires :
  - Mocks OAuth pour Twitch/YouTube/Discord.
  - Validation des signatures HMAC (TradingView, Stripe).
  - Tests du client obs-websocket.
- Logs :
  - Audit des connexions OAuth (`/auth/*`).
  - Erreurs WebSocket.
  - Refus liés aux entitlements.
- Metrics : exposer un endpoint Prometheus (temps de réponse, erreurs, taux de reconnexion).

## 7. Points légaux

- Lightweight Charts (overlay) est Apache-2.0, attribution TradingView requise.
- Ne pas distribuer la “Charting Library” commerciale.
