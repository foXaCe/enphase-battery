# Architecture de la Prédiction de Consommation

Ce document explique l'architecture complète du système de prédiction de consommation basé sur l'historique.

## 📐 Architecture Globale

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        HOME ASSISTANT DATABASE                          │
│                     (home-assistant_v2.db - SQLite)                     │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐    │
│  │   statistics     │  │ statistics_meta  │  │     states       │    │
│  │                  │  │                  │  │                  │    │
│  │ - state          │  │ - statistic_id   │  │ - entity_id      │    │
│  │ - created_ts     │  │ - metadata_id    │  │ - state          │    │
│  │ - metadata_id    │  │                  │  │ - last_updated   │    │
│  └──────────────────┘  └──────────────────┘  └──────────────────┘    │
│                                                                         │
│  📊 Rétention: 10 ans (statistics) | 10 jours (states)                 │
└─────────────────────────────────────────────────────────────────────────┘
                                  ⬇
┌─────────────────────────────────────────────────────────────────────────┐
│                          SQL SENSOR INTEGRATION                         │
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────┐      │
│  │  Sensor: consommation_predite_demain                        │      │
│  │                                                              │      │
│  │  SELECT AVG(state)                                          │      │
│  │  FROM statistics s                                           │      │
│  │  JOIN statistics_meta sm ON s.metadata_id = sm.id          │      │
│  │  WHERE                                                       │      │
│  │    - statistic_id = 'sensor.daily_energy_consumption'       │      │
│  │    - Même jour de la semaine que demain                     │      │
│  │    - Historique des 60 derniers jours                       │      │
│  │    - Exclut valeurs nulles/invalides                        │      │
│  │                                                              │      │
│  │  → Retourne: Consommation moyenne (kWh)                     │      │
│  └─────────────────────────────────────────────────────────────┘      │
│                                                                         │
│  🔄 Mise à jour: Automatique (scan_interval) + trigger 03h00           │
└─────────────────────────────────────────────────────────────────────────┘
                                  ⬇
┌─────────────────────────────────────────────────────────────────────────┐
│                        TEMPLATE SENSORS (HELPERS)                       │
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────┐      │
│  │  deficit_energetique_predit_demain                          │      │
│  │                                                              │      │
│  │  consommation_predite - production_solaire_prevue = déficit │      │
│  │  15 kWh - 8 kWh = 7 kWh                                     │      │
│  └─────────────────────────────────────────────────────────────┘      │
│                                                                         │
│  ┌─────────────────────────────────────────────────────────────┐      │
│  │  soc_requis_pour_deficit                                     │      │
│  │                                                              │      │
│  │  (déficit / capacité_batterie) × 100 = SOC requis           │      │
│  │  (7 kWh / 5 kWh) × 100 = 140% → limité à 100%              │      │
│  └─────────────────────────────────────────────────────────────┘      │
└─────────────────────────────────────────────────────────────────────────┘
                                  ⬇
┌─────────────────────────────────────────────────────────────────────────┐
│                    BLUEPRINT AUTOMATION (CORE LOGIC)                    │
│                                                                         │
│  📥 INPUTS                                                              │
│  ├─ battery_soc_sensor (sensor.enphase_battery_soc)                    │
│  ├─ solar_forecast_sensor (sensor.production_solaire_demain)           │
│  ├─ predicted_consumption_sensor (sensor.consommation_predite_demain)  │
│  ├─ sun_sensor (sun.sun)                                               │
│  └─ enable_consumption_prediction (boolean)                            │
│                                                                         │
│  🧮 CALCULS (Variables)                                                 │
│                                                                         │
│  1️⃣ sunrise_gap_hours                                                  │
│     └─ Temps entre fin HC et lever du soleil                           │
│        Exemple: 08:00 - 06:30 = 1.5h                                   │
│                                                                         │
│  2️⃣ sunrise_soc_adjustment                                             │
│     └─ (gap × consommation/h / capacité) × 100                         │
│        (1.5h × 1 kWh/h / 5 kWh) × 100 = +30%                          │
│                                                                         │
│  3️⃣ predicted_energy_deficit                                           │
│     └─ consommation_prédite - production_prévue                        │
│        15 kWh - 8 kWh = 7 kWh                                          │
│                                                                         │
│  4️⃣ consumption_soc_adjustment                                         │
│     └─ (déficit / capacité) × 100, limité à +50%                       │
│        (7 kWh / 5 kWh) × 100 = 140% → 50% (max)                       │
│                                                                         │
│  5️⃣ target_end_offpeak (SOC CIBLE FINAL)                               │
│     ┌───────────────────────────────────────────────────┐             │
│     │ Étape 1: SOC de base (prévision solaire)         │             │
│     │   Production faible (< 5 kWh) → 100%             │             │
│     │   Production moyenne (5-15 kWh) → interpolation  │             │
│     │   Production élevée (> 15 kWh) → 80%             │             │
│     │                                                    │             │
│     │ Étape 2: + sunrise_soc_adjustment                │             │
│     │   SOC = 80% + 30% = 110%                         │             │
│     │                                                    │             │
│     │ Étape 3: + consumption_soc_adjustment            │             │
│     │   SOC = 110% + 50% = 160%                        │             │
│     │                                                    │             │
│     │ Étape 4: Limitation à 100% max                   │             │
│     │   SOC final = min(160%, 100%) = 100%            │             │
│     └───────────────────────────────────────────────────┘             │
│                                                                         │
│  ⚡ ACTIONS (Triggers)                                                  │
│  ├─ 22:30 (début HC) → Vérifie si charge nécessaire                    │
│  ├─ 06:30 (fin HC) → Arrête la charge                                  │
│  ├─ 03:00 → Recalcul avec nouvel historique                            │
│  ├─ 18:00 → Vérifie Tempo demain                                       │
│  ├─ Changement SOC → Vérifie si objectif atteint                       │
│  └─ Changement prévisions → Recalcule SOC cible                        │
│                                                                         │
│  🎯 DÉCISIONS                                                           │
│  ├─ CAS 1: Tempo ROUGE aujourd'hui → JAMAIS charger                    │
│  ├─ CAS 2: Tempo ROUGE demain + HC → Charge forcée 100%                │
│  ├─ CAS 3: SOC < min (30%) → Charge forcée (même hors HC)              │
│  ├─ CAS 4: HC + SOC < cible → Charge optimisée/immédiate               │
│  └─ CAS 5: Hors HC ou cible atteinte → Arrêt charge                    │
└─────────────────────────────────────────────────────────────────────────┘
                                  ⬇
┌─────────────────────────────────────────────────────────────────────────┐
│                         SWITCH CONTROL                                  │
│                                                                         │
│             switch.enphase_battery_charge_from_grid                     │
│                                                                         │
│                    ON ⚡ → Charge depuis réseau                         │
│                    OFF 🔌 → Pas de charge réseau                       │
└─────────────────────────────────────────────────────────────────────────┘
                                  ⬇
┌─────────────────────────────────────────────────────────────────────────┐
│                      NOTIFICATIONS & FEEDBACK                           │
│                                                                         │
│  📱 Notification Debug (si activé)                                      │
│  ┌─────────────────────────────────────────────────────────────┐      │
│  │ 🔍 Debug - Charge Batterie                                  │      │
│  │                                                              │      │
│  │ 📊 Calculs actuels:                                         │      │
│  │ - SOC: 45%                                                   │      │
│  │ - Consommation prédite: 15 kWh                              │      │
│  │ - Déficit prédit: 7 kWh                                     │      │
│  │ - Ajustement consommation: +50%                             │      │
│  │ - Gap sunrise: 1.5h (ajustement: +30%)                     │      │
│  │ - SOC Cible dynamique: 100%                                 │      │
│  │ - Temps de charge estimé: 2.5h                              │      │
│  └─────────────────────────────────────────────────────────────┘      │
└─────────────────────────────────────────────────────────────────────────┘
```

## 🔄 Flux de Données Complet

### Timeline Journalière

```
00:00 ─────────────────────────────────────────────────────────── 23:59
  │
  ├─ 03:00 🕒 RECALCUL QUOTIDIEN
  │         │
  │         ├─ Sensor SQL interroge l'historique
  │         ├─ Calcule moyenne des 8-10 derniers lundis (si demain = lundi)
  │         ├─ Met à jour: sensor.consommation_predite_demain
  │         └─ Trigger blueprint → Recalcule SOC cible
  │
  ├─ 06:30 🌅 FIN HEURES CREUSES
  │         │
  │         ├─ Arrêt automatique de la charge
  │         ├─ Vérification: SOC atteint cible?
  │         └─ Notification si debug activé
  │
  ├─ 08:00 ☀️ LEVER DU SOLEIL (variable selon saison)
  │         │
  │         └─ Début production solaire
  │
  ├─ 18:00 📋 VÉRIFICATION TEMPO
  │         │
  │         ├─ Lecture: sensor.rte_tempo_tomorrow
  │         ├─ Si ROUGE demain → Ajuste SOC cible à 100%
  │         └─ Trigger blueprint → Prépare stratégie
  │
  └─ 22:30 ⚡ DÉBUT HEURES CREUSES
            │
            ├─ Vérifie tous les critères:
            │  ├─ Tempo demain?
            │  ├─ SOC actuel vs SOC cible?
            │  ├─ Production prévue?
            │  ├─ Consommation prédite?
            │  └─ Gap sunrise?
            │
            ├─ Calcule timing optimal (mode optimized)
            │  │
            │  └─ Temps nécessaire = (SOC cible - SOC actuel) × capacité / puissance
            │      Exemple: (100% - 45%) × 5 kWh / 3.84 kW = 1.4h
            │      → Démarrage: 05:00 (06:30 - 1.4h)
            │
            └─ Démarre charge (mode immediate ou quand calculé)
```

## 📊 Exemple Concret: Journée Type Hiver

### Contexte
- **Date**: Lundi 15 janvier
- **Saison**: Hiver (lever soleil tardif)
- **Tempo**: Jour BLANC aujourd'hui, BLANC demain
- **Batterie**: IQ Battery 5P (5 kWh, 3.84 kW)

### Historique Analysé
Sensor SQL recherche les **lundis des 60 derniers jours** :
- Lundi 18/12: 14 kWh
- Lundi 11/12: 16 kWh
- Lundi 04/12: 15 kWh
- Lundi 27/11: 17 kWh
- ... (8 lundis au total)

**Moyenne**: 15 kWh → `sensor.consommation_predite_demain = 15.0`

### Prévisions
- **Production solaire demain**: 8 kWh (hiver, court)
- **Lever du soleil**: 08:15 (tardif)
- **Fin heures creuses**: 06:30

### Calculs

#### 1. Déficit Énergétique
```
Déficit = Consommation - Production
        = 15 kWh - 8 kWh
        = 7 kWh
```

#### 2. Gap Sunrise
```
Gap = Lever soleil - Fin HC
    = 08:15 - 06:30
    = 1h45 = 1.75h
```

#### 3. SOC Cible

**Étape 1: SOC de base (production solaire)**
```
Production = 8 kWh (entre 5 et 15 kWh)
→ Interpolation linéaire
Ratio = (8 - 5) / (15 - 5) = 0.3
SOC base = 100% - (0.3 × 20%) = 94%
```

**Étape 2: Ajustement gap sunrise**
```
Énergie needed = 1.75h × 1 kWh/h = 1.75 kWh
Ajustement SOC = (1.75 / 5) × 100 = 35%
```

**Étape 3: Ajustement consommation**
```
Déficit = 7 kWh
Ajustement SOC = (7 / 5) × 100 = 140%
→ Limité à 50% maximum
```

**Étape 4: SOC final**
```
SOC final = 94% + 35% + 50% = 179%
→ Limité à 100%
```

**Résultat**: `target_end_offpeak = 100%`

### Actions à 22:30 (Début HC)

**État actuel**: SOC = 45%

**Calcul timing optimal**:
```
Énergie à charger = (100% - 45%) × 5 kWh = 2.75 kWh
Temps nécessaire = 2.75 kWh / 3.84 kW = 0.72h ≈ 43 minutes
Heure démarrage = 06:30 - 00:43 - 00:30 (marge) = 05:17
```

**Décision**: Attendre jusqu'à 05:17 pour démarrer la charge (mode optimized)

### Notification à 05:17

```
⚡ Batterie - Charge Optimisée

🔋 Charge intelligente démarrée

- SOC actuel: 45%
- Cible dynamique: 100%
- Production prévue demain: 8 kWh
- 📊 Consommation prédite demain: 15 kWh
- 📊 Déficit prédit: 7 kWh (ajustement: +50%)
- 🌅 Gap avant lever soleil: 1.8h (ajustement: +35%)
- Temps de charge estimé: 0.7h
- Fin des heures creuses: 06:30
- Stratégie: Timing optimisé

Le système a calculé le moment optimal pour démarrer la charge.
```

## 🎯 Avantages de Cette Architecture

### ✅ Performance
- **Requêtes SQL optimisées**: Indexées sur `created_ts` et `metadata_id`
- **Calculs légers**: Templates simples, exécutés uniquement sur changement
- **Pas de polling**: Triggers événementiels uniquement

### ✅ Fiabilité
- **Valeurs par défaut**: Si pas d'historique, utilise valeurs sécurisées
- **Limitations**: SOC limité à 100%, ajustements plafonnés
- **Fallback**: Si sensor SQL échoue, système fonctionne en mode dégradé

### ✅ Évolutivité
- **Modulaire**: Chaque sensor indépendant
- **Extensible**: Facile d'ajouter nouveaux critères (température, etc.)
- **Configurable**: Tous les seuils ajustables par l'utilisateur

### ✅ Transparence
- **Debug détaillé**: Toutes les étapes de calcul visibles
- **Traçabilité**: Historique des décisions dans les notifications
- **Testable**: Chaque variable template testable indépendamment

## 🔬 Tests et Validation

### Test 1: Vérifier Sensor SQL
```yaml
# Outils développement > Modèles
{{ states('sensor.consommation_predite_demain') }}
# Doit retourner: un nombre (ex: 15.0) pas "unknown"
```

### Test 2: Vérifier Calcul Déficit
```yaml
{% set consumption = states('sensor.consommation_predite_demain') | float(0) %}
{% set production = states('sensor.solcast_pv_forecast_forecast_tomorrow') | float(0) %}
{{ [consumption - production, 0] | max }}
# Doit retourner: le déficit prévu (ex: 7.0)
```

### Test 3: Vérifier SOC Cible
```yaml
# Outils développement > États > Rechercher "automation"
# Cliquer sur votre automation du blueprint
# Onglet "Traces" → Voir dernière exécution
# Variables → target_end_offpeak
# Doit montrer: le SOC calculé (ex: 100)
```

## 🚀 Améliorations Futures Possibles

### Court terme (faisable en YAML)
- ☐ Ajout critère température extérieure
- ☐ Distinction jours ouvrés / week-end
- ☐ Facteur saisonnier plus fin (par mois)

### Moyen terme (nécessite AppDaemon/Python)
- ☐ Machine Learning (scikit-learn) pour prédictions
- ☐ Détection automatique de patterns
- ☐ Clustering des jours similaires
- ☐ Prédiction multi-jours (J+2, J+3)

### Long terme (architecture avancée)
- ☐ API externe pour prédictions météo détaillées
- ☐ Intégration prix marché spot électricité
- ☐ Optimisation multi-objectifs (coût + autonomie + durée vie)
- ☐ Dashboard prédictif avec graphiques

---

**Architecture v1.0** | Dernière mise à jour: 2025-10-25
