# Guide d'utilisation - Enphase Battery IQ 5P

Ce guide vous accompagne étape par étape pour capturer les données de votre app Enphase et créer votre intégration personnalisée.

## 📱 Phase 1 : Capture des données de l'app mobile

### Prérequis

- Une tablette Android avec l'app **Enphase Energy Enlighten** installée
- Un PC Linux/Windows/Mac sur le même réseau Wi-Fi
- Python 3.8+ et mitmproxy

### Installation de mitmproxy

```bash
# Sur Ubuntu/Debian
sudo apt update
sudo apt install mitmproxy

# Ou via pip
pip install mitmproxy

# Vérifier l'installation
mitmproxy --version
```

### Configuration du proxy sur Android

1. **Trouver l'IP de votre PC**
   ```bash
   # Sur Linux
   ip addr show | grep "inet "

   # Vous devriez voir quelque chose comme : 192.168.1.100
   ```

2. **Configurer le proxy sur la tablette**
   - Ouvrez **Paramètres** → **Réseau et Internet** → **Wi-Fi**
   - Appuyez longuement sur votre réseau Wi-Fi actuel
   - Sélectionnez **Modifier le réseau**
   - Cochez **Afficher les options avancées**
   - Sous **Proxy**, sélectionnez **Manuel**
   - **Nom d'hôte du proxy** : `192.168.1.100` (votre IP PC)
   - **Port du proxy** : `8080`
   - Cliquez sur **Enregistrer**

3. **Installer le certificat mitmproxy**

   Sur votre PC, démarrez mitmproxy :
   ```bash
   mitmproxy --listen-port 8080
   ```

   Sur votre tablette :
   - Ouvrez le navigateur Chrome
   - Allez sur `http://mitm.it`
   - Téléchargez le certificat pour Android
   - Allez dans **Paramètres** → **Sécurité** → **Chiffrement et identifiants**
   - Sélectionnez **Installer un certificat**
   - Choisissez **Certificat CA**
   - Sélectionnez le fichier téléchargé depuis mitm.it
   - Donnez un nom (ex: "mitmproxy") et validez

### Lancement de la capture

1. **Démarrer le script de capture**
   ```bash
   cd /mnt/Media/Codage/GitHub/enphase-battery
   mitmdump -s scripts/enphase_mitm_capture.py --listen-port 8080
   ```

2. **Utiliser l'app Enphase sur la tablette**

   Ouvrez l'app **Enphase Energy Enlighten** et naviguez dans toutes les sections :

   - ✅ Écran d'accueil / Dashboard
   - ✅ Vue détaillée des batteries
   - ✅ Cliquez sur chaque batterie IQ 5P individuellement
   - ✅ Statistiques de production
   - ✅ Graphiques historiques
   - ✅ Paramètres des batteries
   - ✅ Modes de fonctionnement (backup, autoconsommation, etc.)
   - ✅ Réglages de réserve
   - ✅ Tout autre écran disponible

3. **Vérifier la capture**

   Dans le terminal où tourne mitmdump, vous devriez voir :
   ```
   🚀 Session de capture démarrée: 20241024_143052
   📁 Logs: captured_data/enphase_capture_20241024_143052.log
   📊 JSON: captured_data/enphase_data_20241024_143052.json

   ================================================================================
   📤 REQUÊTE #1
   URL: GET https://enlighten.enphaseenergy.com/api/v1/systems/12345/summary
   ...
   ```

4. **Arrêter la capture**

   Appuyez sur `Ctrl+C` pour arrêter mitmdump. Les fichiers sont sauvegardés automatiquement.

5. **Nettoyer la configuration**

   Sur votre tablette :
   - Retournez dans les paramètres Wi-Fi
   - Remettez le proxy sur **Aucun**
   - (Optionnel) Supprimez le certificat mitmproxy depuis **Paramètres** → **Sécurité**

## 🔍 Phase 2 : Analyse des données capturées

### Localisation des fichiers

```bash
cd /mnt/Media/Codage/GitHub/enphase-battery/captured_data
ls -lh
```

Vous devriez voir :
- `enphase_capture_YYYYMMDD_HHMMSS.log` - Log détaillé
- `enphase_data_YYYYMMDD_HHMMSS.json` - Données structurées JSON

### Analyse avec jq

```bash
# Installer jq si nécessaire
sudo apt install jq

# Lister tous les endpoints capturés
jq '[.[] | .request.path] | unique' enphase_data_*.json

# Exemple de sortie :
# [
#   "/api/v1/systems/12345/summary",
#   "/api/v1/systems/12345/batteries",
#   "/api/v1/systems/12345/batteries/123/details"
# ]

# Voir la structure d'une réponse batterie
jq '.[] | select(.request.path | contains("batteries")) | .response.data' enphase_data_*.json

# Extraire les données de SOC
jq '.[] | select(.request.path | contains("batteries")) | .response.data.soc' enphase_data_*.json
```

### Identifier les informations clés

Recherchez dans les données JSON :

**Pour les batteries IQ 5P :**
- État de charge (SOC) : cherchez `soc`, `stateOfCharge`, `battery_level`
- Puissance : cherchez `power`, `watts`, `battery_power`
- Modes : cherchez `mode`, `operation_mode`, `backup_mode`
- Statut : cherchez `status`, `state`, `charging`

**Exemple de structure attendue :**
```json
{
  "batteries": [
    {
      "serial": "123456789",
      "model": "IQ5P",
      "soc": 85,
      "power": -1500,
      "voltage": 240,
      "temperature": 25,
      "status": "discharging"
    }
  ]
}
```

## 🔧 Phase 3 : Développement de l'intégration

### Structure actuelle du projet

```
enphase-battery/
├── custom_components/
│   └── enphase_battery/
│       ├── __init__.py          # Point d'entrée
│       ├── config_flow.py       # Configuration UI
│       ├── const.py             # Constantes
│       ├── manifest.json        # Métadonnées HACS
│       ├── strings.json         # Traductions par défaut
│       └── translations/
│           ├── en.json          # Anglais
│           └── fr.json          # Français
├── scripts/
│   ├── enphase_mitm_capture.py  # Script de capture
│   └── README_CAPTURE.md        # Guide capture
└── README.md                    # Documentation principale
```

### Prochaines étapes de développement

1. **Créer le client API** (`api.py`)
   - Implémenter les appels HTTP vers les endpoints découverts
   - Gérer l'authentification
   - Parser les réponses JSON

2. **Créer le coordinator** (`coordinator.py`)
   - Gérer le polling périodique
   - Centraliser les données
   - Gérer les erreurs de connexion

3. **Créer les entités**
   - `sensor.py` : Capteurs (SOC, puissance, température, etc.)
   - `binary_sensor.py` : Capteurs binaires (charging, connected)
   - `switch.py` : Interrupteurs (backup mode)
   - `select.py` : Sélecteurs (mode de fonctionnement)
   - `number.py` : Nombres (réserve de batterie)

4. **Implémenter les services**
   - Service pour changer le mode de batterie
   - Service pour définir la réserve
   - Service pour forcer une mise à jour

### Template de développement

Créez `custom_components/enphase_battery/api.py` :

```python
"""API Client for Enphase Battery."""
import aiohttp
from typing import Any

class EnphaseAPI:
    """API client for Enphase."""

    def __init__(self, host: str, username: str = None, password: str = None):
        self.host = host
        self.username = username
        self.password = password
        self._session: aiohttp.ClientSession | None = None

    async def get_battery_data(self) -> dict[str, Any]:
        """Get battery data from the API."""
        # TODO: Implémenter selon les endpoints découverts
        url = f"https://{self.host}/api/v1/batteries"
        # ...
        pass

    async def set_battery_mode(self, mode: str) -> bool:
        """Set battery operation mode."""
        # TODO: Implémenter
        pass
```

## 📊 Phase 4 : Tests et validation

### Test en environnement de développement

1. **Copier l'intégration dans Home Assistant**
   ```bash
   cp -r custom_components/enphase_battery /path/to/homeassistant/custom_components/
   ```

2. **Redémarrer Home Assistant**

3. **Ajouter l'intégration**
   - Allez dans **Configuration** → **Intégrations**
   - Cliquez sur **+ Ajouter une intégration**
   - Recherchez "Enphase Battery IQ 5P"

4. **Vérifier les logs**
   ```bash
   tail -f /path/to/homeassistant/home-assistant.log | grep enphase_battery
   ```

### Validation des données

Créez des automatisations de test :

```yaml
# configuration.yaml
automation:
  - alias: "Test Battery SOC"
    trigger:
      - platform: numeric_state
        entity_id: sensor.battery_soc
        below: 20
    action:
      - service: notify.mobile_app
        data:
          message: "Batterie faible : {{ states('sensor.battery_soc') }}%"
```

## 🚀 Phase 5 : Publication sur HACS

Une fois l'intégration stable :

1. Créer un repository GitHub public
2. Ajouter les fichiers requis par HACS
3. Créer une release
4. Soumettre à HACS

## 💡 Conseils

- **Sécurité** : Ne commitez JAMAIS vos fichiers de capture (ils contiennent vos tokens)
- **Versions** : Notez la version de firmware de votre Envoy
- **Communauté** : Partagez vos découvertes sur les forums Home Assistant
- **Backup** : Gardez une copie de vos données de capture

## ❓ Besoin d'aide ?

- Consultez les logs de capture
- Vérifiez la documentation de l'API Enphase (si disponible)
- Posez des questions dans les issues GitHub
