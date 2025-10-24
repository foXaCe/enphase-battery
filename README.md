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

1. Allez dans **Configuration** → **Intégrations**
2. Cliquez sur **+ Ajouter une intégration**
3. Recherchez **"Enphase Battery IQ 5P"**
4. Entrez vos identifiants Enphase Enlighten :
   - **Nom d'utilisateur** : Votre email Enphase
   - **Mot de passe** : Votre mot de passe Enphase
   - **Site ID** : (optionnel, auto-détecté) ID de votre site
   - **User ID** : (optionnel, auto-détecté) ID de votre compte

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

- `switch.battery_charge_from_grid` : Activer/désactiver la charge depuis le réseau
- `select.battery_mode` : Sélection du mode (Autoconsommation / Optimisation IA)
- `number.battery_stop_level` : Niveau d'arrêt de la batterie (5-25%)

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

1. Go to **Settings** → **Integrations**
2. Click **+ Add Integration**
3. Search for **"Enphase Battery IQ 5P"**
4. Enter your Enphase Enlighten credentials:
   - **Username**: Your Enphase email
   - **Password**: Your Enphase password
   - **Site ID**: (optional, auto-detected) Your site ID
   - **User ID**: (optional, auto-detected) Your account ID

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

- `switch.battery_charge_from_grid`: Enable/disable charging from grid
- `select.battery_mode`: Mode selection (Self Consumption / AI Optimization)
- `number.battery_stop_level`: Battery minimum discharge level (5-25%)

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
