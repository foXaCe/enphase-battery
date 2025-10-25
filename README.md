# Enphase Battery IQ 5P - Intégration Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/custom-components/hacs)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Intégration Home Assistant pour les batteries Enphase IQ 5P avec support étendu des fonctionnalités non disponibles dans l'intégration officielle.

[English](#english) | [Français](#français)

---

## Français

## 💰 Soutenir le Projet

Si cette intégration vous est utile, vous pouvez soutenir son développement avec un don en Bitcoin :

**🪙 Adresse Bitcoin :** `bc1qhe4ge22x0anuyeg0fmts6rdmz3t735dnqwt3p7`

Vos contributions m'aident à continuer d'améliorer ce projet et à ajouter de nouvelles fonctionnalités. Merci ! 🙏

### 🎯 Objectif

L'intégration officielle Enphase Envoy de Home Assistant ne gère pas correctement les batteries IQ 5P. Cette intégration custom vise à :

- ✅ **Triple-mode** : Local, Cloud OU **Hybride** (local + cloud)
- ✅ **Mode local** : Latence 64ms, pas de quota API, polling 10s
- ✅ **Mode hybride** : Données locales rapides + contrôle cloud (recommandé pour firmware 8.x)
- ✅ **Synchronisation temps réel** : États de contrôle lus depuis le cloud en mode hybride
- ✅ **Stockage persistant** : Données d'énergie quotidienne conservées après redémarrage
- ✅ Capturer toutes les données disponibles de l'app mobile Enphase Energy Enlighten
- ✅ Exposer l'état de charge (SOC) en temps réel
- ✅ Contrôler les modes de fonctionnement des batteries
- ✅ Accéder aux statistiques détaillées de charge/décharge
- ✅ Gérer les paramètres de backup et réserve

### 📋 Prérequis

- Home Assistant 2024.1.0 ou supérieur
- Système Enphase avec batteries IQ 5P
- Passerelle Enphase Envoy
- (Optionnel) `mitmproxy` pour capturer les données de l'app mobile

### 🚀 Installation

#### Via HACS (recommandé)

1. Ouvrez HACS dans Home Assistant
2. Allez dans "Intégrations"
3. Cliquez sur les 3 points en haut à droite
4. Sélectionnez "Dépôts personnalisés"
5. Ajoutez l'URL : `https://github.com/foXaCe/enphase-battery`
6. Catégorie : "Integration"
7. Cliquez sur "Télécharger"
8. Redémarrez Home Assistant

#### Installation manuelle

1. Téléchargez ce dépôt
2. Copiez le dossier `custom_components/enphase_battery` vers `config/custom_components/`
3. Redémarrez Home Assistant

### ⚙️ Configuration

#### Mode Hybride (Recommandé pour firmware 8.x)

**⚡ Meilleur des deux mondes : données locales rapides + contrôle cloud fonctionnel**

1. Allez dans **Configuration** → **Intégrations**
2. Cliquez sur **+ Ajouter une intégration**
3. Recherchez **"Enphase Battery IQ 5P"**
4. **Choisir "Local"** (Envoy direct)
5. Entrez les informations :
   - **Hostname ou IP** : `envoy.local` ou IP fixe (ex: `192.168.1.50`)
   - **Email Enphase** : Votre email Enlighten (requis pour firmware 7.x/8.x)
   - **Mot de passe Enphase** : Votre mot de passe Enlighten
   - **✅ Activer le contrôle cloud (mode hybride)** : Cocher cette case

**Avantages du mode hybride :**
- 📊 Capteurs ultra-rapides (polling local 10s, latence 64ms)
- 🎛️ Switch et select fonctionnels (via API cloud)
- 🔄 États de contrôle synchronisés en temps réel depuis le cloud
- ⚡ UI réactive (changements visibles dès le prochain update ~10s max)
- ❌ Pas de quota API pour les données (seulement pour les contrôles)

> **Note firmware 8.x :** L'API locale ne supporte plus le contrôle des batteries depuis le firmware 8.2.4225. Le mode hybride est donc obligatoire pour utiliser les switch/select.

#### Mode Local Pur (Capteurs uniquement)

1. Même procédure que le mode hybride
2. **Ne PAS cocher** "Activer le contrôle cloud"
3. Les switch et select seront désactivés (limitation firmware 8.x)

#### Mode Cloud Pur (Alternative)

1. Même procédure, mais choisir **"Cloud"** (Enlighten)
2. Entrez vos identifiants Enphase Enlighten :
   - **Email** : Votre email Enphase
   - **Mot de passe** : Votre mot de passe Enphase
   - **Site ID** : (optionnel, auto-détecté)
   - **User ID** : (optionnel, auto-détecté)

**Inconvénients :**
- ⏱️ Polling lent (60s au lieu de 10s)
- 🌐 Latence élevée (accès via serveurs Enphase)
- 📊 Quota API consommé pour tous les appels

📖 **[Documentation détaillée du mode local](docs/LOCAL_MODE.md)**

### 📊 Entités disponibles

#### Capteurs (Sensors)

| Entité | Description | Unité |
|--------|-------------|-------|
| `sensor.battery_soc` | État de charge de la batterie | % |
| `sensor.battery_power` | Puissance instantanée | W |
| `sensor.battery_voltage` | Tension | V |
| `sensor.battery_current` | Courant | A |
| `sensor.battery_temperature` | Température | °C |
| `sensor.battery_energy_charged` | Énergie chargée aujourd'hui | kWh |
| `sensor.battery_energy_discharged` | Énergie déchargée aujourd'hui | kWh |
| `sensor.battery_capacity` | Capacité totale | kWh |
| `sensor.battery_health` | État de santé | % |

#### Capteurs binaires (Binary Sensors)

- `binary_sensor.battery_charging` : Batterie en charge
- `binary_sensor.battery_connected` : Batterie connectée

#### Contrôles (Controls)

> **Important :** Les contrôles nécessitent le **mode cloud** ou **mode hybride** (firmware 8.x ne supporte plus le contrôle via API locale)

- `switch.enphase_battery_iq_5p_charge_depuis_le_reseau` : Activer/désactiver la charge depuis le réseau
  - 🔄 En mode hybride : état synchronisé en temps réel depuis le cloud (visible en ~10s max)
- `select.enphase_battery_iq_5p_mode_de_la_batterie` : Sélection du mode de fonctionnement
  - Autoconsommation (self-consumption)
  - Optimisation IA (cost_savings)
  - 🔄 En mode hybride : état synchronisé en temps réel depuis le cloud (visible en ~10s max)

### 🔍 Capture des données avec mitmdump

Pour découvrir de nouvelles fonctionnalités ou déboguer :

```bash
# Installation de mitmproxy
pip install mitmproxy

# Lancer la capture
cd /mnt/Media/Codage/GitHub/enphase-battery
mitmproxy -s scripts/enphase_mitm_capture.py --listen-port 8080
```

Consultez [scripts/README_CAPTURE.md](scripts/README_CAPTURE.md) pour le guide complet.

### 🐛 Dépannage

**Problème de connexion**
- Vérifiez que votre Envoy est accessible sur le réseau
- Testez l'accès via navigateur : `http://[IP_ENVOY]`

**Données manquantes**
- Certaines fonctionnalités nécessitent un firmware Envoy récent
- Vérifiez les logs : **Configuration** → **Journaux**

**Erreur d'authentification**
- Vérifiez vos identifiants Enphase
- Assurez-vous que le compte a accès au système

### 🤝 Contribution

Les contributions sont les bienvenues ! Voir [CONTRIBUTING.md](CONTRIBUTING.md)

### 📄 Licence

MIT License - voir [LICENSE](LICENSE)

---

## English

## 💰 Support the Project

If this integration is useful to you, you can support its development with a Bitcoin donation:

**🪙 Bitcoin Address:** `bc1qhe4ge22x0anuyeg0fmts6rdmz3t735dnqwt3p7`

Your contributions help me continue improving this project and adding new features. Thank you! 🙏

### 🎯 Purpose

The official Enphase Envoy integration in Home Assistant doesn't properly support IQ 5P batteries. This custom integration aims to:

- ✅ **Triple-mode**: Local, Cloud OR **Hybrid** (local + cloud)
- ✅ **Local mode**: 64ms latency, no API quota, 10s polling
- ✅ **Hybrid mode**: Fast local data + cloud control (recommended for firmware 8.x)
- ✅ **Real-time sync**: Control states read from cloud in hybrid mode
- ✅ **Persistent storage**: Daily energy data preserved after restart
- ✅ Capture all available data from the Enphase Energy Enlighten mobile app
- ✅ Expose real-time state of charge (SOC)
- ✅ Control battery operation modes
- ✅ Access detailed charge/discharge statistics
- ✅ Manage backup settings and reserve

### 📋 Requirements

- Home Assistant 2024.1.0 or higher
- Enphase system with IQ 5P batteries
- Enphase Envoy gateway
- (Optional) `mitmproxy` for capturing mobile app data

### 🚀 Installation

#### Via HACS (recommended)

1. Open HACS in Home Assistant
2. Go to "Integrations"
3. Click on the 3 dots in the top right
4. Select "Custom repositories"
5. Add URL: `https://github.com/foXaCe/enphase-battery`
6. Category: "Integration"
7. Click "Download"
8. Restart Home Assistant

#### Manual installation

1. Download this repository
2. Copy the `custom_components/enphase_battery` folder to `config/custom_components/`
3. Restart Home Assistant

### ⚙️ Configuration

#### Hybrid Mode (Recommended for firmware 8.x)

**⚡ Best of both worlds: fast local data + functional cloud control**

1. Go to **Settings** → **Integrations**
2. Click **+ Add Integration**
3. Search for **"Enphase Battery IQ 5P"**
4. **Choose "Local"** (Envoy direct)
5. Enter information:
   - **Hostname or IP**: `envoy.local` or fixed IP (e.g., `192.168.1.50`)
   - **Enphase Email**: Your Enlighten email (required for firmware 7.x/8.x)
   - **Enphase Password**: Your Enlighten password
   - **✅ Enable cloud control (hybrid mode)**: Check this box

**Hybrid mode benefits:**
- 📊 Ultra-fast sensors (10s local polling, 64ms latency)
- 🎛️ Functional switch and select (via cloud API)
- 🔄 Control states synced in real-time from cloud
- ⚡ Responsive UI (changes visible within next update ~10s max)
- ❌ No API quota for data (only for controls)

> **Firmware 8.x note:** Local API no longer supports battery control since firmware 8.2.4225. Hybrid mode is required to use switch/select.

#### Pure Local Mode (Sensors only)

1. Same procedure as hybrid mode
2. **Do NOT check** "Enable cloud control"
3. Switch and select will be disabled (firmware 8.x limitation)

#### Pure Cloud Mode (Alternative)

1. Same procedure, but choose **"Cloud"** (Enlighten)
2. Enter your Enphase Enlighten credentials:
   - **Email**: Your Enphase email
   - **Password**: Your Enphase password
   - **Site ID**: (optional, auto-detected)
   - **User ID**: (optional, auto-detected)

**Disadvantages:**
- ⏱️ Slow polling (60s instead of 10s)
- 🌐 High latency (access via Enphase servers)
- 📊 API quota consumed for all calls

📖 **[Detailed local mode documentation](docs/LOCAL_MODE.md)**

### 📊 Available Entities

#### Sensors

| Entity | Description | Unit |
|--------|-------------|------|
| `sensor.battery_soc` | Battery state of charge | % |
| `sensor.battery_power` | Instantaneous power | W |
| `sensor.battery_voltage` | Voltage | V |
| `sensor.battery_current` | Current | A |
| `sensor.battery_temperature` | Temperature | °C |
| `sensor.battery_energy_charged` | Energy charged today | kWh |
| `sensor.battery_energy_discharged` | Energy discharged today | kWh |
| `sensor.battery_capacity` | Total capacity | kWh |
| `sensor.battery_health` | Battery health | % |

#### Binary Sensors

- `binary_sensor.battery_charging`: Battery charging status
- `binary_sensor.battery_connected`: Battery connection status

#### Controls

> **Important:** Controls require **cloud mode** or **hybrid mode** (firmware 8.x no longer supports control via local API)

- `switch.enphase_battery_iq_5p_charge_depuis_le_reseau`: Enable/disable charging from grid
  - 🔄 In hybrid mode: state synced in real-time from cloud (visible within ~10s max)
- `select.enphase_battery_iq_5p_mode_de_la_batterie`: Battery operation mode selection
  - Self Consumption (self-consumption)
  - AI Optimization (cost_savings)
  - 🔄 In hybrid mode: state synced in real-time from cloud (visible within ~10s max)

### 🔍 Data Capture with mitmdump

To discover new features or debug:

```bash
# Install mitmproxy
pip install mitmproxy

# Start capture
cd /mnt/Media/Codage/GitHub/enphase-battery
mitmproxy -s scripts/enphase_mitm_capture.py --listen-port 8080
```

See [scripts/README_CAPTURE.md](scripts/README_CAPTURE.md) for the complete guide.

### 🐛 Troubleshooting

**Connection issues**
- Verify your Envoy is accessible on the network
- Test access via browser: `http://[ENVOY_IP]`

**Missing data**
- Some features require recent Envoy firmware
- Check logs: **Settings** → **Logs**

**Authentication error**
- Verify your Enphase credentials
- Ensure the account has access to the system

### 🤝 Contributing

Contributions are welcome! See [CONTRIBUTING.md](CONTRIBUTING.md)

### 📄 License

MIT License - see [LICENSE](LICENSE)
