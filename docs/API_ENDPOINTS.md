# Endpoints API Enphase - Batteries IQ 5P

Documentation des endpoints découverts via capture mitmdump de l'app Enphase Energy Enlighten v4.3.1

**Date de capture** : 24 octobre 2025
**Firmware Batterie** : v3.0.8507
**Modèle** : IQ Battery 5P FlexPhase (IQBATTERY-5P-3P-INT)

---

## 🔐 Authentification

### 1. Login
```
POST https://enlighten.enphaseenergy.com/login/login.json
```

### 2. Token Session
```
POST https://enlighten.enphaseenergy.com/service/auth_ms_enho/api/v1/session/token
```

### 3. Entrez Auth Token
```
GET https://enlighten.enphaseenergy.com/entrez-auth-token?serial_num={ENVOY_SERIAL}
```

---

## 📊 Données temps réel

### Données du jour (principal endpoint)
```
GET https://enlighten.enphaseenergy.com/pv/systems/{SITE_ID}/today
```

**Données retournées** :
- `battery_details.aggregate_soc` : État de charge (%)
- `battery_details.last_24h_consumption` : Consommation 24h (kWh)
- `battery_details.estimated_time` : Temps estimé restant
- `stats[].soc[]` : Historique SOC par intervalle 15min
- `stats[].charge[]` : Historique charge (W)
- `stats[].discharge[]` : Historique décharge (W)
- `stats[].battery_home[]` : Batterie → Maison (W)
- `stats[].grid_battery[]` : Réseau → Batterie (W)
- `stats[].battery_grid[]` : Batterie → Réseau (W)
- `batteryConfig` : Configuration complète batterie
- `connectionDetails` : État connexion Envoy

**Exemple réponse** :
```json
{
  "battery_details": {
    "aggregate_soc": 5,
    "last_24h_consumption": 28.0,
    "estimated_time": 0,
    "backup_type": 0
  },
  "batteryConfig": {
    "usage": "self-consumption",
    "battery_backup_percentage": 0,
    "charge_from_grid": true,
    "very_low_soc": 5
  }
}
```

### Dernière puissance
```
GET https://enlighten.enphaseenergy.com/app-api/{SITE_ID}/get_latest_power
```

---

## ⚙️ Configuration Batterie

### 1. Paramètres batterie
```
GET https://enlighten.enphaseenergy.com/service/batteryConfig/api/v1/batterySettings/{SITE_ID}?source=enho&userId={USER_ID}
```

**Données retournées** :
- `profile` : Mode actuel (self-consumption, cost_savings, backup_only, expert)
- `batteryBackupPercentage` : Réserve backup (%)
- `chargeFromGrid` : Charge depuis réseau activée
- `chargeBeginTime` : Heure début charge (minutes depuis minuit)
- `chargeEndTime` : Heure fin charge
- `veryLowSoc` : SOC minimum (%)
- `stormGuardState` : État Storm Guard
- `cfgControl` : Contrôle Charge From Grid
- `dtgControl` : Contrôle Discharge To Grid
- `rbdControl` : Contrôle Reserve Based Discharge

**Exemple réponse** :
```json
{
  "data": {
    "profile": "self-consumption",
    "batteryBackupPercentage": 0,
    "chargeFromGrid": true,
    "chargeBeginTime": 120,
    "chargeEndTime": 300,
    "veryLowSoc": 5,
    "cfgControl": {
      "enabled": true,
      "scheduleSupported": true
    }
  }
}
```

### 2. Profil batterie
```
GET https://enlighten.enphaseenergy.com/service/batteryConfig/api/v1/profile/{SITE_ID}?source=enho&userId={USER_ID}
```

**Données retournées** :
- `profile` : Mode de fonctionnement
- `operationModeSubType` : Sous-type mode
- `isTariffTou` : Tarif Time-of-Use
- `previousBatteryBackupPercentage` : Historique réserves par mode
- Contrôles DTG/CFG/RBD détaillés

### 3. Planning de charge
```
GET https://enlighten.enphaseenergy.com/service/batteryConfig/api/v1/battery/sites/{SITE_ID}/schedules
```

**Données retournées** :
```json
{
  "cfg": {
    "scheduleStatus": "active",
    "details": [{
      "scheduleId": "xxx",
      "startTime": "05:00",
      "endTime": "05:59",
      "limit": 100,
      "scheduleType": "CFG",
      "days": [1,2,3,4,5,6,7],
      "isEnabled": true
    }]
  },
  "dtg": { "details": null },
  "rbd": { "details": null }
}
```

### 4. Validation planning
```
GET https://enlighten.enphaseenergy.com/service/batteryConfig/api/v1/battery/sites/{SITE_ID}/schedules/isValid
```

### 5. Paramètres site
```
GET https://enlighten.enphaseenergy.com/service/batteryConfig/api/v1/siteSettings/{SITE_ID}?userId={USER_ID}
```

---

## 🔧 Devices & Hardware

### Liste des devices
```
GET https://enlighten.enphaseenergy.com/app-api/{SITE_ID}/devices.json
```

**Devices capturés** :
```json
{
  "result": [
    {
      "type": "encharge",
      "devices": [{
        "name": "IQ Battery 5P FlexPhase",
        "serial_number": "123456789012",
        "sku_id": "IQBATTERY-5P-3P-INT",
        "status": "normal",
        "sw_version": "522-00002-01-v3.0.8507_rel/31.43",
        "warranty_end_date": "2040-10-23"
      }]
    },
    {
      "type": "envoy",
      "devices": [...]
    },
    {
      "type": "meter",
      "devices": [...]
    }
  ]
}
```

### Données système
```
GET https://enlighten.enphaseenergy.com/app-api/{SITE_ID}/data.json?app=1&device_status=non_retired&is_mobile=1
```

---

## 📡 Streaming temps réel (MQTT)

### Obtenir URL signée MQTT
```
GET https://enlighten.enphaseenergy.com/service/batteryConfig/api/v1/mqttSignedUrl/{SITE_ID}
```

**Réponse** :
```json
{
  "topic": "v1/server/response-stream/{SESSION_ID}",
  "stream_duration": 900,
  "aws_iot_endpoint": "a3ayogyffhzcp1-ats.iot.us-east-1.amazonaws.com",
  "aws_authorizer": "aws-lambda-authoriser-prod",
  "aws_token_key": "enph_token",
  "aws_token_value": "{TOKEN}",
  "aws_digest": "{DIGEST}"
}
```

**Utilisation** : Connexion WebSocket MQTT sur AWS IoT pour recevoir les mises à jour temps réel de la batterie.

---

## 🌤️ Données complémentaires

### Météo
```
GET https://enlighten.enphaseenergy.com/systems/{SITE_ID}/weather.json
```

### Énergie quotidienne
```
GET https://enlighten.enphaseenergy.com/pv/systems/{SITE_ID}/daily_energy?start_date=YYYY-MM-DD
```

### Production onduleurs
```
GET https://enlighten.enphaseenergy.com/systems/{SITE_ID}/inverter_status_x.json
```

### Données onduleurs (énergie)
```
GET https://enlighten.enphaseenergy.com/systems/{SITE_ID}/inverter_data_x/energy.json?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD
```

---

## 🔄 Actions (POST)

### Changer le mode batterie
**Endpoint à déterminer** - Nécessite capture lors du changement de mode dans l'app

### Modifier réserve backup
**Endpoint à déterminer** - Nécessite capture lors de la modification

### Activer/désactiver Charge From Grid
**Endpoint à déterminer** - Nécessite capture

---

## 📝 Notes importantes

1. **Rate limiting** : Utiliser intervalle de 30-60s pour polling
2. **Session** : Les tokens expirent, implémenter re-authentification
3. **MQTT** : Pour temps réel, utiliser MQTT plutôt que polling agressif
4. **Site ID** : Récupérable via `/app-api/search_sites.json`
5. **User ID** : Récupérable après login

## 🔒 Sécurité

⚠️ **NE JAMAIS commiter** :
- Tokens d'authentification
- Numéros de série
- Site IDs
- User IDs
- Données de localisation

---

**Prochaines étapes** :
1. Implémenter client API Python avec gestion authentification
2. Créer coordinator Home Assistant avec polling intelligent
3. Implémenter entités (sensors, switches, selects, numbers)
4. Ajouter support MQTT pour temps réel (optionnel)
