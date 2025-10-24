# Script de Capture Enphase via mitmdump

Ce script capture tout le trafic entre l'app Enphase Energy Enlighten et les serveurs Enphase pour analyser les données des batteries IQ 5P.

## Installation

```bash
# Installer mitmproxy
pip install mitmproxy

# ou avec apt (Debian/Ubuntu)
sudo apt install mitmproxy
```

## Configuration de votre tablette Android

### 1. Configurer le proxy sur la tablette

1. Connectez votre tablette au même réseau que votre PC
2. Allez dans **Paramètres → Wi-Fi**
3. Appuyez longuement sur votre réseau Wi-Fi → **Modifier le réseau**
4. **Options avancées** → **Proxy** → **Manuel**
5. Entrez :
   - **Nom d'hôte** : Adresse IP de votre PC (ex: 192.168.1.100)
   - **Port** : 8080

### 2. Installer le certificat mitmproxy

Pour intercepter le trafic HTTPS, vous devez installer le certificat mitmproxy :

1. Démarrez mitmproxy : `mitmproxy`
2. Sur votre tablette, ouvrez un navigateur et allez sur : `http://mitm.it`
3. Téléchargez et installez le certificat pour Android
4. Allez dans **Paramètres → Sécurité → Certificats** et installez le certificat téléchargé

## Utilisation

### Démarrer la capture

```bash
cd /mnt/Media/Codage/GitHub/enphase-battery
mitmproxy -s scripts/enphase_mitm_capture.py --listen-port 8080
```

### Options avancées

```bash
# Mode sans interface (headless)
mitmdump -s scripts/enphase_mitm_capture.py --listen-port 8080

# Avec filtrage uniquement Enphase
mitmdump -s scripts/enphase_mitm_capture.py --listen-port 8080 \
  --flow-detail 2 "~d enlighten.enphaseenergy.com"
```

### Capturer le trafic

1. Ouvrez l'app **Enphase Energy Enlighten** sur votre tablette
2. Naviguez dans toutes les sections qui vous intéressent :
   - Vue d'ensemble des batteries
   - Détails de chaque batterie IQ 5P
   - Statistiques de charge/décharge
   - Paramètres de backup
   - Modes de fonctionnement
3. Le script capture automatiquement toutes les requêtes/réponses

### Fichiers générés

Le script crée deux fichiers dans `captured_data/` :

- **`enphase_capture_YYYYMMDD_HHMMSS.log`** : Log détaillé de toutes les requêtes
- **`enphase_data_YYYYMMDD_HHMMSS.json`** : Données JSON structurées pour analyse

## Analyse des données capturées

Une fois la capture terminée, vous pouvez analyser les fichiers JSON :

```bash
# Voir les endpoints utilisés
jq '[.[] | .request.path] | unique' captured_data/enphase_data_*.json

# Extraire les données de batteries
jq '.[] | select(.request.path | contains("battery"))' captured_data/enphase_data_*.json

# Voir la structure des réponses
jq '.[] | .response.data | keys' captured_data/enphase_data_*.json
```

## Points d'attention

- **Authentification** : Les tokens sont partiellement masqués dans les logs
- **Données sensibles** : Ne partagez pas vos fichiers de capture publiquement
- **Performance** : La capture peut ralentir légèrement l'app mobile

## Domaines capturés

Le script capture automatiquement les requêtes vers :
- `enlighten.enphaseenergy.com` - API cloud principale
- `api.enphaseenergy.com` - API secondaire
- `entrez.enphaseenergy.com` - Authentification
- `envoy.local` - Gateway local (si accessible)

## Prochaines étapes

Après avoir capturé les données :
1. Analyser les endpoints API découverts
2. Identifier les données spécifiques aux batteries IQ 5P
3. Créer l'intégration HACS pour Home Assistant
4. Implémenter les entités (sensors, switches, etc.)
