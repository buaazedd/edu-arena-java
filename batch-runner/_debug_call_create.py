from pathlib import Path

import requests

from java_client import service_login


def main():
    base = "http://127.0.0.1:5001"
    secret = "dev-secret-change-me"

    token = service_login(base, secret)
    # 先验证：纯文本(>=10字)能否创建对战（避开图片/标题编码等问题）
    body2 = {
        "essay_title": "debug-title",
        "essay_content": "1234567890",
        "grade_level": "高中",
    }
    r2 = requests.post(
        f"{base}/api/battle/create",
        headers={"Authorization": f"Bearer {token}"},
        json=body2,
        timeout=60,
    )
    print("status2", r2.status_code)
    print(r2.text[:500])


if __name__ == "__main__":
    main()

