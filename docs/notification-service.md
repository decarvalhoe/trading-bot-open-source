# Notification Service Configuration

Le service de notifications prend en charge plusieurs canaux de diffusion (webhook, Slack, e-mail, Telegram, SMS).
Les variables d'environnement suivantes contrôlent son comportement. Toutes les variables utilisent le préfixe `NOTIFICATION_SERVICE_`.

| Variable | Description | Défaut |
| --- | --- | --- |
| `NOTIFICATION_SERVICE_HTTP_TIMEOUT` | Délai maximal (en secondes) pour les requêtes sortantes HTTP. | `5.0` |
| `NOTIFICATION_SERVICE_SLACK_DEFAULT_WEBHOOK` | Webhook Slack par défaut utilisé si la cible n'en fournit pas. | `""` |
| `NOTIFICATION_SERVICE_SMTP_HOST` | Hôte du serveur SMTP pour l'envoi d'e-mails. | `"localhost"` |
| `NOTIFICATION_SERVICE_SMTP_PORT` | Port du serveur SMTP. | `25` |
| `NOTIFICATION_SERVICE_SMTP_SENDER` | Adresse e-mail de l'expéditeur utilisée par défaut. | `None` |
| `NOTIFICATION_SERVICE_TELEGRAM_BOT_TOKEN` | Jeton du bot Telegram utilisé si la cible n'en définit pas. | `""` |
| `NOTIFICATION_SERVICE_TELEGRAM_DEFAULT_CHAT_ID` | Chat ID Telegram utilisé par défaut pour les notifications. | `""` |
| `NOTIFICATION_SERVICE_TELEGRAM_API_BASE` | Base URL de l'API Telegram Bot. | `"https://api.telegram.org"` |
| `NOTIFICATION_SERVICE_TWILIO_ACCOUNT_SID` | Identifiant de compte Twilio utilisé pour les SMS. | `""` |
| `NOTIFICATION_SERVICE_TWILIO_AUTH_TOKEN` | Jeton d'authentification Twilio. | `""` |
| `NOTIFICATION_SERVICE_TWILIO_FROM_NUMBER` | Numéro d'expéditeur utilisé pour les SMS. | `""` |
| `NOTIFICATION_SERVICE_TWILIO_API_BASE` | Base URL de l'API REST Twilio. | `"https://api.twilio.com"` |
| `NOTIFICATION_SERVICE_DRY_RUN` | Active le mode simulation (aucun appel externe). | `True` |

En mode `dry-run`, aucun appel réseau n'est effectué : les notifications sont simplement journalisées.
Cela permet de tester la configuration de routage sans dépendre d'intégrations externes.
