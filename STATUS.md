# 📊 État du projet Enphase Battery IQ 5P

**Dernière mise à jour** : 24 octobre 2025
**Version** : 0.1.0-dev
**Statut** : 🚧 En développement

---

## ✅ Complété

### 1. Capture des données API ✅
- [x] Script mitmdump fonctionnel
- [x] 120 requêtes API capturées
- [x] Données batterie IQ 5P découvertes
- [x] Documentation endpoints complète
- [x] Identification connexion MQTT AWS IoT

**Fichiers** :
- `scripts/enphase_mitm_capture.py`
- `scripts/README_CAPTURE.md`
- `docs/API_ENDPOINTS.md`

### 2. Architecture intégration ✅
- [x] Structure HACS configurée
- [x] Manifest.json créé
- [x] Fichiers traduction FR/EN complets
- [x] Config flow avec options
- [x] Support MQTT optionnel

**Fichiers** :
- `custom_components/enphase_battery/`
- `hacs.json`
- `translations/fr.json`, `translations/en.json`

### 3. Client API Python ✅
- [x] Classe `EnphaseBatteryAPI` créée
- [x] Parsing données batterie
- [x] Méthodes pour tous les endpoints
- [x] Gestion erreurs et timeouts

**Fichier** : `custom_components/enphase_battery/api.py`

### 4. Support MQTT ✅
- [x] Classe `EnphaseMQTTClient` créée
- [x] Structure connexion AWS IoT
- [x] Option config flow
- [x] Documentation comparative MQTT vs Polling

**Fichiers** :
- `custom_components/enphase_battery/mqtt_client.py`
- `docs/MQTT_VS_POLLING.md`

---

## 🚧 En cours

### Client API
- [ ] Implémentation authentification complète
- [ ] Tests connexion réelle
- [ ] Gestion refresh token

### MQTT
- [ ] Implémentation connexion AWS IoT avec custom authorizer
- [ ] Tests réception messages temps réel
- [ ] Reconnexion automatique

---

## 📋 À faire

### Priorité 1 - Core Features
- [ ] **Coordinator** - DataUpdateCoordinator avec support dual mode
- [ ] **Sensor.py** - Entités capteurs (SOC, puissance, énergie)
- [ ] **Binary Sensor.py** - État charge, connexion
- [ ] **Select.py** - Sélection mode batterie
- [ ] **Number.py** - Réserve backup
- [ ] **Switch.py** - Charge From Grid on/off

### Priorité 2 - Actions
- [ ] **Services** - set_battery_mode, set_backup_reserve
- [ ] **Endpoints POST** - Capture changement config dans app
- [ ] **Validation** - Tests avec vraie batterie IQ 5P

### Priorité 3 - Polish
- [ ] **Tests unitaires** - pytest coverage
- [ ] **Documentation utilisateur** - Installation, config
- [ ] **CI/CD** - GitHub Actions
- [ ] **Icônes** - icons.json avec Material Design Icons

---

## 📊 Données capturées

### Batterie découverte
```json
{
  "name": "IQ Battery 5P FlexPhase",
  "serial_number": "492510005186",
  "sku_id": "IQBATTERY-5P-3P-INT",
  "sw_version": "v3.0.8507",
  "warranty_end_date": "2040-10-23"
}
```

### Configuration actuelle
- **Mode** : `self-consumption`
- **SOC minimum** : `5%`
- **Réserve backup** : `0%` (configurable 10-100%)
- **Charge réseau** : Activée (02:00-05:00)

### Endpoints API fonctionnels
1. ✅ `/pv/systems/{id}/today` - Données temps réel
2. ✅ `/service/batteryConfig/api/v1/batterySettings/{id}` - Config
3. ✅ `/service/batteryConfig/api/v1/profile/{id}` - Profil
4. ✅ `/service/batteryConfig/api/v1/battery/sites/{id}/schedules` - Planning
5. ✅ `/service/batteryConfig/api/v1/mqttSignedUrl/{id}` - Token MQTT
6. ✅ `/app-api/{id}/devices.json` - Liste devices

### Endpoints POST à découvrir
1. ❓ Changement mode batterie
2. ❓ Modification réserve backup
3. ❓ Activation/désactivation Charge From Grid
4. ❓ Modification planning CFG

---

## 🎯 Roadmap

### v0.1.0 (MVP) - En cours
- [x] Capture données API
- [x] Structure projet HACS
- [x] Client API base
- [ ] Coordinator polling
- [ ] Entités sensors de base
- [ ] Installation fonctionnelle

**Objectif** : Intégration minimale fonctionnelle en mode polling

### v0.2.0 - Contrôles
- [ ] Entités select/number/switch
- [ ] Services HA pour actions
- [ ] POST endpoints découverts
- [ ] MQTT expérimental testé

**Objectif** : Contrôle complet batterie depuis HA

### v0.3.0 - MQTT Production
- [ ] MQTT stable et testé
- [ ] Auto-switch polling/MQTT
- [ ] Métriques performance
- [ ] Dashboard statistiques

**Objectif** : MQTT production-ready

### v1.0.0 - Stable
- [ ] Tests complets
- [ ] Documentation complète
- [ ] Soumission HACS officiel
- [ ] Support communauté

**Objectif** : Version stable grand public

---

## 📁 Structure du projet

```
enphase-battery/
├── custom_components/enphase_battery/  # Intégration HA
│   ├── api.py                          # ✅ Client API
│   ├── mqtt_client.py                  # ✅ Client MQTT
│   ├── config_flow.py                  # ✅ Config UI
│   ├── const.py                        # ✅ Constantes
│   ├── __init__.py                     # ✅ Setup intégration
│   ├── coordinator.py                  # ❌ À créer
│   ├── sensor.py                       # ❌ À créer
│   ├── binary_sensor.py                # ❌ À créer
│   ├── select.py                       # ❌ À créer
│   ├── number.py                       # ❌ À créer
│   ├── switch.py                       # ❌ À créer
│   └── translations/                   # ✅ FR + EN
├── docs/                               # Documentation
│   ├── API_ENDPOINTS.md                # ✅ Ref API
│   └── MQTT_VS_POLLING.md              # ✅ Guide choix
├── scripts/                            # Outils dev
│   ├── enphase_mitm_capture.py         # ✅ Capture
│   └── README_CAPTURE.md               # ✅ Guide
├── README.md                           # ✅ Doc principale
├── GUIDE_UTILISATION.md                # ✅ Guide setup
└── hacs.json                           # ✅ Config HACS
```

---

## 🔧 Pour continuer le développement

### 1. Créer le coordinator
```python
# coordinator.py
class EnphaseBatteryDataUpdateCoordinator(DataUpdateCoordinator):
    """Gère polling + optionnel MQTT"""
```

### 2. Créer les entités
```python
# sensor.py
class BatterySOCSensor(CoordinatorEntity, SensorEntity):
    """Entité SOC batterie"""
```

### 3. Tester l'authentification
- Utiliser credentials réels
- Tester connexion API
- Récupérer site_id et user_id

### 4. Implémenter MQTT
- Connexion AWS IoT avec token
- Parser messages MQTT
- Intégrer dans coordinator

---

## 🛠️ Commandes utiles

### Analyser les données capturées
```bash
# Compter requêtes
jq 'length' captured_data/enphase_data_*.json

# Endpoints uniques
jq -r '[.[] | .request.path] | unique[]' captured_data/enphase_data_*.json

# Données batterie
jq '.[] | select(.request.path | contains("batterySettings"))' captured_data/enphase_data_*.json
```

### Tester l'intégration
```bash
# Copier dans HA
cp -r custom_components/enphase_battery /path/to/homeassistant/custom_components/

# Redémarrer HA
ha core restart

# Voir logs
tail -f /path/to/homeassistant/home-assistant.log | grep enphase_battery
```

---

## 📞 Support

**GitHub** : https://github.com/your-username/enphase-battery
**Issues** : https://github.com/your-username/enphase-battery/issues
**Docs** : Voir dossier `/docs`

---

**Prochaine étape recommandée** : Créer `coordinator.py` avec support dual polling/MQTT
