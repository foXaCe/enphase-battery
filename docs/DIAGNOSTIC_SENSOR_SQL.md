# Diagnostic : Sensor SQL ne se Crée Pas

## 🔍 Vérifications à Faire

### 1. Vérifier les Logs

**Outils de développement > Journaux**

Recherchez les erreurs contenant :
- `sql`
- `sensor.consommation_predite_demain`
- `database`

**Erreurs fréquentes :**

| Erreur | Signification | Solution |
|--------|---------------|----------|
| `unable to open database file` | Chemin db incorrect | Vérifier le chemin `/config/home-assistant_v2.db` |
| `no such table: statistics` | Base corrompue | Vérifier l'installation HA |
| `syntax error near` | Erreur SQL | Vérifier la requête |
| `Platform error sensor.sql` | Config YAML invalide | Vérifier indentation |

### 2. Vérifier que le Sensor Source est dans Statistics

**Via Outils de développement > États :**

1. Cherchez : `sensor.energie_dimportation_de_reseau`
2. Cliquez dessus
3. Regardez en bas : section **"Statistiques"**
4. Vous devez voir un graphique avec historique

**Si pas de statistiques → Le sensor n'est pas enregistré !**

**Solution :**

Ajoutez dans `configuration.yaml` :

```yaml
recorder:
  include:
    entities:
      - sensor.energie_dimportation_de_reseau
```

Puis redémarrez et attendez 24h.

### 3. Tester la Requête SQL Directement

**Si vous avez accès SSH :**

```bash
# Se connecter à la base
sqlite3 /config/home-assistant_v2.db

# Lister les sensors disponibles
SELECT statistic_id FROM statistics_meta
WHERE statistic_id LIKE '%energie%' OR statistic_id LIKE '%import%';

# Vérifier votre sensor spécifique
SELECT COUNT(*) FROM statistics s
JOIN statistics_meta sm ON s.metadata_id = sm.id
WHERE sm.statistic_id = 'sensor.energie_dimportation_de_reseau';

# Si COUNT = 0 → Le sensor n'a pas d'historique dans statistics
# Si COUNT > 0 → Le sensor existe, problème ailleurs
```

### 4. Tester avec un Sensor Simple

**Pour vérifier que le SQL Sensor fonctionne, testez d'abord un sensor simple :**

```yaml
sensor:
  - platform: sql
    db_url: sqlite:////config/home-assistant_v2.db
    queries:
      - name: "Test SQL Sensor"
        query: "SELECT 42 as test_value;"
        column: "test_value"
```

**Si ce sensor apparaît avec la valeur 42 → SQL fonctionne, problème dans votre requête**
**Si ce sensor n'apparaît pas → Problème de configuration SQL Sensor**

### 5. Vérifier la Version de Home Assistant

Le SQL Sensor nécessite Home Assistant **2023.6+**

**Vérifier :** `Paramètres` > `Système` > `Mises à jour`

### 6. Vérifier le Chemin de la Base de Données

Le chemin varie selon l'installation :

| Type Installation | Chemin Base de Données |
|-------------------|------------------------|
| Home Assistant OS | `sqlite:////config/home-assistant_v2.db` |
| Container | `sqlite:////config/home-assistant_v2.db` |
| Core (venv) | `sqlite:////home/homeassistant/.homeassistant/home-assistant_v2.db` |
| Supervised | `sqlite:////usr/share/hassio/homeassistant/home-assistant_v2.db` |

**Pour trouver le bon chemin :**

```yaml
# Testez ce sensor qui affiche le chemin
sensor:
  - platform: template
    sensors:
      db_path:
        value_template: "{{ states.recorder }}"
```

Ou vérifiez dans `Paramètres` > `Système` > `Réparations` s'il y a des avertissements sur la base de données.

## 🛠️ Solutions selon les Problèmes

### Problème A : "Sensor n'apparaît jamais"

**Checklist :**
- [ ] La section `sensor:` est bien présente dans configuration.yaml
- [ ] L'indentation est correcte (2 espaces, pas de tabulations)
- [ ] Pas d'erreur dans les logs après redémarrage
- [ ] Le chemin `db_url` est correct

**Test :** Créez le sensor simple (test 42) pour isoler le problème.

### Problème B : "Sensor existe mais valeur 5.0"

Cela signifie : **Aucune donnée trouvée dans l'historique**

**Causes :**
1. **statistic_id incorrect** → Vérifiez le nom exact
2. **Pas assez d'historique** → Attendez d'avoir au moins 7 jours
3. **Sensor pas dans statistics** → Ajoutez dans recorder

**Solution prioritaire :**

```yaml
recorder:
  db_url: sqlite:////config/home-assistant_v2.db
  purge_keep_days: 10
  include:
    entities:
      - sensor.energie_dimportation_de_reseau
```

### Problème C : "Sensor existe mais valeur unknown"

**Causes :**
- Erreur dans la requête SQL
- Column name incorrect
- Base de données verrouillée

**Vérifiez les logs pour l'erreur exacte.**

### Problème D : "Erreur de syntaxe YAML"

**Erreurs courantes :**

```yaml
# MAUVAIS - Tabulations au lieu d'espaces
sensor:
	- platform: sql

# BON - 2 espaces
sensor:
  - platform: sql

# MAUVAIS - Manque > pour query multiligne
query: WITH tomorrow...

# BON - Avec >
query: >
  WITH tomorrow...

# MAUVAIS - Guillemets dans la requête
WHERE sm.statistic_id = "sensor.energie"

# BON - Guillemets simples
WHERE sm.statistic_id = 'sensor.energie_dimportation_de_reseau'
```

## 📋 Configuration Minimale Testée

**Utilisez cette configuration minimale testée :**

```yaml
sensor:
  - platform: sql
    db_url: sqlite:////config/home-assistant_v2.db
    scan_interval: 3600  # Ajout: mise à jour toutes les heures
    queries:
      - name: "Consommation Prédite Demain"
        query: >
          SELECT
            COALESCE(
              ROUND(AVG(CAST(s.state AS FLOAT)), 2),
              5.0
            ) as avg_consumption
          FROM statistics s
          INNER JOIN statistics_meta sm ON s.metadata_id = sm.id
          WHERE sm.statistic_id = 'sensor.energie_dimportation_de_reseau'
            AND s.created_ts > strftime('%s', 'now', '-60 days')
            AND s.state IS NOT NULL
            AND CAST(s.state AS FLOAT) > 0
            AND CAST(s.state AS FLOAT) < 1000
          LIMIT 1;
        column: "avg_consumption"
        unit_of_measurement: "kWh"
```

Cette version simplifiée :
- ✅ Pas de filtre par jour de semaine (pour tester)
- ✅ Filtre les valeurs aberrantes (0 et > 1000)
- ✅ LIMIT 1 pour être sûr d'une seule valeur
- ✅ scan_interval explicite

**Si cette version fonctionne** (retourne une valeur > 5.0), alors ajoutez progressivement les filtres.

## 🆘 Checklist de Dépannage Complète

Cochez au fur et à mesure :

- [ ] J'ai redémarré Home Assistant après modification
- [ ] Il n'y a pas d'erreur dans les logs concernant "sql"
- [ ] Le fichier configuration.yaml est valide (Vérifier la configuration)
- [ ] Mon sensor source existe : `sensor.energie_dimportation_de_reseau`
- [ ] Mon sensor source a un historique visible dans les États
- [ ] Le sensor SQL apparaît dans les États (même avec valeur 5.0)
- [ ] J'ai attendu au moins 5 minutes après le redémarrage
- [ ] J'ai forcé une mise à jour : Service `homeassistant.update_entity`
- [ ] J'ai au moins 7 jours d'historique pour le sensor source
- [ ] Le sensor source est dans `recorder.include` si j'ai un filtre

## 📞 Besoin d'Aide Supplémentaire

**Fournissez ces informations :**

1. **Logs** : Copiez les erreurs contenant "sql" ou "sensor"
2. **Type d'installation** : OS / Container / Core ?
3. **Version HA** : `Paramètres` > `À propos`
4. **Historique** : Combien de jours d'historique avez-vous ?
5. **Test sensor simple** : Le sensor qui retourne 42 fonctionne-t-il ?
6. **Statistic_id** : Résultat de la requête listant les sensors disponibles

Avec ces infos, je peux diagnostiquer précisément le problème ! 🔧
