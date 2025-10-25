#!/usr/bin/env python3
"""Test script to check Envoy /info endpoint response."""
import asyncio
import aiohttp
import json

async def test_envoy_info():
    """Test /info endpoint on local Envoy."""
    host = input("Enter Envoy hostname or IP (default: envoy.local): ").strip() or "envoy.local"
    url = f"https://{host}/info"

    print(f"\n🔍 Testing {url}")
    print("-" * 60)

    async with aiohttp.ClientSession() as session:
        try:
            # Try without SSL verification (Envoy uses self-signed cert)
            async with session.get(url, ssl=False, timeout=aiohttp.ClientTimeout(total=10)) as response:
                print(f"✅ Status: {response.status}")
                print(f"✅ Content-Type: {response.headers.get('Content-Type')}")

                # Try to get text first
                text = await response.text()
                print(f"\n📄 Raw Response (first 500 chars):")
                print(text[:500])

                # Try to parse as JSON
                try:
                    data = json.loads(text)
                    print(f"\n✅ Valid JSON!")
                    print(f"\n📊 JSON Structure:")
                    print(json.dumps(data, indent=2))

                    # Try to find serial
                    print(f"\n🔑 Looking for serial number...")
                    possible_serials = []

                    def find_serial(obj, path=""):
                        if isinstance(obj, dict):
                            for key, value in obj.items():
                                new_path = f"{path}.{key}" if path else key
                                if any(s in key.lower() for s in ["serial", "sn", "serialnumber"]):
                                    possible_serials.append((new_path, value))
                                find_serial(value, new_path)
                        elif isinstance(obj, list):
                            for i, item in enumerate(obj):
                                find_serial(item, f"{path}[{i}]")

                    find_serial(data)

                    if possible_serials:
                        print("✅ Found possible serial number locations:")
                        for path, value in possible_serials:
                            print(f"   {path} = {value}")
                    else:
                        print("❌ No serial number found in JSON")
                        print(f"   Available keys: {list(data.keys())}")

                except json.JSONDecodeError:
                    print(f"\n⚠️  Not valid JSON, might be XML or text")
                    # Try to extract serial from XML
                    import re
                    serial_match = re.search(r'<sn>(\w+)</sn>', text)
                    if serial_match:
                        print(f"✅ Found serial in XML: {serial_match.group(1)}")
                    else:
                        print("❌ Could not find serial in XML")

        except aiohttp.ClientError as err:
            print(f"❌ Connection error: {err}")
        except Exception as err:
            print(f"❌ Unexpected error: {err}")

if __name__ == "__main__":
    print("=" * 60)
    print(" Enphase Envoy /info Endpoint Tester")
    print("=" * 60)
    asyncio.run(test_envoy_info())
