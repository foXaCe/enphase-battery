# Prédiction de Consommation par Analyse Historique

Ce document explique comment activer et configurer la **prédiction de consommation basée sur l'historique** pour optimiser la charge de votre batterie Enphase.

## 📊 Vue d'ensemble

Le système analyse l'historique de consommation des **60-90 derniers jours** pour :
- Identifier des **jours similaires** (même jour de semaine, même saison)
- Prédire la **consommation de demain**
- Calculer le **déficit énergétique** prévu (consommation - production solaire)
- Ajuster automatiquement le **SOC cible** pour couvrir ce déficit

## 🔧 Installation

### Étape 1 : Configurer les sensors SQL

1. **Ouvrez** `configuration.yaml` (ou créez un fichier `sensors.yaml` inclus)

2. **Copiez** le contenu de [`examples/sensors_sql_consumption.yaml`](../examples/sensors_sql_consumption.yaml)

3. **Personnalisez** les entités selon votre installation :

```yaml
sensor:
  - platform: sql
    db_url: sqlite:////config/home-assistant_v2.db
    queries:
      - name: "Consommation Prédite Demain"
        query: >
          # ... (voir le fichier example)
          WHERE sm.statistic_id = 'sensor.votre_sensor_consommation_quotidienne'
          # REMPLACEZ par le nom de VOTRE sensor
```

4. **Redémarrez** Home Assistant

### Étape 2 : Vérifier les sensors

Après redémarrage, vérifiez que les sensors sont créés :

```
Outils de développement > États
Recherchez : sensor.consommation_predite_demain
```

**Si le sensor retourne toujours la valeur par défaut (5.0 kWh)** :
- Vérifiez que le `statistic_id` correspond bien à votre sensor de consommation
- Assurez-vous d'avoir **au moins 60 jours d'historique**
- Vérifiez les logs Home Assistant pour erreurs SQL

### Étape 3 : Activer dans le blueprint

Dans votre automation créée depuis le blueprint :

1. **Activer Prédiction par Consommation Historique** : `ON`
2. **Capteur Consommation Prédite** : `sensor.consommation_predite_demain`
3. **Capteur Prévision Production Solaire** : Votre sensor de production (requis pour calculer le déficit)

## 📈 Fonctionnement

### Calcul du SOC cible

Le SOC cible final est calculé en **3 étapes** :

```
1. SOC de base (selon production solaire prévue)
   ↓
2. + Ajustement gap sunrise (heures avant lever du soleil)
   ↓
3. + Ajustement consommation historique (déficit prévu)
   ↓
4. = SOC cible final (max 100%)
```

### Exemple concret

**Configuration :**
- Batterie : 5 kWh
- Production prévue demain : 8 kWh
- Consommation prédite (jours similaires) : 15 kWh
- Fin HC : 06:30, Lever soleil : 08:00

**Calculs :**
1. **SOC de base** : 80% (production moyenne)
2. **Gap sunrise** : 1,5h × 1 kWh/h = +30%
3. **Déficit prévu** : 15 - 8 = 7 kWh
   - 7 kWh / 5 kWh batterie = +140% → **limité à +50%**
4. **SOC final** : 80% + 30% + 50% = **100%** (max)

### Limitation de sécurité

L'ajustement basé sur la consommation est **limité à +50%** pour éviter :
- De trop charger la batterie inutilement
- Des coûts excessifs si la prédiction est incorrecte
- L'usure prématurée de la batterie

## 🎯 Critères de "jours similaires"

Les sensors SQL recherchent des jours similaires selon :

### Version de base (`Consommation Prédite Demain`)
- ✅ Même **jour de la semaine** (lundi = lundi)
- ✅ Historique des **60 derniers jours**

### Version avancée (`Consommation Prédite Demain Météo`)
- ✅ Même **jour de la semaine**
- ✅ Même **saison** (± 1 mois)
- ✅ Historique des **90 derniers jours**

### Version gap sunrise (`Consommation Gap Heures Creuses Sunrise`)
- ✅ Heures spécifiques : **06h-09h**
- ✅ Historique des **30 derniers jours**

## 🔍 Debug et surveillance

### Activer les notifications de debug

Dans le blueprint : **Notifications de Debug** = `ON`

Vous recevrez des notifications détaillées avec :
```
📊 Calculs actuels:
- SOC: 45%
- Consommation prédite: 15 kWh
- Déficit énergétique prédit: 7 kWh
- Ajustement SOC consommation: +35%
- SOC Cible dynamique: 95%
```

### Vérifier les calculs manuellement

Dans **Outils de développement > Modèles (Templates)** :

```jinja
Consommation prédite: {{ states('sensor.consommation_predite_demain') }} kWh
Production prévue: {{ states('sensor.energy_production_tomorrow_forecast') }} kWh
Déficit: {{ (states('sensor.consommation_predite_demain')|float - states('sensor.energy_production_tomorrow_forecast')|float) | max(0) }} kWh
```

## 🕐 Déclenchement automatique

Le blueprint se déclenche automatiquement :
- ⏰ **03h00** : Recalcul quotidien basé sur l'historique
- 🔄 Quand `sensor.consommation_predite_demain` change
- 🔄 Quand le SOC de la batterie change
- 🔄 Quand la production solaire prévue change

## 📊 Sensors SQL disponibles

| Sensor | Description | Historique | Critères |
|--------|-------------|------------|----------|
| `consommation_predite_demain` | Consommation journalière prévue | 60 jours | Même jour semaine |
| `consommation_predite_demain_meteo` | Avec saison | 90 jours | Jour semaine + saison |
| `consommation_gap_heures_creuses_sunrise` | Consommation horaire matinale | 30 jours | 06h-09h |

## 🛠️ Dépannage

### Le sensor retourne toujours 5.0 kWh

**Causes possibles :**
1. `statistic_id` incorrect dans la requête SQL
2. Pas assez d'historique (< 60 jours)
3. Le sensor de consommation n'est pas enregistré dans `statistics`

**Solution :**
```yaml
# Vérifiez que votre sensor est bien enregistré
recorder:
  include:
    entities:
      - sensor.votre_sensor_consommation_quotidienne
```

### Le sensor ne se met pas à jour

**Vérification :**
```bash
# Outils de développement > Services
Service: homeassistant.update_entity
Entity: sensor.consommation_predite_demain
```

### Erreur SQL dans les logs

**Vérifiez :**
1. Le chemin de la base de données : `/config/home-assistant_v2.db`
2. Les permissions du fichier
3. La syntaxe SQL (peut varier selon MariaDB/PostgreSQL)

## 📚 Ressources

- [Configuration Recorder](https://www.home-assistant.io/integrations/recorder/)
- [SQL Sensor Integration](https://www.home-assistant.io/integrations/sql/)
- [Statistics dans Home Assistant](https://www.home-assistant.io/docs/backend/database/)

## 🎓 Amélioration future

Possibilités d'évolution :
- 🤖 Machine Learning pour prédictions plus précises (scikit-learn)
- 🌡️ Intégration température extérieure dans les critères
- 📈 Analyse saisonnière avancée
- 🏠 Détection automatique des patterns de consommation

---

**Questions ou problèmes ?** Ouvrez une [issue sur GitHub](https://github.com/foXaCe/enphase-battery/issues)
