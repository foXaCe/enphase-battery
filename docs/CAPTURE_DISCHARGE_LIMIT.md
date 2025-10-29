# Capture du bouton "Limiter la décharge de la batterie"

Ce guide explique comment capturer l'endpoint API pour le bouton "limiter la décharge de la batterie" depuis l'application Enphase sur tablette.

## Prérequis

- Tablette Android avec l'app Enphase Energy Enlighten installée
- PC sur le même réseau que la tablette
- `mitmproxy` installé (voir `scripts/README_CAPTURE.md`)

## Procédure de capture

### 1. Préparer l'environnement de capture

```bash
cd /mnt/39c0f0e6-4018-4aa1-8d96-24720083fa77/Codage/GitHub/enphase-battery

# Démarrer mitmdump en mode headless
mitmdump -s scripts/enphase_mitm_capture.py --listen-port 8080
```

### 2. Configurer la tablette

1. **Configurer le proxy Wi-Fi** :
   - Paramètres → Wi-Fi → Appui long sur réseau → Modifier
   - Proxy manuel : IP de votre PC + port 8080
   - Certificat mitmproxy installé (http://mitm.it)

2. **Ouvrir l'app Enphase Energy**

### 3. Actions à effectuer sur la tablette

Suivez ces étapes **dans l'ordre** pour capturer toutes les requêtes :

1. **Se connecter** à l'app Enphase Energy

2. **Naviguer vers les paramètres de la batterie** :
   - Aller dans le menu Batteries / Battery
   - Sélectionner votre système de batterie IQ 5P

3. **Activer le bouton "Limiter la décharge"** :
   - Repérer le bouton/switch "Limiter la décharge de la batterie"
   - **ACTIVER** le bouton (ON) → Cela génère une requête API
   - Attendre 2-3 secondes

4. **Désactiver le bouton** :
   - **DÉSACTIVER** le bouton (OFF) → Génère une autre requête
   - Attendre 2-3 secondes

5. **Répéter 2-3 fois** pour confirmation

### 4. Identifier les données capturées

Une fois la capture terminée (Ctrl+C dans mitmdump), analyser les fichiers :

```bash
# Voir tous les endpoints capturés
jq '[.[] | .request.path] | unique' captured_data/enphase_data_*.json

# Filtrer les requêtes POST/PUT (modifications)
jq '.[] | select(.request.method == "POST" or .request.method == "PUT")' \
  captured_data/enphase_data_*.json

# Rechercher "discharge" ou "limit" dans les requêtes
jq '.[] | select(.request.path | contains("discharge") or contains("limit"))' \
  captured_data/enphase_data_*.json

# Voir la structure des payloads
jq '.[] | select(.request.method == "PUT") | {path: .request.path, body: .request.body}' \
  captured_data/enphase_data_*.json
```

## Informations à rechercher

Lors de l'analyse, identifier :

1. **Endpoint API** :
   - URL complète (ex: `/admin/lib/tariff`, `/api/v1/battery/settings`)
   - Méthode HTTP (POST, PUT, PATCH)

2. **Structure du payload** :
   - Nom du champ (ex: `discharge_limit_enabled`, `limit_discharge`, etc.)
   - Type de valeur (boolean, integer, etc.)
   - Structure JSON complète

3. **Headers spécifiques** :
   - Tokens d'authentification
   - Content-Type

## Exemple de résultat attendu

```json
{
  "request": {
    "method": "PUT",
    "path": "/admin/lib/tariff",
    "body": {
      "tariff": {
        "storage_settings": {
          "charge_from_grid": false,
          "discharge_limit_enabled": true,
          "reserve_soc": 20
        }
      }
    }
  },
  "response": {
    "status": 200,
    "data": {
      "success": true
    }
  }
}
```

## Prochaines étapes

Une fois l'endpoint identifié :

1. **Tester manuellement** avec `curl` ou Postman
2. **Implémenter dans `envoy_local_api.py`** :
   - Méthode `set_discharge_limit(enabled: bool)`
   - Méthode `get_discharge_limit() -> bool`
3. **Créer le switch dans `switch.py`**
4. **Ajouter les traductions**

## Notes importantes

- Le bouton peut être dans `/admin/lib/tariff` (comme `charge_from_grid`)
- Ou dans un endpoint séparé `/admin/lib/battery_settings`
- Le nom du champ peut varier : `discharge_limit`, `limit_discharge`, `enable_discharge_limit`, etc.
- Certains firmware peuvent avoir des endpoints différents

## Endpoints probables à surveiller

Basé sur l'architecture actuelle, les endpoints probables sont :

- `PUT /admin/lib/tariff` (storage_settings)
- `PUT /admin/lib/battery_settings`
- `POST /api/v1/battery/discharge_limit`
- `PUT /ivp/ensemble/settings`

## Aide au débogage

Si aucune requête n'est capturée :

1. Vérifier que le proxy est bien configuré sur la tablette
2. Vérifier que le certificat mitmproxy est installé
3. Essayer de rafraîchir l'app (fermer et rouvrir)
4. Vérifier les logs mitmdump pour voir si des requêtes arrivent

---

**Date de création** : 2025-10-29
**Objectif** : Ajouter le contrôle "Limiter la décharge de la batterie" au mode hybride
