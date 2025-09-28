# Service d'Événements Meetinity

Ce repository contient le service de gestion d'événements de la plateforme Meetinity, gérant les événements professionnels, les inscriptions et les opérations liées aux événements.

## Vue d'ensemble

Le Service d'Événements est développé avec **Python Flask** et fournit des capacités complètes de gestion d'événements pour la plateforme Meetinity. Il gère la création d'événements, la gestion, les inscriptions d'utilisateurs et les fonctionnalités de découverte d'événements.

## Fonctionnalités

- **Gestion d'Événements** : Opérations CRUD complètes pour les événements professionnels
- **Validation de Données** : Validation d'entrée robuste avec messages d'erreur détaillés
- **Découverte d'Événements** : Capacités de recherche et filtrage pour la navigation d'événements
- **Système d'Inscription** : Inscription d'utilisateurs et suivi de présence (planifié)
- **Gestion d'Erreurs** : Gestion d'erreurs complète avec réponses standardisées
- **Filtrage d'Événements** : Paramètres de requête pour filtrer par type, lieu et plage de dates
- **Mises à Jour d'Événements** : Mise à jour partielle via HTTP PATCH pour maintenir les informations à jour

## Stack Technique

- **Flask** : Framework web Python léger
- **Python** : Logique métier centrale et traitement de données

## État du Projet

- **Avancement** : 35%
- **Fonctionnalités terminées** : API CRUD de base, validation de données, gestion d'erreurs, surveillance de santé
- **Fonctionnalités en attente** : Intégration base de données, système d'inscription utilisateur, catégories d'événements, fonctionnalité de recherche

## Implémentation Actuelle

Le service fournit actuellement :

- **Données d'Événements Fictives** : Exemples d'événements professionnels avec informations réalistes
- **Logique de Validation** : Validation d'entrée pour la création et mise à jour d'événements
- **Réponses d'Erreur** : Gestion d'erreurs standardisée avec messages détaillés
- **Surveillance de Santé** : Point de contrôle de santé du service

## Points d'accès API

- `GET /health` - Contrôle de santé du service
- `GET /events` - Récupérer la liste des événements
- `POST /events` - Créer un nouvel événement
- `GET /events/<event_id>` - Obtenir les détails d'un événement spécifique
- `PATCH /events/<event_id>` - Mettre à jour partiellement un événement existant

## Modèle de Données d'Événement

Les événements incluent les informations suivantes :
- **Infos de Base** : Titre, description, date, lieu
- **Type d'Événement** : Catégorie/type d'événement professionnel
- **Présence** : Nombre de participants inscrits
- **Métadonnées** : Horodatages de création et mise à jour

## Pour Commencer

1. Installer les dépendances :
   ```bash
   pip install -r requirements.txt
   ```

2. Lancer le service :
   ```bash
   python src/main.py
   ```

Le service démarrera sur le port 5003 par défaut.

## Feuille de Route de Développement

### Phase 1 (Actuelle)
- Opérations CRUD de base avec données fictives
- Validation d'entrée et gestion d'erreurs
- Surveillance de santé

### Phase 2 (Prochaine)
- Intégration base de données pour stockage persistant
- Inscription utilisateur et suivi de présence
- Recherche et filtrage d'événements

### Phase 3 (Future)
- Recommandations d'événements basées sur les intérêts utilisateur
- Intégration calendrier
- Analyses et rapports d'événements

## Architecture

```
src/
├── main.py              # Point d'entrée de l'application avec routes
├── models/              # Modèles de données (à implémenter)
├── services/            # Logique métier (à implémenter)
└── utils/               # Fonctions utilitaires (à implémenter)
```

## Règles de Validation

La validation d'événement inclut :
- **Titre** : Requis, chaîne non vide
- **Participants** : Entier optionnel >= 0
- **Date** : Format de date valide
- **Lieu** : Chaîne optionnelle

## Tests

```bash
pytest
flake8 src tests
```
