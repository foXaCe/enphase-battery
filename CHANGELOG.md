# Changelog

Toutes les modifications notables de ce projet seront documentées dans ce fichier.

## [2.0.0] - 2025-10-25

### 🎉 Nouvelles Fonctionnalités Majeures

#### Prédiction de Consommation par Analyse Historique
- **Sensors SQL** pour analyser l'historique des 60-90 derniers jours
- **Identification automatique** des jours similaires (même jour semaine + saison)
- **Calcul du déficit énergétique** prévu (consommation - production)
- **Ajustement dynamique** du SOC cible basé sur les prédictions

#### Ajustement Lever du Soleil
- **Calcul du gap** entre fin des heures creuses et lever du soleil
- **Ajustement saisonnier** automatique (hiver vs été)
- **Optimisation** pour couvrir la consommation pendant le gap
- **Intégration** avec le sensor `sun.sun`

### 📝 Modifications

#### Blueprint `smart_battery_charge_tempo.yaml`

**Nouveaux Inputs:**
- `sun_sensor`: Capteur pour le lever du soleil (défaut: `sun.sun`)
- `predicted_consumption_sensor`: Sensor SQL de consommation prédite
- `enable_consumption_prediction`: Active/désactive la prédiction historique
- `sunrise_gap_adjustment`: Active/désactive l'ajustement gap sunrise
- `consumption_per_hour`: Consommation moyenne par heure (kWh/h)

**Nouvelles Variables Calculées:**
- `sunrise_gap_hours`: Heures entre fin HC et lever du soleil
- `sunrise_soc_adjustment`: Ajustement SOC basé sur le gap sunrise
- `predicted_energy_deficit`: Déficit énergétique prévu (kWh)
- `consumption_soc_adjustment`: Ajustement SOC basé sur la consommation historique

**Nouveaux Triggers:**
- Trigger à `03:00` pour recalcul quotidien avec nouvel historique
- Trigger sur changement de `predicted_consumption_sensor`

**Améliorations du Calcul SOC Cible:**
```
Ancien: SOC base + ajustement production solaire
Nouveau: SOC base + ajustement sunrise + ajustement consommation historique
```

**Notifications Améliorées:**
- Affichage consommation prédite
- Affichage déficit énergétique prévu
- Affichage gap sunrise et ajustements
- Détails complets en mode debug

### 📚 Nouvelle Documentation

**Fichiers Ajoutés:**
- `docs/CONSUMPTION_PREDICTION.md`: Guide complet prédiction consommation
- `docs/ARCHITECTURE_PREDICTION.md`: Architecture technique détaillée
- `examples/sensors_sql_consumption.yaml`: Exemples sensors SQL
- `examples/configuration_complete.yaml`: Configuration complète annotée

**Contenu de la Documentation:**
- Guide d'installation étape par étape
- Exemples de requêtes SQL pour différents cas d'usage
- Schémas d'architecture avec flux de données
- Timeline journalière avec exemple concret
- Guide de dépannage complet
- Ressources et liens utiles

### 🔧 Améliorations Techniques

**Base de Données:**
- Requêtes SQL optimisées avec JOIN sur `statistics_meta`
- Filtrage intelligent (exclut valeurs nulles, invalides)
- Valeurs par défaut sécurisées (5.0 kWh si pas d'historique)

**Performance:**
- Calculs uniquement sur événements (pas de polling)
- Templates optimisés avec mise en cache
- Triggers conditionnels (évite exécutions inutiles)

**Sécurité:**
- Limitation ajustement consommation à **+50% max** (évite surcharge)
- SOC final toujours plafonné à **100%**
- Fallback gracieux si sensors indisponibles

### 🐛 Corrections

- Fix: Gestion correcte des sensors vides (`""` vs `none`)
- Fix: Calcul gap sunrise avec heures qui traversent minuit
- Fix: Arrondi cohérent des pourcentages (1 décimale pour debug)

### ⚠️ Breaking Changes

**Aucun !** Toutes les nouvelles fonctionnalités sont **optionnelles** :
- Si vous n'activez pas `enable_consumption_prediction`, le blueprint fonctionne comme avant
- Si vous n'activez pas `sunrise_gap_adjustment`, le calcul reste inchangé
- Rétrocompatibilité totale avec les configurations existantes

### 📊 Comparaison Versions

| Fonctionnalité | v1.x | v2.0 |
|----------------|------|------|
| Heures creuses | ✅ | ✅ |
| Tempo (jours rouges) | ✅ | ✅ |
| Production solaire prévue | ✅ | ✅ |
| Lever du soleil | ❌ | ✅ |
| Consommation historique | ❌ | ✅ |
| Déficit énergétique | ❌ | ✅ |
| Ajustement saisonnier | ❌ | ✅ |
| Prédiction jours similaires | ❌ | ✅ |

### 🎯 Impact sur le SOC Cible

**Exemple Hiver (gap important):**
- **v1.x**: SOC cible = 80% (base production solaire)
- **v2.0**: SOC cible = 100% (80% base + 30% sunrise + 50% consommation)
- **Gain**: +20% autonomie pendant le gap matinal

**Exemple Été (pas de gap):**
- **v1.x**: SOC cible = 80%
- **v2.0**: SOC cible = 80% (pas d'ajustement nécessaire)
- **Gain**: Pas de surcharge inutile

### 📈 Statistiques

**Lignes de Code:**
- Blueprint: ~600 lignes (+200 lignes)
- Documentation: ~1500 lignes (nouveau)
- Exemples SQL: ~200 lignes (nouveau)

**Couverture:**
- 6 nouveaux inputs configurables
- 4 nouvelles variables calculées
- 2 nouveaux triggers temporels
- 3 nouveaux fichiers de documentation
- 15+ exemples de configuration

### 🙏 Remerciements

Merci à la communauté Home Assistant pour :
- L'intégration SQL Sensor
- L'intégration Recorder avec statistics
- Les exemples de requêtes SQL dans les forums

### 🔗 Ressources

- **Documentation principale**: [`docs/CONSUMPTION_PREDICTION.md`](docs/CONSUMPTION_PREDICTION.md)
- **Architecture technique**: [`docs/ARCHITECTURE_PREDICTION.md`](docs/ARCHITECTURE_PREDICTION.md)
- **Configuration complète**: [`examples/configuration_complete.yaml`](examples/configuration_complete.yaml)
- **Support**: [GitHub Issues](https://github.com/foXaCe/enphase-battery/issues)

---

## [1.0.0] - 2025-10-24

### Fonctionnalités Initiales

- Gestion charge batterie selon heures creuses
- Optimisation Tempo (jours rouges EDF)
- Intégration prévisions production solaire
- Stratégies de charge (immédiate / optimisée)
- Notifications intelligentes
- Mode debug détaillé

---

## Format

Le format est basé sur [Keep a Changelog](https://keepachangelog.com/fr/1.0.0/),
et ce projet adhère à [Semantic Versioning](https://semver.org/lang/fr/).

### Types de Changements

- `Ajouté` pour les nouvelles fonctionnalités
- `Modifié` pour les changements aux fonctionnalités existantes
- `Déprécié` pour les fonctionnalités qui seront bientôt supprimées
- `Supprimé` pour les fonctionnalités supprimées
- `Corrigé` pour les corrections de bugs
- `Sécurité` pour les changements de sécurité
