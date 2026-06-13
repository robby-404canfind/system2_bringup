"""report_node.py — report(status) Unit Action helper.

Ch03에서 가져온 순수 함수형 helper입니다.
Ch05에서는 ActionDispatcher가 report_callback으로 /system2/report 연결을 담당합니다.
"""


def exec_report(status: str, report_callback=None) -> bool:
    """report Unit Action 실행.

    Args:
        status: 보고 내용.
        report_callback: 보고 publish 콜백.

    Returns:
        True (항상 성공).
    """
    cb = report_callback or (lambda msg: print(f"[report] {msg}"))
    cb(status)
    return True
