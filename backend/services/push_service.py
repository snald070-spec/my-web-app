import os
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_KEYS_FILE = Path(__file__).parent.parent / "vapid_keys.json"


def _load_vapid_keys() -> tuple[str, str]:
    priv = os.environ.get("VAPID_PRIVATE_KEY", "").strip()
    pub = os.environ.get("VAPID_PUBLIC_KEY", "").strip()
    if priv and pub:
        return priv, pub
    if _KEYS_FILE.exists():
        try:
            data = json.loads(_KEYS_FILE.read_text())
            return data.get("private_key", ""), data.get("public_key", "")
        except Exception:
            pass
    return "", ""


def ensure_vapid_keys() -> tuple[str, str]:
    priv, pub = _load_vapid_keys()
    if priv and pub:
        return priv, pub

    logger.info("VAPID 키가 없습니다. 새로 생성합니다...")
    try:
        from py_vapid import Vapid
        from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
        import base64

        vapid = Vapid()
        vapid.generate_keys()

        # Private key: raw 32-byte scalar as base64url (py_vapid Vapid.from_string 호환)
        private_value = vapid.private_key.private_numbers().private_value
        private_b64 = base64.urlsafe_b64encode(
            private_value.to_bytes(32, "big")
        ).rstrip(b"=").decode()

        # Public key: uncompressed point (65 bytes) as base64url (브라우저 applicationServerKey)
        pub_bytes = vapid.public_key.public_bytes(
            encoding=Encoding.X962,
            format=PublicFormat.UncompressedPoint,
        )
        public_b64 = base64.urlsafe_b64encode(pub_bytes).rstrip(b"=").decode()

        _KEYS_FILE.write_text(json.dumps({
            "private_key": private_b64,
            "public_key": public_b64,
        }, indent=2))
        logger.info("✅ VAPID 키 생성 완료. %s 에 저장됨", _KEYS_FILE)
        return private_b64, public_b64
    except Exception as e:
        logger.error("VAPID 키 생성 실패: %s", e)
        return "", ""


def get_vapid_public_key() -> str:
    _, pub = _load_vapid_keys()
    return pub


def send_push_to_subscription(sub, title: str, body: str, url: str = "/") -> bool:
    private_key, _ = _load_vapid_keys()
    if not private_key:
        logger.warning("VAPID 키 없음 — push 발송 건너뜀")
        return False

    contact = os.environ.get("VAPID_CONTACT_EMAIL", "admin@example.com")
    try:
        from pywebpush import webpush, WebPushException
        subscription_info = {
            "endpoint": sub.endpoint,
            "keys": {"p256dh": sub.p256dh, "auth": sub.auth},
        }
        payload = json.dumps({"title": title, "body": body, "url": url})
        webpush(
            subscription_info=subscription_info,
            data=payload,
            vapid_private_key=private_key,
            vapid_claims={"sub": f"mailto:{contact}"},
        )
        return True
    except Exception as e:
        logger.warning("Push 발송 실패 endpoint=%.50s : %s", sub.endpoint, e)
        return False


def send_push_to_all(
    db,
    title: str,
    body: str,
    url: str = "/",
    exclude_emp_id: str | None = None,
    target_roles: list[str] | None = None,
    target_emp_ids: list[str] | None = None,
) -> dict:
    import models

    q = db.query(models.PushSubscription)
    if exclude_emp_id:
        q = q.filter(models.PushSubscription.emp_id != exclude_emp_id)
    if target_emp_ids:
        q = q.filter(models.PushSubscription.emp_id.in_(target_emp_ids))
    elif target_roles is not None:
        master_emp_ids = [
            u.emp_id for u in
            db.query(models.User).filter(models.User.role.in_(target_roles)).all()
        ]
        if not master_emp_ids:
            return {"sent": 0, "failed": 0}
        q = q.filter(models.PushSubscription.emp_id.in_(master_emp_ids))
    subs = q.all()

    sent = 0
    stale_ids = []
    for sub in subs:
        if send_push_to_subscription(sub, title, body, url):
            sent += 1
        else:
            stale_ids.append(sub.id)

    if stale_ids:
        db.query(models.PushSubscription).filter(
            models.PushSubscription.id.in_(stale_ids)
        ).delete(synchronize_session=False)
        db.commit()

    return {"sent": sent, "failed": len(stale_ids)}
