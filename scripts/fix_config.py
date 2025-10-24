#!/usr/bin/env python3
"""
Script pour ajouter site_id et user_id à la configuration Enphase Battery
"""
import json
import sys
from pathlib import Path

# Paramètres à configurer
SITE_ID = "2168380"
USER_ID = "2241267"

# Chemin vers la configuration Home Assistant
# Adapter selon votre installation
CONFIG_PATHS = [
    Path("/config/.storage/core.config_entries"),
    Path("/home/homeassistant/.homeassistant/.storage/core.config_entries"),
    Path.home() / ".homeassistant" / ".storage" / "core.config_entries",
]

def find_config_file():
    """Trouver le fichier de configuration."""
    for path in CONFIG_PATHS:
        if path.exists():
            return path
    return None

def main():
    """Point d'entrée principal."""
    # Trouver le fichier de config
    config_path = find_config_file()

    if not config_path:
        print("❌ Impossible de trouver le fichier de configuration Home Assistant")
        print("\nChemins testés :")
        for path in CONFIG_PATHS:
            print(f"  - {path}")
        print("\nVeuillez spécifier le chemin manuellement :")
        print(f"  python {sys.argv[0]} /path/to/config/.storage/core.config_entries")
        return 1

    if len(sys.argv) > 1:
        config_path = Path(sys.argv[1])

    print(f"📁 Fichier de configuration trouvé : {config_path}")

    # Backup
    backup_path = config_path.with_suffix(".backup")
    print(f"💾 Création d'une sauvegarde : {backup_path}")

    with open(config_path, "r") as f:
        content = f.read()

    with open(backup_path, "w") as f:
        f.write(content)

    # Charger la config
    config = json.loads(content)

    # Trouver l'entrée enphase_battery
    found = False
    for entry in config["data"]["entries"]:
        if entry["domain"] == "enphase_battery":
            print(f"\n✅ Entrée Enphase Battery trouvée (ID: {entry['entry_id']})")

            # Ajouter/mettre à jour les IDs
            entry["data"]["site_id"] = SITE_ID
            entry["data"]["user_id"] = USER_ID

            print(f"✅ site_id défini : {SITE_ID}")
            print(f"✅ user_id défini : {USER_ID}")

            found = True

    if not found:
        print("\n❌ Aucune entrée 'enphase_battery' trouvée dans la configuration")
        print("   Ajoutez d'abord l'intégration via l'interface Home Assistant")
        return 1

    # Sauvegarder
    with open(config_path, "w") as f:
        json.dump(config, f, indent=2)

    print(f"\n✅ Configuration mise à jour avec succès !")
    print(f"\n🔄 Redémarrez Home Assistant pour appliquer les changements")
    print(f"\nEn cas de problème, restaurez la sauvegarde :")
    print(f"  cp {backup_path} {config_path}")

    return 0

if __name__ == "__main__":
    sys.exit(main())
