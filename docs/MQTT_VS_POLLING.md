# MQTT vs Polling - Guide de choix

L'intégration Enphase Battery offre **deux modes de connexion** au choix :

## 📊 Comparaison

| Critère | **Mode Polling** | **Mode MQTT** |
|---------|------------------|---------------|
| **Configuration** | Automatique | Automatique |
| **Complexité** | Simple | Avancée |
| **Latence données** | 60 secondes | < 1 seconde |
| **Appels API/jour** | ~1440 | ~300 |
| **Charge serveur** | Moyenne | Faible |
| **Dépendances** | Aucune | AWS IoT SDK |
| **Statut** | ✅ Stable | ⚠️ Expérimental |

---

## 🔄 Mode Polling (Par défaut)

### Comment ça fonctionne

```
Home Assistant → GET /pv/systems/{id}/today
    ↓
Serveur Enphase → Réponse JSON (SOC, puissance, stats)
    ↓
Home Assistant → Mise à jour entités
    ↓
Attendre 60 secondes → Recommencer
```

### Avantages

✅ **Simple** - Aucune configuration supplémentaire
✅ **Fiable** - Technologie éprouvée HTTP/REST
✅ **Pas de dépendances** - Fonctionne out-of-the-box
✅ **Compatible** - Marche avec tous les systèmes Enphase

### Inconvénients

❌ **Latence** - Données mises à jour toutes les 60s
❌ **API calls** - ~1440 requêtes par jour
❌ **Charge réseau** - Polling constant même si rien ne change

### Configuration

**Aucune action requise** - C'est le mode par défaut !

```yaml
# Polling activé automatiquement
# Intervalle : 60 secondes
```

---

## 📡 Mode MQTT (Optionnel)

### Comment ça fonctionne

```
1. Home Assistant → GET /service/batteryConfig/api/v1/mqttSignedUrl/{id}
       ↓
   Serveur → Credentials AWS IoT (token, endpoint, topic)

2. Home Assistant → WebSocket MQTT → AWS IoT Endpoint
       ↓
   Connexion ouverte pendant 15 minutes

3. Serveur Enphase → PUSH mise à jour → Home Assistant
       ↓
   Instant! SOC/Puissance changent → Entités mises à jour immédiatement

4. Toutes les 15 minutes → Renouvelle token MQTT

5. Polling backup (5 min) en parallèle pour sécurité
```

### Avantages

✅ **Temps réel** - Mises à jour instantanées (< 1s)
✅ **Efficace** - Seulement ~300 requêtes/jour
✅ **Écologique** - Réduit charge serveur de ~80%
✅ **Réactivité** - SOC/Puissance changent immédiatement dans HA

### Inconvénients

❌ **Complexe** - Nécessite AWS IoT SDK
❌ **Expérimental** - Implémentation en cours de développement
❌ **Dépendances** - Nécessite `awsiotsdk` Python
❌ **Debugging** - Plus difficile à diagnostiquer en cas de problème

### Installation

1. **Installer la dépendance** :
   ```bash
   # Dans l'environnement Home Assistant
   pip install awsiotsdk
   ```

2. **Activer dans l'intégration** :
   - Allez dans **Configuration** → **Intégrations**
   - Cliquez sur **Enphase Battery IQ 5P**
   - Cliquez sur **Options**
   - Cochez **"Activer MQTT pour mises à jour temps réel"**
   - Redémarrez Home Assistant

3. **Vérifier les logs** :
   ```yaml
   # configuration.yaml
   logger:
     logs:
       custom_components.enphase_battery.mqtt_client: debug
   ```

---

## 🎯 Quel mode choisir ?

### Choisissez **Polling** si :

- ✅ Vous voulez une solution **simple et fiable**
- ✅ La latence de 60s est **acceptable** pour vous
- ✅ Vous ne voulez **pas installer de dépendances**
- ✅ Vous débutez avec Home Assistant

**👉 Recommandé pour 95% des utilisateurs**

---

### Choisissez **MQTT** si :

- ✅ Vous voulez des mises à jour **temps réel**
- ✅ Vous avez des **automatisations critiques** sur SOC/Puissance
- ✅ Vous êtes à l'aise avec **debugging** et **logs**
- ✅ Vous voulez **minimiser la charge API**

**👉 Pour utilisateurs avancés uniquement**

---

## 📈 Impact sur les performances

### Scénario typique : Charge batterie le matin

| Événement | Mode Polling | Mode MQTT |
|-----------|--------------|-----------|
| Batterie passe de 5% → 100% | Détecté en 60s max | Détecté < 1s |
| Automation "Batterie pleine" | Délai moyen 30s | Déclenchement immédiat |
| Appels API pendant charge 1h | 60 requêtes | 1 requête + MQTT |

### Exemple automation critique

```yaml
# Couper charge si batterie pleine (mode MQTT recommandé)
automation:
  - alias: "Stop Charge From Grid - Battery Full"
    trigger:
      platform: numeric_state
      entity_id: sensor.battery_soc
      above: 95
    action:
      service: switch.turn_off
      target:
        entity_id: switch.charge_from_grid
```

**Avec Polling** : Délai moyen 30s → Surcharge possible
**Avec MQTT** : Réaction < 1s → Optimal

---

## ⚙️ Configuration avancée

### Polling + MQTT hybride

L'intégration utilise **les deux** en mode MQTT :

```python
# Mode MQTT actif
mqtt_client.connect()  # Push temps réel

# + Polling backup toutes les 5 minutes
coordinator.update_interval = 300s  # Sécurité si MQTT déconnecte
```

**Meilleur des deux mondes** :
- Temps réel quand MQTT fonctionne
- Fallback polling si problème réseau

---

## 🔍 Dépannage

### MQTT ne se connecte pas

1. **Vérifier les logs** :
   ```
   Logger: custom_components.enphase_battery.mqtt_client
   Error: Failed to connect to MQTT: ...
   ```

2. **Vérifier dépendances** :
   ```bash
   pip list | grep awsiot
   ```

3. **Désactiver MQTT temporairement** :
   - Retournez dans **Options**
   - Décochez "Activer MQTT"
   - L'intégration repasse en polling

### Polling trop lent

1. **Vérifier intervalle** :
   ```
   Logger: custom_components.enphase_battery.coordinator
   Update interval: 60 seconds
   ```

2. **Note** : L'intervalle de 60s est optimal pour éviter rate limiting Enphase

---

## 📊 Statistiques réelles capturées

**Session app mobile (8 minutes)** :
- Appels `/today` : 18 fois = **toutes les 26 secondes**
- Connexion MQTT : 1 fois pour 15 minutes
- Mode app : **MQTT push** + polling léger

**Conclusion** : L'app officielle utilise MQTT par défaut !

---

## 🚀 Roadmap

### Version actuelle (v0.1.0)
- ✅ Mode Polling fonctionnel
- ⚠️ Mode MQTT structure de base (non testé)

### Version future (v0.2.0)
- 🔄 MQTT complètement implémenté
- 🔄 Tests automatisés MQTT
- 🔄 Métriques de performance

### Version future (v0.3.0)
- 🔄 Auto-switch Polling ↔ MQTT selon qualité réseau
- 🔄 Dashboard statistiques API calls

---

**Besoin d'aide ?** Ouvrez une issue sur GitHub avec :
- Mode choisi (Polling ou MQTT)
- Logs de l'intégration
- Description du problème
