"""Grant redistribution for one rights-cleared Telegram channel, without downloading files."""
import argparse
import json
from authorized_delivery import CHANNEL_GRANTS


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--channel", type=int, required=True)
    parser.add_argument("--confirm-rights", action="store_true")
    args = parser.parse_args()
    if not args.confirm_rights:
        parser.error("Confirma que el permiso cubre todos los documentos del canal con --confirm-rights")
    try:
        data = json.loads(CHANNEL_GRANTS.read_text(encoding="utf-8")) if CHANNEL_GRANTS.exists() else {"channels": {}}
    except (ValueError, OSError) as exc:
        parser.error(f"Configuración inválida: {exc}")
    if not isinstance(data, dict) or not isinstance(data.get("channels"), dict):
        parser.error("Configuración de canales inválida")
    data["channels"][str(args.channel)] = {"redistribution_authorized": True}
    temp = CHANNEL_GRANTS.with_suffix(".json.tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(CHANNEL_GRANTS)
    print(f"Canal {args.channel} habilitado. No se descargaron PDF.")


if __name__ == "__main__":
    main()
