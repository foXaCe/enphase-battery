# Guide de Création du Sensor SQL de Consommation Prédite

Ce guide vous aide à créer **pas à pas** le sensor SQL qui prédit la consommation de demain.

## 🎯 Prérequis

Avant de commencer, vous devez avoir :
- ✅ Home Assistant installé (Core, Container, ou OS)
- ✅ Un sensor qui enregistre votre consommation quotidienne
- ✅ Au moins **7 jours d'historique** (idéalement 60 jours)

---

## Étape 1 : Identifier Votre Sensor de Consommation

### Option A : Via le Dashboard Énergie

1. **Ouvrez** : `Paramètres` > `Tableaux de bord` > `Énergie`
2. **Regardez** la section **"Consommation du réseau"**
3. **Notez** le nom du sensor utilisé (ex: `sensor.energy_consumed_daily`)

### Option B : Via les Outils de Développement

1. **Ouvrez** : `Outils de développement` > `États`
2. **Recherchez** un sensor avec :
   - Nom contenant `energy`, `consumption`, `consumed`, `daily`
   - Unité : `kWh`
   - Valeur qui augmente puis se réinitialise quotidiennement

**Exemples de noms courants :**
```
sensor.daily_energy
sensor.energy_consumed_daily
sensor.home_energy_consumption
sensor.energy_total_daily
sensor.daily_consumption
```

### Option C : Créer un Utility Meter (si vous n'avez pas de sensor quotidien)

Si vous avez seulement un sensor cumulatif (qui ne se réinitialise jamais), créez un utility meter :

```yaml
# configuration.yaml ou sensors.yaml

utility_meter:
  daily_energy_consumption:
    source: sensor.energy_consumed  # Votre sensor cumulatif
    cycle: daily
```

Cela créera automatiquement : `sensor.daily_energy_consumption`

---

## Étape 2 : Vérifier que le Sensor est dans Statistics

Le sensor SQL lit depuis la table `statistics` de Home Assistant. Vérifions :

### Méthode 1 : Interface graphique

1. **Ouvrez** : `Outils de développement` > `États`
2. **Cherchez** votre sensor
3. **Cliquez** dessus
4. **Regardez** en bas : section **"Statistiques"**
5. Si vous voyez un graphique avec historique → ✅ **OK !**

### Méthode 2 : Vérifier la configuration

**Ouvrez** : `configuration.yaml`

Cherchez la section `recorder` :

```yaml
recorder:
  # Si cette section existe, vérifiez que votre sensor est inclus
  include:
    entities:
      - sensor.votre_sensor_consommation  # AJOUTEZ-LE si absent
```

**Si vous avez un `exclude`, assurez-vous que votre sensor n'y est PAS.**

---

## Étape 3 : Créer le Sensor SQL

### 🔧 Méthode 1 : Via configuration.yaml (Recommandé)

1. **Ouvrez** votre fichier de configuration :
   - Via File Editor (addon) : `/config/configuration.yaml`
   - Via SSH/Terminal : `nano /config/configuration.yaml`

2. **Ajoutez** cette section à la fin :

```yaml
# ============================================================
# SENSOR SQL : CONSOMMATION PRÉDITE
# ============================================================

sensor:
  - platform: sql
    db_url: sqlite:////config/home-assistant_v2.db
    queries:
      - name: "Consommation Prédite Demain"
        query: >
          WITH tomorrow_weekday AS (
            SELECT CAST(strftime('%w', datetime('now', '+1 day')) AS INTEGER) as weekday
          ),
          similar_days AS (
            SELECT
              s.state,
              s.created_ts,
              strftime('%w', datetime(s.created_ts, 'unixepoch', 'localtime')) as day_of_week
            FROM statistics s
            INNER JOIN statistics_meta sm ON s.metadata_id = sm.id
            WHERE sm.statistic_id = 'sensor.VOTRE_SENSOR_ICI'
              AND s.created_ts > strftime('%s', 'now', '-60 days')
              AND s.created_ts < strftime('%s', 'now', '-1 day')
              AND CAST(strftime('%w', datetime(s.created_ts, 'unixepoch', 'localtime')) AS INTEGER) = (SELECT weekday FROM tomorrow_weekday)
              AND s.state IS NOT NULL
              AND s.state != 'unknown'
              AND s.state != 'unavailable'
          )
          SELECT
            CASE
              WHEN COUNT(*) > 0 THEN ROUND(AVG(CAST(state AS FLOAT)), 2)
              ELSE 5.0
            END as avg_consumption
          FROM similar_days;
        column: "avg_consumption"
        unit_of_measurement: "kWh"
```

3. **⚠️ IMPORTANT : Remplacez** `sensor.VOTRE_SENSOR_ICI` par le nom de VOTRE sensor

   Exemple :
   ```sql
   WHERE sm.statistic_id = 'sensor.daily_energy_consumption'
   ```

4. **Sauvegardez** le fichier

5. **Vérifiez** la syntaxe :
   ```
   Outils de développement > YAML
   Cliquer "Vérifier la configuration"
   ```

6. **Redémarrez** Home Assistant :
   ```
   Paramètres > Système > Redémarrer
   ```

### 🔧 Méthode 2 : Fichier séparé (Plus propre)

Si vous préférez séparer les configurations :

1. **Créez** un fichier : `/config/sensors.yaml`

2. **Ajoutez** le contenu du sensor SQL ci-dessus

3. **Modifiez** `configuration.yaml` pour inclure ce fichier :
   ```yaml
   sensor: !include sensors.yaml
   ```

4. **Redémarrez** Home Assistant

---

## Étape 4 : Vérifier que le Sensor Fonctionne

### Après le redémarrage :

1. **Ouvrez** : `Outils de développement` > `États`

2. **Recherchez** : `sensor.consommation_predite_demain`

3. **Vérifiez** :
   - ✅ Le sensor existe
   - ✅ Il a une valeur numérique (ex: `12.5` kWh)
   - ❌ Si la valeur est `5.0` → C'est la valeur par défaut, voir dépannage ci-dessous

### Test manuel :

**Outils de développement > Services**

```yaml
service: homeassistant.update_entity
target:
  entity_id: sensor.consommation_predite_demain
```

Cliquez **"Appeler le service"**, puis vérifiez la valeur mise à jour.

---

## 🐛 Dépannage

### ❌ Le sensor n'apparaît pas

**Vérifiez les logs :**
```
Paramètres > Système > Journaux
Rechercher : "sql"
```

**Erreurs courantes :**
- `unable to open database file` → Chemin db_url incorrect
- `no such table: statistics` → Base de données corrompue
- `syntax error` → Erreur dans la requête SQL

**Solutions :**
1. Vérifiez le chemin de la base de données :
   ```yaml
   db_url: sqlite:////config/home-assistant_v2.db
   # 4 slashes ^^^^ c'est normal !
   ```

2. Vérifiez que le fichier existe :
   ```bash
   ls -la /config/home-assistant_v2.db
   ```

### ❌ Le sensor retourne toujours 5.0 kWh

Cela signifie qu'aucun jour similaire n'a été trouvé dans l'historique.

**Causes possibles :**

1. **Pas assez d'historique** (< 7 jours)
   - Solution : Attendez d'avoir plus d'historique

2. **statistic_id incorrect**
   - Solution : Vérifiez le nom exact du sensor dans la requête

3. **Le sensor n'est pas dans statistics**
   - Solution : Ajoutez-le dans recorder (voir Étape 2)

**Vérification SQL directe :**

Si vous avez accès SSH, testez la requête directement :

```bash
sqlite3 /config/home-assistant_v2.db

# Lister tous les statistic_id disponibles
SELECT statistic_id FROM statistics_meta WHERE statistic_id LIKE '%consumption%' OR statistic_id LIKE '%energy%';

# Compter les entrées pour votre sensor
SELECT COUNT(*) FROM statistics s
JOIN statistics_meta sm ON s.metadata_id = sm.id
WHERE sm.statistic_id = 'sensor.votre_sensor_ici';
```

### ❌ Erreur "Entity is neither a valid entity ID"

Cette erreur vient du blueprint, pas du sensor SQL.

**Solution :** Le blueprint a été corrigé dans la dernière version. Mettez-le à jour.

---

## Étape 5 : Configurer le Blueprint

Une fois le sensor créé et fonctionnel :

1. **Ouvrez** votre automation créée depuis le blueprint

2. **Modifiez** :
   - **Activer Prédiction par Consommation Historique** : `ON`
   - **Capteur Consommation Prédite** : `sensor.consommation_predite_demain`

3. **Sauvegardez**

4. **Testez** : Activez les notifications de debug pour voir les calculs

---

## 📊 Comprendre les Résultats

### Le sensor calcule :

**Si demain = Lundi**, il cherche les **8-10 derniers lundis** dans l'historique (60 jours) et fait la **moyenne** de leur consommation.

**Exemples :**

```
Lundis trouvés dans l'historique :
- 18/12 : 14 kWh
- 11/12 : 16 kWh
- 04/12 : 15 kWh
- 27/11 : 17 kWh
... (8 lundis au total)

Moyenne : 15.5 kWh
→ sensor.consommation_predite_demain = 15.5
```

### Pourquoi par jour de la semaine ?

Les patterns de consommation varient selon le jour :
- **Lundi-Vendredi** : Télétravail, activité normale
- **Samedi-Dimanche** : Plus à la maison, consommation différente

En comparant les **mêmes jours**, la prédiction est plus précise.

---

## 🎯 Variantes Avancées

### Variante 1 : Avec critère saisonnier

Pour tenir compte de la saison (chauffage hiver, clim été) :

```yaml
- name: "Consommation Prédite Demain Météo"
  query: >
    WITH tomorrow_info AS (
      SELECT
        CAST(strftime('%w', datetime('now', '+1 day')) AS INTEGER) as weekday,
        CAST(strftime('%m', datetime('now', '+1 day')) AS INTEGER) as month
    ),
    similar_days AS (
      SELECT s.state
      FROM statistics s
      INNER JOIN statistics_meta sm ON s.metadata_id = sm.id
      WHERE sm.statistic_id = 'sensor.daily_energy_consumption'
        AND s.created_ts > strftime('%s', 'now', '-90 days')
        AND CAST(strftime('%w', datetime(s.created_ts, 'unixepoch', 'localtime')) AS INTEGER) = (SELECT weekday FROM tomorrow_info)
        AND ABS(CAST(strftime('%m', datetime(s.created_ts, 'unixepoch', 'localtime')) AS INTEGER) - (SELECT month FROM tomorrow_info)) <= 1
        AND s.state IS NOT NULL
    )
    SELECT
      CASE
        WHEN COUNT(*) > 0 THEN ROUND(AVG(CAST(state AS FLOAT)), 2)
        ELSE 5.0
      END
    FROM similar_days;
  column: "avg_consumption"
  unit_of_measurement: "kWh"
```

### Variante 2 : Avec distinction semaine/week-end

```yaml
# Ajouter cette condition dans WHERE :
AND (
  -- Si demain est week-end (samedi=6, dimanche=0)
  (SELECT weekday FROM tomorrow_weekday) IN (0, 6)
  -- Chercher seulement les week-ends
  AND CAST(strftime('%w', datetime(s.created_ts, 'unixepoch', 'localtime')) AS INTEGER) IN (0, 6)
)
OR (
  -- Si demain est semaine
  (SELECT weekday FROM tomorrow_weekday) NOT IN (0, 6)
  -- Chercher seulement les jours de semaine
  AND CAST(strftime('%w', datetime(s.created_ts, 'unixepoch', 'localtime')) AS INTEGER) NOT IN (0, 6)
)
```

---

## 📚 Ressources Complémentaires

- **Documentation SQL Sensor** : https://www.home-assistant.io/integrations/sql/
- **Statistics dans HA** : https://www.home-assistant.io/docs/backend/database/
- **Recorder Integration** : https://www.home-assistant.io/integrations/recorder/

---

## ✅ Checklist Finale

Avant d'activer dans le blueprint, vérifiez :

- [ ] Le sensor SQL existe dans les États
- [ ] Il a une valeur différente de 5.0 kWh
- [ ] La valeur semble cohérente avec votre consommation
- [ ] Le sensor se met à jour (testez avec update_entity)
- [ ] Vous avez au moins 7 jours d'historique

**Si tout est ✅ → Vous pouvez activer la prédiction dans le blueprint !** 🎉

---

**Besoin d'aide ?** Ouvrez une [issue sur GitHub](https://github.com/foXaCe/enphase-battery/issues) avec :
- Les logs (sans données sensibles)
- Le nom de votre sensor de consommation
- Le nombre de jours d'historique disponibles
