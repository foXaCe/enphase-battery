# 🔧 Dépannage Mode Local

## ❌ Erreur: "Could not retrieve Envoy serial number"

### Diagnostic

Cette erreur indique que l'endpoint `/info` ne retourne pas le numéro de série dans le format attendu.

### Étape 1 : Tester l'endpoint `/info`

```bash
cd /mnt/Media/Codage/GitHub/enphase-battery
python3 test_envoy_info.py
```

Le script va vous demander l'adresse de l'Envoy et afficher la structure complète de la réponse.

**Exemples de sortie attendue :**

✅ **Cas 1 : JSON valide**
```json
{
  "device": {
    "sn": "123456789012",
    "pn": "800-00654-r03",
    "software": "D7.3.466"
  }
}
```

✅ **Cas 2 : Format direct**
```json
{
  "serial_num": "123456789012",
  "part_num": "800-00654-r03",
  "software": "D7.3.466"
}
```

❌ **Cas 3 : XML (ancien firmware)**
```xml
<envoy_info>
  <sn>123456789012</sn>
  <pn>800-00654-r03</pn>
</envoy_info>
```

### Étape 2 : Vérifier votre firmware

```bash
# Depuis votre navigateur ou curl
curl -k https://envoy.local/info | jq .
```

**Firmware < 7.0** :
- ✅ Authentification `installer` + mot de passe serial
- ✅ Devrait fonctionner avec le code actuel

**Firmware >= 7.0 (D7.x.x)** :
- ❌ **Problème connu** : Nécessite un token cloud
- ⚠️ L'authentification locale simple ne fonctionne plus

## 🔐 Firmware 7.x : Solution de contournement

Si vous avez **firmware D7.x.x ou supérieur**, l'authentification locale directe ne fonctionne plus.

### Option 1 : Utiliser le mode Cloud (Recommandé)

Au lieu de "Local", choisissez **"Cloud"** lors de la configuration :

1. Supprimer l'intégration actuelle
2. Ajouter "Enphase Battery IQ 5P"
3. Choisir **"Cloud"** (pas Local)
4. Entrer vos identifiants Enlighten

✅ Fonctionne avec tous les firmwares
⚠️ Polling 60s au lieu de 10s

### Option 2 : Downgrade firmware (Non recommandé)

Enphase ne permet généralement pas de revenir à une version antérieure.

### Option 3 : Attendre le correctif

Le mode local pour firmware 7.x nécessite :
1. Obtenir un token depuis Enphase cloud
2. Utiliser ce token pour l'authentification locale
3. Renouveler le token périodiquement

**Status :** 🚧 En développement

## 📊 Vérifier le firmware de l'Envoy

### Via navigateur
```
https://envoy.local/info
```

Cherchez le champ `software` ou `fw_version`

### Via Home Assistant

Si l'addon officiel Enphase Envoy est installé :
1. Paramètres → Intégrations → Enphase Envoy
2. Cliquer sur l'appareil
3. Voir "Firmware"

## 🔍 Logs de débogage

Pour voir ce que retourne réellement `/info` :

1. Activer les logs debug dans `configuration.yaml` :
```yaml
logger:
  default: info
  logs:
    custom_components.enphase_battery: debug
```

2. Redémarrer Home Assistant

3. Essayer de configurer le mode local

4. Consulter les logs :
```bash
tail -f /config/home-assistant.log | grep enphase_battery
```

Cherchez les lignes :
```
DEBUG Envoy /info response: {...}
ERROR Cannot find serial in /info response. Keys found: [...]
```

## 🎯 Solutions selon votre cas

| Firmware | Solution | Délai |
|----------|----------|-------|
| **< D7.0** | ✅ Mode local fonctionne | Immédiat |
| **>= D7.0** | ⚠️ Utiliser mode Cloud | Immédiat |
| **>= D7.0 + mode local** | 🚧 Patch à venir | À déterminer |

## 📧 Signaler un problème

Si le test script montre que `/info` retourne bien un serial mais l'intégration échoue quand même :

1. Copier la sortie complète de `test_envoy_info.py`
2. Copier les logs Home Assistant (avec debug activé)
3. Ouvrir une issue sur GitHub avec :
   - Modèle Envoy (ex: Envoy-S)
   - Version firmware (ex: D7.3.466)
   - Sortie du script de test
   - Logs HA

## 🔗 Ressources

- [Documentation Enphase Local API](https://enphase.com/download/iq-gateway-local-apis-or-ui-access-using-token)
- [Issue GitHub firmware 7.x](https://github.com/home-assistant/core/issues/79382)
- [Addon officiel HA Enphase](https://www.home-assistant.io/integrations/enphase_envoy/)

---

**💡 Recommandation actuelle** : Si vous avez firmware 7.x, utilisez le **mode Cloud** en attendant le support complet du mode local avec tokens.
