# 카드 재발급 함수입니다. 신청, 조회, 배송지 수정, 신청 취소.

from datetime import datetime

import data_store
from functions.card import CARD_STATUS
from functions.common import next_id

# 신청 상태 : 접수 → 제작중 → 배송중. 취소하면 취소됨. 실제 제작·배송 진행은 만들지 않습니다. (기획서 5.4)
REISSUE_STATUS = {"received": "접수", "making": "제작중", "shipping": "배송중", "cancelled": "취소됨"}


def get_addresses(owner_id):
    return [a for a in data_store.load()["addresses"] if a["owner_id"] == owner_id]


def find_addresses(owner_id, name):
    # 배송지를 이름(집 / 회사)이나 주소 글자로 찾습니다. "집으로" 처럼 붙은 말이 있어도 찾게 이름이 들어 있는지 봅니다.
    name = (name or "").strip()
    if not name:
        return []
    return [a for a in get_addresses(owner_id) if a["label"] in name or name in a["address"]]


def get_applications(owner_id):
    # 재발급 신청 목록. 최근순입니다.
    apps = [a for a in data_store.load()["reissue_applications"] if a["owner_id"] == owner_id]
    return sorted(apps, key=lambda a: a["created_at"], reverse=True)


def check_reissue(owner_id, card):
    # 재발급을 신청할 수 있는지 봅니다. 안 되면 사유를, 되면 None 을 돌려줍니다.
    if card["status"] != "lost":
        return "분실 정지된 카드만 재발급을 신청할 수 있습니다. 먼저 분실 신고를 해 주세요. (%s : %s)" % (
            card["name"], CARD_STATUS[card["status"]])
    # 취소되지 않은 신청이 있으면 새로 만들지 않고 그 신청을 안내합니다.
    for app in get_applications(owner_id):
        if app["card_id"] == card["card_id"] and app["status"] != "cancelled":
            return "이미 재발급 신청이 있습니다. (%s  %s  [%s])" % (
                app["application_id"], card["name"], REISSUE_STATUS[app["status"]])
    return None


def find_open_application(owner_id, card_id):
    # 이 카드의 취소되지 않은 신청을 돌려줍니다. 카드마다 하나만 있을 수 있으므로(check_reissue) 하나이거나 None 입니다.
    return next((a for a in get_applications(owner_id)
                 if a["card_id"] == card_id and a["status"] != "cancelled"), None)


def check_application(app, action, address_id=None):
    # 신청을 수정·취소할 수 있는지 봅니다. 접수 상태일 때만 됩니다. (기획서 5.4 표)
    # 할 수 없으면 사유를, 할 수 있으면 None 을 돌려줍니다.
    if app["status"] != "received":
        return "%s 상태라 %s할 수 없습니다. 접수 상태일 때만 됩니다. (%s)" % (
            REISSUE_STATUS[app["status"]], "배송지를 수정" if action == "배송지 수정" else "취소", app["application_id"])
    if action == "배송지 수정" and app["address_id"] == address_id:
        return "지금 배송지와 같습니다. (%s)" % app["application_id"]
    return None


def change_application(data, app_id, action, address_id=None):
    # data 안에서 신청의 배송지를 바꾸거나 취소합니다. 취소도 지우지 않고 상태만 바꿉니다. 파일에 저장하지는 않습니다.
    app = next(a for a in data["reissue_applications"] if a["application_id"] == app_id)
    if action == "배송지 수정":
        app["address_id"] = address_id
    else:
        app["status"] = "cancelled"


def add_reissue(data, owner_id, card_id, address_id):
    # data 에 재발급 신청을 한 줄 덧붙입니다. 파일에 저장하지는 않습니다.
    # 기존 카드의 분실 정지는 그대로 둡니다. (기획서 5.4)
    app_id = next_id(data["reissue_applications"], "application_id", "app")
    data["reissue_applications"].append({
        "application_id": app_id,
        "owner_id": owner_id,
        "card_id": card_id,
        "address_id": address_id,
        "status": "received",
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    })
    return app_id
