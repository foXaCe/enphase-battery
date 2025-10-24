#!/usr/bin/env python3
"""
Script mitmdump pour capturer le trafic de l'app Enphase Energy Enlighten
Usage: mitmproxy -s enphase_mitm_capture.py
"""
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional
from mitmproxy import http
from mitmproxy import ctx

# Configuration
OUTPUT_DIR = Path("./captured_data")
OUTPUT_DIR.mkdir(exist_ok=True)

# Domaines Enphase à capturer
ENPHASE_DOMAINS = [
    "enlighten.enphaseenergy.com",
    "api.enphaseenergy.com",
    "entrez.enphaseenergy.com",
    "envoy.local",
]

class EnphaseCapture:
    """Capture et log toutes les requêtes/réponses Enphase"""

    def __init__(self):
        self.request_count = 0
        self.session_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_file = OUTPUT_DIR / f"enphase_capture_{self.session_timestamp}.log"
        self.json_file = OUTPUT_DIR / f"enphase_data_{self.session_timestamp}.json"
        self.captured_data = []

        # Configuration du logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(self.log_file),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
        self.logger.info(f"🚀 Session de capture démarrée: {self.session_timestamp}")
        self.logger.info(f"📁 Logs: {self.log_file}")
        self.logger.info(f"📊 JSON: {self.json_file}")

    def request(self, flow: http.HTTPFlow) -> None:
        """Intercepte toutes les requêtes HTTP"""
        request = flow.request

        # Vérifie si c'est une requête Enphase
        if not any(domain in request.pretty_host for domain in ENPHASE_DOMAINS):
            return

        self.request_count += 1
        self.logger.info(f"\n{'='*80}")
        self.logger.info(f"📤 REQUÊTE #{self.request_count}")
        self.logger.info(f"URL: {request.method} {request.pretty_url}")
        self.logger.info(f"Host: {request.pretty_host}")

        # Headers
        self.logger.info(f"\n🔑 HEADERS:")
        for name, value in request.headers.items():
            # Masquer les tokens sensibles
            if any(s in name.lower() for s in ['auth', 'token', 'key', 'secret']):
                value = f"{value[:10]}...{value[-10:]}" if len(value) > 20 else "***"
            self.logger.info(f"  {name}: {value}")

        # Query parameters
        if request.query:
            self.logger.info(f"\n🔍 QUERY PARAMS:")
            for name, value in request.query.items():
                self.logger.info(f"  {name}: {value}")

        # Body (si présent)
        if request.content:
            self.logger.info(f"\n📝 BODY ({len(request.content)} bytes):")
            try:
                body = request.content.decode('utf-8')
                if request.headers.get("content-type", "").startswith("application/json"):
                    body_json = json.loads(body)
                    self.logger.info(json.dumps(body_json, indent=2, ensure_ascii=False))
                else:
                    self.logger.info(body[:1000])  # Premier 1000 chars
            except Exception as e:
                self.logger.warning(f"  Impossible de décoder le body: {e}")

    def response(self, flow: http.HTTPFlow) -> None:
        """Intercepte toutes les réponses HTTP"""
        request = flow.request
        response = flow.response

        # Vérifie si c'est une réponse Enphase
        if not any(domain in request.pretty_host for domain in ENPHASE_DOMAINS):
            return

        self.logger.info(f"\n📥 RÉPONSE")
        self.logger.info(f"Status: {response.status_code} {response.reason}")

        # Headers de réponse
        self.logger.info(f"\n🔑 RESPONSE HEADERS:")
        for name, value in response.headers.items():
            self.logger.info(f"  {name}: {value}")

        # Body de la réponse
        if response.content:
            self.logger.info(f"\n📊 RESPONSE BODY ({len(response.content)} bytes):")
            try:
                body = response.content.decode('utf-8')
                content_type = response.headers.get("content-type", "")

                if "application/json" in content_type:
                    body_json = json.loads(body)
                    self.logger.info(json.dumps(body_json, indent=2, ensure_ascii=False))

                    # Sauvegarde les données JSON structurées
                    self._save_json_data(request, response, body_json)
                else:
                    self.logger.info(body[:2000])  # Premier 2000 chars
            except Exception as e:
                self.logger.warning(f"  Impossible de décoder la réponse: {e}")

        self.logger.info(f"{'='*80}\n")

    def _save_json_data(self, request: http.Request, response: http.Response, data: dict) -> None:
        """Sauvegarde les données JSON structurées"""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "request": {
                "method": request.method,
                "url": request.pretty_url,
                "host": request.pretty_host,
                "path": request.path,
                "query": dict(request.query),
            },
            "response": {
                "status": response.status_code,
                "data": data
            }
        }

        self.captured_data.append(entry)

        # Écriture périodique (tous les 5 appels)
        if len(self.captured_data) % 5 == 0:
            self._write_json_file()

    def _write_json_file(self) -> None:
        """Écrit toutes les données capturées dans le fichier JSON"""
        try:
            with open(self.json_file, 'w', encoding='utf-8') as f:
                json.dump(self.captured_data, f, indent=2, ensure_ascii=False)
            self.logger.info(f"💾 Données sauvegardées: {len(self.captured_data)} entrées")
        except Exception as e:
            self.logger.error(f"Erreur lors de la sauvegarde JSON: {e}")

    def done(self) -> None:
        """Appelé à la fin de la session"""
        self._write_json_file()
        self.logger.info(f"\n🏁 Session terminée")
        self.logger.info(f"📊 Total de requêtes capturées: {self.request_count}")
        self.logger.info(f"📁 Fichiers générés:")
        self.logger.info(f"  - {self.log_file}")
        self.logger.info(f"  - {self.json_file}")


# Instance de l'addon mitmproxy
addons = [EnphaseCapture()]
