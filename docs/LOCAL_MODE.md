# Mode Local Envoy - Documentation

## 🚀 Présentation

L'intégration Enphase Battery supporte désormais **deux modes de connexion** :

| Mode | Latence | Limites API | Internet requis | Mise à jour |
|------|---------|-------------|-----------------|-------------|
| **Local** | ~64ms | ❌ Aucune | ❌ Non | **10 secondes** |
| **Cloud** | ~2500ms | ✅ Quotas stricts | ✅ Oui | 60 secondes |

## ✅ Avantages du Mode Local

### Performance
- **Latence ultra-faible** : 64ms vs 2500ms (39x plus rapide)
- **Polling rapide** : Mise à jour toutes les 10s au lieu de 60s
- **Réactivité optimale** pour les automatisations critiques

### Fiabilité
- **Pas de limite API** : Pas de quotas cloud à gérer
- **Fonctionne offline** : Même sans connexion Internet
- **Moins d'appels externes** : Moins de points de défaillance

### Cas d'usage idéaux
- ✅ Blueprint gestion batterie Tempo (ce projet)
- ✅ Automatisations temps réel
- ✅ Monitoring haute fréquence
- ✅ Installations sans Internet stable

---

## 🔧 Configuration Mode Local

### Prérequis
- Envoy accessible sur le réseau local
- Hostname par défaut : `envoy.local` ou IP fixe (ex: `192.168.1.50`)
- Firmware Envoy récent (IQ Gateway)

### Étapes de configuration

1. **Ajouter l'intégration**
   - Home Assistant → Paramètres → Intégrations
   - Cliquer sur **+ Ajouter une intégration**
   - Rechercher **"Enphase Battery IQ 5P"**

2. **Sélectionner le mode Local**
   - Écran 1 : Choisir **"Local (Envoy direct - rapide, pas de quota API)"**
   - Cliquer sur **Soumettre**

3. **Renseigner les informations Envoy**
   - **Hostname ou IP** : `envoy.local` (ou IP fixe, ex: `192.168.1.50`)
   - **Username** : `installer` (par défaut, laisser vide)
   - **Password** : Laisser vide (auto-généré depuis le numéro de série)

4. **Validation**
   - L'intégration se connecte à l'Envoy local
   - Récupère le numéro de série automatiquement
   - Authentifie avec le mot de passe dérivé du serial

---

## 🔐 Authentification Locale

### Méthode automatique (recommandée)
L'intégration génère automatiquement le mot de passe à partir du numéro de série de l'Envoy :
```python
# Mot de passe = 6 derniers chiffres du numéro de série
# Ex: Serial 123456789012 → Password: 789012
```

### Méthode manuelle
Si vous connaissez votre mot de passe installateur :
1. Renseigner le champ **Password**
2. Le mot de passe sera utilisé directement

### Trouver l'IP de l'Envoy
```bash
# Option 1: mDNS (si disponible)
ping envoy.local

# Option 2: Scan réseau
nmap -sn 192.168.1.0/24 | grep -i enphase

# Option 3: Interface routeur
# Chercher "Enphase Envoy" dans la liste des appareils
```

---

## 📡 Endpoints Locaux Utilisés

### Authentification
```
POST https://envoy.local/auth/check_jwt
```

### Données batterie temps réel
```
GET https://envoy.local/ivp/meters/readings        # Meters (rapide - 64ms)
GET https://envoy.local/ivp/ensemble/status        # État ensemble batterie
GET https://envoy.local/ivp/ensemble/inventory     # Inventaire batteries
```

### Informations système
```
GET https://envoy.local/info                       # Info Envoy (no auth)
GET https://envoy.local/home.json                  # Résumé gateway
```

---

## 🔄 Comparaison avec Mode Cloud

### Requêtes API
| Opération | Local | Cloud |
|-----------|-------|-------|
| Authentification | 1x (JWT local) | 3x (Login + Session + Token) |
| Données batterie | 1-3 endpoints parallèles | 1 endpoint avec données agrégées |
| Fréquence update | 10s | 60s |
| Requêtes/jour | ~25,920 (mais locales!) | ~1,440 |

### Latence typique
```
Local:  Envoy ──64ms──> Home Assistant
Cloud:  Envoy ──> Enphase Cloud ──2500ms──> Home Assistant
```

---

## 🛠️ Dépannage

### Erreur "cannot_connect"
**Causes possibles :**
- Envoy non accessible sur le réseau
- Hostname incorrect
- Pare-feu bloquant les requêtes

**Solutions :**
```bash
# Tester la connectivité
ping envoy.local

# Tester l'API (sans certificat SSL)
curl -k https://envoy.local/info

# Vérifier les logs HA
Configuration → Journaux → Filtrer "enphase_battery"
```

### Erreur "invalid_auth"
**Causes possibles :**
- Mot de passe incorrect
- Firmware Envoy trop ancien

**Solutions :**
1. Laisser le champ password vide (auto-génération)
2. Vérifier le firmware Envoy (minimum D7.x.x)
3. Essayer avec le mot de passe installateur manuel

### Certificat SSL auto-signé
Le mode local utilise HTTPS avec certificat auto-signé.
L'intégration **désactive la vérification SSL** automatiquement (`ssl=False`).

---

## 📊 Données Disponibles

### Capteurs temps réel (10s)
- **battery_soc** : État de charge (%)
- **battery_power** : Puissance instantanée (W)
  - Négatif = Charge
  - Positif = Décharge
- **battery_voltage** : Tension (V)
- **battery_apparent_power** : Puissance apparente (VA)

### Informations système
- **available_energy** : Énergie disponible (Wh)
- **max_capacity** : Capacité max (Wh)
- **devices** : Liste des batteries individuelles
- **status** : État système (charging, discharging, idle)

---

## 🔮 Limitations Mode Local

### Fonctionnalités non disponibles
- ❌ Historique long terme (disponible uniquement via cloud)
- ❌ Accès distant hors réseau local
- ❌ Certains paramètres avancés (selon firmware)

### Endpoints non documentés
Certains endpoints de contrôle ne sont pas encore implémentés :
- `set_battery_mode()` - Changement de mode (à confirmer via MITM)
- `set_charge_from_grid()` - Contrôle charge réseau (à confirmer)

**Solution temporaire :** Utiliser le mode cloud pour ces actions.

---

## 🤝 Compatibilité Blueprint

Le blueprint **Gestion Intelligente Charge Batterie Enphase (Tempo + Météo)** fonctionne avec les deux modes :

### Mode Local recommandé si :
- ✅ Vous êtes sur le même réseau que l'Envoy
- ✅ Vous voulez une réactivité maximale
- ✅ Vous faites beaucoup d'automatisations

### Mode Cloud recommandé si :
- ✅ Vous voulez l'accès à distance
- ✅ Vous avez besoin de l'historique cloud
- ✅ Votre Envoy n'est pas accessible localement

**Bonus :** Les entités créées sont identiques, le blueprint fonctionne sans modification !

---

## 📚 Références

### Documentation officielle Enphase
- [IQ Gateway Local APIs Technical Brief](https://enphase.com/download/iq-gateway-local-apis-or-ui-access-using-token)

### Documentation communautaire
- [Matthew1471/Enphase-API](https://github.com/Matthew1471/Enphase-API) - Documentation complète endpoints locaux
- [Enphase-API PyPI](https://pypi.org/project/Enphase-API/) - Bibliothèque Python

### Fichiers du projet
- `/custom_components/enphase_battery/envoy_local_api.py` - Client API local
- `/custom_components/enphase_battery/config_flow.py` - Configuration dual-mode
- `/docs/API_ENDPOINTS.md` - Endpoints cloud documentés

---

## ⚠️ Notes importantes

1. **Firmware Envoy**
   - Nécessite IQ Gateway (Envoy-S ou plus récent)
   - Firmware D7.x.x minimum recommandé

2. **Sécurité**
   - API locale accessible uniquement sur réseau local
   - Authentification JWT avec timeout

3. **Performance réseau**
   - Envoy doit avoir une connexion stable au réseau local
   - Latence réseau affecte la réactivité (viser <100ms)

---

**Besoin d'aide ?** Ouvrir une issue sur [GitHub](https://github.com/foXaCe/enphase-battery/issues)
