"""report_node.py — report() Unit Action helper.

Ch03에서는 순수 함수형 helper만 구현합니다.
ROS2 노드는 report_callback을 통해 /system2/report에 연결합니다.
"""


def exec_report(status: str, report_callback=None) -> bool:
    """report Unit Action 실행.

    Args:
        status: 보고 내용.
        report_callback: 보고 발행 콜백.

    Returns:
        True (항상 성공).
    """
    cb = report_callback or (lambda msg: print(f"[report] {msg}"))
    cb(status)
    return True
