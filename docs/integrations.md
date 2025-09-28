# Intégrations externes

Ce service dialogue avec plusieurs micro-services via des clients dédiés situés dans
`src/integrations/`. Chaque client est configuré via `src/config.py` qui centralise les
URL, secrets et paramètres de résilience (timeouts, retries, circuit breaker).

## Dépendances techniques

| Usage | Paquet | Description |
| --- | --- | --- |
| Clients HTTP | `requests` | Appels REST avec gestion du timeout et des en-têtes |
| Tests mockés | `responses` | Simulation des réponses HTTP pour les tests |
| Clients gRPC | `grpcio` | Communication binaire avec le matching-service |
| Génération QR | `qrcode` | Garde l'existant pour les inscriptions |

Ces dépendances sont déclarées dans `requirements.txt`. Les tests d'intégration des
clients se trouvent dans `tests/test_integrations_clients.py` et utilisent `responses`
pour mocker les endpoints externes.

## Variables d'environnement

`src/config.py` lit automatiquement les variables d'environnement suivantes (par
service) pour surcharger les valeurs par défaut :

- `<SERVICE>_URL`
- `<SERVICE>_TIMEOUT`
- `<SERVICE>_SECRET`
- `<SERVICE>_MAX_ATTEMPTS`
- `<SERVICE>_BACKOFF_FACTOR`
- `<SERVICE>_MAX_BACKOFF`
- `<SERVICE>_CB_FAILURE_THRESHOLD`
- `<SERVICE>_CB_RESET_TIMEOUT`

Exemple pour le payment-service :

```bash
export PAYMENT_SERVICE_URL="https://payments.internal/api"
export PAYMENT_SERVICE_SECRET="super-secret-token"
export PAYMENT_SERVICE_MAX_ATTEMPTS=5
```

Les clients gèrent automatiquement le backoff exponentiel et le circuit breaker à
partir de ces paramètres.

